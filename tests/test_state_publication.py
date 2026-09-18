"""Setters must publish their own state.

The entities set `_attr_should_poll = False`, and Home Assistant's `entity_service_call`
only writes an entity's state back after a service call when `should_poll` is true. So
every setter has to do it itself. Without this a `volume_set` updates `self._volume` and
the state machine keeps the old value until the next refresh tick — a dashboard slider
springs back after being dragged, and an automation that selects a source and then reads
it gets the previous one. `XAPZone` was worst hit: its `async_update` was `pass`, so it
had relied entirely on the post-service write - and it still never re-reads its source.
"""

import asyncio

import pytest


class FakeLock:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


class FakeConn:
    conn_id = "test"
    stereo = 0
    connectionLive = True
    matrixGeo = 12

    def __init__(self):
        self._lock = FakeLock()

    def getMaxGain(self, channel, group="I", unitCode=0, stereo=1):
        return 0.0

    def getPropGain(self, channel, group="I", unitCode=0, stereo=1):
        return 0.5

    def setPropGain(self, channel, gain, isAbsolute=1, group="I", unitCode=0, stereo=1):
        return gain

    def getMute(self, channel, group="I", unitCode=0, stereo=1):
        return 0

    def setMute(self, channel, group="I", isMuted=0, unitCode=0, stereo=1):
        return isMuted

    def setMatrixRouting(self, inp, out, state, inGroup="I", outGroup="O",
                         unitCode=0, stereo=1):
        return state

    def getMatrixRouting(self, inp, out, inGroup="I", outGroup="O", unitCode=0, stereo=1):
        return 0


async def _run(fn):
    return fn()


class FakeSource:
    def getSource(self, unit, num=0):
        return 9, "I"

    def __str__(self):
        return "Src"


def added(entity):
    """Mark the entity as added, which is what makes publishing legal."""
    entity.hass = object()
    entity.entity_id = "media_player.x"
    entity._xap = _run
    entity.state_writes = 0
    return entity


def source(component):
    return added(component.XAPSource(None, FakeConn(), "Src", [9]))


def zone(component):
    return added(component.XAPZone(None, FakeConn(), {"Src": FakeSource(), "Off": 0},
                                   "Zone", [7]))


@pytest.mark.parametrize("call", [
    lambda e: e.async_set_volume_level(0.4),
    lambda e: e.async_mute_volume(1),
    lambda e: e.async_turn_on(),
    lambda e: e.async_turn_off(),
])
def test_every_source_setter_publishes(component, call):
    e = source(component)
    asyncio.run(call(e))
    assert e.state_writes > 0


@pytest.mark.parametrize("call", [
    lambda e: e.async_set_volume_level(0.4),
    lambda e: e.async_mute_volume(1),
    lambda e: e.async_select_source("Src"),
    lambda e: e.async_turn_on(),
    lambda e: e.async_turn_off(),
])
def test_every_zone_setter_publishes(component, call):
    """The tick re-reads mute and level but not the source, so select_source relies on it."""
    e = zone(component)
    asyncio.run(call(e))
    assert e.state_writes > 0


def test_publishing_is_skipped_before_the_entity_is_added(component):
    """The setters are also reached from _firstConnect; writing state then raises."""
    e = component.XAPSource(None, FakeConn(), "Src", [9])
    e._xap = _run
    e.state_writes = 0
    asyncio.run(e.async_set_volume_level(0.4))
    assert e.state_writes == 0


def test_first_connect_does_not_publish_before_add(component):
    e = component.XAPSource(None, FakeConn(), "Src", [9])
    e._xap = _run
    e.state_writes = 0
    asyncio.run(e._firstConnect())
    assert e.state_writes == 0
