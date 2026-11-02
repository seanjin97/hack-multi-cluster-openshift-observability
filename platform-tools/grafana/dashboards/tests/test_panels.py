"""components/panels.py: what tile, graph and grid build."""
import pytest

import components as c
from helpers import ext, panels, table


@pytest.mark.parametrize("panel", [
    lambda: c.tile("Used / requested", "d", c.per_pod(f"rate(up{{{c.C}}}[{c.RANGE}])"), c.PERCENT, sizing=True),
    lambda: table(c.RANGE, sizing=True),
])
def test_sizing_panel_ignores_the_time_picker_and_says_so(panel):
    p = panels(ext(panel()))[0]
    assert p.get("timeFrom") and p["title"].endswith(f"({p['timeFrom']})")
