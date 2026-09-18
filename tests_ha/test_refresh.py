"""The refresh tick picks up what was changed on the unit from outside Home Assistant.

G-Ware, the front panel and a raw `send_command` all reach the unit without going
through an entity. A zone used to be `pass` on the tick, so one muted from outside stayed
"on" and unmuted while silent until a restart.
"""

import pytest

from ha_helpers import setup, tick

ZONE = "media_player.zone_kitchen_dining"
SOURCE = "media_player.source_wiim"


async def test_a_zone_muted_from_outside_shows_after_a_tick(hass, entry, unit):
    await setup(hass, entry)
    assert hass.states.get(ZONE).attributes["is_volume_muted"] is False
    unit.mute[("O", "7")] = 1          # as a raw `MUTE 7 O 1` would
    await tick(hass)
    assert hass.states.get(ZONE).attributes["is_volume_muted"] is True


async def test_a_zone_level_changed_from_outside_shows_after_a_tick(hass, entry, unit):
    await setup(hass, entry)
    unit.gain[("O", "7")] = -7.5       # at its -7.5 ceiling
    await tick(hass)
    assert hass.states.get(ZONE).attributes["volume_level"] == pytest.approx(1.0, abs=1e-3)


async def test_a_source_muted_from_outside_turns_off_after_a_tick(hass, entry, unit):
    await setup(hass, entry)
    assert hass.states.get(SOURCE).state == "on"
    unit.mute[("I", "9")] = 1
    await tick(hass)
    assert hass.states.get(SOURCE).state == "off"


async def test_nothing_changes_before_the_tick(hass, entry, unit):
    """The external change is invisible until the period elapses - that is the design."""
    await setup(hass, entry)
    unit.mute[("O", "7")] = 1
    await tick(hass, seconds=5)        # well inside the 30s serial period
    assert hass.states.get(ZONE).attributes["is_volume_muted"] is False


async def test_a_gain_above_its_ceiling_is_reported_as_the_ceiling(hass, entry, unit, caplog):
    """Raised from outside; the entity stays valid and says what happened."""
    await setup(hass, entry)
    unit.gain[("O", "7")] = 0.0        # 7.5 dB above the -7.5 ceiling
    await tick(hass)
    assert hass.states.get(ZONE).attributes["volume_level"] == pytest.approx(1.0, abs=1e-3)
    assert any("above its own MAXGAIN" in r.message for r in caplog.records)
