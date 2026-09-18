"""Entity refresh: one timer per entry, at a period chosen by transport.

The entities do not self-poll. Home Assistant reads a platform's SCAN_INTERVAL once, so
it is global to media_player — a serial entry and a telnet entry in one install cannot
have different periods through it, and they want different ones.
"""

import asyncio
from datetime import timedelta

import pytest


class FakeEntry:
    def __init__(self, conn_type=None, entry_id="e1"):
        data = {}
        if conn_type is not None:
            data["connection_type"] = conn_type
        self.entry_id = entry_id
        self.data = data
        self.on_unload = []

    def async_on_unload(self, fn):
        self.on_unload.append(fn)


class FakeEntity:
    """Stands in for a source or zone entity as the refresh loop sees it."""

    def __init__(self, name="e", hass=object(), entity_id="media_player.x", boom=False):
        self.name = name
        self.hass = hass
        self.entity_id = entity_id
        self.boom = boom
        self.updates = 0
        self.writes = 0
        self.gate = None

    async def async_update(self):
        self.updates += 1
        if self.gate is not None:
            await self.gate
        if self.boom:
            raise RuntimeError(f"{self.name} failed")

    def async_write_ha_state(self):
        self.writes += 1

    def __str__(self):
        return self.name


class FakeHass:
    def __init__(self):
        self.data = {}


def register(component, entry, entities, hass=None):
    hass = hass or FakeHass()
    component.register_for_polling(hass, entry, entities)
    import homeassistant.helpers.event as event

    action, interval = event.tracked[-1]
    return action, interval


@pytest.fixture(autouse=True)
def _clear_tracker():
    import homeassistant.helpers.event as event

    event.tracked.clear()
    event.unsubscribed.clear()


# --- the period ---------------------------------------------------------------------

def test_serial_gets_the_slower_period(component):
    """One port under one lock: every poll competes with real commands."""
    _, interval = register(component, FakeEntry("serial"), [])
    assert interval == timedelta(seconds=30)


def test_telnet_stays_responsive(component):
    """No single-port contention, so the argument for 30s does not apply."""
    _, interval = register(component, FakeEntry("telnet"), [])
    assert interval == timedelta(seconds=10)


def test_an_entry_with_no_connection_type_is_treated_as_serial(component):
    """Entries imported from YAML predate the field, and YAML was serial-only."""
    _, interval = register(component, FakeEntry(None), [])
    assert interval == timedelta(seconds=30)


def test_an_unknown_transport_falls_back_to_the_safe_period(component):
    _, interval = register(component, FakeEntry("carrier-pigeon"), [])
    assert interval == component.DEFAULT_SCAN_INTERVAL


def test_two_entries_can_have_different_periods(component):
    """The whole point: a module-level SCAN_INTERVAL cannot express this."""
    _, serial = register(component, FakeEntry("serial", "e1"), [])
    _, telnet = register(component, FakeEntry("telnet", "e2"), [])
    assert serial != telnet


# --- teardown -----------------------------------------------------------------------

def test_the_timer_is_unsubscribed_with_the_entry(component):
    entry = FakeEntry("serial")
    register(component, entry, [])
    assert entry.on_unload, "timer would outlive the entry and leak on reload"
    for unsub in entry.on_unload:
        unsub()
    import homeassistant.helpers.event as event
    assert event.unsubscribed


# --- the refresh itself -------------------------------------------------------------

def test_a_tick_updates_and_publishes_every_entity(component):
    a, b = FakeEntity("a"), FakeEntity("b")
    action, _ = register(component, FakeEntry("serial"), [a, b])
    asyncio.run(action(None))
    assert (a.updates, a.writes) == (1, 1)
    assert (b.updates, b.writes) == (1, 1)


def test_one_failing_entity_does_not_stop_the_others(component):
    a, bad, c = FakeEntity("a"), FakeEntity("bad", boom=True), FakeEntity("c")
    action, _ = register(component, FakeEntry("serial"), [a, bad, c])
    asyncio.run(action(None))
    assert a.updates == 1 and c.updates == 1
    assert bad.writes == 0, "a failed update must not publish a state"


def test_an_entity_not_yet_added_is_skipped(component):
    """async_add_entities schedules; the first tick can land before it completes."""
    pending = FakeEntity("pending", entity_id=None)
    ready = FakeEntity("ready")
    action, _ = register(component, FakeEntry("serial"), [pending, ready])
    asyncio.run(action(None))
    assert pending.updates == 0 and ready.updates == 1


def test_entities_are_refreshed_one_at_a_time(component):
    """They all queue behind the same connection lock; gathering only piles threads."""
    order = []

    class Ordered(FakeEntity):
        async def async_update(self):
            order.append(f"start {self.name}")
            await asyncio.sleep(0)
            order.append(f"end {self.name}")

    action, _ = register(component, FakeEntry("serial"),
                         [Ordered("a"), Ordered("b")])
    asyncio.run(action(None))
    assert order == ["start a", "end a", "start b", "end b"]


def test_a_tick_that_overruns_skips_the_next_one(component):
    """On a slow link, overlapping ticks are how a backlog becomes a stall."""

    async def scenario():
        slow = FakeEntity("slow")
        slow.gate = asyncio.Event().wait()
        action, _ = register(component, FakeEntry("serial"), [slow])
        first = asyncio.create_task(action(None))
        await asyncio.sleep(0)
        await action(None)          # second tick while the first is still inside update
        assert slow.updates == 1, "the overlapping tick was not skipped"
        first.cancel()

    asyncio.run(scenario())


def test_the_gate_reopens_after_a_tick_finishes(component):
    """The skip must be a guard, not a latch that stops polling for good."""
    e = FakeEntity("a")
    action, _ = register(component, FakeEntry("serial"), [e])
    asyncio.run(action(None))
    asyncio.run(action(None))
    assert e.updates == 2


def test_a_failing_tick_reopens_the_gate_too(component):
    e = FakeEntity("bad", boom=True)
    action, _ = register(component, FakeEntry("serial"), [e])
    asyncio.run(action(None))
    asyncio.run(action(None))
    assert e.updates == 2


# --- the entities stop self-polling --------------------------------------------------

@pytest.mark.parametrize("cls_name", ["XAPSource", "XAPZone"])
def test_entities_do_not_self_poll(component, cls_name):
    assert getattr(component, cls_name)._attr_should_poll is False


# --- one timer per entry, fed by every platform --------------------------------------

def test_a_second_platform_joins_the_same_timer(component):
    """Two timers on one unit would tick independently and meet at the lock."""
    import homeassistant.helpers.event as event

    hass, entry = FakeHass(), FakeEntry("serial")
    media = [FakeEntity("zone")]
    trims = [FakeEntity("trim")]
    component.register_for_polling(hass, entry, media)
    component.register_for_polling(hass, entry, trims)
    assert len(event.tracked) == 1, "a second timer was started"

    action, _ = event.tracked[0]
    asyncio.run(action(None))
    assert media[0].updates == 1 and trims[0].updates == 1


def test_entities_registered_after_the_timer_started_are_picked_up(component):
    hass, entry = FakeHass(), FakeEntry("serial")
    first = FakeEntity("first")
    action, _ = register(component, entry, [first], hass=hass)
    late = FakeEntity("late")
    component.register_for_polling(hass, entry, [late])
    asyncio.run(action(None))
    assert late.updates == 1


def test_separate_entries_get_separate_timers(component):
    """Different units, different connections - they must not share a tick."""
    import homeassistant.helpers.event as event

    hass = FakeHass()
    component.register_for_polling(hass, FakeEntry("serial", "e1"), [FakeEntity("a")])
    component.register_for_polling(hass, FakeEntry("telnet", "e2"), [FakeEntity("b")])
    assert len(event.tracked) == 2
    assert {i for _, i in event.tracked} == {timedelta(seconds=30), timedelta(seconds=10)}


def test_unloading_clears_the_entry_from_the_store(component):
    """Otherwise a reload appends to the old list and refreshes dead entities."""
    hass, entry = FakeHass(), FakeEntry("serial")
    register(component, entry, [FakeEntity("a")], hass=hass)
    assert hass.data[component.POLL_KEY]
    for unsub in entry.on_unload:
        unsub()
    assert not hass.data[component.POLL_KEY]


def test_a_reload_starts_a_fresh_timer_rather_than_appending(component):
    import homeassistant.helpers.event as event

    hass, entry = FakeHass(), FakeEntry("serial")
    old = FakeEntity("old")
    register(component, entry, [old], hass=hass)
    for unsub in entry.on_unload:
        unsub()

    new = FakeEntity("new")
    action, _ = register(component, entry, [new], hass=hass)
    assert len(event.tracked) == 2
    asyncio.run(action(None))
    assert new.updates == 1 and old.updates == 0, "the dead entity was still refreshed"
