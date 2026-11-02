"""PromQL building blocks: filters, slicing to the selection, node groups, granularity."""

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
PEAK = f"[{RANGE}:{STEP}]"  # the one subquery window allowed: peak() at the dashboard's step


def peak(expr):
    """Highest value of expr over the selected range, sampled at STEP. For table columns like "Peak CPU".
    expr should use [RATE] windows, as in a graph."""
    return f"max_over_time(({expr}){PEAK})"
