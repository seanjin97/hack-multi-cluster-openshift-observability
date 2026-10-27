#!/usr/bin/env bash
# Installs ACM on the current oc context (e.g. OpenShift Local). Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

# OpenShift Local ships oc but doesn't put it on PATH
command -v oc >/dev/null || eval "$(crc oc-env)"

echo "Installing ACM. This usually takes 20-30 min in total."

oc apply -f 01-operator.yaml

echo "Waiting for ACM operator to register the MultiClusterHub CRD (~2-5 min)..."
for i in $(seq 60); do  # 60 x 10s = 10 min
  oc get crd multiclusterhubs.operator.open-cluster-management.io >/dev/null 2>&1 && break
  if [ "$i" = 60 ]; then
    echo "Timed out after 10 min. Check: oc get sub advanced-cluster-management -n open-cluster-management -o yaml" >&2
    exit 1
  fi
  sleep 10
done
oc wait --for=condition=Established crd/multiclusterhubs.operator.open-cluster-management.io --timeout=5m

oc apply -f 02-multiclusterhub.yaml

echo "Waiting for MultiClusterHub to reach Running (~10-15 min)..."
oc wait mch/multiclusterhub -n open-cluster-management \
  --for=jsonpath='{.status.phase}'=Running --timeout=30m

# Turn off MultiClusterEngine's cluster-provisioning features; importing existing
# clusters doesn't need them. Patched one at a time: a merge patch would replace
# the whole components list, dropping local-cluster and the rest.
oc patch mce multiclusterengine --type merge -p '{"spec":{"availabilityConfig":"Basic"}}'
for c in hive assisted-service discovery hypershift hypershift-local-hosting; do
  i=$(oc get mce multiclusterengine -o json | python3 -c "import sys,json
cs=json.load(sys.stdin)['spec']['overrides']['components']
print(next(n for n,x in enumerate(cs) if x['name']=='$c'))")
  oc patch mce multiclusterengine --type json \
    -p "[{\"op\":\"replace\",\"path\":\"/spec/overrides/components/$i/enabled\",\"value\":false}]"
done

oc get managedcluster

oc apply -f 03-object-storage.yaml
echo "Waiting for object storage (~1 min)..."
oc rollout status deploy/silo -n open-cluster-management-observability --timeout=5m

oc apply -f 04-observability.yaml
echo "Waiting for MultiClusterObservability to become Ready (~5-10 min)..."
oc wait mco/observability --for=condition=Ready --timeout=20m

echo "Grafana: https://$(oc get route grafana -n open-cluster-management-observability -o jsonpath='{.spec.host}')"
