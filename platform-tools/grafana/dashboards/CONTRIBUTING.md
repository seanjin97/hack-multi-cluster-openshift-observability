# Changing the standard (platform team)

Dashboard authors use the `grafana-dashboard` skill and never touch these files. This page is for whoever changes `standard.py`, `build.py` or the tests.

## Tests: behaviour, not config
`test_standard.py` checks what a helper **does**, not what values it holds. A test fails only when behaviour breaks.

| Test | Don't test |
|---|---|
| where a node name lands in a group | threshold numbers, colour names |
| a Deployment pod's workload drops its ReplicaSet hash | units, descriptions |
| `per_pod` follows every filter | the exact PromQL string |
| every line fills the width, at most 4 graphs per line | a snapshot of the JSON |
| a fixed `[5m]` in a graph fails the build | |
| `build.py` is repeatable, and removes the JSON of a deleted dashboard | |

- **PromQL helpers:** evaluate their regex or label logic in Python (see `group_of`, `workload_of`) on real-looking inputs, including edge cases.
- **Every new helper gets a test** for the behaviour it promises and for the input that would break it.
- **`test_every_committed_dashboard_builds`** re-applies every rule to every team's dashboard.

## A new rule is test-first
A rule that only lives in prose isn't enforced: dashboards built before it quietly break it.
1. **Red:** write the behaviour tests, both the panel that breaks the rule and the one that follows it. Run `uv run pytest` and watch them fail.
2. **Implement** the check in `standard.py`.
3. **Watch it catch real code:** `test_every_committed_dashboard_builds` goes red on existing dashboards that break it. If nothing does, break one on purpose to prove the check, then revert.
4. **Green:** fix the dashboards, not the test.
5. **Document** the rule in the skill (`SKILL.md`), in one line.

## Housekeeping
- **SDK bump:** edit `pyproject.toml`, run `uv lock`, run `uv run pytest` and `uv run build.py`, and commit any JSON changes.
- **ACM upgrade:** someone with hub access runs `python3 acm_builtin.py` and commits `acm-builtin.md`.
- **Checking real data** (needs hub access): `./check-queries.sh <team>/<name>.json`.
- **Hub returns nothing for every cluster "now":** check the crc clock (`oc debug node/crc -- date -u`); Thanos drops samples from the future.
