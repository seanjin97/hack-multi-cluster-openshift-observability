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
    assert pos["L"]["x"] == pos["E"]["x"] == 0


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


def test_golden_signal_quadrants_wrap_to_at_most_four_graphs_a_line():
    j = render(c.golden_signals(*[[ok(f"{q}{i}") for i in range(3)] for q in "LTES"]))
    for line in lines_of(j).values():
        assert len(line) <= c.MAX_PER_LINE
        assert sum(p["gridPos"]["w"] for p in line) == c.WIDTH


def test_wrapped_quadrant_keeps_latency_left_and_traffic_right():
    j = render(c.golden_signals([ok("L0"), ok("L1"), ok("L2")], [ok("T0"), ok("T1"), ok("T2")], [ok("E")], [ok("S")]))
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
        render(c.golden_signals([ok("L0"), ok("L1"), ok("L2")], [ok("T")], [ok("E")], [ok("S")]))


def test_vitals_may_hold_six_tiles():
    j = render(c.vitals(*[c.tile(str(i), "d", c.per_pod(f"up{{{c.C}}}"), c.COUNT) for i in range(6)]))
    assert [len(l) for l in lines_of(j).values()] == [6]
