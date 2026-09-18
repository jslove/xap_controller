"""The trim number entities, which are disabled by default.

None of these tests tick the refresh timer before looking. The number platform reads
through the connection media_player opens, and forwarded together the two platforms
raced; number usually won, and its entities were unavailable until the first tick.
"""

import pytest

from ha_helpers import call, enable_trim, setup


async def test_an_enabled_trim_arrives_with_its_value_and_bounds(hass, entry):
    trim = enable_trim(hass, entry, 9, "source_wiim_trim")
    await setup(hass, entry)
    state = hass.states.get(trim)
    assert float(state.state) == pytest.approx(-1.11, abs=0.01)
    assert state.attributes["max"] == pytest.approx(10.89)
    assert state.attributes["min"] == pytest.approx(10.89 - 20.0)


async def test_an_enabled_trim_arrives_with_its_value_after_a_reload(hass, entry):
    trim = enable_trim(hass, entry, 9, "source_wiim_trim")
    await setup(hass, entry)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert float(hass.states.get(trim).state) == pytest.approx(-1.11, abs=0.01)


async def test_disabled_trims_do_not_touch_the_unit(hass, entry, unit):
    """Home Assistant runs update_before_add for disabled entities as well.

    Harmless while the platforms raced, because the trim found no connection to read
    through; with media_player set up first, the same call would read every channel's
    MAXGAIN and gain on each setup and reload for entities nobody turned on. Nothing
    else reads an input's MAXGAIN, so any such read is a trim entity's.
    """
    await setup(hass, entry)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert unit.count("getMaxGain", "I") == 0, unit.calls
    assert hass.states.get("number.source_wiim_trim") is None


async def test_set_value_is_published_at_once(hass, entry, unit):
    """should_poll is False, so without its own state write the slider springs back."""
    trim = enable_trim(hass, entry, 9, "source_wiim_trim")
    await setup(hass, entry)
    await call(hass, "number", "set_value", {"entity_id": trim, "value": -3.0})
    assert float(hass.states.get(trim).state) == pytest.approx(-3.0, abs=0.01)
    assert unit.gain[("I", "9")] == pytest.approx(-3.0, abs=0.01)


async def test_a_value_outside_the_window_is_refused(hass, entry, unit):
    """Refused against the real bounds - not accepted against the -65..+20 placeholder,
    and not skipped without a word, which is what a service call does to an entity that
    is still unavailable."""
    from homeassistant.exceptions import ServiceValidationError

    trim = enable_trim(hass, entry, 9, "source_wiim_trim")
    await setup(hass, entry)
    with pytest.raises(ServiceValidationError):
        await call(hass, "number", "set_value", {"entity_id": trim, "value": 15.0})
    assert unit.gain[("I", "9")] == pytest.approx(-1.11)
