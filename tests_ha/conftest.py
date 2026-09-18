"""Real Home Assistant, fake hardware.

The suite in `tests/` stubs Home Assistant, which keeps channel parsing and gain
arithmetic fast and dependency-free. It cannot see lifecycle or state-machine behaviour,
because a stub is only as strict as whoever wrote it — and three times it was more
forgiving than Home Assistant and hid a real bug: a MAXGAIN fixture that made a loop bug
produce identical output, `async_write_ha_state` calls silently discarded, and unload
callback return values silently discarded. The last two broke a live install.

So this suite runs the integration inside a real Home Assistant, through
`pytest-homeassistant-custom-component`, and fakes only what is genuinely external: the
XAPX00 serial library, replaced by a model of one unit's gains, ceilings, mutes and
crosspoints.

It needs Home Assistant installed, so it is kept apart from `tests/` — that suite injects
a fake `homeassistant` into `sys.modules`, which would shadow the real one if both were
collected in one process. Run it on its own:

    pip install pytest-homeassistant-custom-component
    python -m pytest tests_ha
"""

import json
import math
import shutil
import sys
import threading
import types
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent


# --- the hardware ---------------------------------------------------------------------

class Unit:
    """One XAP800's state, shared by every connection opened to it — as the real one is.

    Keys are (group, channel) with the channel as a string, so a processing block's
    letter and an input's number live in the same maps.
    """

    def __init__(self):
        self.gain = {}      # dB
        self.max = {}       # MAXGAIN, dB; factory default is +20
        self.mute = {}      # 0/1
        self.matrix = {}    # (in_group, in, out_group, out) -> crosspoint state
        self.calls = []     # (method, group, channel) - every round trip, in order

    @staticmethod
    def key(group, channel):
        return (group, str(channel))

    def ceiling(self, group, channel):
        return self.max.get(self.key(group, channel), 20.0)

    def count(self, method, group=None):
        return sum(1 for m, g, _ in self.calls
                   if m == method and (group is None or g == group))


UNIT = Unit()


class XAPCommError(Exception):
    pass


class XAPRespError(Exception):
    pass


class FakeXAPX00:
    """The subset of XAPX00's API the integration calls, over the shared Unit.

    Conversions match XAPX00 2026.09.10, the pinned release: a proportional gain is the
    linear ratio to MAXGAIN less a 1e-6 epsilon, and a write is clamped to MAXGAIN because
    that release enforces it. Stereo pairing is ignored — the tests use explicit channel
    lists, which is the configuration the deprecation of `stereo` recommends.
    """

    def __init__(self, *args, **kwargs):
        self.connectionLive = 1
        self.matrixGeo = 12
        self.stereo = 0
        self.convertDb = 1
        self.conn_id = "fake"
        self._lock = threading.Lock()

    def test_connection(self):
        self.connectionLive = 1
        return True

    def getMaxGain(self, channel, group="I", unitCode=0, stereo=1, **kwargs):
        UNIT.calls.append(("getMaxGain", group, str(channel)))
        return UNIT.ceiling(group, channel)

    def setMaxGain(self, channel, gain, group="I", unitCode=0, stereo=1):
        UNIT.calls.append(("setMaxGain", group, str(channel)))
        UNIT.max[Unit.key(group, channel)] = float(gain)
        return gain

    def _prop(self, channel, group):
        db = UNIT.gain.get(Unit.key(group, channel), 0.0)
        return max(0.0, 10.0 ** ((db - UNIT.ceiling(group, channel)) / 20.0) - 1e-6)

    def getPropGain(self, channel, group="I", unitCode=0, stereo=1):
        UNIT.calls.append(("getPropGain", group, str(channel)))
        return self._prop(channel, group)

    def setPropGain(self, channel, gain, isAbsolute=1, group="I", unitCode=0, stereo=1):
        UNIT.calls.append(("setPropGain", group, str(channel)))
        ceiling = UNIT.ceiling(group, channel)
        db = ceiling + 20.0 * math.log10(float(gain) + 1e-6)
        UNIT.gain[Unit.key(group, channel)] = min(db, ceiling)
        return self._prop(channel, group)

    def getMute(self, channel, group="I", unitCode=0, stereo=1):
        UNIT.calls.append(("getMute", group, str(channel)))
        return UNIT.mute.get(Unit.key(group, channel), 0)

    def setMute(self, channel, group="I", isMuted=0, unitCode=0, stereo=1):
        UNIT.calls.append(("setMute", group, str(channel)))
        UNIT.mute[Unit.key(group, channel)] = int(isMuted)
        return int(isMuted)

    def getMatrixRouting(self, inp, out, inGroup="I", outGroup="O", unitCode=0, stereo=1):
        UNIT.calls.append(("getMatrixRouting", inGroup, str(inp)))
        return UNIT.matrix.get((inGroup, str(inp), outGroup, str(out)), 0)

    def setMatrixRouting(self, inp, out, state, inGroup="I", outGroup="O",
                         unitCode=0, stereo=1):
        UNIT.calls.append(("setMatrixRouting", inGroup, str(inp)))
        UNIT.matrix[(inGroup, str(inp), outGroup, str(out))] = state
        return state

    def setMatrixLevel(self, *args, **kwargs):
        return 0

    def XAPCommand(self, verb, *args, unitCode=0, rtnCount=16):
        UNIT.calls.append(("XAPCommand", verb, " ".join(str(a) for a in args)))
        return ["50", verb, *[str(a) for a in args]]


def _install_fake_library():
    mod = types.ModuleType("XAPX00")
    mod.__version__ = "fake"
    mod.XAPX00 = FakeXAPX00
    mod.XAPCommError = XAPCommError
    mod.XAPRespError = XAPRespError
    sys.modules["XAPX00"] = mod


_install_fake_library()


# --- the integration, where Home Assistant looks for it --------------------------------

@pytest.fixture(scope="session", autouse=True)
def _custom_components(tmp_path_factory):
    """Put the integration at `custom_components/xap_controller/`.

    The repo IS the component (hacs.json `content_in_root`), so there is no
    `custom_components/` to point Home Assistant at. A copy in a temporary directory is
    portable and needs no symlink privileges; it is taken fresh each session, from the
    working tree. A link inside the repo would be found again by collection and recurse.

    Imported here, as a regular package, before Home Assistant looks. Home Assistant
    finds custom integrations by importing `custom_components` with its config dir
    first on sys.path, and the plugin's test config dir has a `custom_components`
    package of its own that would otherwise win.
    """
    root = tmp_path_factory.mktemp("ha")
    package = root / "custom_components"
    dst = package / "xap_controller"
    dst.mkdir(parents=True)
    (package / "__init__.py").write_text("")
    for path in REPO.iterdir():
        if path.is_file() and path.suffix in (".py", ".json", ".yaml"):
            shutil.copy2(path, dst / path.name)
    shutil.copytree(REPO / "translations", dst / "translations")
    sys.path.insert(0, str(root))
    sys.modules.pop("custom_components", None)
    import custom_components  # noqa: F401 - cached, so Home Assistant's import finds this one

    assert Path(custom_components.__file__).parent == package
    yield
    sys.path.remove(str(root))


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


# --- a unit in a realistic state, and an entry pointing at it --------------------------

SOURCES = {"WiiM": [9], "Home Assistant": [11]}
ZONES = {"Kitchen & Dining": [7, 8], "Patio": [5, 6]}


@pytest.fixture
def unit():
    """A unit with WiiM routed into both zones and ceilings below the factory +20."""
    UNIT.__init__()
    for out in (5, 6, 7, 8):
        UNIT.matrix[("I", "9", "O", str(out))] = 1
        UNIT.max[Unit.key("O", out)] = -7.5
        UNIT.gain[Unit.key("O", out)] = -15.0
    for inp in (9, 11):
        UNIT.max[Unit.key("I", inp)] = 10.89
        UNIT.gain[Unit.key("I", inp)] = -1.11
    return UNIT


@pytest.fixture
def entry(hass, unit):
    from pytest_homeassistant_custom_component.common import MockConfigEntry

    e = MockConfigEntry(
        domain="xap_controller",
        title="XAP800",
        entry_id="xap1",
        data={
            "name": "XAP800",
            "XAPType": "XAP800",
            "stereo": False,
            "connection_type": "serial",
            "path": "/dev/fake-xap",
            "baud": 57600,
            "sources": json.dumps(SOURCES),
            "zones": json.dumps(ZONES),
            "max_gain": "",
            "expose_source_gain": False,
        },
    )
    e.add_to_hass(hass)
    return e
