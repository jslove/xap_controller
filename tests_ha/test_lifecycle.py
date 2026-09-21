"""Setup, unload and reload, through a real ConfigEntry.

The unload path is only exercised by a reload - never by a restart - which is how a bug
there survived several restarts of a live install before an options change reloaded the
entry and left it in failed_unload.
"""

from homeassistant.config_entries import ConfigEntryState

from ha_helpers import setup, tick


async def test_setup_loads_and_creates_the_entities(hass, entry):
    await setup(hass, entry)
    assert entry.state is ConfigEntryState.LOADED
    for eid in ("media_player.zone_kitchen_dining", "media_player.zone_patio",
                "media_player.source_wiim", "media_player.source_home_assistant"):
        assert hass.states.get(eid) is not None, f"{eid} was not created"


async def test_the_entry_unloads(hass, entry):
    """The regression: an unload callback returned a dict, and HA tried to await it."""
    await setup(hass, entry)
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.NOT_LOADED


async def test_the_entry_reloads(hass, entry):
    await setup(hass, entry)
    assert await hass.config_entries.async_reload(entry.entry_id)
    await hass.async_block_till_done()
    assert entry.state is ConfigEntryState.LOADED
    assert hass.states.get("media_player.zone_kitchen_dining").state != "unavailable"


async def test_repeated_reloads_do_not_stack_timers(hass, entry, unit):
    """Each reload must replace the refresh timer, not add another beside it.

    A stacked timer would also keep refreshing the previous load's entities, so the
    count below goes up with every reload that leaked one.
    """
    await setup(hass, entry)
    for _ in range(3):
        assert await hass.config_entries.async_reload(entry.entry_id)
        await hass.async_block_till_done()

    unit.calls.clear()
    await tick(hass)
    # one refresh reads each source's mute and each zone's mute once: 2 + 2
    assert unit.count("getMute") == 4, unit.calls


async def test_the_service_goes_away_with_the_last_entry(hass, entry):
    await setup(hass, entry)
    assert hass.services.has_service("xap_controller", "send_command")
    assert await hass.config_entries.async_unload(entry.entry_id)
    await hass.async_block_till_done()
    assert not hass.services.has_service("xap_controller", "send_command")
