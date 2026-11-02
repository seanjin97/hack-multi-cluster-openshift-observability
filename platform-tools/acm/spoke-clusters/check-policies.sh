#!/usr/bin/env bash
# Checks the L1 Kyverno policies (kyverno/l1-policies.yaml) allow and deny what
# doc/app-teams/0-levels.md says, with server-side dry runs: nothing is created.
# Exits 1 and lists the cases that behaved differently otherwise.
# Usage: ./check-policies.sh [spoke-N]   (default spoke-1)
set -euo pipefail
command -v oc >/dev/null || eval "$(crc oc-env)"
ctx=k3d-${1:-spoke-1}
ns=$(oc --context "$ctx" get ns -l starlab-platform/maturity=L1 -o jsonpath='{.items[0].metadata.name}')
fail=0

# expect allow|deny, case name, manifest on stdin
expect() {
  if out=$(oc --context "$ctx" apply --dry-run=server -f - 2>&1); then got=allow; else got=deny; fi
  [ "$got" = "$1" ] && echo "ok    $1: $2" || { echo "FAIL  want $1, got $got: $2"; echo "      $out"; fail=1; }
}
pod() {  # namespace, pod annotations, container fields
  printf 'apiVersion: v1\nkind: Pod\nmetadata: {name: check, namespace: %s, annotations: {%s}}\nspec: {containers: [{name: c, image: busybox, %s}]}\n' "$1" "$2" "$3"
}
namespace() {  # labels, annotations
  printf 'apiVersion: v1\nkind: Namespace\nmetadata: {name: check-l1, labels: {%s}, annotations: {%s}}\n' "$1" "$2"
}
M='ports: [{name: metrics, containerPort: 9}]'
P='readinessProbe: {tcpSocket: {port: 9}}, livenessProbe: {tcpSocket: {port: 9}}'
R='resources: {requests: {cpu: 1m, memory: 1Mi}, limits: {memory: 1Mi}}'
L1='starlab-platform/maturity: L1'

pod "$ns" "" "$M, $P, $R"                                     | expect allow "L1 pod meeting every rule"
pod "$ns" "" "$P, $R"                                         | expect deny  "L1 pod without a metrics port"
pod "$ns" "starlab-platform/metrics-exempt: x" "$P, $R"       | expect allow "L1 pod without a metrics port, exempt"
pod "$ns" "" "$M, $R"                                         | expect deny  "L1 pod without probes"
pod "$ns" "starlab-platform/probes-exempt: x" "$M, $R"        | expect allow "L1 pod without probes, exempt"
pod "$ns" "" "$M, $P, resources: {requests: {cpu: 1m, memory: 1Mi}}" | expect deny "L1 pod without a memory limit"
pod default "" "image: busybox"                               | expect allow "L0 pod with nothing"
namespace "$L1" ""                                            | expect deny  "L1 namespace without owner"
namespace "$L1, starlab-platform/team: x" ""                  | expect deny  "L1 namespace without contact"
namespace "$L1, starlab-platform/team: x" 'starlab-platform/contact: "#x"' | expect allow "L1 namespace with owner"
namespace "" ""                                               | expect allow "L0 namespace"

exit $fail
