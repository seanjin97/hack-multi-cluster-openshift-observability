#!/usr/bin/env bash
# Runs real lightweight spoke clusters for the crc ACM hub: k3s via k3d, in
# Docker, imported into ACM so the observability addon pushes their metrics to
# the hub's Thanos. One spoke per spoke-*/ directory.
# Usage: ./spokes.sh          create/update every spoke (safe to re-run)
#        ./spokes.sh down     remove every spoke, from ACM and k3d
#   Behind Cloudflare WARP: CA=~/.config/cloudflare/Cloudflare_CA.pem ./spokes.sh
#
# Files:
#   k3d-cluster.yaml               the k3s cluster (2 nodes), shared by every spoke
#   spoke-N/managed-cluster.yaml   registers spoke-N with ACM (applied to the hub)
#   spoke-N/kustomization.yaml     spoke-N's sample apps (applied to the spoke)
set -euo pipefail
cd "$(dirname "$0")"

# OpenShift Local ships oc but doesn't put it on PATH
command -v oc >/dev/null || eval "$(crc oc-env)"

if [ "${1:-}" = down ]; then
  for dir in spoke-*/; do
    spoke=${dir%/}
    # hub first, so ACM can clean up the klusterlet while the cluster still exists
    oc delete -f "$spoke/managed-cluster.yaml" --ignore-not-found --timeout=5m
    k3d cluster delete "$spoke"
  done
  exit 0
fi

# Values k3d fills into k3d-cluster.yaml
export HUB_IP=$(docker run --rm --add-host h:host-gateway busybox grep -w h /etc/hosts | awk '{print $1}')
export CA=${CA:-/dev/null}
# crc's pull secret, as a k3s registries.yaml (JSON is valid YAML). Generated
# rather than stored: it holds your Red Hat registry credentials.
export REGISTRIES=$(oc get secret pull-secret -n openshift-config -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d |
  python3 -c 'import sys, json
auths = json.load(sys.stdin)["auths"]
print(json.dumps({"configs": {r: {"auth": {"auth": a["auth"]}} for r, a in auths.items()}}))')

for dir in spoke-*/; do
  export SPOKE=${dir%/}
  ctx=k3d-$SPOKE

  k3d cluster get "$SPOKE" >/dev/null 2>&1 || k3d cluster create --config k3d-cluster.yaml

  # Import into ACM: register on the hub, then apply the manifests ACM generates
  oc apply -f "$SPOKE/managed-cluster.yaml"
  echo "Waiting for ACM to generate $SPOKE's import manifests..."
  for i in $(seq 60); do  # 60 x 5s = 5 min
    oc get secret "$SPOKE-import" -n "$SPOKE" >/dev/null 2>&1 && break
    sleep 5
  done
  oc get secret "$SPOKE-import" -n "$SPOKE" -o jsonpath='{.data.crds\.yaml}' | base64 -d | oc --context "$ctx" apply -f -
  oc --context "$ctx" wait crd/klusterlets.operator.open-cluster-management.io --for=condition=Established --timeout=2m
  oc get secret "$SPOKE-import" -n "$SPOKE" -o jsonpath='{.data.import\.yaml}' | base64 -d | oc --context "$ctx" apply -f -

  oc --context "$ctx" apply -k "$SPOKE"
done

for dir in spoke-*/; do
  oc wait "managedcluster/${dir%/}" --for=condition=ManagedClusterConditionAvailable --timeout=10m
done
oc get managedcluster
echo "Spokes send metrics every 30s (interval in 04-observability.yaml); give the dashboards a few min to show them."
