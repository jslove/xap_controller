"""A source's published state must follow its mute, from every path that changes it.

A source has no power of its own - off *is* muted. The refresh derived on/off from the
mute, but `volume_mute` changed only the mute, so the entity published "on" with
is_volume_muted true until the next tick flipped it to "off", and an unmute after that
tick published "off" for a whole refresh period (30s on serial) while the input was live.

These tests record what each `async_write_ha_state` would have put in the state machine,
because what the entity holds in memory is not what Home Assistant shows.
"""

import asyncio

import pytest


class FakeLock:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


class FakeUnit:
    """Remembers each input's mute and answers like the XAP800 does."""

    conn_id = "test"
    stereo = 0
    connectionLive = True

    def __init__(self, muted=()):
        self._lock = FakeLock()
        self.muted = {chan: 1 for chan in muted}

    def getPropGain(self, channel, group="I", unitCode=0, stereo=1):
        return 0.5

    def getMute(self, channel, group="I", unitCode=0, stereo=1):
        return self.muted.get(channel, 0)

    def setMute(self, channel, isMuted=1, group="I", unitCode=0, stereo=1):
        # MUTE <chan> I 2 toggles; the reply carries the state the channel landed in.
        now = 1 - self.getMute(channel) if int(isMuted) == 2 else int(isMuted)
        self.muted[channel] = now
        return now


async def _run(fn):
    return fn()


def published(entity):
    """What Home Assistant's state machine holds for the entity after the last write."""
    return entity.writes[-1]


def source(component, unit, inputs=(9,)):
    """An added source that records (state, is_volume_muted) at every state write."""
    e = component.XAPSource(None, unit, "WiiM", list(inputs))
    e.hass = object()
    e.entity_id = "media_player.source_wiim"
    e._xap = _run
    e.writes = []
    e.async_write_ha_state = lambda: e.writes.append((e.state, e.is_volume_muted))
    return e


def test_volume_mute_publishes_off_straight_away(component):
    """The 2026-09-18 report: muted at the unit, still "on" and unmuted in HA."""
    unit = FakeUnit()
    e = source(component, unit)
    asyncio.run(e.async_update())
    assert e.state == "on"

    asyncio.run(e.async_mute_volume(True))

    assert unit.muted[9] == 1
    assert published(e) == ("off", True)


def test_volume_unmute_after_a_refresh_publishes_on_straight_away(component):
    """The tick marks a muted source off; the unmute must not leave it there."""
    unit = FakeUnit()
    e = source(component, unit)
    asyncio.run(e.async_mute_volume(True))
    asyncio.run(e.async_update())   # a refresh tick landing mid-announcement
    assert e.state == "off"

    asyncio.run(e.async_mute_volume(False))

    assert unit.muted[9] == 0
    assert published(e) == ("on", False)


def test_refresh_agrees_with_what_the_setter_published(component):
    """Mute, then tick: nothing in the unit changed, so nothing published may change."""
    unit = FakeUnit()
    e = source(component, unit)
    for mute in (True, False):
        asyncio.run(e.async_mute_volume(mute))
        after_setter = published(e)
        asyncio.run(e.async_update())
        assert (e.state, e.is_volume_muted) == after_setter


def test_refresh_follows_a_mute_made_outside_home_assistant(component):
    """send_command, G-Ware or the front panel - the tick is the only way to see it."""
    unit = FakeUnit()
    e = source(component, unit)
    asyncio.run(e.async_update())
    unit.setMute(9, isMuted=1)

    asyncio.run(e.async_update())

    assert (e.state, e.is_volume_muted) == ("off", True)


def test_toggle_publishes_the_state_the_unit_landed_in(component):
    unit = FakeUnit(muted=[9])
    e = source(component, unit)

    asyncio.run(e.async_mute_volume(2))

    assert published(e) == ("on", False)


@pytest.mark.parametrize("call, expected", [
    (lambda e: e.async_turn_off(), ("off", True)),
    (lambda e: e.async_turn_on(), ("on", False)),
])
def test_turn_on_and_off_are_the_mute(component, call, expected):
    unit = FakeUnit(muted=[9] if expected[0] == "on" else [])
    e = source(component, unit)
    e._first_connect = 1

    asyncio.run(call(e))

    assert published(e) == expected


def test_every_input_of_a_multi_input_source_is_muted(component):
    unit = FakeUnit()
    e = source(component, unit, inputs=(9, 10))

    asyncio.run(e.async_mute_volume(True))

    assert unit.muted == {9: 1, 10: 1}
    assert published(e) == ("off", True)
