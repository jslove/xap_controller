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
    const.Platform = types.SimpleNamespace(MEDIA_PLAYER="media_player")

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
    cv = _module("homeassistant.helpers.config_validation")
    cv.string = str
    helpers.config_validation = cv

    comp = _module("homeassistant.components")
    mp = _module("homeassistant.components.media_player")
    mp.MediaPlayerEntity = type("MediaPlayerEntity", (), {})
    mp.MediaType = types.SimpleNamespace(MUSIC="music")
    comp.media_player = mp

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
