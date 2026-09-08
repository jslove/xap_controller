"""Registration, teardown and argument parsing for xap_controller.send_command."""

import asyncio

import pytest


class FakeServices:
    def __init__(self):
        self.registered = {}

    def has_service(self, domain, service):
        return (domain, service) in self.registered

    def async_register(self, domain, service, handler, schema=None, supports_response=None):
        self.registered[(domain, service)] = handler

    def async_remove(self, domain, service):
        self.registered.pop((domain, service), None)


class FakeHass:
    def __init__(self):
        self.data = {}
        self.services = FakeServices()

    async def async_add_executor_job(self, fn):
        return fn()


class FakeEntry:
    def __init__(self, entry_id):
        self.entry_id = entry_id


class FakeConn:
    def __init__(self, name="a", reply="OK"):
        self.name = name
        self.reply = reply
        self.calls = []

        class _Lock:
            def __enter__(self_inner):
                return None

            def __exit__(self_inner, *a):
                return False

        self._lock = _Lock()

    def XAPCommand(self, verb, *args, unitCode=0, rtnCount=2):
        self.calls.append((verb, args, unitCode, rtnCount))
        if isinstance(self.reply, Exception):
            raise self.reply
        return self.reply


class Call:
    def __init__(self, **data):
        data.setdefault("unit", 0)
        data.setdefault("return_count", 16)
        self.data = data


def setup(component, conns):
    hass = FakeHass()
    for entry_id, conn in conns.items():
        hass.data.setdefault(component.DOMAIN, {})[entry_id] = conn
    component._register_send_command(hass)
    handler = hass.services.registered[(component.DOMAIN, component.SERVICE_SEND_COMMAND)]
    return hass, handler


# --- connection resolution ---------------------------------------------------------

def hass_with(component, conns):
    hass = FakeHass()
    hass.data[component.DOMAIN] = dict(conns)
    return hass


def test_a_single_entry_needs_no_entry_id(component):
    conn = FakeConn()
    assert component._connection_for(hass_with(component, {"e1": conn})) is conn


def test_entry_id_selects_among_several(component):
    a, b = FakeConn("a"), FakeConn("b")
    hass = hass_with(component, {"e1": a, "e2": b})
    assert component._connection_for(hass, "e2") is b


def test_several_entries_without_entry_id_is_refused_not_guessed(component):
    """Guessing would silently talk to whichever entry set up first."""
    hass = hass_with(component, {"e1": FakeConn("a"), "e2": FakeConn("b")})
    with pytest.raises(Exception) as err:
        component._connection_for(hass)
    assert "entry_id" in str(err.value)


def test_an_unknown_entry_id_is_refused(component):
    hass = hass_with(component, {"e1": FakeConn()})
    with pytest.raises(Exception):
        component._connection_for(hass, "nope")


def test_no_connection_at_all_is_refused(component):
    with pytest.raises(Exception):
        component._connection_for(hass_with(component, {}))


# --- teardown ----------------------------------------------------------------------

def test_the_service_goes_away_with_the_last_entry(component):
    hass, _ = setup(component, {"e1": FakeConn()})
    component.async_release_connection(hass, FakeEntry("e1"))
    assert not hass.services.has_service(component.DOMAIN, component.SERVICE_SEND_COMMAND)


def test_the_service_survives_while_another_entry_is_up(component):
    hass, _ = setup(component, {"e1": FakeConn("a"), "e2": FakeConn("b")})
    component.async_release_connection(hass, FakeEntry("e1"))
    assert hass.services.has_service(component.DOMAIN, component.SERVICE_SEND_COMMAND)
    assert list(hass.data[component.DOMAIN]) == ["e2"]


def test_a_reloaded_entry_does_not_leave_a_dead_connection_behind(component):
    """The reported bug: unload then set up again must reach the new connection."""
    old, new = FakeConn("old"), FakeConn("new")
    hass, _ = setup(component, {"e1": old})
    component.async_release_connection(hass, FakeEntry("e1"))
    hass.data.setdefault(component.DOMAIN, {})["e1"] = new
    component._register_send_command(hass)
    handler = hass.services.registered[(component.DOMAIN, component.SERVICE_SEND_COMMAND)]
    asyncio.run(handler(Call(command="VER")))
    assert new.calls and not old.calls


# --- argument parsing --------------------------------------------------------------

def test_a_quoted_argument_stays_one_token(component):
    conn = FakeConn()
    _, handler = setup(component, {"e1": conn})
    asyncio.run(handler(Call(command='LABEL 5 O "Living Room"')))
    verb, args, _, _ = conn.calls[0]
    assert (verb, args) == ("LABEL", ("5", "O", "Living Room"))


def test_plain_arguments_are_unchanged(component):
    conn = FakeConn()
    _, handler = setup(component, {"e1": conn})
    asyncio.run(handler(Call(command="GAIN 7 O")))
    assert conn.calls[0][:2] == ("GAIN", ("7", "O"))


def test_an_unbalanced_quote_is_a_validation_error_not_a_traceback(component):
    _, handler = setup(component, {"e1": FakeConn()})
    with pytest.raises(Exception):
        asyncio.run(handler(Call(command='LABEL 5 O "Living')))


@pytest.mark.parametrize("raw", ["", "   "])
def test_an_empty_command_is_refused(component, raw):
    _, handler = setup(component, {"e1": FakeConn()})
    with pytest.raises(Exception):
        asyncio.run(handler(Call(command=raw)))


def test_a_refused_command_comes_back_as_data(component):
    from XAPX00 import XAPRespError

    conn = FakeConn(reply=XAPRespError("Argument error"))
    _, handler = setup(component, {"e1": conn})
    out = asyncio.run(handler(Call(command="BOGUS 1")))
    assert "error" in out and "response" not in out
