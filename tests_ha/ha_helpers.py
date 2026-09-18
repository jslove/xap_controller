"""Shared steps for the real-Home-Assistant suite."""

from datetime import timedelta


async def setup(hass, entry):
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def call(hass, domain, service, data):
    await hass.services.async_call(domain, service, data, blocking=True)
    await hass.async_block_till_done()


async def tick(hass, seconds=31):
    """Advance past one serial refresh period and let the refresh finish.

    A time-interval listener runs as a background task, which async_block_till_done
    does not wait for unless asked - without it the refresh has barely started.
    """
    from homeassistant.util import dt as dt_util
    from pytest_homeassistant_custom_component.common import async_fire_time_changed

    async_fire_time_changed(hass, dt_util.utcnow() + timedelta(seconds=seconds))
    await hass.async_block_till_done(wait_background_tasks=True)


def enable_trim(hass, entry, channel, object_id):
    """Register a trim entity as enabled before setup - they are disabled by default.

    Pre-creating the registry entry is what a user toggling "Enabled" leaves behind, and
    it pins the entity_id rather than relying on the name slugging a particular way.
    """
    from homeassistant.helpers import entity_registry as er

    er.async_get(hass).async_get_or_create(
        "number", "xap_controller", f"XAP-Trim-{entry.entry_id}-0-{channel}",
        config_entry=entry, suggested_object_id=object_id,
    )
    return f"number.{object_id}"
