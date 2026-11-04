"""Shared test helpers: a conforming panel, a conforming page around it, and the test's own panels."""
import build
import components as c


def ok(title="G", **k):
    """Panel that passes every conformance rule: sliced, described, with a unit."""
    return c.graph(title, "desc", c.COUNT, (c.per_pod(f'up{{{c.C}}}'), "{{cluster}}"), **k)


def table(window, **k):
    return c.grid("T", "d", ("v", c.per_pod(f"increase(up{{{c.C}}}[{window}])"), c.COUNT, None), **k)


def page(*sections, **k):
    """A dashboard of the given sections, padded to a conforming page: adds System Vitals and Golden Signals
    (standard panels only) when a test leaves them out. panels() skips the standard panels."""
    given = {sec[0]: sec for sec in sections}
    head = [given.get("System Vitals") or c.vitals(),
            given.get("Golden Signals") or c.golden_signals()]
    rest = [sec for sec in sections if sec[0] not in ("System Vitals", "Golden Signals")]
    return c.dashboard("T", "desc", [], *head, *rest, **k)


def render(*sections, **k):
    """JSON of page(*sections), as build.py renders it."""
    return build.render(page(*sections, **k), "team-test", "team")


def ext(*lines):
    """JSON of lines as an extension on a conforming page."""
    return render(c.extension("Why?", *lines))


def panels(j):
    """The test's own panels: no rows, quadrant headers or standard panels."""
    return [p for top in j["panels"] for p in [top, *top.get("panels", [])]
            if p["type"] not in ("row", "text") and p.get("title") not in c.STANDARD_TITLES]
