"""components/queries.py: slicing, workload, node groups, peak. PromQL logic is evaluated in Python."""
import re

import pytest

import components as c


# --- node groups: a node lands in exactly one group, by its name ---
def group_of(node):
    """Evaluates by_node_group's label_replace chain the way Prometheus would."""
    calls = re.findall(r'"node_group", "([^"]+)", "instance", "([^"]+)"', c.by_node_group("x"))
    group = None
    for value, regex in calls:  # innermost label_replace comes first in the string, and runs first
        if re.fullmatch(regex, node):
            group = value
    return group


@pytest.mark.parametrize("node, group", [
    ("w-1", "worker"), ("w-12-a", "worker"), ("i-3", "infra"), ("m-1", "control-plane"),
    ("cp-0", "control-plane"), ("k3d-spoke-1-agent-0", "worker"), ("k3d-spoke-1-server-0", "control-plane"),
    ("crc", "other"), ("worker-1", "other"),  # no prefix match: never silently dropped
])
def test_node_lands_in_its_group(node, group):
    assert group_of(node) == group


def test_node_groups_are_disjoint():
    names = ["w-1", "i-1", "m-1", "cp-1", "x-agent-1", "x-server-1"]
    for n in names:
        hits = [g for g, r in c.NODE_GROUPS.items() if re.fullmatch(r, n)]
        assert len(hits) <= 1, f"{n} matches {hits}"


# --- workload: derived from the pod's owner ---
def workload_of(kind, owner):
    """Evaluates SCOPE's label_replace for one pod's owner."""
    regex = re.search(r'created_by_kind="ReplicaSet"\}, "workload", "\$1", "created_by_name", "([^"]+)"', c.SCOPE).group(1)
    return re.fullmatch(regex, owner).group(1) if kind == "ReplicaSet" else owner


@pytest.mark.parametrize("kind, owner, workload", [
    ("ReplicaSet", "frontend-77b888787d", "frontend"),       # Deployment: ReplicaSet hash dropped
    ("ReplicaSet", "my-app-v2-5d9d9885bc", "my-app-v2"),
    ("StatefulSet", "redis", "redis"),
    ("DaemonSet", "node-exporter", "node-exporter"),
])
def test_workload_is_the_owner_without_replicaset_hash(kind, owner, workload):
    assert workload_of(kind, owner) == workload


def test_workload_filter_selects_its_pods_only():
    sel = re.search(r'created_by_name=~"([^"]+)"', c.SCOPE).group(1).replace("$workload", "frontend")
    assert re.fullmatch(sel, "frontend-77b888787d")
    assert not re.fullmatch(sel, "backend-756b468648")
    assert not re.fullmatch(sel, "frontend-api-77b888787d")  # a different Deployment sharing the prefix


# --- slicing: per_pod/per_node apply every filter ---
@pytest.mark.parametrize("f", ["$cluster", "$node", "$namespace", "$workload", "$pod"])
def test_per_pod_follows_every_filter(f):
    assert f in c.per_pod("up")


def test_per_pod_adds_workload_and_node_labels():
    assert "group_left (workload, node)" in c.per_pod("up")


@pytest.mark.parametrize("label", ["instance", "node"])
def test_per_node_joins_on_the_series_node_label(label):
    q = c.per_node("up", label)
    assert f"on (cluster, {label})" in q and "$pod" in q


# --- peak over a range: the highest STEP-resolution value in the window ---
def test_peak_samples_at_the_dashboard_step_over_the_whole_range():
    q = c.peak("x")
    assert f"[{c.RANGE}:{c.STEP}]" in q and q.startswith("max_over_time(")
