"""components/links.py: drill-downs refilter this dashboard; built-in links resolve against the snapshot."""
import json
import re

import pytest

import build
import components as c
from helpers import ext, page

CATALOG = """| Dashboard | uid | Folder | Filters | Default range | Data here | Panels |
|---|---|---|---|---|---|---|
| Alert Analysis | `w1V3PRTnk` | Alerts | severity | 30m | yes | Total Alerts |
| Kubernetes / API server | `09ec`<br/>also `ef53` | General | cluster | 3h | yes | Up |
| Kubernetes / Networking / Pod | `7a18` | Platform - MCOA | cluster | 1h | none | Bytes |
"""


# --- drill-down links reopen this dashboard filtered to the row ---
def test_drill_link_points_at_own_dashboard_with_row_values():
    t = c.grid("t", "d", ("v", c.per_pod(f"up{{{c.C}}}"), c.COUNT, None), links={"namespace": c.drill("cluster", "namespace")})
    url = re.search(r'"url": "([^"]+)"', json.dumps(ext(t))).group(1)
    assert url.startswith("/d/team-test?")
    assert "var-cluster=${__data.fields.cluster}" in url and "var-namespace=${__data.fields.namespace}" in url
    assert "__url_time_range" in url


def test_drill_maps_a_filter_to_a_differently_named_column():
    assert "var-node=${__data.fields.instance}" in c.drill(node="instance")


# --- built-in ACM dashboards ---
def test_builtin_link_opens_the_snapshot_uid_keeping_time_and_filters():
    link = c.builtin("Kubernetes / API server", c.builtins(CATALOG)).build()
    assert link.url == "/d/09ec" and link.keep_time and link.include_vars


def test_linking_an_unknown_builtin_fails():
    with pytest.raises(AssertionError, match="acm-builtin.md"):
        c.builtin("Made Up Dashboard", c.builtins(CATALOG))


def test_linking_a_builtin_without_data_here_fails():
    with pytest.raises(AssertionError, match="no data"):
        c.builtin("Kubernetes / Networking / Pod", c.builtins(CATALOG))


def test_header_links_land_on_the_dashboard():
    d = page(links=[c.builtin("Alert Analysis", c.builtins(CATALOG))])
    assert [l["url"] for l in build.render(d, "team-test", "team")["links"]] == ["/d/w1V3PRTnk"]


# --- built-in dashboard snapshot (acm_builtin.py): finds the metrics a dashboard depends on ---
@pytest.mark.parametrize("expr, metrics", [
    ('sum by (cluster) (rate(container_cpu_usage_seconds_total{cluster="$cluster"}[5m]))', {"container_cpu_usage_seconds_total"}),
    ("a:b:sum / on (namespace) group_left kube_node_info", {"a:b:sum", "kube_node_info"}),
    ("histogram_quantile(0.99, sum by (le) (rate(x_bucket[$__rate_interval])))", {"x_bucket"}),
    ('count(ALERTS{alertstate="firing"} offset 1d) or vector(0)', {"ALERTS"}),
    ('label_replace(up, "dst", "$1", "src", "(.*)")', {"up"}),  # strings and functions aren't metrics
])
def test_builtin_snapshot_finds_the_metrics_a_query_needs(expr, metrics):
    import acm_builtin
    assert acm_builtin.metrics_in(expr) == metrics
