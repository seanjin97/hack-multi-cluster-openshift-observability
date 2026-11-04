#!/usr/bin/env bash
# Demo step 5: a hand edit hard-codes a [5m] window, and conformance catches it. doc/demo/l1-onboarding.md#5
#   Edits dashboards/sensor-team-2/worker_1.py: the first [{RATE}] window -> [5m].
#   A fixed window doesn't widen on zoom: zoomed out, the graph samples too little and hides spikes.
# State (reached from any other state, safe to re-run):
#   cluster     as step 3: L1, port metrics, scraped, loadgen running
#   dashboard   present (demo/fixtures/worker_1.py, what step 4 generates), with its first window hard-coded to [5m]
# Usage: demo/step5.sh        converge, break it, run the tests (red)
#        demo/step5.sh undo   put [{RATE}] back, run the tests (green)
source "$(dirname "$0")/lib.sh"

PY=$DASH/sensor-team-2/worker_1.py
if [ "${1:-}" != undo ]; then
  say "Converging to step 4's end: step 3 on the cluster, dashboard in the repo"
  converge L1 metrics
  dashboard present
fi
cd "$DASH"

if [ "${1:-}" = undo ]; then
  perl -pi -e 's/\[5m\]/[{RATE}]/g' "$PY"
  say "Undone: [5m] -> [{RATE}]"
  uv run pytest -q 2>&1 | tail -1
  exit 0
fi

grep -q '\[5m\]' "$PY" || perl -0pi -e 's/\[\{RATE\}\]/[5m]/' "$PY"   # the first query's window, whatever the dashboard
grep -q '\[5m\]' "$PY" || { echo "No [{RATE}] window to break in $PY."; exit 1; }
say "Hand edit: hard-coded a query window"
grep -n '\[5m\]' "$PY"

say "Conformance: uv run pytest"
uv run pytest -q tests/test_conformance.py 2>&1 | grep -E "^E +AssertionError|FAILED|passed|failed" || true
cat <<'MSG'

Show next: push it, and CI's dashboards / gate goes red with the same message; Merge is blocked.
Fix: demo/step5.sh undo
MSG
