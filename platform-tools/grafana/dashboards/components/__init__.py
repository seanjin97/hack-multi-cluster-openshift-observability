"""STARFORGE dashboard component library: the design language as code (ADR 0005).
Team dashboards build from these components only:  from components import *
Components build; tests/test_conformance.py judges whether a dashboard follows the golden path.

Page structure, always full width. vitals() and golden_signals() always open with the standard RED +
saturation panels (blank when the app doesn't emit the golden-path histogram); teams add to them, never replace them.
  System Vitals    standard tiles, then the team's: is anything wrong right now?    vitals()
  Golden Signals   Latency | Traffic, then Errors | Saturation, standard graph first golden_signals()
  Extensions       collapsed rows, one per extra question; team metrics live here   extension()
"""
from .layout import MAX_PER_LINE, MAX_TEAM_TILES, STANDARD_TITLES, WIDTH, extension, golden_signals, vitals
from .links import SELF, builtin, builtins, drill
from .page import FILTERS, dashboard
from .panels import graph, grid, query, tile
from .queries import (APP, C, CLUSTER_ONLY, NODE_GROUPS, PEAK, RANGE, RATE, SCOPE, SIZING, STEP,
                      by_node_group, peak, per_node, per_pod, ratio)
from .units import (BPS, BYTES, CORES, COUNT, ERRORS, LATENCY, NEUTRAL, PERCENT, PPS, PROBLEMS, PROVISIONING,
                    REQPS, SECONDS, THROTTLING, UTILISATION)

__all__ = [
    # page and layout
    "dashboard", "vitals", "golden_signals", "extension", "FILTERS", "WIDTH", "MAX_PER_LINE", "MAX_TEAM_TILES", "STANDARD_TITLES",
    # panels
    "tile", "graph", "grid", "query",
    # queries: filters, slicing, granularity
    "C", "APP", "CLUSTER_ONLY", "SCOPE", "per_pod", "per_node", "NODE_GROUPS", "by_node_group", "ratio",
    "peak", "STEP", "RATE", "RANGE", "SIZING", "PEAK",
    # links
    "builtin", "builtins", "drill", "SELF",
    # units and colours
    "PERCENT", "CORES", "BYTES", "BPS", "PPS", "SECONDS", "REQPS", "COUNT",
    "NEUTRAL", "UTILISATION", "PROVISIONING", "ERRORS", "THROTTLING", "LATENCY", "PROBLEMS",
]
