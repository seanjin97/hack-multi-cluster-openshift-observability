"""The page: dashboard settings, the five standard filters, and placing sections on the grid."""
from grafana_foundation_sdk.builders import dashboard as db
from grafana_foundation_sdk.models import dashboard as dm

from .layout import WIDTH
from .panels import DS
from .queries import _SEL, C, SCOPE

FILTERS = ("cluster", "node", "namespace", "workload", "pod")


def dashboard(title, description, tags, *sections, links=(), scope=None):
    """The page. build.py sets the uid from the file path. links: builtin(...) header links.
    scope: filters the page opens on, e.g. {"namespace": "shop"} for a team's dashboard; users can still widen them."""
    scope = scope or {}
    assert set(scope) <= set(FILTERS), f"scope keys must be filters {FILTERS}, got {sorted(scope)}"
    b = (db.Dashboard(title).description(description).tags(["golden-path", *tags])
         .time("now-1h", "now").refresh("1m").timezone("browser")
         .tooltip(dm.DashboardCursorSync.CROSSHAIR)
         .with_variable(db.DatasourceVariable("datasource").type("prometheus")
                        .current(dm.VariableOption(text="Observatorium", value="Observatorium"))
                        .hide(dm.VariableHide.HIDE_VARIABLE)))
    for link in links:
        b = b.link(link)
    # Filters, each narrowed by the ones before it
    for name, q, regex in [
        ("cluster", "label_values(kube_node_status_allocatable, cluster)", ""),
        ("node", f"label_values(kube_node_status_allocatable{{{C}}}, node)", ""),
        ("namespace", f'label_values(kube_pod_info{{{C}, node=~"$node"}}, namespace)', ""),
        ("workload", f"query_result({SCOPE.replace('$pod', '.*').replace('$workload', '.*')})", '/workload="([^"]+)"/'),
        ("pod", f"label_values(kube_pod_info{{{_SEL.replace('$pod', '.*')}}}, pod)", ""),
    ]:
        b = b.with_variable(_filter(name, q, regex, scope.get(name)))

    y = 0
    for title, collapsed, lines in sections:
        r = db.Row(title).collapsed(collapsed).grid_pos(dm.GridPos(h=1, w=WIDTH, x=0, y=y))
        y += 1
        placed = []
        for line in lines:
            x, h = 0, max(p.build().grid_pos.h for p, _ in line)
            for p, w in line:
                placed.append(p.grid_pos(dm.GridPos(h=h, w=w, x=x, y=y)))
                x += w
            y += h
        if collapsed:
            for p in placed:
                r = r.with_panel(p)
            b = b.with_row(r)
            y -= sum(max(p.build().grid_pos.h for p, _ in l) for l in lines)  # hidden until expanded
        else:
            b = b.with_row(r)
            for p in placed:
                b = b.with_panel(p)
    return b


def _filter(name, q, regex, default=None):
    current = dm.VariableOption(text=[default], value=[default], selected=True) if default else dm.VariableOption(text="All", value="$__all")
    v = (db.QueryVariable(name).label(name.capitalize()).datasource(DS)
         .query({"query": q, "refId": "StandardVariableQuery"})
         .refresh(dm.VariableRefresh.ON_TIME_RANGE_CHANGED).sort(dm.VariableSort.ALPHABETICAL_ASC)
         .multi(True).include_all(True).all_value(".*")
         .current(current))
    return v.regex(regex) if regex else v
