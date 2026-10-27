#!/usr/bin/env bash
# Runs real lightweight spoke clusters for the crc ACM hub: k3s via k3d, in
# Colima's Docker, imported into ACM so the observability addon pushes their
# metrics to the hub's Thanos.
# Usage: ./spokes.sh [count]     (default 2; 0 removes them all)
#   Behind Cloudflare WARP: CA=~/.config/cloudflare/Cloudflare_CA.pem ./spokes.sh
#
# Each spoke-N is 1 server + 1 agent node, with traefik/servicelb/metrics-server
# off, plus the sample apps in apps/spoke-N.yaml if that file exists.
set -euo pipefail
cd "$(dirname "$0")"

# OpenShift Local ships oc but doesn't put it on PATH
command -v oc >/dev/null || eval "$(crc oc-env)"

COUNT=${1:-2}

# Remove spokes above COUNT (all of them for 0). Hub first, so ACM can clean up
# the klusterlet while the cluster still exists.
for name in $( { oc get managedcluster -l spoke-cluster=true -o name | sed 's|.*/||'
                 k3d cluster list --no-headers | awk '/^spoke-/{print $1}'; } | sort -u); do
  if [ "${name#spoke-}" -gt "$COUNT" ]; then
    oc delete managedcluster "$name" --ignore-not-found --timeout=5m
    k3d cluster delete "$name"
  fi
done
[ "$COUNT" -gt 0 ] || exit 0

# crc's api.crc.testing / *.apps-crc.testing resolve to the Mac's 127.0.0.1.
# From inside Colima that's the docker host-gateway, so point the hub names there.
HOST_IP=$(docker run --rm --add-host h:host-gateway busybox grep -w h /etc/hosts | awk '{print $1}')
HUB_HOSTS=api.crc.testing
HUB_HOSTS+=,observatorium-api-open-cluster-management-observability.apps-crc.testing
HUB_HOSTS+=,alertmanager-open-cluster-management-observability.apps-crc.testing

# ACM's agent images come from registry.redhat.io, which needs auth. Give the
# k3s nodes the same pull secret crc uses (and the Cloudflare CA, if set).
regcfg=$(mktemp)
trap 'rm -f "$regcfg"' EXIT
oc get secret pull-secret -n openshift-config -o jsonpath='{.data.\.dockerconfigjson}' | base64 -d |
  python3 -c 'import sys, json, os
auths = json.load(sys.stdin)["auths"]
cfg = {}
for r, a in auths.items():
    cfg[r] = {"auth": {"auth": a["auth"]}}
    if os.environ.get("CA"):
        cfg[r]["tls"] = {"ca_file": "/etc/ssl/certs/cloudflare.pem"}
json.dump({"configs": cfg}, sys.stdout)' > "$regcfg"  # JSON is valid registries.yaml

extra=()
[ -n "${CA:-}" ] && extra+=(--volume "$CA:/etc/ssl/certs/cloudflare.pem@all")

for n in $(seq 1 "$COUNT"); do
  name=spoke-$n
  ctx=k3d-$name

  if ! k3d cluster get "$name" >/dev/null 2>&1; then
    # don't switch context: oc shares ~/.kube/config and must keep pointing at the hub
    k3d cluster create "$name" --agents 1 --no-lb --wait \
      --kubeconfig-switch-context=false \
      --k3s-arg '--disable=traefik,servicelb,metrics-server@server:0' \
      --host-alias "$HOST_IP:$HUB_HOSTS" \
      --registry-config "$regcfg" ${extra[@]+"${extra[@]}"}
  fi

  cat <<EOF | oc apply -f -
apiVersion: cluster.open-cluster-management.io/v1
kind: ManagedCluster
metadata:
  name: $name
  labels:
    spoke-cluster: "true"
    name: $name
    cloud: auto-detect
    vendor: auto-detect
    cluster.open-cluster-management.io/clusterset: default
spec:
  hubAcceptsClient: true
EOF

  echo "Waiting for ACM to generate $name's import manifests..."
  for i in $(seq 60); do  # 60 x 5s = 5 min
    oc get secret "$name-import" -n "$name" >/dev/null 2>&1 && break
    sleep 5
  done
  oc get secret "$name-import" -n "$name" -o jsonpath='{.data.crds\.yaml}' | base64 -d | oc --context "$ctx" apply -f -
  oc --context "$ctx" wait crd --all --for=condition=Established --timeout=2m
  oc get secret "$name-import" -n "$name" -o jsonpath='{.data.import\.yaml}' | base64 -d | oc --context "$ctx" apply -f -

  if [ -f "apps/$name.yaml" ]; then oc --context "$ctx" apply -f "apps/$name.yaml"; fi
done

for n in $(seq 1 "$COUNT"); do
  oc wait "managedcluster/spoke-$n" --for=condition=ManagedClusterConditionAvailable --timeout=10m
done
oc get managedcluster
echo "Spokes send metrics every 5 min; give the dashboards ~5-10 min to show them."
