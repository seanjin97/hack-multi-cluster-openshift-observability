"""Panels: tile (one number), graph (time series), grid (table). Each comes described, unitised and on the
dashboard's step; layout places them."""
from grafana_foundation_sdk.builders import common as cb
from grafana_foundation_sdk.builders import prometheus, stat, table, text, timeseries
from grafana_foundation_sdk.models import common as cm
from grafana_foundation_sdk.models import dashboard as dm
from grafana_foundation_sdk.models import prometheus as pm
from grafana_foundation_sdk.models import text as tm

from .queries import SIZING, STEP
from .units import NEUTRAL

# Datasource: ACM's Observatorium (Thanos behind rbac-query-proxy), picked through a hidden variable like ACM's own dashboards.
DS = cm.DataSourceRef(type_val="prometheus", uid="${datasource}")


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


def header(title, subtitle):
    """Quadrant heading: one markdown line, no panel title (a titled 2-row text panel clips its own text)."""
    return (text.Panel().content(f"#### {title} <small>· {subtitle}</small>").mode(tm.TextMode.MARKDOWN)
            .transparent(True).height(2))
