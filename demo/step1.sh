#!/usr/bin/env bash
# Demo step 1: the team is NOT onboarded (L0). doc/demo/l1-onboarding.md#1
#   worker-1 runs and emits sensor_readings_total, but on a port named "http": nobody scrapes it.
# Files after this script:
#   deploy/namespace.yaml   no labels (L0)
#   deploy/deployment.yaml  port "http", probes + resources already set
#   no dashboards/sensor-team-2/ (not in the dashboards repo, not on the hub)
# Usage: demo/step1.sh   (resets everything, safe to re-run)
source "$(dirname "$0")/lib.sh"

ensure_image
say "Resetting sensor-team-2 to L0"
s2 delete ns $NS --ignore-not-found --wait
namespace L0
deployment http
apply

say "Removing any sensor-team-2 dashboard (repo + hub)"
rm -rf "$DASH/sensor-team-2"
(cd "$DASH" && uv run -q build.py)
oc -n open-cluster-management-observability delete cm grafana-dashboard-sensor-team-2-worker-1 --ignore-not-found  # the loader drops it from Grafana

say "State: L0. The app emits, nobody scrapes"
s2 -n $NS get pods
scraped | grep -q . && echo "WARN: still scraped (old series). Wait ~5 min before showing step 1." || echo "Not scraped: up{namespace=\"$NS\"} has no data."
cat <<'MSG'

Show next:
  curl the app:   s2 -n sensor-team-2 port-forward deploy/worker-1 8080 & curl -s localhost:8080/metrics | grep ^sensor_
  Grafana Explore: up{namespace="sensor-team-2"}   -> No data
Then: demo/step2.sh
MSG
