#!/usr/bin/env bash
# Checks every running pod on every spoke has metrics on the hub:
#   - pods in golden-path.level=L1 namespaces (not exempt): own metrics, up == 1
#   - every other pod: at least pod-level metrics (kube_pod_info)
# Exits 1 and lists the missing pods otherwise.
# Usage: ./check-metrics.sh
set -euo pipefail
cd "$(dirname "$0")"
command -v oc >/dev/null || eval "$(crc oc-env)"

# PromQL against the hub's Thanos, as "cluster namespace pod" lines
hub() {
  oc get --raw "/api/v1/namespaces/open-cluster-management-observability/services/http:observability-thanos-query:9090/proxy/api/v1/query?query=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$1")" |
    python3 -c 'import sys, json
for r in json.load(sys.stdin)["data"]["result"]:
    m = r["metric"]; print(m["cluster"], m["namespace"], m["pod"])'
}
scraped=$(hub 'count by (cluster, namespace, pod) (up{job="open-cluster-management-addon-observability/app-metrics"} == 1)')
known=$(hub 'count by (cluster, namespace, pod) (kube_pod_info)')

missing=0
for dir in spoke-*/; do
  spoke=${dir%/}
  grep -q "^$spoke " <<<"$known" || { echo "NO DATA from $spoke at all: check its addon (oc --context k3d-$spoke get pods -n open-cluster-management-addon-observability)"; missing=1; continue; }
  grep -q "^$spoke " <<<"$scraped" || echo "WARN: no app-metrics from $spoke: PodMonitor missing? (oc get manifestwork app-metrics -n $spoke)"
  l1=" $(oc --context "k3d-$spoke" get ns -l golden-path.level=L1 -o jsonpath='{.items[*].metadata.name}') "
  # "namespace pod exempt" lines, exempt = yes/no
  while read -r ns pod exempt; do
    if [[ $l1 == *" $ns "* && $exempt == no ]]; then want=$scraped; kind="own metrics"; else want=$known; kind="pod metrics"; fi
    grep -qx "$spoke $ns $pod" <<<"$want" || { echo "MISSING ($kind): $spoke $ns/$pod"; missing=1; }
  done < <(oc --context "k3d-$spoke" get pods -A --field-selector=status.phase=Running -o json | python3 -c 'import sys, json
for p in json.load(sys.stdin)["items"]:
    m = p["metadata"]
    print(m["namespace"], m["name"], "yes" if "golden-path/metrics-exempt" in m.get("annotations", {}) else "no")')
done

[ $missing = 0 ] && echo "OK: every running spoke pod has metrics on the hub."
exit $missing
