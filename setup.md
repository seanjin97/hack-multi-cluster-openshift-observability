# Openshift-local setup
1. Go to https://console.redhat.com/openshift/create/local (create account and login)
2. Click `Download Openshift Local`
3. Go through installation process (no homebrew alternative it seems)
4. Test if `crc` is installed correctly: `which crc`
5. `crc setup`
6. `crc start`
7. After the cluster is setup, the CLI prints out some lines. Just record it somewhere

![post-install.png](images/post-install.png)

8. Access the web portal: https://console-openshift-console.apps-crc.testing
9. Get `oc` on your PATH: `eval $(crc oc-env)` (add it to `~/.zshrc` to keep it across shells)
10. Verify `oc` works: `oc login -u developer https://api.crc.testing:6443`
11. Enable cluster monitoring: `crc config set enable-cluster-monitoring true`
12. Adjust cpu limits: `crc config set cpus 8`. Adjust accordingly.
13. Adjust memory limits: `crc config set memory 32768`. 24GB is enough for ACM alone, but not with ACM Observability on top.
14. Adjust disk size: `crc config set disk-size 100`. The default 31GB is too small for ACM (see [Troubleshooting](#troubleshooting)). The disk can only grow, not shrink.
15. Restart cluster to get the updated limits: `crc stop`, `crc start`.
16. Verify that limits are updated: `crc config view`
17. Verify that Prometheus is installed: `oc get pods -n openshift-monitoring | grep prometheus`
18. (Only if behind Cloudflare WARP / Zero Trust) Trust the Cloudflare CA in the cluster, otherwise image pulls from `registry.redhat.io` fail (see [Troubleshooting](#troubleshooting)).
    - Check: `echo | openssl s_client -connect registry.redhat.io:443 2>/dev/null | openssl x509 -noout -issuer` shows `Gateway CA - Cloudflare Managed G1`
    - Log in as admin: `oc login -u kubeadmin https://api.crc.testing:6443`
    - Add the CA to crc's existing `registry-certs` configmap (don't replace it, it holds the internal registry's cert). Point `CA` at wherever your Cloudflare root cert lives:
      ```
      CA=~/.config/cloudflare/Cloudflare_CA.pem
      oc set data cm/registry-certs -n openshift-config \
        --from-file=registry.redhat.io=$CA \
        --from-file=quay.io=$CA \
        --from-file=registry.connect.redhat.com=$CA
      ```
    - Wait 1-2 min for the node to pick it up.
19. Install ACM and ACM Observability: `./platform-tools/acm/install/install.sh` (takes ~20-30 min, safe to re-run). It installs:
    - the ACM operator and MultiClusterHub
    - [Silo](https://github.com/pgsty/silo) (community MinIO fork) as in-cluster S3 for Thanos
    - MultiClusterObservability, sized down to fit one crc node
20. Open Grafana: https://grafana-open-cluster-management-observability.apps-crc.testing (see [Grafana](#grafana))
21. Verify metrics are flowing: `oc get pods -n open-cluster-management-observability` shows everything Running, and the ACM dashboards in Grafana show `local-cluster`.

## Checking metrics
- Single cluster, built-in Prometheus: console → **Observe → Dashboards** / **Observe → Metrics**.
- All managed clusters, via ACM: Grafana link above, **Dashboards → ACM**.
- From the CLI:
  ```
  H=$(oc get route rbac-query-proxy -n open-cluster-management-observability -o jsonpath='{.spec.host}')
  curl -sk -H "Authorization: Bearer $(oc whoami -t)" "https://$H/api/v1/query" \
    --data-urlencode 'query=count by (cluster) (up)'
  ```

## Grafana

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
- **Editing in the UI:** changes to ACM-shipped dashboards can be overwritten from their configmaps when the operator reconciles. Export anything you want to keep into a custom dashboard configmap.
- **Grafana settings and data sources:** these secrets are operator-managed and hand edits get reverted. Change them through the `MultiClusterObservability` resource instead.

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
- Cause: ACM's default sizing reserves ~10 CPU cores and 2-3 replicas of every component, more than a single 8-core crc node has. `04-observability.yaml` shrinks this; if you changed it, or a node is still short, check `oc describe node crc | grep -A5 'Allocated resources'`.
- If you lower resources in `04-observability.yaml` after pods are already `Pending`, the StatefulSet won't replace them. Delete them so they come back with the new values:
  ```
  oc delete pod -n open-cluster-management-observability --field-selector=status.phase=Pending
  ```

### Object storage pod won't start
- `ImagePullBackOff` with `unauthorized` on `minio/minio`: MinIO no longer publishes free images. `03-object-storage.yaml` uses Silo instead.

### `oc: command not found`
- crc ships `oc` at `~/.crc/bin/oc/oc` but doesn't add it to PATH. Run `eval $(crc oc-env)`. `install.sh` does this itself if `oc` is missing.
