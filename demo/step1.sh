#!/usr/bin/env bash
# Demo step 1, the baseline: the team's app is deployed and working, at L0. doc/demo/l1-onboarding.md#1
#   worker-1 runs and emits sensor_readings_total, but on a port named "http": nobody scrapes it.
# State (reached from any other state, safe to re-run):
#   namespace   L0, no labels                     deploy/namespace.yaml
#   worker-1    port "http", running              deploy/deployment.yaml
#   loadgen     busybox calling /read ~5x/s       deploy/loadgen.yaml (same at every step)
#   dashboard   absent (repo + hub)
# Usage: demo/step1.sh
source "$(dirname "$0")/lib.sh"

say "Converging to step 1: L0, port http, no dashboard"
converge L0 http
dashboard absent

say "State: L0. The app emits, nobody scrapes"
s2 -n $NS get pods
scraped | grep -q . && echo "WARN: still scraped (old series). Wait ~5 min before showing step 1." || echo "Not scraped: up{namespace=\"$NS\"} has no data."
cat <<'MSG'

Show next:
  curl the app:   s2 -n sensor-team-2 port-forward deploy/worker-1 8080 & curl -s localhost:8080/metrics | grep ^sensor_
  Grafana Explore: up{namespace="sensor-team-2"}   -> No data
Then: demo/step2.sh
MSG
