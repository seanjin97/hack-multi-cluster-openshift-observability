"""Links: header links to built-in ACM dashboards, and drill-downs that refilter this dashboard."""
import pathlib

from grafana_foundation_sdk.builders import dashboard as db
from grafana_foundation_sdk.models import dashboard as dm

# Built-in ACM dashboards: the committed snapshot, no hub needed
BUILTIN_SNAPSHOT = pathlib.Path(__file__).parent.parent / "acm-builtin.md"
SELF = "__self__"  # replaced by the dashboard's own uid at build time


def builtins(markdown=None):
    """{title: (uid, data here)} from acm-builtin.md. The first uid in a row is the preferred copy."""
    rows = {}
    for line in (markdown if markdown is not None else BUILTIN_SNAPSHOT.read_text()).splitlines():
        cells = [c.strip() for c in line.strip().strip("|").split("|")]
        if len(cells) >= 6 and cells[1].startswith("`"):
            rows[cells[0]] = (cells[1].split("`")[1], cells[5])
    return rows


def builtin(title, catalog=None):
    """Header link to a built-in ACM dashboard, keeping the time range and filters."""
    catalog = builtins() if catalog is None else catalog
    assert title in catalog, f"{title!r} isn't in acm-builtin.md; re-run acm_builtin.py, don't guess uids"
    uid, data = catalog[title]
    assert data != "none", f"{title!r} has no data on this hub (acm-builtin.md); rebuild the panel instead"
    return (db.DashboardLink(title).type(dm.DashboardLinkType.LINK).url(f"/d/{uid}")
            .keep_time(True).include_vars(True).target_blank(True).tooltip("ACM built-in dashboard"))


def drill(*labels, **renamed):
    """Link that reopens this dashboard filtered to the clicked table row, keeping the time range.
    labels: filters named like their column ("cluster", "namespace"). renamed: filter=column, e.g. node="instance"."""
    pairs = [(l, l) for l in labels] + list(renamed.items())
    return f"/d/{SELF}?" + "&".join(f"var-{f}=${{__data.fields.{c}}}" for f, c in pairs) + "&${__url_time_range}"
