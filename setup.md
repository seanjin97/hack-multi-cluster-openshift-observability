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
9. Get `oc` installed: `eval $(crc oc-env)`
10. Verify `oc` works: `oc login -u developer https://api.crc.testing:6443`
11. Enable cluster monitoring: `crc config set enable-cluster-monitoring true`
12. Adjust cpu limits: `crc config set cpus 8`. Adjust accordingly.
13. Adjust memory limits: `crc config set memory 24576`. Adjust accordingly.
14. Restart cluster to get the updated limits: `crc stop`, `crc start`.
15. Verify that limit are updated: `crc config view`
16. Verify that Prometheus is installed: `oc get pods -n openshift-monitoring | grep prometheus`
17. (Only if behind Cloudflare WARP / Zero Trust) Trust the Cloudflare CA in the cluster, otherwise image pulls from `registry.redhat.io` fail with `x509: certificate signed by unknown authority` and the ACM install hangs at the CRD wait.
    - Check: `echo | openssl s_client -connect registry.redhat.io:443 2>/dev/null | openssl x509 -noout -issuer` shows `Gateway CA - Cloudflare Managed G1`
    - Log in as admin: `oc login -u kubeadmin https://api.crc.testing:6443`
    - Add the CA to crc's existing `registry-certs` configmap (don't replace it, it holds the internal registry's cert):
      ```
      CA=~/.config/cloudflare/Cloudflare_CA.pem
      oc set data cm/registry-certs -n openshift-config \
        --from-file=registry.redhat.io=$CA \
        --from-file=quay.io=$CA \
        --from-file=registry.connect.redhat.com=$CA
      ```
    - Wait 1-2 min for nodes to pick it up.
    - If a previous ACM install already failed, clean it up first:
      ```
      oc delete job -n openshift-marketplace --all
      oc delete sub advanced-cluster-management -n open-cluster-management
      oc delete csv -n open-cluster-management --all
      ```
18. Install ACM: `./platform-tools/acm/install/install.sh`