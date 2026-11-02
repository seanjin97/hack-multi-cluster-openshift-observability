"""build.py: team folders map to uids, folders and ConfigMaps; output follows the sources
(CI then asserts the build changed nothing)."""
import pathlib

import pytest

import build
import components as c
from helpers import ok, render


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


def test_library_and_tests_are_not_team_dashboards():
    assert {p.parent.name for p in build.sources()}.isdisjoint(build.NOT_TEAMS)


def test_team_is_tagged_for_search():
    assert "team" in render(c.vitals(ok()))["tags"]


def test_panel_ids_are_unique():
    j = render(c.vitals(ok("a"), ok("b")), c.extension("Why?", ok("c"), (ok("d"), ok("e"))))
    ids = [p["id"] for top in j["panels"] for p in [top, *top.get("panels", [])]]
    assert len(ids) == len(set(ids))


def team_dir(tmp_path, monkeypatch):
    """A throwaway dashboards root with one team dashboard, and build.py pointed at it."""
    (tmp_path / "team").mkdir()
    (tmp_path / "team" / "board.py").write_text(
        "from components import *\n"
        f"dashboard = dashboard('B', 'd', [], vitals(tile('T', 'd', per_pod('up{{{c.C}}}'), COUNT)))\n")
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
