"""sensor-team-1, system A (podinfo frontend -> backend in spoke-1-demo): is our CPU limit slowing our requests?
Built by ../build.py."""
from components import *  # noqa: F403  the component library: panels, layout, queries, units, thresholds

# Per container (per_pod keeps the selected pods and adds workload and node)
REAL = 'container!="", container!="POD"'
USED = lambda w=RATE: per_pod(f"rate(container_cpu_usage_seconds_total{{{C}, {REAL}}}[{w}])")  # noqa: E731
REQ = per_pod(f'kube_pod_container_resource_requests{{{C}, resource="cpu"}}')
LIMIT = per_pod(f'kube_pod_container_resource_limits{{{C}, resource="cpu"}}')
THROTTLED = lambda w=RATE: per_pod(f"rate(container_cpu_cfs_throttled_periods_total{{{C}, {REAL}}}[{w}])")  # noqa: E731
PERIODS = lambda w=RATE: per_pod(f"rate(container_cpu_cfs_periods_total{{{C}, {REAL}}}[{w}])")  # noqa: E731
# Golden-path app metrics (doc/app-teams/1-metrics.md)
REQS = lambda w=RATE: per_pod(f"rate(http_request_duration_seconds_count{{{C}, {APP}}}[{w}])")  # noqa: E731
LAT = lambda w=RATE: per_pod(f"rate(http_request_duration_seconds_bucket{{{C}, {APP}}}[{w}])")  # noqa: E731


def throttling(by, w=RATE):
    return ratio(f"sum by ({by}) ({THROTTLED(w)})", f"sum by ({by}) ({PERIODS(w)})")


def p95(by, w=RATE):
    return f"histogram_quantile(0.95, sum by ({by}, le) ({LAT(w)}))"


dashboard = dashboard(
    "Sensor Team 1 - System A CPU limits",
    "Is our CPU limit slowing our requests? Throttling next to latency, per workload and pod. "
    "Opens on spoke-1-demo; widen the filters to compare.",
    ["system-a", "cpu"],

    vitals(
        tile("Throttled CPU periods", "Share of CPU periods where a container hit its CPU limit. Above 10%: open Saturation.",
             throttling("cluster"), PERCENT, THROTTLING),
        tile("Peak CPU / limit", "The busiest container's CPU as a share of its limit. Near 100%: the kernel throttles it.",
             f"max({ratio(f'sum by (cluster, namespace, pod, container) ({USED()})', f'sum by (cluster, namespace, pod, container) ({LIMIT})')})",
             PERCENT, UTILISATION),
    ),

    golden_signals(
        latency=[
            graph("p95 by endpoint", "Which endpoints slow down when throttled.", SECONDS,
                  (p95("cluster, workload, method, path"), "{{cluster}} {{workload}} {{method}} {{path}}"), thresholds=LATENCY),
        ],
        traffic=[
            graph("CPU per request", "CPU seconds spent per request. A step up after a deploy: the release got less efficient, "
                  "not the limit.", SECONDS,
                  (ratio(f"sum by (cluster, workload) ({USED()})", f"sum by (cluster, workload) ({REQS()})"), "{{cluster}} {{workload}}")),
        ],
        errors=[
            graph("Restarts by pod", "Container restarts per step. CPU limits don't kill pods; restarts point at memory or crashes instead.", COUNT,
                  (f"sum by (cluster, pod) ({per_pod(f'increase(kube_pod_container_status_restarts_total{{{C}}}[{RATE}])')}) > 0", "{{cluster}} {{pod}}")),
        ],
        saturation=[
            graph("CPU throttling by pod", "Share of CPU periods each pod was throttled. Sustained above 10%: raise the limit or remove it. "
                  "Source: ACM Kubernetes / Compute Resources / Pod.", PERCENT,
                  (throttling("cluster, pod"), "{{cluster}} {{pod}}"), thresholds=THROTTLING),
        ],
    ),

    extension("Is CPU use close to the request and limit?",
              graph("CPU used vs request and limit", "Used cores per workload against what it reserved and its ceiling. "
                    "Used near the limit line: throttled. Source: ACM Kubernetes / Compute Resources / Pod.", CORES,
                    (f"sum by (cluster, workload) ({USED()})", "{{cluster}} {{workload}} used"),
                    (f"sum by (cluster, workload) ({REQ})", "{{cluster}} {{workload}} request"),
                    (f"sum by (cluster, workload) ({LIMIT})", "{{cluster}} {{workload}} limit"))),

    extension("Which containers should change their CPU limit?",
              grid("Containers", "Per container, over the selected time range. High throttling and high p95: raise the limit. "
                   "High throttling, low p95: the limit is fine for now. Peak near limit, low average: bursty, consider no limit.",
                   ("Used avg", f"sum by (cluster, namespace, workload, pod, container) ({USED(RANGE)})", CORES, None),
                   ("Peak", f"max by (cluster, namespace, workload, pod, container) ({peak(USED())})", CORES, None),
                   ("Request", f"sum by (cluster, namespace, workload, pod, container) ({REQ})", CORES, None),
                   ("Limit", f"sum by (cluster, namespace, workload, pod, container) ({LIMIT})", CORES, None),
                   ("Throttled", throttling("cluster, namespace, workload, pod, container", RANGE), PERCENT, THROTTLING),
                   sort="Throttled", links={"pod": drill("cluster", "namespace", "pod")})),

    scope={"namespace": "spoke-1-demo"},
    links=[builtin("Kubernetes / Compute Resources / Workload")],
)
