#!/usr/bin/env bash
# Demo step 2: the team onboards to L1 to get its metric to Grafana, and Kyverno BLOCKS it. doc/demo/l1-onboarding.md#2
#   They read doc/app-teams/0-levels.md, label the namespace L1, but keep the port named "http".
#   The running pod stays up; its replacement is rejected by require-metrics-port.
# Files after this script:
#   deploy/namespace.yaml   L1: maturity + team label, contact annotation
#   deploy/deployment.yaml  port "http" (unchanged from step 1)  <- live edit for step 3: rename to "metrics"
# Usage: demo/step2.sh   (runs step 1 first if the team isn't deployed)
source "$(dirname "$0")/lib.sh"

s2 -n $NS get deploy worker-1 >/dev/null 2>&1 || "$(dirname "$0")/step1.sh"
namespace L1
deployment http

say "Applying the L1 namespace, then rolling the pod: it must pass L1 now"
s2 apply -k "$DEPLOY"
s2 -n $NS rollout restart deploy/worker-1
for _ in $(seq 20); do  # the ReplicaSet retries creating the pod; wait for the first denial
  why=$(s2 -n $NS get events --field-selector reason=FailedCreate -o jsonpath='{.items[-1:].message}')
  [ -n "$why" ] && break; sleep 1
done

say "Kyverno said"
echo "${why:-no denial yet: re-run 's2 -n $NS get events --field-selector reason=FailedCreate'}" | sed 's/.*denied the request: //'
say "Pods: the old one keeps running"
s2 -n $NS get pods
cat <<'MSG'

Show next: the error links to doc/app-teams/1-metrics.md. Fix live in deploy/deployment.yaml:
  rename the port "http" -> "metrics" (3 places), then: s2 apply -k sensor-team-2-monorepo/deploy
Or jump there: demo/step3.sh
MSG
