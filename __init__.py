"""ClearOne XAP Controller integration."""
import json
import logging

from homeassistant.config_entries import ConfigEntry, SOURCE_IMPORT
from homeassistant.const import Platform, CONF_NAME
from homeassistant.core import HomeAssistant

from .config_flow import CONF_PATH, CONF_SOURCES, CONF_ZONES

DOMAIN = "xap_controller"
PLATFORMS = [Platform.MEDIA_PLAYER]

_LOGGER = logging.getLogger(__name__)


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Import configuration from configuration.yaml if present."""
    if DOMAIN not in config:
        return True
    for entry_config in config[DOMAIN]:
        hass.async_create_task(
            hass.config_entries.flow.async_init(
                DOMAIN,
                context={"source": SOURCE_IMPORT},
                data=entry_config,
            )
        )
    return True


async def _options_updated(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Reload the entry so edited options actually take effect.

    The options flow writes straight into entry.data, but nothing re-reads it: entities
    take expose_source_gain at construction and max_gain is applied once during setup. Without
    this listener, saving the form stores the new value and the running integration keeps
    the old one until Home Assistant restarts - a source stays "does not support volume"
    with the box ticked, and an edited ceiling is never written to the unit.
    """
    await hass.config_entries.async_reload(entry.entry_id)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up XAP Controller from a config entry."""
    entry.async_on_unload(entry.add_update_listener(_options_updated))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    from .media_player import async_release_connection

    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        async_release_connection(hass, entry)
    return unloaded
