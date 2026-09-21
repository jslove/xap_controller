"""A service call must be visible in the state machine immediately.

The entities opt out of Home Assistant's polling, and `entity_service_call` only writes
an entity's state back after a service when `should_poll` is true. So each setter has to
publish for itself. The stub suite could not see this: its `async_write_ha_state`
accepted the call and threw it away. Here the call goes through the real service layer
and is checked in the real state machine, with no refresh tick in between.
"""

import pytest

from ha_helpers import call, setup

ZONE = "media_player.zone_kitchen_dining"
SOURCE = "media_player.source_wiim"


async def test_zone_volume_set_is_published_at_once(hass, entry):
    await setup(hass, entry)
    await call(hass, "media_player", "volume_set",
               {"entity_id": ZONE, "volume_level": 0.5})
    assert hass.states.get(ZONE).attributes["volume_level"] == pytest.approx(0.5, abs=1e-3)


async def test_zone_mute_is_published_at_once(hass, entry):
    await setup(hass, entry)
    await call(hass, "media_player", "volume_mute",
               {"entity_id": ZONE, "is_volume_muted": True})
    assert hass.states.get(ZONE).attributes["is_volume_muted"] is True


async def test_zone_source_select_is_published_at_once(hass, entry):
    """The zone never re-reads its source, so this write is the only way it updates."""
    await setup(hass, entry)
    await call(hass, "media_player", "select_source",
               {"entity_id": ZONE, "source": "Home Assistant"})
    assert hass.states.get(ZONE).attributes["source"] == "Home Assistant"


async def test_source_mute_turns_it_off_at_once(hass, entry):
    """A source's on/off is its mute; the two used to be able to disagree."""
    await setup(hass, entry)
    assert hass.states.get(SOURCE).state == "on"
    await call(hass, "media_player", "volume_mute",
               {"entity_id": SOURCE, "is_volume_muted": True})
    assert hass.states.get(SOURCE).state == "off"
    await call(hass, "media_player", "volume_mute",
               {"entity_id": SOURCE, "is_volume_muted": False})
    assert hass.states.get(SOURCE).state == "on"


async def test_the_write_reaches_the_unit(hass, entry, unit):
    """Not just the state machine: the hardware model moved too."""
    await setup(hass, entry)
    await call(hass, "media_player", "volume_mute",
               {"entity_id": ZONE, "is_volume_muted": True})
    assert unit.mute[("O", "7")] == 1 and unit.mute[("O", "8")] == 1
