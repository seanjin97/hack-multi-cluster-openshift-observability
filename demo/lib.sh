# Shared by demo/step*.sh: paths, the L0/L1 manifests, and cluster helpers. Not run directly.
set -euo pipefail
ROOT=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
DEPLOY=$ROOT/sensor-team-2-monorepo/deploy
DASH=$ROOT/platform-tools/grafana/dashboards
NS=sensor-team-2
command -v oc >/dev/null || eval "$(crc oc-env)"
s2() { oc --context k3d-spoke-2 "$@"; }
say() { printf '\n\033[1m== %s\033[0m\n' "$*"; }

# Namespace: L0 (no labels) or L1 (level + owner, so require-owner passes)
namespace() {
  if [ "$1" = L0 ]; then
    cat > "$DEPLOY/namespace.yaml" <<'YAML'
apiVersion: v1
kind: Namespace
metadata:
  name: sensor-team-2
YAML
  else
    cat > "$DEPLOY/namespace.yaml" <<'YAML'
# L1 (Operate): pods need a metrics port, probes and resources. Rules: doc/app-teams/0-levels.md
apiVersion: v1
kind: Namespace
metadata:
  name: sensor-team-2
  labels: {starlab-platform/maturity: L1, starlab-platform/team: sensor-team-2}
  annotations: {starlab-platform/contact: "#sensor-team-2-oncall"}
YAML
  fi
}

# Deployment: the port is named "http" (not scraped, fails L1) or "metrics" (scraped, passes L1).
# Probes and resources are always there, so require-metrics-port is the only L1 rule that can fail.
deployment() {
  sed "s/__PORT__/$1/g" > "$DEPLOY/deployment.yaml" <<'YAML'
# ACM's Prometheus scrapes the port named "metrics" (doc/app-teams/1-metrics.md).
apiVersion: apps/v1
kind: Deployment
metadata: {name: worker-1}
spec:
  replicas: 1
  selector: {matchLabels: {app: worker-1}}
  template:
    metadata: {labels: {app: worker-1}}
    spec:
      containers:
        - name: worker-1
          image: worker-1:dev
          imagePullPolicy: Never
          ports: [{name: __PORT__, containerPort: 8080}]   # serves /metrics
          readinessProbe: {httpGet: {path: /metrics, port: __PORT__}}
          livenessProbe: {httpGet: {path: /metrics, port: __PORT__}}
          resources: {requests: {cpu: 10m, memory: 16Mi}, limits: {memory: 64Mi}}
YAML
}

# Deploy what's in deploy/ and wait for the rollout. deploy/loadgen.yaml (mock traffic) is static: every step ships it.
apply() { s2 apply -k "$DEPLOY" && s2 -n $NS rollout status deploy/worker-1 --timeout=90s && s2 -n $NS rollout status deploy/loadgen --timeout=60s; }

# --- Declarative state: each step names where everything should be, and these get there from any state ---

# converge <L0|L1> <http|metrics>: namespace level and worker port, from whatever is on the cluster now
converge() {
  ensure_image
  namespace "$1"
  deployment "$2"
  [ "$1" = L0 ] && drop_l1
  apply
}

# Take the namespace off L1. require-owner checks an UPDATE when the old OR new namespace is L1, so drop
# maturity alone first (owner still set, passes), then the owner (no longer L1). No-op when there's no namespace.
drop_l1() {
  s2 get ns $NS >/dev/null 2>&1 || return 0
  s2 label ns $NS starlab-platform/maturity-
  s2 label ns $NS starlab-platform/team-
  s2 annotate ns $NS starlab-platform/contact-
}

# dashboard <absent|present>: the sensor-team-2 dashboard in the repo (and, when absent, on the hub).
# present = demo/fixtures/worker_1.py, what step 4 generates.
dashboard() {
  if [ "$1" = absent ]; then
    rm -rf "$DASH/sensor-team-2"
    (cd "$DASH" && uv run -q build.py)
    oc -n open-cluster-management-observability delete cm grafana-dashboard-sensor-team-2-worker-1 --ignore-not-found  # the loader drops it from Grafana
  else
    mkdir -p "$DASH/sensor-team-2"
    cp "$ROOT/demo/fixtures/worker_1.py" "$DASH/sensor-team-2/worker_1.py"
    (cd "$DASH" && uv run -q build.py)
  fi
}

# The worker-1 image must be on spoke-2 (imagePullPolicy: Never)
ensure_image() {
  docker exec k3d-spoke-2-agent-0 crictl images 2>/dev/null | grep -q 'worker-1 .*dev' && return
  say "Importing the worker-1 image into spoke-2"
  (cd "$ROOT/sensor-team-2-monorepo" && make docker) && k3d image import worker-1:dev -c spoke-2
}

# Spoke-2 Prometheus: is the team scraped right now?
scraped() {
  s2 -n open-cluster-management-addon-observability exec prometheus-k8s-0 -c prometheus -- \
    promtool query instant http://localhost:9090 "up{namespace=\"$NS\"} == 1"
}
