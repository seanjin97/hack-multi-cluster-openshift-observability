"""Layout: sections made of lines of (panel, width); every line fills WIDTH. page.dashboard() places them."""
from .panels import header

WIDTH = 24  # Grafana's grid; every line of panels fills it
MAX_PER_LINE = 4  # graphs or tables per line; more and they get too narrow to read. Tiles are exempt.


def even(n, total=WIDTH):
    """Widths for n panels sharing `total` columns, remainder to the first ones."""
    return [total // n + (i < total % n) for i in range(n)]


def wrap(panels, per_line, total=WIDTH):
    """Panels split into lines of at most per_line, each line sharing `total` columns evenly."""
    chunks = [panels[i:i + per_line] for i in range(0, len(panels), per_line)]
    return [list(zip(c, even(len(c), total))) for c in chunks]


def vitals(*tiles):
    """System Vitals: the open first row, one line of tiles."""
    return "System Vitals", False, [list(zip(tiles, even(len(tiles))))]


def golden_signals(latency, traffic, errors, saturation):
    """Golden Signals: Latency | Traffic, then Errors | Saturation. Each quadrant is a list of panels."""
    half = WIDTH // 2

    def pair(left, right, left_panels, right_panels):
        l, r = wrap(left_panels, MAX_PER_LINE // 2, half), wrap(right_panels, MAX_PER_LINE // 2, half)
        assert len(l) == len(r), (f"{left[0]} and {right[0]} sit side by side, so they must wrap to the same number of lines: "
                                  f"give them panel counts that wrap alike ({MAX_PER_LINE // 2} per line each)")
        return [[(header(*left), half), (header(*right), half)], *[a + b for a, b in zip(l, r)]]

    return "Golden Signals", False, [
        *pair(("Latency", "How long requests take"), ("Traffic", "How much demand"), latency, traffic),
        *pair(("Errors", "How often requests fail"), ("Saturation", "How full the system is"), errors, saturation),
    ]


def extension(title, *lines):
    """A collapsed row for one extra question. Each line is a panel or a tuple of panels, sharing the width evenly.
    A tuple longer than MAX_PER_LINE wraps onto more lines."""
    lines = [l if isinstance(l, tuple) else (l,) for l in lines]
    return title, True, [w for l in lines for w in wrap(list(l), MAX_PER_LINE)]
