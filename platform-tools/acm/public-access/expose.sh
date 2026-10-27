#!/usr/bin/env bash
# Publishes ACM's Grafana, read-only, to the internet via a Cloudflare Quick Tunnel.
# Needs install.sh to have run first. Undo with: oc delete -f public-grafana.yaml
set -euo pipefail
cd "$(dirname "$0")"

# OpenShift Local ships oc but doesn't put it on PATH
command -v oc >/dev/null || eval "$(crc oc-env)"

echo "Publishing ACM Grafana. This usually takes 1-2 min."
oc apply -f public-grafana.yaml

# Behind Cloudflare WARP, cloudflared must trust the Gateway CA to reach trycloudflare.com
CA=${EXTRA_CA:-$HOME/.config/cloudflare/Cloudflare_CA.pem}
if [ -f "$CA" ]; then
  # restart only when the CA changed, since a restart gives the tunnel a new URL
  if oc create configmap extra-ca -n acm-public-grafana --from-file=ca.pem="$CA" \
      --dry-run=client -o yaml | oc apply -f - | grep -qv unchanged; then
    oc rollout restart deploy/cloudflared -n acm-public-grafana
  fi
fi
oc rollout status deploy/nginx -n acm-public-grafana --timeout=5m
oc rollout status deploy/cloudflared -n acm-public-grafana --timeout=5m

echo "Waiting for the tunnel URL..."
for i in $(seq 30); do  # 30 x 2s = 1 min
  # newest pod only: after a restart, deploy/cloudflared can still resolve to the old one
  pod=$(oc get pods -n acm-public-grafana -l app=cloudflared --field-selector=status.phase=Running \
    --sort-by=.metadata.creationTimestamp -o name | tail -1)
  url=$(oc logs "$pod" -n acm-public-grafana 2>/dev/null \
    | grep -oE 'https://[a-z0-9-]+\.trycloudflare\.com' | grep -v '//api\.' | tail -1 || true)
  [ -n "$url" ] && break
  sleep 2
done
if [ -z "$url" ]; then
  echo "No tunnel URL after 1 min. Check: oc logs deploy/cloudflared -n acm-public-grafana" >&2
  exit 1
fi

echo "Public, read-only ACM Grafana (anyone with this link can view): $url"
