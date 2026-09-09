"""Editing options has to reach the running integration.

The options flow writes into entry.data, but entities read source_trim at construction
and max_gain is applied once during setup. Without an update listener the form saves
successfully and nothing changes until Home Assistant restarts.
"""

import asyncio


class FakeConfigEntries:
    def __init__(self):
        self.forwarded = []
        self.reloaded = []

    async def async_forward_entry_setups(self, entry, platforms):
        self.forwarded.append((entry.entry_id, tuple(platforms)))

    async def async_reload(self, entry_id):
        self.reloaded.append(entry_id)


class FakeHass:
    def __init__(self):
        self.data = {}
        self.config_entries = FakeConfigEntries()


class FakeEntry:
    """Mimics the bits of ConfigEntry the listener wiring touches."""

    def __init__(self, entry_id="e1"):
        self.entry_id = entry_id
        self._listeners = []
        self.on_unload = []

    def add_update_listener(self, listener):
        self._listeners.append(listener)
        return lambda: self._listeners.remove(listener)

    def async_on_unload(self, unsub):
        self.on_unload.append(unsub)

    async def fire_update(self, hass):
        """What Home Assistant does after async_update_entry."""
        for listener in list(self._listeners):
            await listener(hass, self)


def _setup(integration):
    hass, entry = FakeHass(), FakeEntry()
    asyncio.run(integration.async_setup_entry(hass, entry))
    return hass, entry


def test_setup_registers_an_update_listener(integration):
    _, entry = _setup(integration)
    assert entry._listeners, "no update listener; edited options never take effect"


def test_saving_options_reloads_the_entry(integration):
    hass, entry = _setup(integration)
    asyncio.run(entry.fire_update(hass))
    assert hass.config_entries.reloaded == ["e1"]


def test_the_listener_is_unsubscribed_on_unload(integration):
    _, entry = _setup(integration)
    assert entry.on_unload, "listener would outlive the entry and leak on reload"
    for unsub in entry.on_unload:
        unsub()
    assert not entry._listeners


def test_setup_still_forwards_the_platform(integration):
    hass, entry = _setup(integration)
    assert hass.config_entries.forwarded == [("e1", ("media_player",))]
