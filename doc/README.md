# Docs

← [Project](../README.md)

| You are | Start at |
|---|---|
| **App team:** your metrics and dashboard | [app-teams/](app-teams/README.md): 1. metrics → 2. dashboard → 3. ship |
| **Platform team:** run and extend the stack | [platform/](platform/setup.md): [setup](platform/setup.md) · [operate](platform/operate.md) · [extend](platform/extend.md) |
| **Reviewer:** why it's built this way | [decisions/](decisions/) · [research/](research/) · [architecture/](architecture/README.md) |

## Reference
- **Decisions:**
  - [0001 k3d spokes](decisions/0001-k3d-spoke-clusters.md)
  - [0002 trimmed ACM](decisions/0002-trimmed-acm-sizing.md)
  - [0003 per-pod app metrics](decisions/0003-per-pod-app-metrics.md)
  - [0004 dashboards as code](decisions/0004-dashboards-as-code.md)
- **Research:** [Network Observability Operator](research/network-observability.md).
- **Built-in ACM dashboards:** [acm-builtin.md](../platform-tools/grafana/dashboards/acm-builtin.md), generated.
- **Legacy, not the golden path:**
  - Grafana Operator ([install](../platform-tools/grafana/docs/deployment/grafana.md), [argohub workflow](../platform-tools/grafana/docs/operations/creating-updating-grafana-dashboard-workflow.md));
  - [Keycloak](../platform-tools/keycloak/README.md).

## Writing docs here
- **Concise:** short points and tables. A diagram beats a paragraph.
- **Diagrams:**
  - **mermaid**, inline, for anything with a person and steps in order (journeys, sequences, decisions);
  - **d2**, in [`architecture/`](architecture/README.md) and embedded as SVG, for what runs where and how data moves.
- **One home per fact:** link to it, don't copy it. Folders that hold code keep a 3-line README pointing here.
