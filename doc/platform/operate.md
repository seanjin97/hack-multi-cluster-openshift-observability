# Platform: operate

← [Docs](../README.md) · [setup](setup.md) · [extend](extend.md)

## ACM Grafana

### Logging in
1. Open https://grafana-open-cluster-management-observability.apps-crc.testing. The first page is a 403 "Log In" page; that's OpenShift's login in front of Grafana, not an error.
2. Click **Log in with OpenShift** and choose **kube:admin**. The password is the one `crc start` printed; `crc console --credentials` shows it again.
3. You land on **ACM - Clusters Overview**. The other dashboards are under **Dashboards → ACM**.

The ACM console also links to Grafana from **Infrastructure → Clusters**.

### How it's provisioned
Nothing in this repo configures Grafana. The ACM observability operator creates it from the `MultiClusterObservability` resource (`platform-tools/acm/install/04-observability.yaml`) and owns the `observability-grafana` deployment in `open-cluster-management-observability`. The pod runs three containers:

| Container | Role |
|---|---|
| `grafana` | Red Hat's Grafana build. Settings come from the `grafana-config` secret. |
| `grafana-dashboard-loader` | Loads the configmaps named `grafana-dashboard-*` into Grafana. ACM ships about 58 of them. |
| `grafana-proxy` | OpenShift OAuth proxy. Only users allowed to list `projects` get in. |

Data sources come from the `grafana-datasources` secret. Both (`Observatorium`, the default, and `Observatorium-Dynamic`) point at `rbac-query-proxy`, which sits in front of Thanos and filters by user: a user only sees metrics for clusters whose namespaces they can access. `kubeadmin` sees everything.

### Customizing
- **Custom dashboards:** create a configmap in `open-cluster-management-observability` labelled `grafana-custom-dashboard: "true"`, holding the dashboard JSON. The loader picks it up. This is the supported way, and it keeps dashboards in git.
  Ours are written in Python and generated, never hand-edited: `platform-tools/grafana/dashboards/`, synced to the hub by ArgoCD on merge to `main` (GitOps is set up outside this repo; locally: `oc apply -k platform-tools/grafana/dashboards`). They're grouped by team, `dashboards/<team>/<name>.py`, and show under **Dashboards → `<team>`**. How teams add one: [app teams](../app-teams/README.md); how it's delivered: [dashboard delivery](../architecture/README.md#dashboard-delivery).
- **Editing in the UI:** changes to ACM-shipped dashboards can be overwritten from their configmaps when the operator reconciles. Export anything you want to keep into a custom dashboard configmap.
- **Grafana settings and data sources:** these secrets are operator-managed and hand edits get reverted. Change them through the `MultiClusterObservability` resource instead.

### Sharing ACM's Grafana publicly, read-only
`./platform-tools/acm/public-access/expose.sh` publishes ACM's own Grafana through a Cloudflare Quick Tunnel and prints a `https://*.trycloudflare.com` link. It's the same Grafana, dashboards and data as the in-cluster one, so nothing drifts.
- **Anyone with the link can view every managed cluster's metrics, with no login.** They're signed in as `public-viewer`.
- **Read-only is enforced by nginx, not Grafana.** ACM's Grafana lets viewers edit, so nginx refuses every request except reads and panel queries (`POST /api/ds/query`); attempts to save or delete get a 403.
- The tunnel runs in the cluster, so nothing needs installing on your Mac and no Cloudflare account is needed. The link only works while crc is running.
- The link changes whenever the `cloudflared` pod restarts, for example after `crc stop`/`crc start`. Re-run `expose.sh` to get the new one.
- To take it down: `oc delete -f platform-tools/acm/public-access/public-grafana.yaml`

How it works: ACM's Grafana sits behind an OpenShift login proxy and trusts two headers from it, `X-Forwarded-User` (who you are) and `X-Forwarded-Access-Token` (sent on to `rbac-query-proxy`, which decides which clusters' metrics you see). The nginx pod skips that login, talks to the Grafana container directly, and sets both headers using the `grafana-viewer` service account. That account can read all namespaces, projects and ManagedClusters (`acm-public-grafana-viewer` ClusterRole), which makes the proxy return every cluster, read-only.
- Its token is short-lived and rotated by Kubernetes; nginx re-reads it every 5 min. A long-lived `service-account-token` secret doesn't work: `rbac-query-proxy` only shows those `local-cluster`.

## Working with the 3 clusters
All three are contexts in `~/.kube/config`: `crc-admin` (hub), `k3d-spoke-1`, `k3d-spoke-2`. Keep the current context on the hub and pass `--context` for spokes, instead of switching back and forth. Every command then says which cluster it hits, and a forgotten switch can't land a deploy on the wrong cluster.
```
oc get pods -A                                          # hub (current context)
oc --context k3d-spoke-1 get pods -n spoke-1-demo       # one spoke
for c in crc-admin k3d-spoke-1 k3d-spoke-2; do echo "== $c"; oc --context $c get nodes; done   # all
oc --context k3d-spoke-2 apply -k platform-tools/acm/spoke-clusters/spoke-2          # deploy
```
- **Read-only checks across clusters:** you rarely need to log in to a spoke. The hub's Grafana and the `rbac-query-proxy` query above already show every cluster's metrics, filtered by the `cluster` label.
- **Deploying:** `oc --context <spoke> apply -k <spoke dir>` for these demo apps. To drive spokes from the hub instead, ACM's `ManifestWork` (installed, `oc get manifestwork -A`) applies manifests to a managed cluster from its namespace on the hub. Use it only once you want the hub to own what runs where; for 2 demo spokes it's extra indirection.
- **Interactive:** [k9s](https://k9scli.io) (`brew install k9s`, `:ctx` to switch) is the easiest way to browse several clusters. If you do switch contexts, `oc config use-context crc-admin` gets you back, and `install.sh`/`spokes.sh` assume the hub is current.

## Troubleshooting

### ACM install hangs at "Waiting for ACM operator to register the MultiClusterHub CRD"
- Symptom: `oc get sub advanced-cluster-management -n open-cluster-management -o yaml` shows `BundleUnpackFailed`, and `oc get events -n openshift-marketplace | grep -i pull` shows `x509: certificate signed by unknown authority`.
- Cause: Cloudflare WARP intercepts TLS; the crc VM doesn't trust its CA.
- Fix: step 18, then clear the failed attempt and re-run the install:
  ```
  oc delete job -n openshift-marketplace --all
  oc delete sub advanced-cluster-management -n open-cluster-management
  oc delete csv -n open-cluster-management --all
  ./platform-tools/acm/install/install.sh
  ```

### ACM install times out at "Waiting for MultiClusterHub to reach Running"
- Symptom: pods in `open-cluster-management` stuck in `ImagePullBackOff` / `Error` / `ContainerStatusUnknown`; `oc get events -A --field-selector type=Warning` shows `Evicted ... low on resource: ephemeral-storage` and `DiskPressure`.
- Cause: crc VM disk is full (default 31GB).
- Fix: `crc stop && crc config set disk-size 100 && crc start`, then re-run the install.

### Observability install times out at "Waiting for MultiClusterObservability to become Ready"
- Symptom: `observability-*` pods in `open-cluster-management-observability` stuck `Pending`; their events say `Insufficient cpu` or `Insufficient memory`.
- Cause: ACM's default sizing reserves ~10 CPU cores and 2-3 replicas of every component, more than a single 6-core crc node has. `04-observability.yaml` shrinks this; if you changed it, or a node is still short, check `oc describe node crc | grep -A5 'Allocated resources'`.
- If you lower resources in `04-observability.yaml` after pods are already `Pending`, the StatefulSet won't replace them. Delete them so they come back with the new values:
  ```
  oc delete pod -n open-cluster-management-observability --field-selector=status.phase=Pending
  ```

### Object storage pod won't start
- `ImagePullBackOff` with `unauthorized` on `minio/minio`: MinIO no longer publishes free images. `03-object-storage.yaml` uses Silo instead.

### `oc: command not found`
- crc ships `oc` at `~/.crc/bin/oc/oc` but doesn't add it to PATH. Run `eval $(crc oc-env)`. `install.sh` does this itself if `oc` is missing.
