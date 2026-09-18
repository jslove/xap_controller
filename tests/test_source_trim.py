"""Source input trim: the dB number entity, the reported-level clamp, and startup.

Covers #29 (a source could report volume_level > 1.0), #30 (_firstConnect flattened a
multi-input source to input 0's trim) and #31 (trim as a dB number entity).
"""

import asyncio
import json
import math

import pytest


class FakeLock:
    def __enter__(self):
        return None

    def __exit__(self, *a):
        return False


class FakeConn:
    """A unit holding a real gain and ceiling per input channel, in dB."""

    conn_id = "test"
    stereo = 0
    connectionLive = True

    def __init__(self, gains=None, ceilings=None):
        self.gains = dict(gains or {})
        self.ceilings = dict(ceilings or {})
        self.set_calls = []
        self.set_stereo = []
        self._lock = FakeLock()

    def _ceiling(self, channel):
        return self.ceilings.get(channel, 20.0)

    def getMaxGain(self, channel, group="I", unitCode=0, stereo=1):
        return self._ceiling(channel)

    def getPropGain(self, channel, group="I", unitCode=0, stereo=1):
        return 10.0 ** ((self.gains[channel] - self._ceiling(channel)) / 20.0)

    def setPropGain(self, channel, prop, isAbsolute=1, group="I", unitCode=0, stereo=1):
        self.set_calls.append((channel, prop))
        self.set_stereo.append(stereo)
        self.gains[channel] = self._ceiling(channel) + 20.0 * math.log10(prop)
        return prop

    def getMute(self, channel, group="I", unitCode=0, stereo=1):
        return 0

    def setMute(self, channel, group="I", isMuted=0, unitCode=0, stereo=1):
        return isMuted


class FakeHass:
    def __init__(self, conns=None):
        self.data = {"xap_controller": dict(conns or {})}

    async def async_add_executor_job(self, fn):
        return fn()


class FakeEntry:
    def __init__(self, sources, entry_id="e1", conn_type="serial"):
        self.entry_id = entry_id
        self.data = {"sources": json.dumps(sources), "connection_type": conn_type}
        self.on_unload = []

    def async_on_unload(self, fn):
        self.on_unload.append(fn)


async def _run(fn):
    return fn()


def make_source(component, conn, inputs):
    src = component.XAPSource(None, conn, "Src", inputs)
    src._xap = _run
    return src


# --- #29: a source above its own ceiling ------------------------------------------

def test_a_source_above_its_ceiling_reports_the_ceiling(component, caplog):
    """getPropGain returns > 1.0, which Home Assistant will not accept as a level."""
    conn = FakeConn(gains={9: 0.0}, ceilings={9: -3.0})   # 3 dB above its ceiling
    src = make_source(component, conn, [9])
    level = asyncio.run(src._get_volume_level())
    assert level == 1.0


def test_it_says_so_the_first_time_rather_than_clamping_silently(component, caplog):
    """A silent clamp recreates the blindness that made the output case hard to find."""
    conn = FakeConn(gains={9: 0.0}, ceilings={9: -3.0})
    src = make_source(component, conn, [9])
    asyncio.run(src._get_volume_level())
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert warnings, "expected one warning on the first crossing"
    assert "3.00 dB above" in warnings[0].message


def test_it_does_not_warn_again_every_poll(component, caplog):
    conn = FakeConn(gains={9: 0.0}, ceilings={9: -3.0})
    src = make_source(component, conn, [9])
    for _ in range(5):
        asyncio.run(src._get_volume_level())
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 1


def test_a_recurrence_is_reported_again(component, caplog):
    """The latch has to reset, or a second excursion is invisible."""
    conn = FakeConn(gains={9: 0.0}, ceilings={9: -3.0})
    src = make_source(component, conn, [9])
    asyncio.run(src._get_volume_level())
    conn.ceilings[9] = 6.0                      # back under the ceiling
    asyncio.run(src._get_volume_level())
    conn.ceilings[9] = -3.0                     # and above it again
    asyncio.run(src._get_volume_level())
    assert len([r for r in caplog.records if r.levelname == "WARNING"]) == 2


def test_a_normal_level_is_untouched_and_quiet(component, caplog):
    conn = FakeConn(gains={9: -10.0}, ceilings={9: 0.0})
    src = make_source(component, conn, [9])
    level = asyncio.run(src._get_volume_level())
    assert level == pytest.approx(10.0 ** (-10.0 / 20.0))
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_a_zone_above_its_ceiling_is_clamped_too(component):
    """max_gain need not name every output, so the zone getter wants the same guard."""
    conn = FakeConn(gains={7: 0.0}, ceilings={7: -3.0})
    zone = component.XAPZone(None, conn, {}, "Zone", [7])
    zone._xap = _run
    assert asyncio.run(zone._get_volume_level()) == 1.0


# --- #30: startup must not rewrite the hardware ------------------------------------

def test_startup_does_not_write_input_trim(component):
    """_firstConnect used to write input 0's level back over every input."""
    conn = FakeConn(gains={9: -6.0, 10: -12.0}, ceilings={9: 0.0, 10: 0.0})
    src = make_source(component, conn, [9, 10])
    asyncio.run(src._firstConnect())
    assert conn.set_calls == [], "startup wrote to the unit"


def test_a_pair_trimmed_apart_survives_startup(component):
    """The user-visible shape: channel balance set deliberately, kept across a restart."""
    conn = FakeConn(gains={9: -6.0, 10: -12.0}, ceilings={9: 0.0, 10: 0.0})
    src = make_source(component, conn, [9, 10])
    asyncio.run(src._firstConnect())
    assert conn.gains[9] == pytest.approx(-6.0)
    assert conn.gains[10] == pytest.approx(-12.0)


def test_the_entity_still_reports_input_0(component):
    conn = FakeConn(gains={9: -6.0, 10: -12.0}, ceilings={9: 0.0, 10: 0.0})
    src = make_source(component, conn, [9, 10])
    asyncio.run(src._firstConnect())
    assert src.volume_level == pytest.approx(10.0 ** (-6.0 / 20.0))


# --- #31: the trim number entity ---------------------------------------------------

def build(number_platform, conn, sources):
    added = []
    entry = FakeEntry(sources)
    hass = FakeHass({entry.entry_id: conn})
    asyncio.run(number_platform.async_setup_entry(hass, entry, added.extend))
    return added


def test_one_entity_per_input_channel(component, number_platform):
    conn = FakeConn(gains={9: -6.0, 10: -6.0}, ceilings={9: 0.0, 10: 0.0})
    entities = build(number_platform, conn, {"Laptop": [9, 10]})
    assert len(entities) == 2


def test_a_single_input_source_is_not_suffixed(component, number_platform):
    conn = FakeConn(gains={9: -6.0}, ceilings={9: 0.0})
    entity = build(number_platform, conn, {"Laptop": [9]})[0]
    assert entity.name == "Source: Laptop trim"


def test_channels_are_distinguishable_on_a_multi_input_source(component, number_platform):
    conn = FakeConn(gains={9: -6.0, 10: -6.0}, ceilings={9: 0.0, 10: 0.0})
    names = [e.name for e in build(number_platform, conn, {"Laptop": [9, 10]})]
    assert names == ["Source: Laptop trim 0:9", "Source: Laptop trim 0:10"]


def test_unique_ids_do_not_collide(component, number_platform):
    conn = FakeConn(gains={9: -6.0, 10: -6.0}, ceilings={9: 0.0, 10: 0.0})
    ids = [e.unique_id for e in build(number_platform, conn, {"Laptop": [9, 10]})]
    assert len(set(ids)) == 2


def test_it_is_a_config_entity_disabled_by_default(component, number_platform):
    """Both are what keep it out of voice assistants, bridges and broad automations."""
    conn = FakeConn(gains={9: -6.0}, ceilings={9: 0.0})
    entity = build(number_platform, conn, {"Laptop": [9]})[0]
    assert entity.entity_category == "config"
    assert entity.entity_registry_enabled_default is False


def test_it_reports_absolute_dB_not_a_proportion(component, number_platform):
    conn = FakeConn(gains={9: -6.0}, ceilings={9: 0.0})
    entity = build(number_platform, conn, {"Laptop": [9]})[0]
    asyncio.run(entity.async_update())
    assert entity.native_value == pytest.approx(-6.0)
    assert entity.native_unit_of_measurement == "dB"


def test_the_range_is_bounded_to_the_ceiling_and_a_trim_window(component, number_platform):
    conn = FakeConn(gains={9: -6.0}, ceilings={9: -1.11})
    entity = build(number_platform, conn, {"Laptop": [9]})[0]
    asyncio.run(entity.async_update())
    assert entity.native_max_value == pytest.approx(-1.11)
    assert entity.native_min_value == pytest.approx(-1.11 - number_platform.TRIM_RANGE_DB)


def test_setting_a_value_writes_that_gain(component, number_platform):
    conn = FakeConn(gains={9: -6.0}, ceilings={9: 0.0})
    entity = build(number_platform, conn, {"Laptop": [9]})[0]
    asyncio.run(entity.async_update())
    asyncio.run(entity.async_set_native_value(-3.0))
    assert conn.gains[9] == pytest.approx(-3.0)
    assert entity.native_value == pytest.approx(-3.0)


def test_a_value_above_the_ceiling_is_clamped_to_it(component, number_platform):
    """The ceiling is the clipping guard; the entity must not offer a way past it."""
    conn = FakeConn(gains={9: -6.0}, ceilings={9: -1.11})
    entity = build(number_platform, conn, {"Laptop": [9]})[0]
    asyncio.run(entity.async_update())
    asyncio.run(entity.async_set_native_value(10.0))
    assert conn.gains[9] == pytest.approx(-1.11)


def test_a_value_below_the_window_is_clamped_to_it(component, number_platform):
    conn = FakeConn(gains={9: -6.0}, ceilings={9: 0.0})
    entity = build(number_platform, conn, {"Laptop": [9]})[0]
    asyncio.run(entity.async_update())
    asyncio.run(entity.async_set_native_value(-100.0))
    assert conn.gains[9] == pytest.approx(-number_platform.TRIM_RANGE_DB)


def test_setting_one_channel_leaves_its_pair_alone(component, number_platform):
    """The whole point of one entity per channel."""
    conn = FakeConn(gains={9: -6.0, 10: -12.0}, ceilings={9: 0.0, 10: 0.0})
    entities = build(number_platform, conn, {"Laptop": [9, 10]})
    asyncio.run(entities[0].async_update())
    asyncio.run(entities[0].async_set_native_value(-3.0))
    assert conn.gains[9] == pytest.approx(-3.0)
    assert conn.gains[10] == pytest.approx(-12.0)


def test_the_connection_is_resolved_per_call_not_captured(component, number_platform):
    """So a reload cannot leave the entity talking to a dead connection."""
    old = FakeConn(gains={9: -6.0}, ceilings={9: 0.0})
    entry = FakeEntry({"Laptop": [9]})
    hass = FakeHass({entry.entry_id: old})
    added = []
    asyncio.run(number_platform.async_setup_entry(hass, entry, added.extend))
    entity = added[0]

    new = FakeConn(gains={9: -9.0}, ceilings={9: 0.0})
    hass.data["xap_controller"][entry.entry_id] = new
    asyncio.run(entity.async_update())
    assert entity.native_value == pytest.approx(-9.0)


def test_an_unparseable_source_does_not_stop_the_others(component, number_platform):
    conn = FakeConn(gains={9: -6.0}, ceilings={9: 0.0})
    entities = build(number_platform, conn, {"Bad": ["1:2:3:4:5"], "Laptop": [9]})
    assert [e.name for e in entities] == ["Source: Laptop trim"]


def test_the_write_pairs_under_stereo_mode(component, number_platform):
    """The one place stereo=0 must NOT be forced.

    XAPSource's own volume write lets the @stereo decorator pair the channel, so forcing
    stereo=0 here would make the trim entity the only thing that sets one half of a pair
    and silently leaves the other behind - which is the configuration this was first
    deployed onto, one channel per source with stereo on.
    """
    conn = FakeConn(gains={9: -6.0}, ceilings={9: 0.0})
    entity = build(number_platform, conn, {"WiiM": [9]})[0]
    asyncio.run(entity.async_update())
    asyncio.run(entity.async_set_native_value(-3.0))
    assert conn.set_stereo == [1], "stereo=0 was forced, halving a stereo pair"


def test_the_window_stretches_to_hold_a_gain_below_it(component, number_platform):
    """Found on hardware: an input at -4.19 dB against an unconfigured +20 dB ceiling.

    The window hangs off the ceiling, so 0..+20 put the channel's own current value
    below its own minimum - an entity reporting a number it would refuse to accept.
    """
    conn = FakeConn(gains={9: -4.19}, ceilings={9: 20.0})
    entity = build(number_platform, conn, {"WiiM": [9]})[0]
    asyncio.run(entity.async_update())
    assert entity.native_value == pytest.approx(-4.19)
    assert entity.native_min_value <= entity.native_value
    assert entity.native_max_value == pytest.approx(20.0)


def test_a_stretched_window_still_lets_the_value_be_restored(component, number_platform):
    conn = FakeConn(gains={9: -4.19}, ceilings={9: 20.0})
    entity = build(number_platform, conn, {"WiiM": [9]})[0]
    asyncio.run(entity.async_update())
    asyncio.run(entity.async_set_native_value(0.0))
    asyncio.run(entity.async_set_native_value(-4.19))
    assert conn.gains[9] == pytest.approx(-4.19)


def test_the_window_never_goes_below_the_hardware_floor(component, number_platform):
    conn = FakeConn(gains={9: -64.0}, ceilings={9: -60.0})
    entity = build(number_platform, conn, {"WiiM": [9]})[0]
    asyncio.run(entity.async_update())
    assert entity.native_min_value >= number_platform.HW_MIN_GAIN_DB


def test_a_configured_ceiling_still_gives_the_plain_window(component, number_platform):
    """The normal case must not change: ceiling at the top, TRIM_RANGE_DB below it."""
    conn = FakeConn(gains={9: -1.11}, ceilings={9: 10.89})
    entity = build(number_platform, conn, {"Laptop": [9]})[0]
    asyncio.run(entity.async_update())
    assert entity.native_max_value == pytest.approx(10.89)
    assert entity.native_min_value == pytest.approx(10.89 - number_platform.TRIM_RANGE_DB)


def test_a_missing_connection_is_quiet_at_first(component, number_platform, caplog):
    """The number platform can set up before media_player fills hass.data."""
    entry = FakeEntry({"WiiM": [9]})
    hass = FakeHass({})                       # no connection registered yet
    added = []
    asyncio.run(number_platform.async_setup_entry(hass, entry, added.extend))
    assert added[0].available is False
    assert not [r for r in caplog.records if r.levelname == "WARNING"]


def test_a_connection_that_never_arrives_is_reported(component, number_platform, caplog):
    entry = FakeEntry({"WiiM": [9]})
    hass = FakeHass({})
    added = []
    asyncio.run(number_platform.async_setup_entry(hass, entry, added.extend))
    for _ in range(number_platform.LOOKUP_MISSES_BEFORE_WARNING + 3):
        added[0].available
    warnings = [r for r in caplog.records if r.levelname == "WARNING"]
    assert len(warnings) == 1, "expected exactly one, not one per attempt"
    assert "still no connection" in warnings[0].message


def test_the_miss_counter_resets_once_the_connection_appears(component, number_platform,
                                                             caplog):
    entry = FakeEntry({"WiiM": [9]})
    hass = FakeHass({})
    added = []
    asyncio.run(number_platform.async_setup_entry(hass, entry, added.extend))
    added[0].available                                    # one miss during startup
    hass.data["xap_controller"][entry.entry_id] = FakeConn(gains={9: -6.0}, ceilings={9: 0.0})
    assert added[0].available is True
    hass.data["xap_controller"].clear()
    for _ in range(number_platform.LOOKUP_MISSES_BEFORE_WARNING - 1):
        added[0].available
    assert not [r for r in caplog.records if r.levelname == "WARNING"], \
        "the counter did not reset, so the warning came early"
