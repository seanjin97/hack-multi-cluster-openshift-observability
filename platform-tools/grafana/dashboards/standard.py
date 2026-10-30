"""STARFORGE dashboard standard: the design language as code (ADR 0004).

Every dashboard builds its panels from these helpers. To change a rule, change
it here and regenerate every dashboard; don't override it in one dashboard.

Page structure, always full width:
  System Vitals    one line of tiles: is anything wrong right now?
  Golden Signals   Latency | Traffic, then Errors | Saturation
  Extensions       collapsed rows, one per extra question
"""
import json
import pathlib
import re
from collections import defaultdict

from grafana_foundation_sdk.builders import common as cb
from grafana_foundation_sdk.builders import dashboard as db
from grafana_foundation_sdk.builders import prometheus, stat, table, text, timeseries
from grafana_foundation_sdk.cog.encoder import JSONEncoder
from grafana_foundation_sdk.models import common as cm
from grafana_foundation_sdk.models import dashboard as dm
from grafana_foundation_sdk.models import prometheus as pm
from grafana_foundation_sdk.models import text as tm

WIDTH = 24  # Grafana's grid; every line of panels fills it
MAX_PER_LINE = 4  # graphs or tables per line; more and they get too narrow to read. Tiles are exempt.

# Datasource: ACM's Observatorium (Thanos behind rbac-query-proxy), picked through a hidden variable like ACM's own dashboards.
DS = cm.DataSourceRef(type_val="prometheus", uid="${datasource}")

# --- Filters: every panel slices on cluster, node, namespace, workload and pod ---
C = 'cluster=~"$cluster"'
APP = 'job="open-cluster-management-addon-observability/app-metrics"'  # golden-path app metrics, ADR 0003
CLUSTER_ONLY = "Cluster filter only."  # end a description with this when the metric has no node/pod labels

# Workload = the pod's owner, with a Deployment's ReplicaSet hash dropped. Built from kube_pod_info
# so it works on every cluster (ACM's workload recording rule is missing on the hub).
# ponytail: selecting workload "my" also matches a StatefulSet/DaemonSet "my-x" (one extra name segment);
# exact matching needs the owner kind in the filter.
_SEL = f'{C}, namespace=~"$namespace", node=~"$node", pod=~"$pod", created_by_name=~"(?:$workload)(?:-[a-z0-9]+)?"'
SCOPE = (
    'max by (cluster, namespace, pod, node, workload) ('
    f'label_replace(kube_pod_info{{{_SEL}, created_by_kind="ReplicaSet"}}, "workload", "$1", "created_by_name", "(.+)-[a-z0-9]+")'
    f' or label_replace(kube_pod_info{{{_SEL}, created_by_kind!="ReplicaSet"}}, "workload", "$1", "created_by_name", "(.*)"))'
)


def per_pod(expr):
    """Keeps the series of pods in the selected filters, and adds workload and node labels."""
    return f"({expr}) * on (cluster, namespace, pod) group_left (workload, node) {SCOPE}"


def per_node(expr, label="instance"):
    """Keeps node series of nodes running pods in the selected filters. label holds the node name:
    instance for node-exporter, node for kube-state-metrics."""
    nodes = f"max by (cluster, node) ({SCOPE})"
    if label != "node":
        nodes = f'label_replace({nodes}, "{label}", "$1", "node", "(.*)")'
    return f"({expr}) and on (cluster, {label}) {nodes}"


# Node groups by node name. Later entries win, so keep the patterns disjoint.
# ponytail: the k3d patterns (-agent-, -server-) are for the demo spokes; remove them on a real fleet.
NODE_GROUPS = {
    "worker": "w-.*|.*-agent-.*",
    "infra": "i-.*",
    "control-plane": "m-.*|cp-.*|.*-server-.*",
}


def by_node_group(expr, node_label="instance"):
    """Adds a node_group label to expr, worked out from the node name in node_label."""
    e = f'label_replace({expr}, "node_group", "other", "{node_label}", ".*")'
    for group, regex in NODE_GROUPS.items():
        e = f'label_replace({e}, "node_group", "{group}", "{node_label}", "{regex}")'
    return e


def ratio(num, den):
    return f"({num}) / ({den})"


# --- Granularity ---
STEP = "1m"            # graphs: one point per minute at the 1h default; spokes push every 30s, so 2 samples per point
RATE = "$__rate_interval"  # graph and tile rate windows: widen with the step when you zoom out
RANGE = "$__range"     # tables and sizing panels: summarise the whole selected (or fixed) window
SIZING = "7d"          # sizing panels ignore the time picker: an hour of data gives the wrong size
_WINDOW = re.compile(r"\[([^\]]+)\]")
_TITLE_WINDOW = re.compile(r"\((\d+[smhdw])\)$")


PEAK = f"[{RANGE}:{STEP}]"  # the one subquery window allowed: peak() at the dashboard's step


def peak(expr):
    """Highest value of expr over the selected range, sampled at STEP. For table columns like "Peak CPU".
    expr should use [RATE] windows, as in a graph."""
    return f"max_over_time(({expr}){PEAK})"


# --- Built-in ACM dashboards: the committed snapshot, no hub needed ---
BUILTIN_SNAPSHOT = pathlib.Path(__file__).with_name("acm-builtin.md")


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


# --- Units ---
PERCENT, CORES, BYTES, BPS, PPS, SECONDS, REQPS, COUNT = (
    "percentunit", "suffix: cores", "bytes", "Bps", "pps", "s", "reqps", "short")


# --- Colours: pick a threshold set, never a colour ---
def _steps(*steps):
    return db.ThresholdsConfig().mode(dm.ThresholdsMode.ABSOLUTE).steps(
        [dm.Threshold(value=v, color=c) for v, c in steps])


NEUTRAL = _steps((None, "text"))
UTILISATION = _steps((None, "green"), (0.7, "orange"), (0.85, "red"))       # share of capacity
PROVISIONING = _steps((None, "blue"), (0.3, "green"), (1.0, "red"))         # used / requested: blue = waste, red = bursting past request
ERRORS = _steps((None, "green"), (0.01, "orange"), (0.05, "red"))           # error or retransmit ratio
THROTTLING = _steps((None, "green"), (0.1, "orange"), (0.25, "red"))        # share of CFS periods throttled
LATENCY = _steps((None, "green"), (0.3, "orange"), (1, "red"))              # seconds
PROBLEMS = _steps((None, "green"), (1, "red"))                              # anything above 0 needs a look


# --- Panels ---
def query(expr, legend="", ref="A"):
    return prometheus.Dataquery().expr(expr).legend_format(legend).ref_id(ref).datasource(DS)


def _sized(p, title, sizing):
    """Sizing panels look at SIZING whatever the time picker says, and say so in the title."""
    return p.title(f"{title} ({SIZING})").time_from(SIZING) if sizing else p.title(title)


def tile(title, description, expr, unit, thresholds=NEUTRAL, sizing=False):
    """Stat tile: one number for the whole selection, with a sparkline. sizing=True: over SIZING, use RANGE."""
    p = (stat.Panel().description(description).datasource(DS).unit(unit).interval(STEP)
         .thresholds(thresholds).color_mode(cm.BigValueColorMode.BACKGROUND)
         .graph_mode(cm.BigValueGraphMode.NONE if sizing else cm.BigValueGraphMode.AREA)
         .reduce_options(cb.ReduceDataOptions().calcs(["lastNotNull"]))
         .height(4).with_target(query(expr).instant() if sizing else query(expr)))
    return _sized(p, title, sizing)


def graph(title, description, unit, *targets, thresholds=None):
    """Time series. targets: (expr, legend) pairs. Always keep the cluster in the legend."""
    p = (timeseries.Panel().title(title).description(description).datasource(DS).unit(unit)
         .interval(STEP).min(0).fill_opacity(10).height(8)
         .legend(cb.VizLegendOptions().display_mode(cm.LegendDisplayMode.LIST)
                 .placement(cm.LegendPlacement.BOTTOM).show_legend(True)))
    for i, (expr, legend) in enumerate(targets):
        p = p.with_target(query(expr, legend, chr(ord("A") + i)))
    if thresholds:
        p = p.thresholds(thresholds).thresholds_style(
            cb.GraphThresholdsStyleConfig().mode(cm.GraphThresholdsStyleMode.DASHED))
    return p


def grid(title, description, *columns, sort=None, links=None, height=10, sizing=False):
    """Table built from instant queries joined on their labels, each summarising the selected range (RANGE).
    columns: (header, expr, unit, thresholds or None). Labels come from each query's `by (...)`.
    links: {column: url} turns a label column into a link, e.g. drill() to filter this dashboard.
    sizing=True: summarise SIZING instead of the time picker's range."""
    p = _sized(table.Panel().description(description).datasource(DS).height(height), title, sizing)
    rename = {}
    for i, (name, expr, unit, thresholds) in enumerate(columns):
        ref = chr(ord("A") + i)
        p = p.with_target(query(expr, ref=ref).format(pm.PromQueryFormat.TABLE).instant())
        rename["Value" if len(columns) == 1 else f"Value #{ref}"] = name
        props = [dm.DynamicConfigValue(id_val="unit", value=unit)]
        if thresholds:
            props += [dm.DynamicConfigValue(id_val="thresholds", value=thresholds.build()),
                      dm.DynamicConfigValue(id_val="custom.cellOptions", value={"type": "color-background"})]
        p = p.override_by_name(name, props)
    for column, url in (links or {}).items():
        p = p.override_by_name(column, [dm.DynamicConfigValue(id_val="links", value=[{"title": "Filter to this", "url": url}])])
    p = (p.with_transformation(dm.DataTransformerConfig(id_val="merge", options={}))
         .with_transformation(dm.DataTransformerConfig(id_val="organize", options={
             "excludeByName": {"Time": True}, "renameByName": rename})))
    if sort:
        p = p.sort_by([cb.TableSortByFieldState().display_name(sort).desc(True)])
    return p


SELF = "__self__"  # replaced by the dashboard's own uid at build time


def drill(*labels, **renamed):
    """Link that reopens this dashboard filtered to the clicked table row, keeping the time range.
    labels: filters named like their column ("cluster", "namespace"). renamed: filter=column, e.g. node="instance"."""
    pairs = [(l, l) for l in labels] + list(renamed.items())
    return f"/d/{SELF}?" + "&".join(f"var-{f}=${{__data.fields.{c}}}" for f, c in pairs) + "&${__url_time_range}"


def _header(title, subtitle):
    return (text.Panel().title(title).content(subtitle).mode(tm.TextMode.MARKDOWN)
            .transparent(True).height(2))


# --- Layout: sections made of lines; every line fills WIDTH ---
def _even(n, total=WIDTH):
    """Widths for n panels sharing `total` columns, remainder to the first ones."""
    return [total // n + (i < total % n) for i in range(n)]


def _wrap(panels, per_line, total=WIDTH):
    """Panels split into lines of at most per_line, each line sharing `total` columns evenly."""
    chunks = [panels[i:i + per_line] for i in range(0, len(panels), per_line)]
    return [list(zip(c, _even(len(c), total))) for c in chunks]


def vitals(*tiles):
    """System Vitals: the open first row, one line of tiles."""
    return "System Vitals", False, [list(zip(tiles, _even(len(tiles))))]


def golden_signals(latency, traffic, errors, saturation):
    """Golden Signals: Latency | Traffic, then Errors | Saturation. Each quadrant is a list of panels."""
    half = WIDTH // 2

    def pair(left, right, left_panels, right_panels):
        l, r = _wrap(left_panels, MAX_PER_LINE // 2, half), _wrap(right_panels, MAX_PER_LINE // 2, half)
        assert len(l) == len(r), (f"{left[0]} and {right[0]} sit side by side, so they must wrap to the same number of lines: "
                                  f"give them panel counts that wrap alike ({MAX_PER_LINE // 2} per line each)")
        return [[(_header(*left), half), (_header(*right), half)], *[a + b for a, b in zip(l, r)]]

    return "Golden Signals", False, [
        *pair(("Latency", "How long requests take"), ("Traffic", "How much demand"), latency, traffic),
        *pair(("Errors", "How often requests fail"), ("Saturation", "How full the system is"), errors, saturation),
    ]


def extension(title, *lines):
    """A collapsed row for one extra question. Each line is a panel or a tuple of panels, sharing the width evenly.
    A tuple longer than MAX_PER_LINE wraps onto more lines."""
    lines = [l if isinstance(l, tuple) else (l,) for l in lines]
    return title, True, [w for l in lines for w in _wrap(list(l), MAX_PER_LINE)]


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


# --- Build ---
def render(builder, uid, team):
    """Dashboard JSON for builder: uid and team tag set, panel ids numbered, links to SELF resolved, house rules checked."""
    assert len(uid) <= 40, f"Grafana uids are at most 40 characters: {uid}"
    j = json.loads(JSONEncoder().encode(builder.uid(uid).build()))
    j["tags"].append(team)
    sections = []
    for top in j["panels"]:
        if top["type"] == "row":
            sections.append(list(top.get("panels", [])))  # a copy: open rows must not nest their panels
        else:
            sections[-1].append(top)
    for i, p in enumerate([*j["panels"], *[c for s in sections for c in s if c not in j["panels"]]], 1):
        p["id"] = i
    check(j, sections)
    return json.loads(json.dumps(j).replace(f"/d/{SELF}?", f"/d/{uid}?"))


def check(j, sections):
    """Rules the SDK's types can't enforce. They fail the build, not the review."""
    assert j.get("uid") and j.get("title") and j.get("description"), "uid, title and description are required"
    assert "golden-path" in j.get("tags", []), "tag golden-path"
    names = [v["name"] for v in j["templating"]["list"]]
    assert tuple(names[1:]) == FILTERS, f"standard filters only, got {names}"
    for panels in sections:
        lines = defaultdict(int)
        for p in panels:
            lines[p["gridPos"]["y"]] += p["gridPos"]["w"]
        assert all(w == WIDTH for w in lines.values()), f"every line fills the page width: {dict(lines)}"
        crowded = defaultdict(int)
        for p in panels:
            if p["type"] not in ("stat", "text"):
                crowded[p["gridPos"]["y"]] += 1
        assert all(n <= MAX_PER_LINE for n in crowded.values()), f"at most {MAX_PER_LINE} graphs or tables per line: {dict(crowded)}"
        for p in panels:
            if p["type"] == "text":
                continue
            t, desc = p.get("title"), p.get("description", "")
            assert desc, f"{t}: say what question the panel answers and what to do when it's red"
            assert p["type"] == "table" or p.get("fieldConfig", {}).get("defaults", {}).get("unit"), f"{t}: set a unit"
            sizing = bool(p.get("timeFrom"))
            claimed = _TITLE_WINDOW.search(t or "")
            assert not claimed or claimed.group(1) == p.get("timeFrom"), \
                f"{t}: the title names a window the panel doesn't fix; use sizing=True or drop it from the title"
            if p["type"] != "table" and not sizing:
                assert p.get("interval") == STEP, f"{t}: graphs and tiles step at {STEP} (finer is noise, coarser hides spikes)"
            src = re.search(r"Source: ACM ([^.]+)\.", desc)
            assert not src or src.group(1) in builtins(), f"{t}: Source names {src and src.group(1)!r}, not in acm-builtin.md"
            for target in p.get("targets", []):
                e = target["expr"]
                want = RANGE if p["type"] == "table" or sizing else RATE
                windows = _WINDOW.findall(re.sub(r'"[^"]*"', '""', e))
                windows = [w for w in windows if not (w == PEAK[1:-1] and want == RANGE)]
                if want == RANGE and PEAK in e:  # peak() wraps a graph-style expression
                    windows = [w for w in windows if w != RATE]
                assert all(w == want for w in windows), \
                    f"{t}: windows must be {want} ({'summarise the range' if want == RANGE else 'widen on zoom'}), got {windows}"
                assert "$cluster" in e, f"{t}: every query filters on $cluster"
                assert "$pod" in e or "$node" in e or desc.endswith(CLUSTER_ONLY), \
                    f"{t}: slice on the filters with per_pod()/per_node(), or end the description with {CLUSTER_ONLY!r}"
