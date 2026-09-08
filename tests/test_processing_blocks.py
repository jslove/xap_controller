"""Which processing block feeds which output, and what happens when they differ.

The bug this guards against is silent: a zone whose outputs are fed by different blocks
routes every output into whichever block the first one used. `_get_source` only inspects
`_outputs[0]`, so it reports the source set correctly while half the zone is silent.
"""

import asyncio

import pytest


class FakeConn:
    conn_id = "test"
    stereo = 0
    matrixGeo = 12
    connectionLive = True

    def __init__(self, blocks=None):
        # blocks maps (unit, output) -> the block letter feeding it, or None for direct
        self.blocks = blocks or {}
        self.probes = []
        self.routes = []

    def getMatrixRouting(self, inp, out, inGroup="I", outGroup="O", unitCode=0, stereo=1):
        if inGroup == "P":
            self.probes.append((unitCode, out, inp))
            return 1 if self.blocks.get((unitCode, out)) == inp else 0
        return 0

    def setMatrixRouting(self, inp, out, state, inGroup="I", outGroup="O",
                         unitCode=0, stereo=1):
        self.routes.append((unitCode, inp, inGroup, out, outGroup, state))
        return state


class FakeSource:
    def __init__(self, chan):
        self.chan = chan

    def getSource(self, unit, num=0):
        return self.chan, "I"

    def __str__(self):
        return "Src"


def make_zone(component, conn, outputs):
    zone = component.XAPZone(None, conn, {"Src": FakeSource(9)}, "Zone", outputs)
    zone._xap = lambda fn: _run(fn)
    return zone


async def _run(fn):
    return fn()


def test_each_output_resolves_its_own_block(component):
    conn = FakeConn({(0, 3): "A", (0, 4): "B"})
    zone = make_zone(component, conn, [3, 4])
    assert asyncio.run(zone._feeding_block(3, 0)) == "A"
    assert asyncio.run(zone._feeding_block(4, 0)) == "B"


def test_a_direct_output_is_cached_as_direct(component):
    """None must be cached too, or an unblocked output is re-probed on every call."""
    conn = FakeConn({})
    zone = make_zone(component, conn, [3])
    assert asyncio.run(zone._feeding_block(3, 0)) is None
    probes = len(conn.probes)
    assert asyncio.run(zone._feeding_block(3, 0)) is None
    assert len(conn.probes) == probes, "second call re-probed instead of using the cache"


def test_the_cache_is_not_shared_between_outputs(component):
    """The regression: output 4 must not inherit output 3's block."""
    conn = FakeConn({(0, 3): "A", (0, 4): "B"})
    zone = make_zone(component, conn, [3, 4])
    asyncio.run(zone._feeding_block(3, 0))
    assert asyncio.run(zone._feeding_block(4, 0)) == "B"


def test_the_cache_is_keyed_by_unit_too(component):
    conn = FakeConn({(0, 1): "A", (1, 1): "C"})
    zone = make_zone(component, conn, ["0:1", "1:1"])
    assert asyncio.run(zone._feeding_block(1, 0)) == "A"
    assert asyncio.run(zone._feeding_block(1, 1)) == "C"


def test_selecting_a_source_routes_each_output_into_its_own_block(component):
    """The user-visible consequence: both halves of the zone must get the source."""
    conn = FakeConn({(0, 3): "A", (0, 4): "B"})
    zone = make_zone(component, conn, [3, 4])
    asyncio.run(zone.async_select_source("Src"))
    destinations = {(out, grp) for _, _, _, out, grp, state in conn.routes if state}
    assert destinations == {("A", "P"), ("B", "P")}


def test_a_block_the_unit_refuses_does_not_take_the_zone_down(component):
    class Refusing(FakeConn):
        def getMatrixRouting(self, inp, out, inGroup="I", outGroup="O",
                             unitCode=0, stereo=1):
            if inGroup == "P" and inp in "EFGH":
                raise component.XAPRespError("Argument error")
            return super().getMatrixRouting(inp, out, inGroup, outGroup, unitCode, stereo)

    conn = Refusing({(0, 3): "C"})
    zone = make_zone(component, conn, [3])
    assert asyncio.run(zone._feeding_block(3, 0)) == "C"


def test_an_840t_style_unit_with_only_four_blocks_falls_through_to_direct(component):
    """A–D answer, E–H are refused; a direct output must still resolve to None."""
    class FourBlocks(FakeConn):
        def getMatrixRouting(self, inp, out, inGroup="I", outGroup="O",
                             unitCode=0, stereo=1):
            if inGroup == "P" and inp in "EFGH":
                raise component.XAPCommError("no such block")
            return super().getMatrixRouting(inp, out, inGroup, outGroup, unitCode, stereo)

    zone = make_zone(component, FourBlocks({}), [3])
    assert asyncio.run(zone._feeding_block(3, 0)) is None
