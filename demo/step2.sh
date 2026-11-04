#!/usr/bin/env bash
# Demo step 2: the team onboards to L1 to get its metric to Grafana, and Kyverno BLOCKS it. doc/demo/l1-onboarding.md#2
#   They read doc/app-teams/0-levels.md, label the namespace L1, but keep the port named "http".
#   The running pod stays up; its replacement is rejected by require-metrics-port.
# State (reached from any other state, safe to re-run):
#   namespace   L1: maturity + team label, contact annotation
#   worker-1    port "http": old pod running, its replacement denied   <- live edit for step 3: rename to "metrics"
#   loadgen     busybox calling /read ~5x/s
#   dashboard   absent (repo + hub)
# Usage: demo/step2.sh
source "$(dirname "$0")/lib.sh"

say "Converging to step 1 first, so there's a running pod to keep"
converge L0 http
dashboard absent

say "Labelling the namespace L1, then rolling the pod: it must pass L1 now"
namespace L1
s2 apply -k "$DEPLOY"
s2 -n $NS rollout restart deploy/worker-1
sleep 2
s2 -n $NS get events --field-selector reason=FailedCreate

say "Kyverno said"
s2 -n $NS get events --field-selector reason=FailedCreate -o jsonpath='{.items[-1:].message}' 2>/dev/null \
  | sed 's/.*denied the request: //'; echo
say "Pods: the old one keeps running"
s2 -n $NS get pods
cat <<'MSG'

Show next: the error links to doc/app-teams/1-metrics.md. Fix live in deploy/deployment.yaml:
  rename the port "http" -> "metrics" (3 places), then: s2 apply -k sensor-team-2-monorepo/deploy
Or jump there: demo/step3.sh
MSG
