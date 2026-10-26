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
13. Adjust memory limits: `crc config set memory 24576`. Adjust accordingly.
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
19. Install ACM: `./platform-tools/acm/install/install.sh` (takes ~15-20 min, safe to re-run)

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

### `oc: command not found`
- crc ships `oc` at `~/.crc/bin/oc/oc` but doesn't add it to PATH. Run `eval $(crc oc-env)`. `install.sh` does this itself if `oc` is missing.
