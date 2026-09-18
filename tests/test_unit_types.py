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


# --- discovery at setup -------------------------------------------------------

import asyncio


class _Hass:
    async def async_add_executor_job(self, fn, *args):
        return fn(*args)


class _Conn:
    def __init__(self, models):
        self.models = models          # {unit: type} of what is really on the chain
        self.asked = []
        self.unit_types = {}

    def discoverUnitType(self, unit):
        self.asked.append(unit)
        return self.models.get(unit)


@pytest.mark.parametrize("sources,zones,expected", [
    ({"A": [1]}, {"K": [3]}, [0]),
    ({"A": ["0:1:O:E"]}, {"K": ["1:3"], "W": ["2:1", "2:2"]}, [0, 1, 2]),
    ({"A": ["3"]}, {"K": ["7"]}, [0]),
    ({}, {}, []),
])
def test_referenced_units(config_flow, sources, zones, expected):
    assert config_flow._referenced_units(sources, zones) == expected


def test_discovery_probes_only_referenced_units(component):
    conn = _Conn({0: "CP880T", 1: "CP880T", 2: "CP880"})
    asyncio.run(component._discover_unit_types(
        _Hass(), conn, {"A": [1]}, {"K": [3], "W": ["2:1"]}))
    assert conn.asked == [0, 2]


def test_discovery_survives_a_silent_unit(component, caplog):
    conn = _Conn({0: "CP880T"})
    asyncio.run(component._discover_unit_types(
        _Hass(), conn, {"A": [1]}, {"W": ["2:1"]}))
    assert conn.asked == [0, 2]
    assert "unit 2 did not answer" in caplog.text


def test_flow_discovery_fills_the_field_for_referenced_units(config_flow, monkeypatch):
    """Submitting sources & zones asks the chain and writes what it learns."""
    class FakeXAPX00:
        def __init__(self, *a, **kw):
            self.kw = kw
        def test_connection(self):
            return True
        def discoverUnitType(self, unit):
            return {0: "CP880T", 1: "CP880T", 2: "CP880"}.get(unit)

    monkeypatch.setitem(sys.modules, "XAPX00", types.SimpleNamespace(XAPX00=FakeXAPX00))
    data = {config_flow.CONF_TYPE: "CP880T", config_flow.CONF_UNIT_TYPES: "5:XAP800"}
    text = config_flow._discover_unit_types(data, [0, 1, 2, 3])
    # 0/1 match the device type (no override), 2 differs, 3 is silent, 5 was
    # entered by hand and not referenced - kept, discovery does not forget.
    assert text == "2:CP880, 5:XAP800"


def test_flow_discovery_keeps_the_field_when_not_connected(config_flow, monkeypatch):
    class FakeXAPX00:
        def __init__(self, *a, **kw): pass
        def test_connection(self): return False

    monkeypatch.setitem(sys.modules, "XAPX00", types.SimpleNamespace(XAPX00=FakeXAPX00))
    data = {config_flow.CONF_TYPE: "CP880T", config_flow.CONF_UNIT_TYPES: "2:CP880"}
    assert config_flow._discover_unit_types(data, [0, 2]) == "2:CP880"
