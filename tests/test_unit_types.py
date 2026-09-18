"""Unit types: a chain can mix Converge models, and each answers only to its own prefix.

Found 2026-09-18: two 880Ts (#D0, #D1) gained a plain 880 at device ID 2. Every
command to unit 2 went out as "#D2 ..." and nothing answered - the 880 listens for
"#12". One device type per connection cannot say that; this field names the
exceptions and _build_xapconn hands them to XAPX00.
"""

import sys
import types

import pytest


@pytest.mark.parametrize("raw,expected", [
    ("", {}),
    ("   ", {}),
    ("2:CP880", {2: "CP880"}),
    (" 2 : CP880 , 3:CP880TA ", {2: "CP880", 3: "CP880TA"}),
    ("2:CP880,", {2: "CP880"}),
])
def test_valid_unit_types(config_flow, raw, expected):
    assert config_flow._validate_unit_types(raw) == expected


@pytest.mark.parametrize("raw", [
    "CP880",          # no unit
    "2",              # no type
    "2:CP999",        # unknown model
    "8:CP880",        # unit out of range
    "x:CP880",
    "2:CP880,2:CP880T",  # same unit twice
    '{"2": "CP880"}',    # JSON is the other fields' format, not this one's
])
def test_invalid_unit_types_rejected(config_flow, raw):
    with pytest.raises(config_flow.vol.Invalid):
        config_flow._validate_unit_types(raw)


def test_build_xapconn_passes_unit_types_through(config_flow, monkeypatch):
    """The field is only useful if it reaches the library's constructor."""
    seen = {}

    class FakeXAPX00:
        def __init__(self, *args, **kwargs):
            seen.update(kwargs)

    monkeypatch.setitem(sys.modules, "XAPX00", types.SimpleNamespace(XAPX00=FakeXAPX00))
    config_flow._build_xapconn({
        config_flow.CONF_CONNECTION_TYPE: "telnet",
        config_flow.CONF_HOST: "xap.local",
        config_flow.CONF_TYPE: "CP880T",
        config_flow.CONF_UNIT_TYPES: "2:CP880",
    })
    assert seen["XAPType"] == "CP880T"
    assert seen["unit_types"] == {2: "CP880"}


def test_build_xapconn_without_the_field_sends_no_overrides(config_flow, monkeypatch):
    """An entry saved before the field existed must behave exactly as it did."""
    seen = {}

    class FakeXAPX00:
        def __init__(self, *args, **kwargs):
            seen.update(kwargs)

    monkeypatch.setitem(sys.modules, "XAPX00", types.SimpleNamespace(XAPX00=FakeXAPX00))
    config_flow._build_xapconn({config_flow.CONF_TYPE: "CP880T"})
    assert seen["unit_types"] == {}
