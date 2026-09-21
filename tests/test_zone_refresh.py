"""A zone's refresh tick must pick up a mute or level changed outside Home Assistant.

`XAPZone.async_update` was `pass`, on the grounds that nothing else could change a zone.
send_command can (`MUTE 5 O 1`), and so can G-Ware and the front panel. Unlike a source,
where muted means off, a zone's on/off comes from routing - so a zone muted from outside
stayed "on" with is_volume_muted false, and nothing short of a restart corrected it.

The ticks here go through the real refresh loop from `register_for_polling`, and the
entity records what each `async_write_ha_state` would have put in the state machine,
because what the entity holds in memory is not what Home Assistant shows.
"""

import asyncio
import logging

import pytest


class FakeLock:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


class FakeUnit:
    """Remembers each output's mute and level and every crosspoint, like the XAP800.

    Every call is logged as a query or a write, so a test can say what a tick cost and
    that it changed nothing on the unit.
    """

    conn_id = "test"
    stereo = 0
    connectionLive = True
    matrixGeo = 12

    def __init__(self, routes=()):
        self._lock = FakeLock()
        self.muted = {}    # (unit, output) -> 0 / 1
        self.level = {}    # (unit, output) -> proportion of that channel's MAXGAIN
        self.routes = {key: 1 for key in routes}   # (unit, in, inGroup, out, outGroup)
        self.queries = []
        self.writes = []

    def getMute(self, channel, group="I", unitCode=0, stereo=1):
        self.queries.append(("MUTE", unitCode, channel))
        return self.muted.get((unitCode, channel), 0)

    def setMute(self, channel, isMuted=1, group="I", unitCode=0, stereo=1):
        self.writes.append(("MUTE", unitCode, channel))
        # MUTE <chan> O 2 toggles; the reply carries the state the channel landed in.
        key = (unitCode, channel)
        now = 1 - self.muted.get(key, 0) if int(isMuted) == 2 else int(isMuted)
        self.muted[key] = now
        return now

    def getPropGain(self, channel, group="I", unitCode=0, stereo=1):
        self.queries.append(("GAIN", unitCode, channel))
        return self.level.get((unitCode, channel), 0.5)

    def setPropGain(self, channel, gain, isAbsolute=1, group="I", unitCode=0, stereo=1):
        self.writes.append(("GAIN", unitCode, channel))
        self.level[(unitCode, channel)] = gain
        return gain

    def getMatrixRouting(self, inp, out, inGroup="I", outGroup="O", unitCode=0,
                         stereo=1):
        self.queries.append(("MTRX", unitCode, out))
        return self.routes.get((unitCode, inp, inGroup, out, outGroup), 0)

    def setMatrixRouting(self, inp, out, state, inGroup="I", outGroup="O", unitCode=0,
                         stereo=1):
        self.writes.append(("MTRX", unitCode, out))
        self.routes[(unitCode, inp, inGroup, out, outGroup)] = state
        return state


class FakeHass:
    def __init__(self):
        self.data = {}


class FakeEntry:
    entry_id = "e1"
    data = {"connection_type": "serial"}

    def async_on_unload(self, fn):
        pass


async def _run(fn):
    return fn()


# Input 9 is the WiiM, routed to both halves of the Patio pair.
WIIM_ON_PATIO = [(0, 9, "I", 5, "O"), (0, 9, "I", 6, "O")]


def published(entity):
    """What Home Assistant's state machine holds for the entity after the last write."""
    return entity.writes[-1]


def zone(component, unit, outputs=(5, 6)):
    """A zone as it stands once set up: first-connected, added, and recording
    (state, is_volume_muted, volume_level, source) at every state write.

    The sources carry an expansion bus so they resolve from an output on any unit.
    """
    sources = {
        name: component.XAPSource(None, unit, name, [spec])
        for name, spec in (("Laptop", "0:1:P:E"), ("WiiM", "0:9:O:E"))
    }
    sources["Off"] = 0
    z = component.XAPZone(None, unit, sources, "Patio", list(outputs))
    z._xap = _run
    asyncio.run(z.async_added_to_hass())    # _firstConnect runs before there is an id
    z.hass = object()
    z.entity_id = "media_player.zone_patio"
    z.writes = []
    z.async_write_ha_state = lambda: z.writes.append(
        (z.state, z.is_volume_muted, z.volume_level, z.source))
    unit.queries.clear()
    unit.writes.clear()
    return z


def tick(component, *entities):
    """One pass of the entry's refresh timer, exactly as Home Assistant runs it."""
    import homeassistant.helpers.event as event

    component.register_for_polling(FakeHass(), FakeEntry(), list(entities))
    action, _interval = event.tracked[-1]
    asyncio.run(action(None))


def test_refresh_follows_a_mute_made_outside_home_assistant(component):
    """The case that prompted this: `MUTE 5 O 1` through send_command. Routing is
    untouched, so the zone stays "on" - and its is_volume_muted is on show."""
    unit = FakeUnit(routes=WIIM_ON_PATIO)
    z = zone(component, unit)
    tick(component, z)
    assert published(z) == ("on", False, 0.5, "WiiM")

    unit.muted[(0, 5)] = 1

    tick(component, z)
    assert published(z) == ("on", True, 0.5, "WiiM")


def test_refresh_follows_an_unmute_made_outside_home_assistant(component):
    unit = FakeUnit(routes=WIIM_ON_PATIO)
    z = zone(component, unit)
    asyncio.run(z.async_mute_volume(True))
    assert published(z) == ("on", True, 0.5, "WiiM")

    unit.muted[(0, 5)] = 0

    tick(component, z)
    assert published(z) == ("on", False, 0.5, "WiiM")


def test_refresh_follows_a_level_set_outside_home_assistant(component):
    """G-Ware, the front panel, or `GAIN 5 O <dB> A`."""
    unit = FakeUnit(routes=WIIM_ON_PATIO)
    z = zone(component, unit)

    unit.level[(0, 5)] = 0.25

    tick(component, z)
    assert published(z) == ("on", False, 0.25, "WiiM")


def test_refresh_agrees_with_what_the_setters_published(component):
    """Nothing in the unit changed between setter and tick, so nothing published may."""
    unit = FakeUnit(routes=WIIM_ON_PATIO)
    z = zone(component, unit)
    steps = [
        lambda: z.async_mute_volume(True),
        lambda: z.async_mute_volume(False),
        lambda: z.async_set_volume_level(0.3),
    ]
    for step in steps:
        asyncio.run(step())
        after_setter = published(z)
        tick(component, z)
        assert published(z) == after_setter


def test_a_tick_costs_one_mute_and_one_gain_query_and_writes_nothing(component):
    """Serial is one port under one lock, so what a tick costs is the point.

    Both reads are on the first output only, however many the zone has, and routing is
    not read at all: that costs a query per configured source, on every tick.
    """
    unit = FakeUnit(routes=WIIM_ON_PATIO)
    z = zone(component, unit, outputs=(5, 6, 5, 6))

    tick(component, z)

    assert unit.queries == [("MUTE", 0, 5), ("GAIN", 0, 5)]
    assert unit.writes == []


def test_a_zone_on_a_chained_unit_is_read_on_that_unit(component):
    unit = FakeUnit()
    z = zone(component, unit, outputs=("1:5", "1:6"))

    tick(component, z)

    assert unit.queries == [("MUTE", 1, 5), ("GAIN", 1, 5)]


def test_a_level_above_the_ceiling_found_by_a_tick_is_reported_as_the_ceiling(
        component, caplog):
    """The 2.371 reading: a GAIN raised above MAXGAIN from outside, now seen on a tick
    rather than only at the next setup."""
    unit = FakeUnit(routes=WIIM_ON_PATIO)
    z = zone(component, unit)

    unit.level[(0, 5)] = 1.4

    with caplog.at_level(logging.WARNING):
        tick(component, z)
    assert published(z)[2] == 1.0
    assert any("above its own MAXGAIN" in r.message for r in caplog.records)


def test_an_unreachable_unit_is_not_queried(component):
    """connectionLive drops on a failed command; the tick must not hammer a dead port."""
    unit = FakeUnit(routes=WIIM_ON_PATIO)
    z = zone(component, unit)
    tick(component, z)
    before = published(z)

    unit.connectionLive = False
    unit.muted[(0, 5)] = 1

    tick(component, z)
    assert unit.queries == [("MUTE", 0, 5), ("GAIN", 0, 5)]   # the first tick's only
    assert published(z) == before
