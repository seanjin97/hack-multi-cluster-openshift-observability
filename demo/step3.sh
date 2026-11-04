#!/usr/bin/env bash
# Demo step 3: the team names the port "metrics", admission passes, ACM scrapes it. doc/demo/l1-onboarding.md#3
# State (reached from any other state, safe to re-run):
#   namespace   L1
#   worker-1    port "metrics", running, scraped
#   loadgen     busybox calling /read ~5x/s
#   dashboard   absent: step 4 generates it live
# Usage: demo/step3.sh
source "$(dirname "$0")/lib.sh"

say "Converging to step 3: L1, port metrics, no dashboard"
converge L1 metrics
dashboard absent

say "Waiting for spoke-2's Prometheus to scrape it"
for _ in $(seq 30); do scraped | grep -q . && break; sleep 2; done
scraped | sed -E 's/container="[^"]*", endpoint="[^"]*", instance="[^"]*", job="[^"]*", //' || true
cat <<'MSG'

Verify on the hub (Grafana -> Explore), ~1 min after the scrape:
  up{cluster="spoke-2", namespace="sensor-team-2"}                                             -> 1
  sum by (outcome) (increase(sensor_readings_total{cluster="spoke-2", namespace="sensor-team-2"}[1m]))   -> success ~11, failure ~1
  sensor_reading_celsius{cluster="spoke-2", namespace="sensor-team-2"}                          -> 15..30, graph view
  sum by (status) (rate(http_request_duration_seconds_count{cluster="spoke-2", namespace="sensor-team-2"}[1m]))   -> 200 ~4.5/s, 503 ~0.5/s (loadgen)
Then step 4: no script. Generate the dashboard with /grafana-dashboard (doc/demo/l1-onboarding.md#4)
MSG
