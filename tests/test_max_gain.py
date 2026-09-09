"""The ceiling/clamp path in `_apply_max_gain`.

This is the one function in the component that writes gain to hardware without a person
asking it to, so it is the one worth pinning down.
"""

import asyncio
import json
import math

import pytest


class FakeHass:
    async def async_add_executor_job(self, fn):
        return fn()


class FakeXap:
    """A unit holding a real gain and ceiling per channel, in dB.

    Modelled rather than canned, because the order the component reads and writes in is
    the thing under test: a proportional gain only means something relative to whichever
    ceiling was in place when it was read.
    """

    connectionLive = True

    def __init__(self, gains=None, ceilings=None, refuse=()):
        self.gains = dict(gains or {})
        self.ceilings = dict(ceilings or {})
        self.refuse = set(refuse)
        self.max_writes = []
        self.gain_writes = []
        self.reads = []

    def _ceiling(self, channel):
        return self.ceilings.get(channel, 20.0)  # factory default

    def getMaxGain(self, channel, group="I", unitCode=0, stereo=1):
        self.reads.append(("MAX", channel, unitCode))
        return self._ceiling(channel)

    def setMaxGain(self, channel, gain, group="I", unitCode=0, stereo=1):
        if channel in self.refuse:
            raise RuntimeError(f"channel {channel} refused")
        self.max_writes.append((channel, gain, group, stereo, unitCode))
        self.ceilings[channel] = gain
        return gain

    def getPropGain(self, channel, group="I", unitCode=0, stereo=1):
        self.reads.append(("GAIN", channel, unitCode))
        if channel in self.refuse:
            raise RuntimeError(f"channel {channel} refused")
        return 10.0 ** ((self.gains[channel] - self._ceiling(channel)) / 20.0)

    def setPropGain(self, channel, prop, isAbsolute=1, group="I", unitCode=0, stereo=1):
        self.gain_writes.append((channel, prop, group, stereo, unitCode))
        self.gains[channel] = self._ceiling(channel) + 20.0 * math.log10(prop)
        return prop


def apply(component, gains, config, ceilings=None, refuse=()):
    xap = FakeXap(gains, ceilings, refuse)
    asyncio.run(component._apply_max_gain(FakeHass(), xap, config))
    return xap


def channels(writes):
    return [w[0] for w in writes]


def test_writes_a_ceiling_that_differs_from_the_unit(component):
    xap = apply(component, {7: -20.0, 8: -20.0}, json.dumps({"7": -7.5, "8": -10}),
                ceilings={7: 20.0, 8: 20.0})
    assert xap.max_writes == [(7, -7.5, "O", 0, 0), (8, -10.0, "O", 0, 0)]


def test_an_unchanged_ceiling_is_not_rewritten(component):
    """A restart should not be a device write when nothing has changed."""
    xap = apply(component, {7: -20.0}, json.dumps({"7": -7.5}), ceilings={7: -7.5})
    assert xap.max_writes == []


def test_the_level_is_read_before_the_ceiling_is_written(component):
    """Reading first is what makes the old ceiling knowable at all."""
    xap = apply(component, {7: -20.0}, json.dumps({"7": -7.5}), ceilings={7: 20.0})
    assert xap.reads[0][0] == "GAIN"
    assert xap.max_writes, "expected the ceiling to be written after the read"


def test_ceilings_are_written_per_channel_not_per_stereo_pair(component):
    xap = apply(component, {7: -20.0}, json.dumps({"7": -7.5}), ceilings={7: 20.0})
    assert all(w[3] == 0 for w in xap.max_writes)
    assert all(r[1] == 7 for r in xap.reads)


def test_a_bare_key_means_unit_0(component):
    xap = apply(component, {7: -20.0}, json.dumps({"7": -7.5}), ceilings={7: 20.0})
    assert xap.max_writes[0][4] == 0


def test_a_unit_qualified_key_addresses_that_unit(component):
    """A chained system: without this only the master ever gets a ceiling."""
    xap = apply(component, {1: -20.0}, json.dumps({"1:1": -12.5}), ceilings={1: 20.0})
    assert xap.max_writes == [(1, -12.5, "O", 0, 1)]
    assert all(r[2] == 1 for r in xap.reads)


def test_the_clamp_addresses_the_same_unit_as_the_ceiling(component):
    xap = apply(component, {1: 0.0}, json.dumps({"2:1": -12.5}), ceilings={1: 20.0})
    assert xap.max_writes[0][4] == 2
    assert xap.gain_writes[0][4] == 2


def test_units_are_kept_apart(component):
    xap = apply(component, {3: -20.0}, json.dumps({"3": -7.5, "1:3": -12.0}),
                ceilings={3: 20.0})
    assert [(w[0], w[4]) for w in xap.max_writes] == [(3, 0), (3, 1)]


def test_clamps_a_channel_left_above_its_new_ceiling(component):
    """The 2026-09-06 state: ceilings lowered under gains that were already above them."""
    gains = {1: -12.5, 2: -12.5, 3: -13.34, 4: -13.34,
             5: -13.09, 6: -13.09, 7: -7.5, 8: -7.5}
    ceilings = {c: -15.0 for c in gains}
    config = json.dumps({str(c): -20 for c in gains})
    xap = apply(component, gains, config, ceilings=ceilings)
    assert channels(xap.gain_writes) == [1, 2, 3, 4, 5, 6, 7, 8]
    assert {w[1] for w in xap.gain_writes} == {1.0}
    assert all(v == pytest.approx(-20.0) for v in xap.gains.values())


def test_leaves_a_channel_below_its_ceiling_alone(component):
    xap = apply(component, {7: -20.0, 8: -30.0}, json.dumps({"7": -7.5, "8": -7.5}),
                ceilings={7: -7.5, 8: -7.5})
    assert xap.gain_writes == []


@pytest.mark.parametrize("gain", [-7.5, -7.5001, -7.5 - 1e-9])
def test_at_the_ceiling_is_not_a_clamp(component, gain):
    """Neither XAPX00 build reports a clean 1.0 for a channel sitting on its ceiling.

    2026.04.22 adds 1e-7 dB and returns 1.0000000115; 2026.09.03 subtracts a linear
    epsilon and returns 0.999999. A bare `> 1.0` test would clamp the first on every
    startup and log a "0.00 dB above" warning each time.
    """
    xap = apply(component, {7: gain}, json.dumps({"7": -7.5}), ceilings={7: -7.5})
    assert xap.gain_writes == []


def test_a_real_overshoot_still_clamps(component):
    """0.01 dB is the unit's own reporting resolution, so it must not be swallowed."""
    xap = apply(component, {7: -7.49}, json.dumps({"7": -7.5}), ceilings={7: -7.5})
    assert channels(xap.gain_writes) == [7]


def test_a_malformed_entry_does_not_stop_the_others(component):
    xap = apply(component, {7: 0.0}, json.dumps({"7": -7.5, "9": "not-a-number"}),
                ceilings={7: 20.0})
    assert channels(xap.max_writes) == [7]
    assert channels(xap.gain_writes) == [7]


def test_a_refused_channel_does_not_abort_the_rest(component):
    xap = apply(component, {7: 0.0, 8: 0.0}, json.dumps({"7": -7.5, "8": -7.5}),
                ceilings={7: 20.0, 8: 20.0}, refuse=(7,))
    assert channels(xap.gain_writes) == [8]


def test_an_offline_unit_is_left_alone(component):
    """Every channel would otherwise raise and log a full traceback."""
    xap = FakeXap({7: 0.0})
    xap.connectionLive = False
    asyncio.run(component._apply_max_gain(FakeHass(), xap, json.dumps({"7": -7.5})))
    assert xap.max_writes == [] and xap.gain_writes == [] and xap.reads == []


@pytest.mark.parametrize("config", ["", "   ", None, "{not json", '["not", "a", "map"]'])
def test_nothing_is_written_without_usable_config(component, config):
    xap = FakeXap({7: 0.0})
    asyncio.run(component._apply_max_gain(FakeHass(), xap, config))
    assert xap.max_writes == [] and xap.gain_writes == []


def test_a_gain_above_an_unchanged_ceiling_is_reported_as_an_error(component, caplog):
    """Nothing in the integration can produce this; something else moved the gain."""
    apply(component, {7: -5.0}, json.dumps({"7": -7.5}), ceilings={7: -7.5})
    assert any(r.levelname == "ERROR" and "outside this integration" in r.message
               for r in caplog.records), [r.message for r in caplog.records]


def test_a_gain_above_a_ceiling_we_just_lowered_is_only_a_warning(component, caplog):
    """The expected consequence of lowering a ceiling, not a fault."""
    apply(component, {7: -5.0}, json.dumps({"7": -7.5}), ceilings={7: 0.0})
    levels = {r.levelname for r in caplog.records}
    assert "ERROR" not in levels
    assert "WARNING" in levels


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
