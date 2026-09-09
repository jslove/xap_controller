"""Channel-spec parsing, and the config-flow validation in front of it.

These two have to agree: config_flow decides what the user may save, parse_output and
parse_source decide what the component can actually do with it. A spec the first accepts
and the second cannot parse is a crash at setup, long after the mistake was made.
"""

import json

import pytest


def make_zone(component, outputs):
    return component.XAPZone(None, _Conn(), {}, "Zone", outputs)


def make_source(component, inputs):
    return component.XAPSource(None, _Conn(), "Src", inputs)


class _Conn:
    conn_id = "test"
    stereo = 0


@pytest.mark.parametrize(
    "spec,expected",
    [
        (3, (0, 3)),
        ("2:1", (2, 1)),
        ("0:8", (0, 8)),
    ],
)
def test_parse_output_accepts_documented_forms(component, spec, expected):
    assert make_zone(component, [spec]).parse_output(spec) == expected


def test_parse_output_accepts_a_bare_numeric_string(component):
    """`{"Kitchen": ["3"]}` passes config-flow validation, so it must parse.

    _validate_sources_zones accepts `(int, str)` for every channel entry, and the README's
    own examples mix the two. A string that is just digits and carries no unit therefore
    reaches parse_output, and has to mean unit 0 exactly as the integer 3 does.
    """
    assert make_zone(component, ["3"]).parse_output("3") == (0, 3)


def test_parse_output_rejects_nonsense(component):
    with pytest.raises(Exception):
        make_zone(component, [1]).parse_output("kitchen")


@pytest.mark.parametrize(
    "spec,chan,unit,bus,busgrp",
    [
        (9, 9, 0, None, "E"),
        ("1:9", 9, 1, None, "E"),
        ("1:9:O", 9, 1, "O", "E"),
        ("1:9:O:E", 9, 1, "O", "E"),
        ("11", 11, 0, None, "E"),
    ],
)
def test_parse_source_accepts_documented_forms(component, spec, chan, unit, bus, busgrp):
    src = make_source(component, [spec])
    got = src._inputs[0]
    assert (got["CHAN"], got["UNIT"], got["BUS"], got["BUSGRP"]) == (chan, unit, bus, busgrp)


def test_source_channel_count_follows_the_spec_list(component):
    assert make_source(component, [9, 10]).numChannels == 2


# --- config flow validation -------------------------------------------------------

@pytest.mark.parametrize(
    "raw", ['{"Kitchen": [3]}', '{"Kitchen": ["2:1", "2:2"]}', '{"A": [1], "B": [2]}', "{}"]
)
def test_valid_sources_zones_accepted(config_flow, raw):
    config_flow._validate_sources_zones(raw, "zones")


@pytest.mark.parametrize(
    "raw", ['{"Kitchen": 3}', '["Kitchen"]', '{"Kitchen": [1.5]}', "{not json"]
)
def test_invalid_sources_zones_rejected(config_flow, raw):
    with pytest.raises(Exception):
        config_flow._validate_sources_zones(raw, "zones")


# --- malformed specs: caught at config time, and survivable at parse time -----------

@pytest.mark.parametrize(
    "spec,why",
    [
        ("1:2:3", "a zone output is unit:channel, nothing longer"),
        ("1:2:3:4:5", "longer than any documented form"),
        ("a:2", "unit is not a number"),
        ("1:b", "channel is not a number"),
        ("kitchen", "not a channel at all"),
        ("", "empty"),
        ("   ", "blank"),
        (1.5, "not an int or a string"),
        (True, "a bool is not a channel"),
    ],
)
def test_malformed_zone_specs_are_rejected_at_config_time(config_flow, spec, why):
    with pytest.raises(Exception):
        config_flow._validate_channel_spec(spec, "zones")


@pytest.mark.parametrize("spec", [3, "3", "1:3"])
def test_valid_zone_specs_are_accepted(config_flow, spec):
    config_flow._validate_channel_spec(spec, "zones")


@pytest.mark.parametrize("spec", [9, "9", "1:9", "1:9:O", "1:9:O:E"])
def test_valid_source_specs_are_accepted(config_flow, spec):
    """A source may name an expansion bus and its group; a zone output may not."""
    config_flow._validate_channel_spec(spec, "sources")


def test_a_source_bus_spec_is_not_valid_for_a_zone(config_flow):
    config_flow._validate_channel_spec("1:9:O:E", "sources")
    with pytest.raises(Exception):
        config_flow._validate_channel_spec("1:9:O:E", "zones")


@pytest.mark.parametrize("spec", ["1:2:3:4:5", "1:9::E"])
def test_malformed_source_specs_are_rejected_at_config_time(config_flow, spec):
    with pytest.raises(Exception):
        config_flow._validate_channel_spec(spec, "sources")


def test_the_validator_rejects_a_bad_spec_inside_a_zone_list(config_flow):
    with pytest.raises(Exception):
        config_flow._validate_sources_zones('{"Kitchen": [3, "1:2:3"]}', "zones")


@pytest.mark.parametrize("spec", ["1:2:3", "a:2", "1:b"])
def test_parse_output_raises_its_own_error_on_a_bad_spec(component, spec):
    """Not ValueError from an unpack - these reach setup if validation is bypassed."""
    zone = make_zone(component, [1])
    with pytest.raises(Exception) as err:
        zone.parse_output(spec)
    assert "Invalid Output" in str(err.value)


@pytest.mark.parametrize("spec", ["1:2:3:4:5", "a:2", "1:b"])
def test_parse_source_raises_its_own_error_on_a_bad_spec(component, spec):
    """"1:2:3:4:5" matched no comps branch and died on int(None)."""
    with pytest.raises(Exception) as err:
        make_source(component, [spec])
    assert "Invalid Input String" in str(err.value)
