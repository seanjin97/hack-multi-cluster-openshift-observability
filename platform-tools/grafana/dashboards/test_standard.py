"""Behaviour tests for the dashboard standard: what helpers do, not what values they hold.
  uv run pytest
"""
import pathlib
from collections import defaultdict
import re

import pytest

import build
import standard as s


def g(*a, **k):
    return s.graph("g", "d", s.COUNT, *a, **k)


def ok(title="G", **k):
    """Panel that passes every house rule: sliced, described, with a unit."""
    return s.graph(title, "desc", s.COUNT, (s.per_pod(f'up{{{s.C}}}'), "{{cluster}}"), **k)


def page(*sections):
    return s.dashboard("T", "desc", [], *sections)


def render(*sections):
    return s.render(page(*sections), "team-test", "team")


def panels(j):
    return [p for top in j["panels"] for p in [top, *top.get("panels", [])] if p["type"] not in ("row", "text")]


# --- node groups: a node lands in exactly one group, by its name ---
def group_of(node):
    """Evaluates by_node_group's label_replace chain the way Prometheus would."""
    calls = re.findall(r'"node_group", "([^"]+)", "instance", "([^"]+)"', s.by_node_group("x"))
    group = None
    for value, regex in calls:  # innermost label_replace comes first in the string, and runs first
        if re.fullmatch(regex, node):
            group = value
    return group


@pytest.mark.parametrize("node, group", [
    ("w-1", "worker"), ("w-12-a", "worker"), ("i-3", "infra"), ("m-1", "control-plane"),
    ("cp-0", "control-plane"), ("k3d-spoke-1-agent-0", "worker"), ("k3d-spoke-1-server-0", "control-plane"),
    ("crc", "other"), ("worker-1", "other"),  # no prefix match: never silently dropped
])
def test_node_lands_in_its_group(node, group):
    assert group_of(node) == group


def test_node_groups_are_disjoint():
    names = ["w-1", "i-1", "m-1", "cp-1", "x-agent-1", "x-server-1"]
    for n in names:
        hits = [g for g, r in s.NODE_GROUPS.items() if re.fullmatch(r, n)]
        assert len(hits) <= 1, f"{n} matches {hits}"


# --- workload: derived from the pod's owner ---
def workload_of(kind, owner):
    """Evaluates SCOPE's label_replace for one pod's owner."""
    regex = re.search(r'created_by_kind="ReplicaSet"\}, "workload", "\$1", "created_by_name", "([^"]+)"', s.SCOPE).group(1)
    return re.fullmatch(regex, owner).group(1) if kind == "ReplicaSet" else owner


@pytest.mark.parametrize("kind, owner, workload", [
    ("ReplicaSet", "frontend-77b888787d", "frontend"),       # Deployment: ReplicaSet hash dropped
    ("ReplicaSet", "my-app-v2-5d9d9885bc", "my-app-v2"),
    ("StatefulSet", "redis", "redis"),
    ("DaemonSet", "node-exporter", "node-exporter"),
])
def test_workload_is_the_owner_without_replicaset_hash(kind, owner, workload):
    assert workload_of(kind, owner) == workload


def test_workload_filter_selects_its_pods_only():
    sel = re.search(r'created_by_name=~"([^"]+)"', s.SCOPE).group(1).replace("$workload", "frontend")
    assert re.fullmatch(sel, "frontend-77b888787d")
    assert not re.fullmatch(sel, "backend-756b468648")
    assert not re.fullmatch(sel, "frontend-api-77b888787d")  # a different Deployment sharing the prefix


# --- slicing: per_pod/per_node apply every filter ---
@pytest.mark.parametrize("f", ["$cluster", "$node", "$namespace", "$workload", "$pod"])
def test_per_pod_follows_every_filter(f):
    assert f in s.per_pod("up")


def test_per_pod_adds_workload_and_node_labels():
    assert "group_left (workload, node)" in s.per_pod("up")


@pytest.mark.parametrize("label", ["instance", "node"])
def test_per_node_joins_on_the_series_node_label(label):
    q = s.per_node("up", label)
    assert f"on (cluster, {label})" in q and "$pod" in q


# --- layout: every line fills the page ---
@pytest.mark.parametrize("n", range(1, 9))
def test_even_widths_fill_the_line(n):
    w = s._even(n)
    assert sum(w) == s.WIDTH and max(w) - min(w) <= 1


def test_golden_signals_put_latency_left_of_traffic_and_errors_above_saturation():
    j = render(s.golden_signals([ok("L")], [ok("T")], [ok("E")], [ok("S")]))
    pos = {p["title"]: p["gridPos"] for p in panels(j)}
    assert pos["L"]["y"] == pos["T"]["y"] and pos["L"]["x"] < pos["T"]["x"]
    assert pos["E"]["y"] == pos["S"]["y"] > pos["L"]["y"]
    assert pos["L"]["x"] == pos["E"]["x"] == 0


def test_open_section_panels_appear_once():
    j = render(s.vitals(ok("a"), ok("b")))
    assert [p["title"] for p in panels(j)] == ["a", "b"]


def test_sections_stack_and_extensions_start_collapsed():
    j = render(s.vitals(ok("a"), ok("b")), s.extension("Why?", ok("c")))
    rows = [p for p in j["panels"] if p["type"] == "row"]
    assert [r["collapsed"] for r in rows] == [False, True]
    assert rows[1]["gridPos"]["y"] > rows[0]["gridPos"]["y"]


def test_tuple_line_shares_the_width():
    j = render(s.extension("Why?", (ok("a"), ok("b"), ok("c"))))
    assert [p["gridPos"]["w"] for p in panels(j)] == s._even(3)


def test_panel_ids_are_unique():
    j = render(s.vitals(ok("a"), ok("b")), s.extension("Why?", ok("c"), (ok("d"), ok("e"))))
    ids = [p["id"] for top in j["panels"] for p in [top, *top.get("panels", [])]]
    assert len(ids) == len(set(ids))


# --- drill-down links reopen this dashboard filtered to the row ---
def test_drill_link_points_at_own_dashboard_with_row_values():
    t = s.grid("t", "d", ("v", s.per_pod(f"up{{{s.C}}}"), s.COUNT, None), links={"namespace": s.drill("cluster", "namespace")})
    j = render(s.extension("Why?", t))
    url = re.search(r'"url": "([^"]+)"', __import__("json").dumps(j)).group(1)
    assert url.startswith("/d/team-test?")
    assert "var-cluster=${__data.fields.cluster}" in url and "var-namespace=${__data.fields.namespace}" in url
    assert "__url_time_range" in url


def test_drill_maps_a_filter_to_a_differently_named_column():
    assert "var-node=${__data.fields.instance}" in s.drill(node="instance")


# --- house rules: a bad dashboard fails the build ---
@pytest.mark.parametrize("bad, rule", [
    (s.graph("G", "", s.COUNT, (s.per_pod(f"up{{{s.C}}}"), "")), "say what question"),
    (s.graph("G", "d", "", (s.per_pod(f"up{{{s.C}}}"), "")), "unit"),
    (s.graph("G", "d", s.COUNT, ('up{namespace="x"}', "")), "$cluster"),
    (s.graph("G", "d", s.COUNT, (f"up{{{s.C}}}", "")), "slice on the filters"),
])
def test_house_rule_violations_fail_the_build(bad, rule):
    with pytest.raises(AssertionError, match=re.escape(rule)):
        render(s.extension("Why?", bad))


def test_cluster_only_panels_are_allowed_when_they_say_so():
    render(s.extension("Why?", s.graph("G", f"API latency. {s.CLUSTER_ONLY}", s.SECONDS, (f"up{{{s.C}}}", ""))))


def test_a_line_short_of_full_width_fails_the_build():
    b = page(s.extension("Why?", ok("a")))
    b._internal.panels[0].panels[0].grid_pos.w = 12
    with pytest.raises(AssertionError, match="fills the page width"):
        s.render(b, "team-test", "team")


# --- build: team folders map to uids, folders and ConfigMaps ---
@pytest.mark.parametrize("path, uid", [
    ("starforge/platform_health.py", "starforge-platform-health"),
    ("payments/Checkout_API.py", "payments-checkout-api"),
])
def test_uid_comes_from_team_and_file_name(path, uid):
    assert build.uid(pathlib.Path(path)) == uid


def test_every_dashboard_gets_a_configmap_in_its_team_folder():
    k = build.kustomization([pathlib.Path("starforge/platform_health.py"), pathlib.Path("payments/checkout.py")])
    assert "name: grafana-dashboard-payments-checkout" in k and "files: [payments/checkout.json]" in k
    assert "dashboard-folder: payments}" in k and "dashboard-folder: starforge}" in k


def test_team_is_tagged_for_search():
    assert "team" in render(s.vitals(ok()))["tags"]


def test_every_committed_dashboard_builds():
    for p in build.sources():
        s.render(build.load(p), build.uid(p), p.parent.name)



# --- built-in dashboard snapshot: finds the metrics a dashboard depends on ---
@pytest.mark.parametrize("expr, metrics", [
    ('sum by (cluster) (rate(container_cpu_usage_seconds_total{cluster="$cluster"}[5m]))', {"container_cpu_usage_seconds_total"}),
    ("a:b:sum / on (namespace) group_left kube_node_info", {"a:b:sum", "kube_node_info"}),
    ("histogram_quantile(0.99, sum by (le) (rate(x_bucket[$__rate_interval])))", {"x_bucket"}),
    ('count(ALERTS{alertstate="firing"} offset 1d) or vector(0)', {"ALERTS"}),
    ('label_replace(up, "dst", "$1", "src", "(.*)")', {"up"}),  # strings and functions aren't metrics
])
def test_builtin_snapshot_finds_the_metrics_a_query_needs(expr, metrics):
    import acm_builtin
    assert acm_builtin.metrics_in(expr) == metrics


# --- granularity: graphs step at 1m and widen their window on zoom; tables and sizing summarise a range ---
def windowed(window, title="G", desc="d"):
    return s.graph(title, desc, s.COUNT, (s.per_pod(f"rate(up{{{s.C}}}[{window}])"), ""))


def ext(*lines):
    return render(s.extension("Why?", *lines))


def test_graph_rate_window_widens_when_zoomed_out():
    ext(windowed(s.RATE))


@pytest.mark.parametrize("window", ["5m", "1h", "30s"])
def test_graph_with_a_fixed_rate_window_fails_the_build(window):
    with pytest.raises(AssertionError, match=re.escape("$__rate_interval")):
        ext(windowed(window))


def test_tile_follows_the_graph_window_rule():
    with pytest.raises(AssertionError, match=re.escape("$__rate_interval")):
        ext(s.tile("T", "d", s.per_pod(f"rate(up{{{s.C}}}[5m])"), s.COUNT))


def test_graph_finer_than_the_minimum_step_fails_the_build():
    with pytest.raises(AssertionError, match="step"):
        ext(ok().interval("10s"))


def test_brackets_inside_label_regexes_are_not_windows():
    ext(s.graph("G", "d", s.COUNT, (s.per_pod(f'rate(up{{{s.C}, pod=~"a-[a-z0-9]+"}}[{s.RATE}])'), "")))


def table(window, **k):
    return s.grid("T", "d", ("v", s.per_pod(f"increase(up{{{s.C}}}[{window}])"), s.COUNT, None), **k)


def test_table_summarises_the_selected_range():
    ext(table(s.RANGE))


def test_table_with_a_fixed_window_fails_the_build():
    with pytest.raises(AssertionError, match=re.escape("$__range")):
        ext(table("1h"))


@pytest.mark.parametrize("panel", [
    lambda: s.tile("Used / requested", "d", s.per_pod(f"rate(up{{{s.C}}}[{s.RANGE}])"), s.PERCENT, sizing=True),
    lambda: table(s.RANGE, sizing=True),
])
def test_sizing_panel_ignores_the_time_picker_and_says_so(panel):
    p = panels(ext(panel()))[0]
    assert p.get("timeFrom") and p["title"].endswith(f"({p['timeFrom']})")


def test_sizing_panel_must_summarise_its_whole_window():
    with pytest.raises(AssertionError, match=re.escape("$__range")):
        ext(s.tile("T", "d", s.per_pod(f"rate(up{{{s.C}}}[{s.RATE}])"), s.PERCENT, sizing=True))


def test_title_claiming_a_window_the_panel_doesnt_fix_fails_the_build():
    with pytest.raises(AssertionError, match="window"):
        ext(ok("Restarts (1h)"))


# --- built-in ACM dashboards: links and sources resolve against the committed snapshot ---
CATALOG = """| Dashboard | uid | Folder | Filters | Default range | Data here | Panels |
|---|---|---|---|---|---|---|
| Alert Analysis | `w1V3PRTnk` | Alerts | severity | 30m | yes | Total Alerts |
| Kubernetes / API server | `09ec`<br/>also `ef53` | General | cluster | 3h | yes | Up |
| Kubernetes / Networking / Pod | `7a18` | Platform - MCOA | cluster | 1h | none | Bytes |
"""


def test_builtin_link_opens_the_snapshot_uid_keeping_time_and_filters():
    link = s.builtin("Kubernetes / API server", s.builtins(CATALOG)).build()
    assert link.url == "/d/09ec" and link.keep_time and link.include_vars


def test_linking_an_unknown_builtin_fails():
    with pytest.raises(AssertionError, match="acm-builtin.md"):
        s.builtin("Made Up Dashboard", s.builtins(CATALOG))


def test_linking_a_builtin_without_data_here_fails():
    with pytest.raises(AssertionError, match="no data"):
        s.builtin("Kubernetes / Networking / Pod", s.builtins(CATALOG))


def test_header_links_land_on_the_dashboard():
    d = s.dashboard("T", "d", [], s.vitals(ok()), links=[s.builtin("Alert Analysis", s.builtins(CATALOG))])
    assert [l["url"] for l in s.render(d, "team-test", "team")["links"]] == ["/d/w1V3PRTnk"]


def test_source_naming_an_unknown_builtin_fails_the_build():
    with pytest.raises(AssertionError, match="Source"):
        ext(s.graph("G", "Shows x. Source: ACM Made Up Dashboard.", s.COUNT, (s.per_pod(f"up{{{s.C}}}"), "")))


def test_source_and_cluster_only_can_share_a_description():
    title = next(iter(s.builtins()))
    ext(s.graph("G", f"Shows x. Source: ACM {title}. {s.CLUSTER_ONLY}", s.COUNT, (f"up{{{s.C}}}", "")))


def test_source_naming_a_snapshot_dashboard_builds():
    title = next(iter(s.builtins()))
    ext(s.graph("G", f"Shows x. Source: ACM {title}.", s.COUNT, (s.per_pod(f"up{{{s.C}}}"), "")))


# --- density: at most MAX_PER_LINE graphs or tables on a line; tiles are exempt ---
def lines_of(j):
    """{y: [panel types]} for every non-header panel."""
    out = defaultdict(list)
    for p in panels(j):
        if p["type"] != "text":
            out[p["gridPos"]["y"]].append(p)
    return out


def test_golden_signal_quadrants_wrap_to_at_most_four_graphs_a_line():
    j = render(s.golden_signals(*[[ok(f"{q}{i}") for i in range(3)] for q in "LTES"]))
    for line in lines_of(j).values():
        assert len(line) <= s.MAX_PER_LINE
        assert sum(p["gridPos"]["w"] for p in line) == s.WIDTH


def test_wrapped_quadrant_keeps_latency_left_and_traffic_right():
    j = render(s.golden_signals([ok("L0"), ok("L1"), ok("L2")], [ok("T0"), ok("T1"), ok("T2")], [ok("E")], [ok("S")]))
    for p in panels(j):
        if p["title"][0] in "LE":
            assert p["gridPos"]["x"] + p["gridPos"]["w"] <= s.WIDTH // 2, p["title"]
        if p["title"][0] in "TS":
            assert p["gridPos"]["x"] >= s.WIDTH // 2, p["title"]


def test_extension_line_wraps_after_four_panels():
    j = render(s.extension("Why?", tuple(ok(str(i)) for i in range(6))))
    sizes = sorted(len(l) for l in lines_of(j).values())
    assert max(sizes) <= s.MAX_PER_LINE and sum(sizes) == 6


def test_quadrants_side_by_side_must_wrap_to_the_same_lines():
    with pytest.raises(AssertionError, match="same number of lines"):
        render(s.golden_signals([ok("L0"), ok("L1"), ok("L2")], [ok("T")], [ok("E")], [ok("S")]))


def test_vitals_may_hold_six_tiles():
    j = render(s.vitals(*[s.tile(str(i), "d", s.per_pod(f"up{{{s.C}}}"), s.COUNT) for i in range(6)]))
    assert [len(l) for l in lines_of(j).values()] == [6]


def test_a_crowded_line_fails_the_build():
    b = page(s.extension("Why?", tuple(ok(str(i)) for i in range(4))))
    row = b._internal.panels[0]
    for p in row.panels:
        p.grid_pos.w = 4
    extra = ok("x").build(); extra.grid_pos = s.dm.GridPos(h=8, w=8, x=16, y=row.panels[0].grid_pos.y)
    row.panels.append(extra)
    with pytest.raises(AssertionError, match="at most"):
        s.render(b, "team-test", "team")


# --- team defaults: a team dashboard opens on the team's own scope ---
def test_team_dashboard_opens_on_its_namespace():
    j = s.render(s.dashboard("T", "d", [], s.vitals(ok()), scope={"namespace": "shop"}), "team-test", "team")
    v = {x["name"]: x for x in j["templating"]["list"]}
    assert v["namespace"]["current"]["value"] == ["shop"]
    assert v["cluster"]["current"]["value"] == "$__all"  # unscoped filters stay on All


def test_scope_on_an_unknown_filter_fails():
    with pytest.raises(AssertionError, match="filters"):
        s.dashboard("T", "d", [], s.vitals(ok()), scope={"team": "shop"})


# --- peak over a range: the highest STEP-resolution value in the window, allowed in tables ---
def test_peak_is_allowed_in_a_table():
    ext(s.grid("T", "d", ("Peak", s.peak(s.per_pod(f"rate(up{{{s.C}}}[{s.RATE}])")), s.CORES, None)))


def test_peak_samples_at_the_dashboard_step_over_the_whole_range():
    q = s.peak("x")
    assert f"[{s.RANGE}:{s.STEP}]" in q and q.startswith("max_over_time(")


def test_hand_written_subquery_still_fails_the_build():
    with pytest.raises(AssertionError, match=re.escape("$__range")):
        ext(s.grid("T", "d", ("v", s.per_pod(f"max_over_time(rate(up{{{s.C}}}[1m])[{s.RANGE}:30s])"), s.CORES, None)))


# --- build: output follows the sources (CI then asserts the build changed nothing) ---
def team_dir(tmp_path, monkeypatch):
    """A throwaway dashboards root with one team dashboard, and build.py pointed at it."""
    (tmp_path / "team").mkdir()
    (tmp_path / "team" / "board.py").write_text(
        "from standard import *\n"
        f"dashboard = dashboard('B', 'd', [], vitals(tile('T', 'd', per_pod('up{{{s.C}}}'), COUNT)))\n")
    monkeypatch.setattr(build, "HERE", tmp_path)
    return tmp_path


def test_build_is_repeatable(tmp_path, monkeypatch):
    root = team_dir(tmp_path, monkeypatch)
    build.main()
    first = {p: p.read_text() for p in root.rglob("*") if p.suffix in (".json", ".yaml")}
    build.main()
    assert first == {p: p.read_text() for p in root.rglob("*") if p.suffix in (".json", ".yaml")}


def test_build_removes_the_json_of_a_deleted_dashboard(tmp_path, monkeypatch):
    root = team_dir(tmp_path, monkeypatch)
    build.main()
    (root / "team" / "keep.py").write_text((root / "team" / "board.py").read_text())
    (root / "team" / "board.py").unlink()
    build.main()
    assert not (root / "team" / "board.json").exists()
    assert "team/board.json" not in (root / "kustomization.yaml").read_text()
