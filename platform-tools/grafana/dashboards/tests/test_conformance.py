"""Golden-path conformance: does every team's <team>/<name>.py follow the golden path?
  uv run pytest tests/test_conformance.py
CI gate 1 runs it on every MR, so nothing that breaks a rule can merge. A red test names the team file,
the panel and the rule. check() reads the rendered JSON: it judges what a dashboard shows, not which
components built it. components/ builds dashboards; this file judges them.
"""
import re
from collections import defaultdict

import pytest
from grafana_foundation_sdk.models import dashboard as dm

import build
import components as s
from helpers import ext as _ext, ok, page, render, table

_WINDOW = re.compile(r"\[([^\]]+)\]")
_APP_METRIC = re.compile(r"([a-zA-Z_:][a-zA-Z0-9_:]*)\{[^}]*" + re.escape(s.APP))
RED = "http_request_duration_seconds"  # the golden-path histogram: the one app metric allowed above the extensions
_TITLE_WINDOW = re.compile(r"\((\d+[smhdw])\)$")


def sections_of(j):
    """Panels per row, whether the row is open (panels follow it) or collapsed (panels nest in it)."""
    sections = []
    for top in j["panels"]:
        if top["type"] == "row":
            sections.append(list(top.get("panels", [])))
        else:
            sections[-1].append(top)
    return sections


def check(j):
    """The golden path, as rules on a rendered dashboard. Fails on the first broken rule."""
    # Page
    assert j.get("uid") and j.get("title") and j.get("description"), "uid, title and description are required"
    assert "golden-path" in j.get("tags", []), "tag golden-path"
    names = [v["name"] for v in j["templating"]["list"]]
    assert tuple(names[1:]) == s.FILTERS, f"standard filters only, got {names}"
    rows = [(p["title"], p.get("collapsed", False)) for p in j["panels"] if p["type"] == "row"]
    assert rows[:2] == [("System Vitals", False), ("Golden Signals", False)], \
        f"open with vitals(...) then golden_signals(...), got {rows[:2]}"
    assert all(c for _, c in rows[2:]), f"everything after Golden Signals is an extension(...), got {rows[2:]}"
    sections = sections_of(j)
    # Standard panels: every page opens with the same RED + saturation panels, unchanged, in the same places
    vit, gold = sections[0], [p for p in sections[1] if p["type"] != "text"]
    want_v = [_shown(p.build()) for p in s.layout.standard_vitals()]
    assert [_shown(p) for p in vit[:len(want_v)]] == want_v, \
        f"System Vitals opens with the standard tiles {[t for t, _ in want_v]}, unchanged: build it with vitals(...)"
    std = s.layout.standard_signals()
    by_title = {p["title"]: p for p in gold}
    for quadrant, p in std.items():
        t, e = _shown(p.build())
        assert t in by_title and _shown(by_title[t]) == (t, e), \
            f"Golden Signals {quadrant} opens with the standard {t!r}, unchanged: build it with golden_signals(...)"
    # Team metrics (scraped through APP) answer the team's own questions, so they go in an extension
    for p in [*vit, *gold]:
        for target in p.get("targets", []):
            team = {m for m in _APP_METRIC.findall(target["expr"]) if not m.startswith(RED)}
            assert not team, f"{p.get('title')}: team metric {sorted(team)} goes in an extension(...), " \
                             f"not System Vitals or Golden Signals (they hold the standard RED panels)"
    titles = [p.get("title") for sec in sections for p in sec if p["type"] != "text"]
    dupes = {t for t in titles if titles.count(t) > 1}
    assert not dupes, f"panel titles are unique on the page; {sorted(dupes)} repeat (the standard panels are already there)"
    for panels in sections:
        # Layout
        lines, crowded = defaultdict(int), defaultdict(int)
        for p in panels:
            lines[p["gridPos"]["y"]] += p["gridPos"]["w"]
            if p["type"] not in ("stat", "text"):
                crowded[p["gridPos"]["y"]] += 1
        assert all(w == s.WIDTH for w in lines.values()), f"every line fills the page width: {dict(lines)}"
        assert all(n <= s.MAX_PER_LINE for n in crowded.values()), \
            f"at most {s.MAX_PER_LINE} graphs or tables per line: {dict(crowded)}"
        for p in panels:
            if p["type"] == "text":
                continue
            # Panel
            t, desc = p.get("title"), p.get("description", "")
            assert desc, f"{t}: say what question the panel answers and what to do when it's red"
            assert p["type"] == "table" or p.get("fieldConfig", {}).get("defaults", {}).get("unit"), f"{t}: set a unit"
            sizing = bool(p.get("timeFrom"))
            claimed = _TITLE_WINDOW.search(t or "")
            assert not claimed or claimed.group(1) == p.get("timeFrom"), \
                f"{t}: the title names a window the panel doesn't fix; use sizing=True or drop it from the title"
            if p["type"] != "table" and not sizing:
                assert p.get("interval") == s.STEP, \
                    f"{t}: graphs and tiles step at {s.STEP} (finer is noise, coarser hides spikes)"
            src = re.search(r"Source: ACM ([^.]+)\.", desc)
            assert not src or src.group(1) in s.builtins(), \
                f"{t}: Source names {src and src.group(1)!r}, not in acm-builtin.md"
            # Queries
            for target in p.get("targets", []):
                e = target["expr"]
                want = s.RANGE if p["type"] == "table" or sizing else s.RATE
                windows = _WINDOW.findall(re.sub(r'"[^"]*"', '""', e))
                windows = [w for w in windows if not (w == s.PEAK[1:-1] and want == s.RANGE)]
                if want == s.RANGE and s.PEAK in e:  # peak() wraps a graph-style expression
                    windows = [w for w in windows if w != s.RATE]
                assert all(w == want for w in windows), \
                    f"{t}: windows must be {want} ({'summarise the range' if want == s.RANGE else 'widen on zoom'}), got {windows}"
                assert "$cluster" in e, f"{t}: every query filters on $cluster"
                assert "$pod" in e or "$node" in e or desc.endswith(s.CLUSTER_ONLY), \
                    f"{t}: slice on the filters with per_pod()/per_node(), or end the description with {s.CLUSTER_ONLY!r}"


def _shown(p):
    """(title, expressions) of a panel, as JSON or as an SDK model: what the standard rule compares."""
    if not isinstance(p, dict):
        p = {"title": p.title, "targets": [{"expr": t.expr} for t in p.targets or []]}
    return p.get("title"), [t["expr"] for t in p.get("targets", [])]


# --- every committed team dashboard conforms ---
@pytest.mark.parametrize("path", build.sources(), ids=lambda p: f"{p.parent.name}/{p.name}")
def test_team_dashboard_conforms(path):
    check(build.render(build.load(path), build.uid(path), path.parent.name))


# --- each rule fails the dashboard that breaks it, and passes the one that follows it ---
def ext(*lines):
    """lines as an extension on an otherwise conforming page, checked."""
    j = _ext(*lines)
    check(j)
    return j


def checked(builder):
    check(build.render(builder, "team-test", "team"))


def test_a_conforming_page_passes():
    checked(page())


# page
@pytest.mark.parametrize("sections, rule", [
    (lambda: [s.extension("Why?", ok())], "vitals"),                                          # no vitals or golden signals
    (lambda: [s.golden_signals(*[[ok(q)] for q in "LTES"]), s.vitals(ok())], "vitals"),       # wrong order
    (lambda: [s.vitals(ok()), s.golden_signals(*[[ok(q)] for q in "LTES"]),
              ("Open extra", False, [[(ok("x"), s.WIDTH)]])], "extension"),                   # open row after them
])
def test_page_out_of_structure_fails(sections, rule):
    with pytest.raises(AssertionError, match=rule):
        checked(s.dashboard("T", "d", [], *sections()))


# standard panels: RED + saturation on every page, team metrics below
def test_standard_panels_are_on_every_page():
    titles = {p.get("title") for top in render(s.vitals(), s.golden_signals())["panels"] for p in [top, *top.get("panels", [])]}
    assert s.STANDARD_TITLES <= titles


def test_page_without_the_standard_vitals_fails():
    b = page()
    b._internal.panels[1].targets[0].expr = s.per_pod(f"up{{{s.C}}}")  # first standard tile, query swapped
    with pytest.raises(AssertionError, match="standard tiles"):
        checked(b)


def test_page_with_a_changed_standard_signal_fails():
    b = page()
    p = next(p for p in b._internal.panels if getattr(p, "title", None) == "p95 by workload")
    p.title = "p99 by workload"
    with pytest.raises(AssertionError, match="Latency|latency"):
        checked(b)


TEAM = s.per_pod(f"rate(sensor_readings_total{{{s.C}, {s.APP}}}[{s.RATE}])")


@pytest.mark.parametrize("section", [
    lambda: s.vitals(s.tile("Readings", "d", f"sum({TEAM})", s.REQPS)),
    lambda: s.golden_signals(traffic=[s.graph("Readings", "d", s.REQPS, (f"sum by (cluster) ({TEAM})", "{{cluster}}"))]),
])
def test_team_metric_above_the_extensions_fails(section):
    with pytest.raises(AssertionError, match="extension"):
        checked(page(section()))


def test_team_metric_in_an_extension_passes():
    ext(s.graph("Readings", "d", s.REQPS, (f"sum by (cluster) ({TEAM})", "{{cluster}}")))


def test_red_histogram_may_add_panels_above_the_extensions():
    lat = s.per_pod(f"rate(http_request_duration_seconds_bucket{{{s.C}, {s.APP}}}[{s.RATE}])")
    checked(page(s.golden_signals(latency=[s.graph("p95 by path", "d", s.SECONDS,
                                                   (f"histogram_quantile(0.95, sum by (cluster, path, le) ({lat}))", "{{cluster}}"))])))


def test_repeating_a_standard_panel_fails():
    with pytest.raises(AssertionError, match="unique"):
        ext(ok("p95 latency"))


# panels and queries
@pytest.mark.parametrize("bad, rule", [
    (s.graph("G", "", s.COUNT, (s.per_pod(f"up{{{s.C}}}"), "")), "say what question"),
    (s.graph("G", "d", "", (s.per_pod(f"up{{{s.C}}}"), "")), "unit"),
    (s.graph("G", "d", s.COUNT, ('up{namespace="x"}', "")), "$cluster"),
    (s.graph("G", "d", s.COUNT, (f"up{{{s.C}}}", "")), "slice on the filters"),
])
def test_panel_breaking_a_rule_fails(bad, rule):
    with pytest.raises(AssertionError, match=re.escape(rule)):
        ext(bad)


def test_cluster_only_panels_are_allowed_when_they_say_so():
    ext(s.graph("G", f"API latency. {s.CLUSTER_ONLY}", s.SECONDS, (f"up{{{s.C}}}", "")))


# layout
def test_a_line_short_of_full_width_fails():
    b = page(s.extension("Why?", ok("a")))
    b._internal.panels[-1].panels[0].grid_pos.w = 12
    with pytest.raises(AssertionError, match="fills the page width"):
        checked(b)


def test_a_crowded_line_fails():
    b = page(s.extension("Why?", tuple(ok(str(i)) for i in range(4))))
    row = b._internal.panels[-1]
    for p in row.panels:
        p.grid_pos.w = 4
    extra = ok("x").build(); extra.grid_pos = dm.GridPos(h=8, w=8, x=16, y=row.panels[0].grid_pos.y)
    row.panels.append(extra)
    with pytest.raises(AssertionError, match="at most"):
        checked(b)


# granularity: graphs step at 1m and widen their window on zoom; tables and sizing summarise a range
def windowed(window):
    return s.graph("G", "d", s.COUNT, (s.per_pod(f"rate(up{{{s.C}}}[{window}])"), ""))


def test_graph_rate_window_widens_when_zoomed_out():
    ext(windowed(s.RATE))


@pytest.mark.parametrize("window", ["5m", "1h", "30s"])
def test_graph_with_a_fixed_rate_window_fails(window):
    with pytest.raises(AssertionError, match=re.escape("$__rate_interval")):
        ext(windowed(window))


def test_tile_follows_the_graph_window_rule():
    with pytest.raises(AssertionError, match=re.escape("$__rate_interval")):
        ext(s.tile("T", "d", s.per_pod(f"rate(up{{{s.C}}}[5m])"), s.COUNT))


def test_graph_finer_than_the_minimum_step_fails():
    with pytest.raises(AssertionError, match="step"):
        ext(ok().interval("10s"))


def test_brackets_inside_label_regexes_are_not_windows():
    ext(s.graph("G", "d", s.COUNT, (s.per_pod(f'rate(up{{{s.C}, pod=~"a-[a-z0-9]+"}}[{s.RATE}])'), "")))


def test_table_summarises_the_selected_range():
    ext(table(s.RANGE))


def test_table_with_a_fixed_window_fails():
    with pytest.raises(AssertionError, match=re.escape("$__range")):
        ext(table("1h"))


def test_sizing_panel_must_summarise_its_whole_window():
    with pytest.raises(AssertionError, match=re.escape("$__range")):
        ext(s.tile("T", "d", s.per_pod(f"rate(up{{{s.C}}}[{s.RATE}])"), s.PERCENT, sizing=True))


def test_title_claiming_a_window_the_panel_doesnt_fix_fails():
    with pytest.raises(AssertionError, match="window"):
        ext(ok("Restarts (1h)"))


def test_peak_is_allowed_in_a_table():
    ext(s.grid("T", "d", ("Peak", s.peak(s.per_pod(f"rate(up{{{s.C}}}[{s.RATE}])")), s.CORES, None)))


def test_hand_written_subquery_fails():
    with pytest.raises(AssertionError, match=re.escape("$__range")):
        ext(s.grid("T", "d", ("v", s.per_pod(f"max_over_time(rate(up{{{s.C}}}[1m])[{s.RANGE}:30s])"), s.CORES, None)))


# built-in sources
def test_source_naming_an_unknown_builtin_fails():
    with pytest.raises(AssertionError, match="Source"):
        ext(s.graph("G", "Shows x. Source: ACM Made Up Dashboard.", s.COUNT, (s.per_pod(f"up{{{s.C}}}"), "")))


def test_source_naming_a_snapshot_dashboard_passes():
    title = next(iter(s.builtins()))
    ext(s.graph("G", f"Shows x. Source: ACM {title}.", s.COUNT, (s.per_pod(f"up{{{s.C}}}"), "")))


def test_source_and_cluster_only_can_share_a_description():
    title = next(iter(s.builtins()))
    ext(s.graph("G", f"Shows x. Source: ACM {title}. {s.CLUSTER_ONLY}", s.COUNT, (f"up{{{s.C}}}", "")))
