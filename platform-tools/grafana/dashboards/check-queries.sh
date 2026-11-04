#!/usr/bin/env bash
# Runs every query of a generated dashboard against the hub's Thanos, the way Grafana would at the default view:
#   filters ($cluster, $node, $namespace, $workload, $pod) = All, $__rate_interval = 2m (1m step x 2),
#   $__range = 1h, or the panel's fixed window (sizing panels, 7d).
# Prints each panel's series count and the clusters it saw.
#   ERROR = the query doesn't parse. 0 series = no data: metric not allowlisted, or not emitted.
# Needs read access to the hub (platform team or CI), not something app teams run.
# Exits 1 if any query errors.
# Usage: ./check-queries.sh starforge/platform_health.json
set -euo pipefail
command -v oc >/dev/null || eval "$(crc oc-env)"
failed=0

while IFS=$'\t' read -r title expr; do
  printf '%s: ' "$title"
  oc get --raw "/api/v1/namespaces/open-cluster-management-observability/services/http:observability-thanos-query:9090/proxy/api/v1/query?query=$(python3 -c 'import sys, urllib.parse; print(urllib.parse.quote(sys.argv[1]))' "$expr")" 2>&1 |
    python3 -c 'import sys, json
raw = sys.stdin.read()
try:
    d = json.loads(raw)
except ValueError:
    print("ERROR", raw.strip()); sys.exit(1)
if d["status"] != "success": print("ERROR", d.get("error")); sys.exit(1)
r = d["data"]["result"]
print(len(r), "series", sorted({s["metric"].get("cluster", "-") for s in r}))' || failed=1
done < <(python3 - "$1" <<'EOF'
import json, re, sys
j = json.load(open(sys.argv[1]))
for top in j["panels"]:
    for p in [top] + top.get("panels", []):
        for t in p.get("targets", []):
            e = re.sub(r"\$(cluster|node|namespace|workload|pod)\b", ".*", t["expr"])
            e = e.replace("$__rate_interval", "2m").replace("$__range", p.get("timeFrom") or "1h")
            print(f'{p["title"]} [{t["refId"]}]\t{e}')
EOF
)
exit $failed
