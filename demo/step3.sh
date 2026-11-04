#!/usr/bin/env bash
# Demo step 3: the team names the port "metrics", admission passes, ACM scrapes it. doc/demo/l1-onboarding.md#3
# Files after this script:
#   deploy/namespace.yaml   L1
#   deploy/deployment.yaml  port "metrics"
# Then verify by hand in Grafana Explore (queries printed at the end).
# Usage: demo/step3.sh
source "$(dirname "$0")/lib.sh"

ensure_image
namespace L1
deployment metrics
say "Deploying the fixed manifest"
apply

say "Waiting for spoke-2's Prometheus to scrape it"
for _ in $(seq 30); do scraped | grep -q . && break; sleep 2; done
scraped | sed -E 's/container="[^"]*", endpoint="[^"]*", instance="[^"]*", job="[^"]*", //' || true
cat <<'MSG'

Verify on the hub (Grafana -> Explore), ~1 min after the scrape:
  up{cluster="spoke-2", namespace="sensor-team-2"}                                             -> 1
  sum by (outcome) (increase(sensor_readings_total{cluster="spoke-2", namespace="sensor-team-2"}[1m]))   -> success ~11, failure ~1
  sensor_reading_celsius{cluster="spoke-2", namespace="sensor-team-2"}                          -> 15..30, graph view
Then step 4: no script. Generate the dashboard with /grafana-dashboard (doc/demo/l1-onboarding.md#4)
MSG
