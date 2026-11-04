"""Layout: sections made of lines of (panel, width); every line fills WIDTH. page.dashboard() places them.
Every page opens with the same standard panels: vitals() and golden_signals() put them first, teams append theirs."""
from .panels import graph, header, tile
from .queries import APP, C, RATE, per_pod, ratio
from .units import ERRORS, LATENCY, PERCENT, REQPS, SECONDS, UTILISATION

WIDTH = 24  # Grafana's grid; every line of panels fills it
MAX_PER_LINE = 4  # graphs or tables per line; more and they get too narrow to read. Tiles are exempt.
MAX_TEAM_TILES = 6  # the team's tiles share the second vitals line; more and they get too narrow to read

# --- The standard panels: RED from the golden-path histogram (doc/app-teams/1-metrics.md), saturation from the pod ---
# Blank, not zero, when the app doesn't emit the histogram: no data is a finding, not a healthy 0.
_REQS = per_pod(f"rate(http_request_duration_seconds_count{{{C}, {APP}}}[{RATE}])")
_ERRS = per_pod(f'rate(http_request_duration_seconds_count{{{C}, {APP}, status=~"5.."}}[{RATE}])')
_LAT = per_pod(f"rate(http_request_duration_seconds_bucket{{{C}, {APP}}}[{RATE}])")
_MEM = per_pod(f'container_memory_working_set_bytes{{{C}, container!="", container!="POD"}}')
_MEM_LIMIT = per_pod(f'kube_pod_container_resource_limits{{{C}, resource="memory"}}')
_NO_RED = "Empty: the app doesn't emit http_request_duration_seconds yet; see doc/app-teams/1-metrics.md."


def _p95(by):
    return f"histogram_quantile(0.95, sum by ({by}, le) ({_LAT}))"


def _mem_vs_limit(by):
    return ratio(f"sum by ({by}) ({_MEM})", f"sum by ({by}) ({_MEM_LIMIT})")


def standard_vitals():
    """The tiles every System Vitals row opens with: Rate, Errors, Duration, Saturation."""
    return [
        tile("Requests/s", f"Requests per second across the selection. Drops to zero: the app stopped serving. {_NO_RED}",
             f"sum({_REQS})", REQPS),
        tile("5xx rate", f"Share of requests answered 5xx. Above 1%: open Errors. {_NO_RED}",
             ratio(f"sum({_ERRS}) or vector(0)", f"sum({_REQS})"), PERCENT, ERRORS),
        tile("p95 latency", f"95th percentile request duration. Above 300ms: open Latency. {_NO_RED}",
             _p95("cluster"), SECONDS, LATENCY),
        tile("Peak memory / limit", "The fullest container's memory as a share of its limit. Near 100%: it gets OOM-killed. "
             "Empty: no memory limit set.", f"max({_mem_vs_limit('cluster, namespace, pod, container')})", PERCENT, UTILISATION),
    ]


def standard_signals():
    """The graph every Golden Signals quadrant opens with."""
    by = "cluster, workload"
    return {
        "latency": graph("p95 by workload", f"Request latency per workload. Above 300ms: find the endpoint in an extension. {_NO_RED}",
                         SECONDS, (_p95(by), "{{cluster}} {{workload}}"), thresholds=LATENCY),
        "traffic": graph("Requests/s by workload", f"Load per workload. {_NO_RED}", REQPS,
                         (f"sum by ({by}) ({_REQS})", "{{cluster}} {{workload}}")),
        "errors": graph("5xx ratio by workload", f"Share of requests answered 5xx. Above 1%: check the workload's logs. {_NO_RED}",
                        PERCENT, (ratio(f"sum by ({by}) ({_ERRS})", f"sum by ({by}) ({_REQS})"), "{{cluster}} {{workload}}"),
                        thresholds=ERRORS),
        "saturation": graph("Memory used / limit by workload", "Working-set memory against the limit. Near 100%: raise the limit "
                            "or find the leak. Empty: no memory limit set.", PERCENT,
                            (_mem_vs_limit(by), "{{cluster}} {{workload}}"), thresholds=UTILISATION),
    }


STANDARD_TITLES = {p.build().title for p in [*standard_vitals(), *standard_signals().values()]}


def even(n, total=WIDTH):
    """Widths for n panels sharing `total` columns, remainder to the first ones."""
    return [total // n + (i < total % n) for i in range(n)]


def wrap(panels, per_line, total=WIDTH):
    """Panels split into lines of at most per_line, each line sharing `total` columns evenly."""
    chunks = [panels[i:i + per_line] for i in range(0, len(panels), per_line)]
    return [list(zip(c, even(len(c), total))) for c in chunks]


def vitals(*tiles):
    """System Vitals: the open first row. Line 1: the standard RED + saturation tiles. Line 2: up to MAX_TEAM_TILES
    of the team's own (platform metrics or the golden-path histogram; team metrics go in an extension)."""
    assert len(tiles) <= MAX_TEAM_TILES, f"at most {MAX_TEAM_TILES} team tiles, got {len(tiles)}"
    std = standard_vitals()
    return "System Vitals", False, [list(zip(std, even(len(std)))), *([list(zip(tiles, even(len(tiles))))] if tiles else [])]


def golden_signals(latency=(), traffic=(), errors=(), saturation=()):
    """Golden Signals: Latency | Traffic, then Errors | Saturation. Each quadrant opens with its standard graph;
    the lists add the team's (platform metrics or the golden-path histogram only, never team metrics)."""
    half = WIDTH // 2
    std = standard_signals()
    latency, traffic = [std["latency"], *latency], [std["traffic"], *traffic]
    errors, saturation = [std["errors"], *errors], [std["saturation"], *saturation]

    def pair(left, right, left_panels, right_panels):
        l, r = wrap(left_panels, MAX_PER_LINE // 2, half), wrap(right_panels, MAX_PER_LINE // 2, half)
        assert len(l) == len(r), (f"{left[0]} and {right[0]} sit side by side, so they must wrap to the same number of lines: "
                                  f"give them panel counts that wrap alike ({MAX_PER_LINE // 2} per line each)")
        return [[(header(*left), half), (header(*right), half)], *[a + b for a, b in zip(l, r)]]

    return "Golden Signals", False, [
        *pair(("Latency", "How long requests take"), ("Traffic", "How much demand"), latency, traffic),
        *pair(("Errors", "How often requests fail"), ("Saturation", "How full the system is"), errors, saturation),
    ]


def extension(title, *lines):
    """A collapsed row for one extra question. Each line is a panel or a tuple of panels, sharing the width evenly.
    A tuple longer than MAX_PER_LINE wraps onto more lines."""
    lines = [l if isinstance(l, tuple) else (l,) for l in lines]
    return title, True, [w for l in lines for w in wrap(list(l), MAX_PER_LINE)]
