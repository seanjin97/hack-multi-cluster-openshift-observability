"""Units and colours. Pick a unit constant and a threshold set, never a colour."""
from grafana_foundation_sdk.builders import dashboard as db
from grafana_foundation_sdk.models import dashboard as dm

PERCENT, CORES, BYTES, BPS, PPS, SECONDS, REQPS, COUNT = (
    "percentunit", "suffix: cores", "bytes", "Bps", "pps", "s", "reqps", "short")


def _steps(*steps):
    return db.ThresholdsConfig().mode(dm.ThresholdsMode.ABSOLUTE).steps(
        [dm.Threshold(value=v, color=c) for v, c in steps])


NEUTRAL = _steps((None, "text"))
UTILISATION = _steps((None, "green"), (0.7, "orange"), (0.85, "red"))       # share of capacity
PROVISIONING = _steps((None, "blue"), (0.3, "green"), (1.0, "red"))         # used / requested: blue = waste, red = bursting past request
ERRORS = _steps((None, "green"), (0.01, "orange"), (0.05, "red"))           # error or retransmit ratio
THROTTLING = _steps((None, "green"), (0.1, "orange"), (0.25, "red"))        # share of CFS periods throttled
LATENCY = _steps((None, "green"), (0.3, "orange"), (1, "red"))              # seconds
PROBLEMS = _steps((None, "green"), (1, "red"))                              # anything above 0 needs a look
