"""components/page.py: a team dashboard opens on its own scope."""
import pytest

import components as c
from helpers import ok, render


def test_team_dashboard_opens_on_its_namespace():
    v = {x["name"]: x for x in render(scope={"namespace": "shop"})["templating"]["list"]}
    assert v["namespace"]["current"]["value"] == ["shop"]
    assert v["cluster"]["current"]["value"] == "$__all"  # unscoped filters stay on All


def test_scope_on_an_unknown_filter_fails():
    with pytest.raises(AssertionError, match="filters"):
        c.dashboard("T", "d", [], c.vitals(ok()), scope={"team": "shop"})
