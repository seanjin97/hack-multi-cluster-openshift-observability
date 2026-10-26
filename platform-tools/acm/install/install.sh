#!/usr/bin/env bash
# Installs ACM on the current oc context (e.g. OpenShift Local). Safe to re-run.
set -euo pipefail
cd "$(dirname "$0")"

# OpenShift Local ships oc but doesn't put it on PATH
command -v oc >/dev/null || eval "$(crc oc-env)"

echo "Installing ACM. This usually takes 15-20 min in total."

oc apply -f 01-operator.yaml

echo "Waiting for ACM operator to register the MultiClusterHub CRD (~2-5 min)..."
until oc get crd multiclusterhubs.operator.open-cluster-management.io >/dev/null 2>&1; do sleep 10; done
oc wait --for=condition=Established crd/multiclusterhubs.operator.open-cluster-management.io --timeout=5m

oc apply -f 02-multiclusterhub.yaml

echo "Waiting for MultiClusterHub to reach Running (~10-15 min)..."
oc wait mch/multiclusterhub -n open-cluster-management \
  --for=jsonpath='{.status.phase}'=Running --timeout=30m

oc get managedcluster
