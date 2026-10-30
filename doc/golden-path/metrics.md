# Golden path: app metrics

How app teams get their metrics into the fleet's Grafana. Design: [ADR 0003](../decisions/0003-per-pod-app-metrics.md).

## Levels
| | L0: spike, POC | L1: scale, maintain |
|---|---|---|
| Namespace label | none | `golden-path.level: L1` |
| You get for free | CPU, memory, network, restarts, replicas (cAdvisor + kube-state-metrics) | same |
| Own metrics | Optional: name a port `metrics` and it's scraped | **Required**: every pod has a `metrics` port, enforced at admission |
| Off-the-shelf software (nginx, redis, …) | — | Exporter sidecar on a `metrics` port |
| What to emit | anything | RED: request rate, errors, duration histogram |
| Pods with nothing to expose | — | `golden-path/metrics-exempt: "<reason>"` annotation |

## Onboard to L1
1. Expose Prometheus `/metrics` over plain HTTP, and name the container port `metrics`:
   ```yaml
   ports: [{name: metrics, containerPort: 9898}]
   ```
   Example: `platform-tools/acm/spoke-clusters/spoke-1/apps.yaml` (podinfo, native `/metrics`).
2. No native metrics? Add the exporter as a sidecar and give *it* the `metrics` port:
   ```yaml
   - name: exporter
     image: oliver006/redis_exporter:v1.67.0
     ports: [{name: metrics, containerPort: 9121}]
   ```
   Examples in `spoke-2/apps.yaml`: `redis_exporter`, and `nginx-prometheus-exporter` reading nginx's `stub_status` (`spoke-2/nginx-status.conf`).
3. Emit RED metrics: a request counter labelled by status code, and a duration histogram, e.g. podinfo's `http_requests_total` and `http_request_duration_seconds`. Keep label values bounded (no user IDs, no raw URLs).
4. Exempt only what truly has nothing to expose (load generators, one-shot jobs):
   ```yaml
   annotations: {golden-path/metrics-exempt: "busybox load generator, no metrics to expose"}
   ```
5. Label the namespace:
   ```yaml
   metadata: {name: my-team, labels: {golden-path.level: L1}}
   ```
   From now on, a pod without a `metrics` port is rejected:
   ```
   golden-path L1: expose a container port named "metrics", or annotate the pod with golden-path/metrics-exempt: "<reason>".
   ```

## See it
- Grafana on the hub → Explore, e.g.:
  ```promql
  sum by (cluster, namespace, pod) (rate(http_requests_total{cluster="spoke-1"}[5m]))
  ```
- Is my pod scraped? `up{job="open-cluster-management-addon-observability/app-metrics", namespace="my-team"}`: `1` = scraped, `0` = port named `metrics` but not serving plain `/metrics`.
- Fleet-wide check: `platform-tools/acm/spoke-clusters/check-metrics.sh`.
- Metrics arrive within ~1 minute (30s scrape + 30s push).

## Next: put a business metric on your dashboard
Success/failure counts, durations, backlogs: [custom-metrics.md](custom-metrics.md).

## Rules of thumb
- One `metrics` port per pod is enough; with sidecars, put it on the exporter.
- Everything scraped is sent to the hub, so mind cardinality: ~1k series per spoke today.
- No ServiceMonitor or PodMonitor needed: the platform's PodMonitor finds the port. Custom paths, intervals or relabelling aren't supported yet; ask the platform team.
