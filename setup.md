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
17. Install ACM: `./platform-tools/acm/install/install.sh`