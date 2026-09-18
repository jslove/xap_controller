"""Make the component importable without Home Assistant installed.

`pytest-homeassistant-custom-component` pulls in the whole of Home Assistant to test what
is, here, a few hundred lines of gain arithmetic and config parsing. These stubs cover the
handful of names the module touches at import time, so the suite runs anywhere with just
pytest — including on a machine that has never had HA on it.

The stubs are deliberately dumb. Anything that needs real Home Assistant behaviour does not
belong in this suite.
"""

import sys
import types

import pytest


def _module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod


def _install_stubs():
    if "homeassistant" in sys.modules:
        return

    _module("homeassistant")

    ce = _module("homeassistant.config_entries")
    ce.SOURCE_IMPORT = "import"

    class _Flow:
        def __init_subclass__(cls, **kwargs):  # domain=... on the subclass
            pass

    ce.ConfigFlow = _Flow
    ce.OptionsFlow = type("OptionsFlow", (), {})
    ce.ConfigEntry = type("ConfigEntry", (), {})

    const = _module("homeassistant.const")
    const.STATE_OFF = "off"
    const.STATE_ON = "on"
    const.CONF_NAME = "name"
    const.Platform = types.SimpleNamespace(MEDIA_PLAYER="media_player", NUMBER="number")
    const.EntityCategory = types.SimpleNamespace(CONFIG="config", DIAGNOSTIC="diagnostic")

    core = _module("homeassistant.core")
    core.HomeAssistant = type("HomeAssistant", (), {})
    core.SupportsResponse = types.SimpleNamespace(OPTIONAL="optional")
    core.callback = lambda fn: fn

    exc = _module("homeassistant.exceptions")

    class HomeAssistantError(Exception):
        pass

    class ServiceValidationError(HomeAssistantError):
        pass

    exc.HomeAssistantError = HomeAssistantError
    exc.ServiceValidationError = ServiceValidationError

    helpers = _module("homeassistant.helpers")

    # Records the registered callback and interval, and hands back an unsub the caller
    # is expected to pass to entry.async_on_unload.
    event = _module("homeassistant.helpers.event")

    def _async_track_time_interval(hass, action, interval, **kwargs):
        event.tracked.append((action, interval))
        return lambda: event.unsubscribed.append(action)

    event.tracked = []
    event.unsubscribed = []
    event.async_track_time_interval = _async_track_time_interval
    helpers.event = event

    cv = _module("homeassistant.helpers.config_validation")
    cv.string = str
    helpers.config_validation = cv

    # Home Assistant writes an entity's state back after a service call ONLY when
    # should_poll is true. These entities opt out, so every setter has to publish for
    # itself - and a stub that silently accepts async_write_ha_state cannot tell whether
    # it was called. Counting it is what makes that testable.
    def _record_write(self):
        self.state_writes = getattr(self, "state_writes", 0) + 1

    comp = _module("homeassistant.components")
    mp = _module("homeassistant.components.media_player")
    # Entity.should_poll defaults True and is backed by _attr_should_poll, which is
    # how an entity opts out of Home Assistant's own polling.
    mp.MediaPlayerEntity = type(
        "MediaPlayerEntity", (),
        {"should_poll": property(lambda self: getattr(self, "_attr_should_poll", True)),
         "async_write_ha_state": _record_write,
         "entity_id": None, "hass": None},
    )
    mp.MediaType = types.SimpleNamespace(MUSIC="music")
    comp.media_player = mp

    # Home Assistant's Entity exposes every `_attr_x` as a read-only `x` property, and
    # the component relies on that rather than defining each one. Reproduce it for the
    # handful the trim entity uses, or every read comes back AttributeError.
    _ATTR_PROPS = (
        "name", "unique_id", "entity_category", "entity_registry_enabled_default",
        "should_poll",
        "native_value", "native_unit_of_measurement", "native_min_value",
        "native_max_value", "native_step", "available",
    )


    def _attr_property(attr):
        return property(lambda self: getattr(self, f"_attr_{attr}", None))

    num = _module("homeassistant.components.number")
    num.NumberEntity = type(
        "NumberEntity", (),
        {**{a: _attr_property(a) for a in _ATTR_PROPS},
         "async_write_ha_state": _record_write,
         "entity_id": None, "hass": None},
    )
    comp.number = num

    mp_const = _module("homeassistant.components.media_player.const")

    class _Feature(int):
        """Enough of an IntFlag for `A | B` in the SUPPORT_ constants."""

        def __or__(self, other):
            return _Feature(int(self) | int(other))

    mp_const.MediaPlayerEntityFeature = types.SimpleNamespace(
        VOLUME_MUTE=_Feature(8), VOLUME_SET=_Feature(4),
        TURN_ON=_Feature(128), TURN_OFF=_Feature(256),
        SELECT_SOURCE=_Feature(2048),
    )
    mp.const = mp_const

    # voluptuous: only Invalid and the schema-building names used at import time.
    vol = _module("voluptuous")

    class Invalid(Exception):
        pass

    vol.Invalid = Invalid
    vol.Schema = lambda *a, **k: types.SimpleNamespace(schema=a[0] if a else None)
    vol.Required = lambda *a, **k: a[0] if a else None
    vol.Optional = lambda *a, **k: a[0] if a else None
    vol.In = lambda *a, **k: a[0] if a else None
    vol.All = lambda *a, **k: a[0] if a else None
    vol.Coerce = lambda *a, **k: a[0] if a else None
    vol.Range = lambda *a, **k: None

    # XAPX00: the entities only ever reach it through the connection object, which every
    # test supplies itself. Nothing here is exercised.
    xap = _module("XAPX00")
    xap.__version__ = "stub"
    xap.XAPX00 = type("XAPX00", (), {})

    class XAPCommError(Exception):
        pass

    class XAPRespError(Exception):
        pass

    xap.XAPCommError = XAPCommError
    xap.XAPRespError = XAPRespError


_install_stubs()

# The component is a flat package at the repo root (hacs.json content_in_root), so the
# root has to be importable and `.config_flow` has to resolve as a relative import.
_ROOT = __import__("pathlib").Path(__file__).resolve().parent.parent
if str(_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(_ROOT.parent))

_PKG = _ROOT.name


@pytest.fixture(scope="session")
def component():
    import importlib

    pkg = importlib.import_module(_PKG)
    return importlib.import_module(f"{_PKG}.media_player")


@pytest.fixture(scope="session")
def config_flow():
    import importlib

    importlib.import_module(_PKG)
    return importlib.import_module(f"{_PKG}.config_flow")


@pytest.fixture(scope="session")
def integration():
    """The package __init__ itself - entry setup, unload and the options listener."""
    import importlib

    return importlib.import_module(_PKG)


@pytest.fixture(scope="session")
def number_platform():
    import importlib

    importlib.import_module(_PKG)
    return importlib.import_module(f"{_PKG}.number")
