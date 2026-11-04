"""components/layout.py and page placement: every line fills the page, quadrants keep their sides."""
from collections import defaultdict

import pytest

import components as c
from components.layout import even
from helpers import ok, panels, render


def lines_of(j):
    """{y: [panels]} for every non-header panel."""
    out = defaultdict(list)
    for p in panels(j):
        out[p["gridPos"]["y"]].append(p)
    return out


@pytest.mark.parametrize("n", range(1, 9))
def test_even_widths_fill_the_line(n):
    w = even(n)
    assert sum(w) == c.WIDTH and max(w) - min(w) <= 1


def test_golden_signals_put_latency_left_of_traffic_and_errors_above_saturation():
    j = render(c.golden_signals([ok("L")], [ok("T")], [ok("E")], [ok("S")]))
    pos = {p["title"]: p["gridPos"] for p in panels(j)}
    assert pos["L"]["y"] == pos["T"]["y"] and pos["L"]["x"] < pos["T"]["x"]
    assert pos["E"]["y"] == pos["S"]["y"] > pos["L"]["y"]
    assert pos["L"]["x"] == pos["E"]["x"] < c.WIDTH // 2


def test_golden_signals_open_each_quadrant_with_its_standard_graph():
    j = render(c.golden_signals([ok("L")]))
    pos = {p["title"]: p["gridPos"] for top in j["panels"] for p in [top, *top.get("panels", [])] if p["type"] not in ("row", "text")}
    assert pos["p95 by workload"]["x"] == 0 and pos["p95 by workload"]["x"] < pos["L"]["x"]


def test_open_section_panels_appear_once():
    j = render(c.vitals(ok("a"), ok("b")))
    assert [p["title"] for p in panels(j)] == ["a", "b"]


def test_sections_stack_and_extensions_start_collapsed():
    j = render(c.vitals(ok("a"), ok("b")), c.extension("Why?", ok("c")))
    rows = [p for p in j["panels"] if p["type"] == "row"]
    assert [r["collapsed"] for r in rows] == [False, False, True]
    assert rows[1]["gridPos"]["y"] > rows[0]["gridPos"]["y"]


def test_tuple_line_shares_the_width():
    j = render(c.extension("Why?", (ok("a"), ok("b"), ok("c"))))
    assert [p["gridPos"]["w"] for p in panels(j)] == even(3)


def all_lines_of(j):
    """{y: [panels]} for every graph, standard panels included."""
    out = defaultdict(list)
    for top in j["panels"]:
        for p in [top, *top.get("panels", [])]:
            if p["type"] not in ("row", "text"):
                out[p["gridPos"]["y"]].append(p)
    return out


def test_golden_signal_quadrants_wrap_to_at_most_four_graphs_a_line():
    j = render(c.golden_signals(*[[ok(f"{q}{i}") for i in range(3)] for q in "LTES"]))
    for line in all_lines_of(j).values():
        assert len(line) <= c.MAX_PER_LINE
        assert sum(p["gridPos"]["w"] for p in line) == c.WIDTH


def test_wrapped_quadrant_keeps_latency_left_and_traffic_right():
    j = render(c.golden_signals([ok("L0"), ok("L1"), ok("L2")], [ok("T0"), ok("T1"), ok("T2")], [ok("E")], [ok("S")]))
    # standard graph + 3 each side: wraps to 2 lines per side
    for p in panels(j):
        if p["title"][0] in "LE":
            assert p["gridPos"]["x"] + p["gridPos"]["w"] <= c.WIDTH // 2, p["title"]
        if p["title"][0] in "TS":
            assert p["gridPos"]["x"] >= c.WIDTH // 2, p["title"]


def test_extension_line_wraps_after_four_panels():
    j = render(c.extension("Why?", tuple(ok(str(i)) for i in range(6))))
    sizes = sorted(len(l) for l in lines_of(j).values())
    assert max(sizes) <= c.MAX_PER_LINE and sum(sizes) == 6


def test_quadrants_side_by_side_must_wrap_to_the_same_lines():
    with pytest.raises(AssertionError, match="same number of lines"):
        render(c.golden_signals([ok("L0"), ok("L1")], [], [], []))


def test_vitals_put_team_tiles_on_their_own_line_after_the_standard_ones():
    j = render(c.vitals(*[c.tile(str(i), "d", c.per_pod(f"up{{{c.C}}}"), c.COUNT) for i in range(6)]))
    vit = [p for p in j["panels"] if p["type"] == "stat"]
    lines = defaultdict(list)
    for p in vit:
        lines[p["gridPos"]["y"]].append(p["title"])
    std, team = sorted(lines.items())
    assert set(std[1]) <= c.STANDARD_TITLES and team[1] == [str(i) for i in range(6)]


def test_vitals_with_too_many_team_tiles_fails():
    with pytest.raises(AssertionError, match="team tiles"):
        c.vitals(*[c.tile(str(i), "d", c.per_pod(f"up{{{c.C}}}"), c.COUNT) for i in range(c.MAX_TEAM_TILES + 1)])
