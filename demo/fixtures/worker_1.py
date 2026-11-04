"""sensor-team-2, worker-1 (a sensor read every 5s in namespace sensor-team-2): are our sensor reads succeeding?
Built by ../build.py."""
from components import *  # noqa: F403  the component library: panels, layout, queries, units, thresholds

# Team metrics (sensor-team-2-monorepo/worker-1/main.go, doc/app-teams/1-metrics.md)
READS = lambda sel="": per_pod(f"increase(sensor_readings_total{{{C}, {APP}{sel}}}[{RATE}])")  # noqa: E731
CELSIUS = per_pod(f"sensor_reading_celsius{{{C}, {APP}}}")

dashboard = dashboard(
    "Sensor Team 2 - Worker 1 sensor reads",
    "Are our sensor reads succeeding, and what do they read? Read counts by outcome and the last temperature, "
    "per pod. Opens on sensor-team-2; widen the filters to compare.",
    ["worker-1", "sensor"],

    vitals(),
    golden_signals(),

    extension("Are our sensor reads succeeding?",
              tile("Read success rate", "Share of sensor reads that succeeded. Expect about 90%. Well below: check the sensor "
                   "and the pod logs.", ratio(f"sum({READS(', outcome=\"success\"')})", f"sum({READS()})"), PERCENT),
              graph("Sensor reads by outcome", "Reads per interval, split by success and failure. Failures climbing, or "
                    "both lines at zero: the sensor or the read loop is stuck.", COUNT,
                    (f"sum by (cluster, outcome) ({READS()})", "{{cluster}} {{outcome}}"))),

    extension("What temperature are the sensors reading?",
              graph("Sensor reading", "Last successful reading per pod, in °C. Expect 15-30°C. A flat line: no successful "
                    "reads, so the gauge keeps its last value.", "celsius",
                    (f"max by (cluster, pod) ({CELSIUS})", "{{cluster}} {{pod}}"))),

    scope={"namespace": "sensor-team-2"},
)
