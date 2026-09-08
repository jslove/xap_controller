"""The ceiling/clamp path in `_apply_max_gain`.

This is the one function in the component that writes gain to hardware without a person
asking it to, so it is the one worth pinning down.
"""

import asyncio
import json

import pytest


class FakeHass:
    async def async_add_executor_job(self, fn):
        return fn()


class FakeXap:
    """props maps channel -> proportional gain reported after its ceiling is written."""

    connectionLive = True

    def __init__(self, props=None, refuse=()):
        self.props = props or {}
        self.refuse = set(refuse)
        self.max_writes = []
        self.gain_writes = []

    def setMaxGain(self, channel, gain, group="I", unitCode=0, stereo=1):
        if channel in self.refuse:
            raise RuntimeError(f"channel {channel} refused")
        self.max_writes.append((channel, gain, group, stereo, unitCode))
        return gain

    def getPropGain(self, channel, group="I", unitCode=0, stereo=1):
        return self.props[channel]

    def setPropGain(self, channel, gain, isAbsolute=1, group="I", unitCode=0, stereo=1):
        self.gain_writes.append((channel, gain, group, stereo, unitCode))
        return 1.0


def apply(component, props, config, refuse=()):
    xap = FakeXap(props, refuse)
    asyncio.run(component._apply_max_gain(FakeHass(), xap, config))
    return xap


def channels(writes):
    return [w[0] for w in writes]


def test_writes_every_configured_ceiling(component):
    xap = apply(component, {7: 1.0, 8: 1.0}, json.dumps({"7": -7.5, "8": -10}))
    assert xap.max_writes == [(7, -7.5, "O", 0, 0), (8, -10.0, "O", 0, 0)]


def test_a_bare_key_means_unit_0(component):
    xap = apply(component, {7: 1.0}, json.dumps({"7": -7.5}))
    assert xap.max_writes[0][4] == 0


def test_a_unit_qualified_key_addresses_that_unit(component):
    """A chained system: without this only the master ever gets a ceiling."""
    xap = apply(component, {1: 1.0}, json.dumps({"1:1": -12.5}))
    assert xap.max_writes == [(1, -12.5, "O", 0, 1)]


def test_the_clamp_addresses_the_same_unit_as_the_ceiling(component):
    xap = apply(component, {1: 2.0}, json.dumps({"2:1": -12.5}))
    assert xap.max_writes[0][4] == 2
    assert xap.gain_writes[0][4] == 2


def test_units_are_kept_apart(component):
    xap = apply(component, {3: 1.0}, json.dumps({"3": -7.5, "1:3": -12.0}))
    assert [(w[0], w[4]) for w in xap.max_writes] == [(3, 0), (3, 1)]


def test_an_offline_unit_is_left_alone(component):
    """Every channel would otherwise raise and log a full traceback."""
    xap = FakeXap({7: 2.0})
    xap.connectionLive = False
    asyncio.run(component._apply_max_gain(FakeHass(), xap, json.dumps({"7": -7.5})))
    assert xap.max_writes == [] and xap.gain_writes == []


def test_ceilings_are_written_per_channel_not_per_stereo_pair(component):
    """stereo=0 on every write: the config names channels, so it must write those exactly."""
    xap = apply(component, {7: 1.0}, json.dumps({"7": -7.5}))
    assert all(w[3] == 0 for w in xap.max_writes)


def test_clamps_a_channel_left_above_its_new_ceiling(component):
    """The 2026-09-06 state: ceilings lowered under gains that were already above them."""
    live = {1: 1.3335, 2: 1.3335, 3: 1.2106, 4: 1.2106,
            5: 1.2459, 6: 1.2459, 7: 2.3714, 8: 2.3714}
    config = json.dumps({"1": -12.5, "2": -12.5, "3": -10, "4": -10,
                         "5": -10, "6": -10, "7": -7.5, "8": -7.5})
    xap = apply(component, live, config)
    assert channels(xap.gain_writes) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert {w[1] for w in xap.gain_writes} == {1.0}
    assert {w[2] for w in xap.gain_writes} == {"O"}
    assert all(w[3] == 0 for w in xap.gain_writes)


def test_leaves_a_channel_below_its_ceiling_alone(component):
    xap = apply(component, {7: 0.73, 8: 0.68}, json.dumps({"7": -7.5, "8": -7.5}))
    assert xap.gain_writes == []


@pytest.mark.parametrize("prop", [1.0, 0.999999, 1.0000000115129255])
def test_at_the_ceiling_is_not_a_clamp(component, prop):
    """Neither XAPX00 build reports a clean 1.0 for a channel sitting on its ceiling.

    2026.04.22 adds 1e-7 dB and returns 1.0000000115; 2026.09.03 subtracts a linear
    epsilon and returns 0.999999. A bare `> 1.0` test would clamp the first one on every
    single startup and log a "0.00 dB above" warning each time.
    """
    xap = apply(component, {7: prop}, json.dumps({"7": -7.5}))
    assert xap.gain_writes == []


def test_a_real_overshoot_still_clamps(component):
    """0.01 dB is the unit's own reporting resolution, so it must not be swallowed."""
    xap = apply(component, {7: 1.00115}, json.dumps({"7": -7.5}))
    assert channels(xap.gain_writes) == [7]


def test_a_malformed_entry_does_not_stop_the_others(component):
    xap = apply(component, {7: 2.0}, json.dumps({"7": -7.5, "9": "not-a-number"}))
    assert channels(xap.max_writes) == [7]
    assert channels(xap.gain_writes) == [7]


def test_a_refused_channel_does_not_abort_the_rest(component):
    xap = apply(component, {7: 2.0, 8: 2.0},
                      json.dumps({"7": -7.5, "8": -7.5}), refuse=(7,))
    assert channels(xap.gain_writes) == [8]


@pytest.mark.parametrize("config", ["", "   ", None, "{not json", '["not", "a", "map"]'])
def test_nothing_is_written_without_usable_config(component, config):
    xap = FakeXap({7: 2.0})
    try:
        asyncio.run(component._apply_max_gain(FakeHass(), xap, config))
    except AttributeError:
        pytest.fail("a non-dict config should be ignored, not crash")
    assert xap.max_writes == []
    assert xap.gain_writes == []


# --- config-flow validation of the max_gain keys ------------------------------------

@pytest.mark.parametrize(
    "raw",
    [
        '{"7": -15}',
        '{"7": -15, "8": -10.5}',
        '{"1:1": -12}',
        '{"7": -15, "1:1": -12}',
        '{"0:7": -15}',
        '{"1": 20}',
        '{"1": -65}',
        "",
        "   ",
    ],
)
def test_valid_max_gain_is_accepted(config_flow, raw):
    config_flow._validate_max_gain(raw)


@pytest.mark.parametrize(
    "raw,why",
    [
        ('{"7": -66}', "below the -65 dB floor"),
        ('{"7": 21}', "above the +20 dB maximum"),
        ('{"0": -15}', "channel numbers start at 1"),
        ('{"8:1": -15}', "unit codes stop at 7"),
        ('{"1:0": -15}', "channel numbers start at 1"),
        ('{"1:2:3": -15}', "not a unit:channel pair"),
        ('{"kitchen": -15}', "not a channel at all"),
        ('{"7": -15, "0:7": -12}', "same channel twice"),
        ('{"7": true}', "a bool is not a dB value"),
        ('{"7": "-15"}', "a string is not a dB value"),
        ('["7", -15]', "must be an object"),
        ("{not json", "must be JSON"),
    ],
)
def test_invalid_max_gain_is_rejected(config_flow, raw, why):
    with pytest.raises(Exception):
        config_flow._validate_max_gain(raw)


@pytest.mark.parametrize(
    "key,expected", [("7", (0, 7)), ("0:7", (0, 7)), ("1:1", (1, 1)), (7, (0, 7))]
)
def test_parse_channel_key(config_flow, key, expected):
    assert config_flow.parse_channel_key(key) == expected


def test_max_gain_bounds_match_the_documented_hardware_range(config_flow):
    """MAX takes a Signed Float of -65.00 - 20.00 dB on XAP and Converge alike."""
    assert (config_flow.MAX_GAIN_MIN_DB, config_flow.MAX_GAIN_MAX_DB) == (-65.0, 20.0)
