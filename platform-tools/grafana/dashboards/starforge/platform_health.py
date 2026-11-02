"""Platform health: the platform team's fleet dashboard. Built by ../build.py."""
from components import *  # noqa: F403  the component library: panels, layout, queries, units, thresholds

# Per-pod series, sliced by every filter (per_pod adds workload and node labels).
# w: the window. RATE for graphs and tiles (widens on zoom), RANGE for tables and sizing (the whole window).
CPU = lambda w=RATE: per_pod(f'rate(container_cpu_usage_seconds_total{{{C}, container!="", container!="POD"}}[{w}])')  # noqa: E731
MEM = per_pod(f'container_memory_working_set_bytes{{{C}, container!="", container!="POD"}}')
MEM_AVG = per_pod(f'avg_over_time(container_memory_working_set_bytes{{{C}, container!="", container!="POD"}}[{RANGE}])')
REQ = lambda r: per_pod(f'kube_pod_container_resource_requests{{{C}, resource="{r}"}}')  # noqa: E731
LIM = lambda r: per_pod(f'kube_pod_container_resource_limits{{{C}, resource="{r}"}}')  # noqa: E731
NET = lambda m: per_pod(f'rate(container_network_{m}_total{{{C}, interface="eth0"}}[{RANGE}])')  # noqa: E731
RESTARTS = lambda w=RATE: per_pod(f"increase(kube_pod_container_status_restarts_total{{{C}}}[{w}])")  # noqa: E731
THROTTLED = per_pod(f'rate(container_cpu_cfs_throttled_periods_total{{{C}, container!=""}}[{RATE}])')
PERIODS = per_pod(f'rate(container_cpu_cfs_periods_total{{{C}, container!=""}}[{RATE}])')
# Golden-path app metrics: the histogram's _count carries path, method and status (doc/app-teams/1-metrics.md)
REQS = lambda w=RATE: per_pod(f"rate(http_request_duration_seconds_count{{{C}, {APP}}}[{w}])")  # noqa: E731
ERRS = lambda w=RATE: per_pod(f'rate(http_request_duration_seconds_count{{{C}, {APP}, status=~"5.."}}[{w}])')  # noqa: E731
LAT = lambda w=RATE: per_pod(f"rate(http_request_duration_seconds_bucket{{{C}, {APP}}}[{w}])")  # noqa: E731

# Node series (node-exporter, instance = node name), sliced to nodes running the selected pods
NODE = lambda m: by_node_group(per_node(f"{m}{{{C}}}"))  # noqa: E731
NODE_MAX = lambda m: by_node_group(per_node(f"max_over_time({m}{{{C}}}[{RANGE}])"))  # noqa: E731
ALLOC = lambda r: per_node(f'kube_node_status_allocatable{{{C}, resource="{r}"}}', "node")  # noqa: E731

dashboard = dashboard(
    "Platform Health",
    "Platform team view of every cluster: vitals, golden signals, provisioning, node groups, workloads "
    "and endpoints. Slice any panel with the cluster, node, namespace, workload and pod filters.",
    ["platform", "fleet"],

    vitals(
        tile("Clusters reporting", f"Clusters that sent metrics to the hub. Lower than expected: check the spoke's addon. {CLUSTER_ONLY}",
             f"count(count by (cluster) (kube_node_status_allocatable{{{C}}}))", COUNT),
        tile("Firing alerts", f"Alerts firing now. Above 0: open Alerting, or ACM's alert dashboards. {CLUSTER_ONLY}",
             f'sum(ALERTS{{{C}, alertstate="firing"}}) or vector(0)', COUNT, PROBLEMS),
        tile("Nodes not ready", "Selected nodes whose Ready condition isn't true. Above 0: check the node.",
             f'sum(kube_node_status_condition{{{C}, node=~"$node", condition="Ready", status!="true"}}) or vector(0)', COUNT, PROBLEMS),
        tile("Pods not running", "Pods in Pending, Failed or Unknown. Above 0: filter to the namespace and check its workloads.",
             f'sum({per_pod(f"kube_pod_status_phase{{{C}, phase=~\"Pending|Failed|Unknown\"}}")}) or vector(0)', COUNT, PROBLEMS),
        tile("App 5xx rate", "Share of golden-path app requests answered 5xx. Above 1%: open the endpoints row.",
             ratio(f"sum({ERRS()}) or vector(0)", f"sum({REQS()})"), PERCENT, ERRORS),
        tile("Peak node CPU", "The busiest selected node's CPU. Above 85%: find the node group in Saturation.",
             f'max({per_node(f"instance:node_cpu_utilisation:rate1m{{{C}}}")})', PERCENT, UTILISATION),
    ),

    golden_signals(
        latency=[
            graph("App p95 by cluster", "95th percentile golden-path request duration. Above 300ms: open the endpoints row.", SECONDS,
                  (f"histogram_quantile(0.95, sum by (cluster, le) ({LAT()}))", "{{cluster}}"), thresholds=LATENCY),
            graph("API server p99", f"Kubernetes API latency, 99th percentile. Slow: everything that talks to the API slows down. "
                  f"Source: ACM Kubernetes / API server. {CLUSTER_ONLY}", SECONDS,
                  (f"apiserver_request_duration_seconds:histogram_quantile_99{{{C}}}", "{{cluster}}"), thresholds=LATENCY),
            graph("Disk IO wait by node group", "Weighted IO time per second: how long disk IO waits. Rising: disk-bound nodes. "
                  "Source: ACM USE Method / Node.", SECONDS,
                  (f'max by (cluster, node_group) ({NODE("instance_device:node_disk_io_time_weighted_seconds:rate1m")})', "{{cluster}} {{node_group}}")),
        ],
        traffic=[
            graph("App requests/s by cluster", "Golden-path app requests per second.", REQPS,
                  (f"sum by (cluster) ({REQS()})", "{{cluster}}")),
            graph("App requests/s by status", "Requests per second per status code. Watch 4xx and 5xx grow.", REQPS,
                  (f"sum by (cluster, status) ({REQS()})", "{{cluster}} {{status}}")),
            graph("Node network by group", "Bytes received and sent by node group. Source: ACM USE Method / Node.", BPS,
                  (f'sum by (cluster, node_group) ({NODE("instance:node_network_receive_bytes_excluding_lo:rate1m")})', "{{cluster}} {{node_group}} in"),
                  (f'sum by (cluster, node_group) ({NODE("instance:node_network_transmit_bytes_excluding_lo:rate1m")})', "{{cluster}} {{node_group}} out")),
        ],
        errors=[
            graph("App 5xx ratio", "Share of requests answered 5xx. Above 1%: open the endpoints row.", PERCENT,
                  (ratio(f"sum by (cluster) ({ERRS()})", f"sum by (cluster) ({REQS()})"), "{{cluster}}"), thresholds=ERRORS),
            graph("TCP retransmits by node group", "Share of TCP segments retransmitted. Above 1%: packet loss or a congested node; "
                  "find the pod in 'Which pods are loading the node network?'. Source: ACM Kubernetes / Networking / Node.", PERCENT,
                  (ratio(f'sum by (cluster, node_group) ({by_node_group(per_node(f"rate(node_netstat_Tcp_RetransSegs{{{C}}}[{RATE}])"))})',
                         f'sum by (cluster, node_group) ({by_node_group(per_node(f"rate(node_netstat_Tcp_OutSegs{{{C}}}[{RATE}])"))})'),
                   "{{cluster}} {{node_group}}"), thresholds=ERRORS),
            graph("Restarts by workload", "Container restarts per step. Any bar: a crash loop or OOM kill.", COUNT,
                  (f"sum by (cluster, namespace, workload) ({RESTARTS()}) > 0", "{{cluster}} {{namespace}}/{{workload}}")),
        ],
        saturation=[
            graph("CPU by node group", "Average CPU utilisation per node group.", PERCENT,
                  (f'avg by (cluster, node_group) ({NODE("instance:node_cpu_utilisation:rate1m")})', "{{cluster}} {{node_group}}"),
                  thresholds=UTILISATION),
            graph("Memory by node group", "Average memory utilisation per node group.", PERCENT,
                  (f'avg by (cluster, node_group) ({NODE("instance:node_memory_utilisation:ratio")})', "{{cluster}} {{node_group}}"),
                  thresholds=UTILISATION),
            graph("CPU throttling", "Share of CPU periods where containers hit their CPU limit. High: limits too low; latency suffers.", PERCENT,
                  (ratio(f"sum by (cluster) ({THROTTLED})", f"sum by (cluster) ({PERIODS})"), "{{cluster}}"), thresholds=THROTTLING),
        ],
    ),

    # Business question 1: utilisation and over/under-provisioning, sized over SIZING (not the time picker)
    extension("Are we using what we've reserved?",
              (tile("CPU requested / allocatable", "Share of the selected nodes' CPU reserved by the selected pods. Above 85%: new pods may not schedule.",
                    ratio(f'sum({REQ("cpu")})', f'sum({ALLOC("cpu")})'), PERCENT, UTILISATION),
               tile("CPU used / requested", "Average use over 7 days against the request. Blue: reserved but idle (over-provisioned). "
                    "Red: using more than reserved (under-provisioned).",
                    ratio(f"sum({CPU(RANGE)})", f'sum({REQ("cpu")})'), PERCENT, PROVISIONING, sizing=True),
               tile("Memory requested / allocatable", "Share of the selected nodes' memory reserved by the selected pods.",
                    ratio(f'sum({REQ("memory")})', f'sum({ALLOC("memory")})'), PERCENT, UTILISATION),
               tile("Memory used / requested", "Average use over 7 days against the request. Blue: reserved but idle. "
                    "Red: using more than reserved, at risk of OOM or eviction.",
                    ratio(f"sum({MEM_AVG})", f'sum({REQ("memory")})'), PERCENT, PROVISIONING, sizing=True)),
              grid("Provisioning by namespace", "Average use over 7 days against the requests, per namespace. Blue (<30%): lower the requests. "
                   "Red (>100%): raise them. Empty ratio: no requests set, so the scheduler is guessing. Click a namespace to filter to it. "
                   "For recommended values, open ACM Right-Sizing Namespace from the header. Source: ACM ACM Right-Sizing Namespace.",
                   ("CPU used", f"sum by (cluster, namespace) ({CPU(RANGE)})", CORES, None),
                   ("CPU requested", f'sum by (cluster, namespace) ({REQ("cpu")})', CORES, None),
                   ("CPU used / requested", ratio(f"sum by (cluster, namespace) ({CPU(RANGE)})", f'sum by (cluster, namespace) ({REQ("cpu")})'), PERCENT, PROVISIONING),
                   ("Memory used", f"sum by (cluster, namespace) ({MEM_AVG})", BYTES, None),
                   ("Memory requested", f'sum by (cluster, namespace) ({REQ("memory")})', BYTES, None),
                   ("Memory used / requested", ratio(f"sum by (cluster, namespace) ({MEM_AVG})", f'sum by (cluster, namespace) ({REQ("memory")})'), PERCENT, PROVISIONING),
                   sort="CPU requested", links={"namespace": drill("cluster", "namespace")}, height=12, sizing=True)),

    # Business question 2: team ownership. Teams filter to their namespace; links go one level down.
    extension("How are my workloads doing? (filter to your namespace)",
              grid("Workloads", "Per workload, over the selected time range: pods, average use vs request, memory vs limit, restarts. "
                   "You build it, you run it: fix blue and red cells by changing your requests. Click a workload to filter to it.",
                   ("Pods", f"count by (cluster, namespace, workload) ({SCOPE})", COUNT, None),
                   ("CPU used / requested", ratio(f"sum by (cluster, namespace, workload) ({CPU(RANGE)})", f'sum by (cluster, namespace, workload) ({REQ("cpu")})'), PERCENT, PROVISIONING),
                   ("Memory used / requested", ratio(f"sum by (cluster, namespace, workload) ({MEM_AVG})", f'sum by (cluster, namespace, workload) ({REQ("memory")})'), PERCENT, PROVISIONING),
                   ("Memory used / limit", ratio(f"sum by (cluster, namespace, workload) ({MEM_AVG})", f'sum by (cluster, namespace, workload) ({LIM("memory")})'), PERCENT, UTILISATION),
                   ("Restarts", f"sum by (cluster, namespace, workload) ({RESTARTS(RANGE)})", COUNT, PROBLEMS),
                   sort="Pods", links={"workload": drill("cluster", "namespace", "workload")}),
              (graph("CPU by pod", "CPU used per pod.", CORES, (f"sum by (cluster, pod) ({CPU()})", "{{cluster}} {{pod}}")),
               graph("Memory by pod", "Working-set memory per pod. Reaching the limit means OOM kills.", BYTES,
                     (f"sum by (cluster, pod) ({MEM})", "{{cluster}} {{pod}}")))),

    # Business question 4: node logical groups
    extension("Which nodes are under pressure?",
              grid("Nodes", "One row per selected node: its group, and peak saturation over the selected time range. "
                   "Click a node to filter to it. Source: ACM USE Method / Node.",
                   ("CPU", f'max by (cluster, node_group, instance) ({NODE_MAX("instance:node_cpu_utilisation:rate1m")})', PERCENT, UTILISATION),
                   ("Memory", f'max by (cluster, node_group, instance) ({NODE_MAX("instance:node_memory_utilisation:ratio")})', PERCENT, UTILISATION),
                   ("Load per CPU", f'max by (cluster, node_group, instance) ({NODE_MAX("instance:node_load1_per_cpu:ratio")})', PERCENT, UTILISATION),
                   ("Pods", f"count by (cluster, instance) (label_replace({SCOPE}, \"instance\", \"$1\", \"node\", \"(.*)\"))", COUNT, None),
                   sort="CPU", links={"instance": drill("cluster", node="instance")})),

    # Business question 3: pods that hurt their node's network
    extension("Which pods are loading the node network?",
              grid("Pods by network", "The busiest pods by average bytes over the selected time range, and their dropped packets. A pod at the top on a node with "
                   "TCP retransmits is the likely noisy neighbour. Click a pod to filter to it.",
                   ("Received", f"sum by (cluster, node, namespace, pod) ({NET('receive_bytes')})", BPS, None),
                   ("Sent", f"sum by (cluster, node, namespace, pod) ({NET('transmit_bytes')})", BPS, None),
                   ("Dropped", f"sum by (cluster, node, namespace, pod) ({NET('receive_packets_dropped')}) + "
                               f"sum by (cluster, node, namespace, pod) ({NET('transmit_packets_dropped')})", PPS, PROBLEMS),
                   sort="Received", links={"pod": drill("cluster", "namespace", "pod")}, height=12)),

    # Business question 5: endpoint drill-down (golden-path app metrics)
    extension("Which endpoints are slow or failing?",
              grid("Endpoints", "Per endpoint, over the selected time range, from the golden-path histogram "
                   "http_request_duration_seconds, labelled path, method, status. Missing your app? See doc/app-teams/1-metrics.md.",
                   ("Requests/s", f"sum by (cluster, namespace, workload, method, path) ({REQS(RANGE)})", REQPS, None),
                   ("Errors", ratio(f"sum by (cluster, namespace, workload, method, path) ({ERRS(RANGE)})",
                                    f"sum by (cluster, namespace, workload, method, path) ({REQS(RANGE)})"), PERCENT, ERRORS),
                   ("p50", f"histogram_quantile(0.5, sum by (cluster, namespace, workload, method, path, le) ({LAT(RANGE)}))", SECONDS, LATENCY),
                   ("p95", f"histogram_quantile(0.95, sum by (cluster, namespace, workload, method, path, le) ({LAT(RANGE)}))", SECONDS, LATENCY),
                   ("p99", f"histogram_quantile(0.99, sum by (cluster, namespace, workload, method, path, le) ({LAT(RANGE)}))", SECONDS, LATENCY),
                   sort="p95"),
              graph("p95 by endpoint", "Latency over time for the 10 slowest endpoints.", SECONDS,
                    (f"topk(10, histogram_quantile(0.95, sum by (cluster, workload, method, path, le) ({LAT()})))",
                     "{{cluster}} {{workload}} {{method}} {{path}}"), thresholds=LATENCY)),

    # Deep dives the platform team opens from the header; steps of our own questions are rebuilt above
    links=[builtin(t) for t in ("Alert Analysis", "Kubernetes / API server", "Kubernetes / Service-Level Overview / API Server",
                                "Kubernetes / etcd Cluster", "USE Method / Node", "ACM Right-Sizing Namespace")],
)
