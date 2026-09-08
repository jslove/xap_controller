"""
Support for interfacing with ClearOne XAP800 and XAP400 units via serial port.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/media_player.xap_controller/
(no docs there until release)

There are two components in the platform: output Zones and input Sources.  The input sources are assumed to be XAP
type I inputs, the output zones type O outputs. The XAP system can have multple units linked together.  The configured
Sources and Zones can specify only the channel for input or output, in which case it is assumed they are on unit 0.  They
can also specify the unit, and optionally, for sources, an expansion bus that the source is also mapped to, so that it
can be used on other units in the systems.  In this case, list the unit:channel of the source, and then the expansion
channel and optinoally expansion group (E or P).  When sources or zones are specified with units and expansion buses,
the items should be listed as a string of the format "<Unit#>:<Channel#>:<Expansion Bus Channel Letter>:<Expansion BUS
Group>".  See below for an example.  For the expansion bus setup to work the matrix needs to have the sources mapped to
the expansin channels through the G-Ware software.

The system can assume that the channels are set up for stereo, so that there are 2 channels paired together.  If
stereo=1, the module will take each action twice, once on the listed source/zone number and again on the source/zone + 1.
This functionality may be removed in the future to promote clarity, so if ia stereo setup is used, it is recommneded to list
each channel explicitly.

For each source or zone, multiple channels can be listed, as a list.  If multiple channels are listed for a source and
an output, they will be paired sequentially, source item 1 to zone item 1, source item 2 to zone item 2, etc.  If there
are more source channels than zone channels, only the first channels in the source will be used.  If there are more
channels in a zone than in the source being applied ot it, the source channels will be repeated.  This multiple channel
 apporach can be used to handle stereo (instead of the stereo=1 approach), but it was added to handle surround sound
  sources / zones. The XAP system will mix multiple source channels applied to one output zone channel.

The platform will create individual media_player controls for each source and zone.  Each source will be shown with a
 volume slider, adjusting the gain for that input.  Each Zone will be shown with a dropbox to select from the available
 sources and a volume slider to adjust the gain for that output zone.

Basic configuration
```
media_player:
   - platform: xap_controller
     path: /dev/ttyUSB-XAP800
     name: MyXAP
     stereo: 1 # 1 or 0, default is 0, recommend explicitly listing sterero channels
     baud: 38400 #default
     XAPType: XAP800 # XAP800 or XAP400, default is XAP800
     zones:
       'Office':
         - 1
       'Kitchen':
         - 3
       'Outside':
         - 5
       'Upstairs':
         - 7
       'Living/Dining/Library':
         - 9
       'WorkRoom':
         - "2:1"
     sources:
       'Home Audio':
         - 9
       'Family TV Audio':
         - 11
```

Multi-unit example
```
media_player:
   - platform: xap_controller
     path: /dev/ttyUSB-XAP800
     name: MyXAP
     stereo: 0
     baud: 38400
     zones:
       'Office':
         - "1:1"
         - "1:2"
       'Kitchen':
         - "1:3"
         - "1:4"
        'Family Room Surround':
         - "2:1"
         - "2:2"
         - "2:3"
         - "2:4"
         - "2:1"
         - "2:2"
         # Family Room Surround has no center speaker, so list the two front
         # speakers at the end and map the center channel to each of them

     sources:
       'Home Audio':
         - "1:9:O:E"
         - "1:10:P:E"
       'Family TV Surround Audio':
         - "2:1:V:E"
         - "2:2:W:E"
         - "2:3:X:E"
         - "2:4:Y:E"
         - "2:5:Z:E"
         - "2:5:Z:E"
         # Family Room Surround has no center channel, so list the center channel twice at the end,
         # then it will be connected to the last 2 itens in the zone channel list
```

* zones: a list of output zone names, with a list of one or more outputs for each zone name.
* sources: a list of source names, with a list of one or more sources per source name.
   sources are listed as either a digit, indicating the input channel on unit 0, or else a string of the format:
   "<unit#>:<input#>:<bus letter>:<bus type>.
   Bus and Bus type are optional, but are needed if using more than 1 unit and you want a source to be available
   on outputs in other units.
* path: serial device path (can be a virtual serial port, using socat for example)
* name: the name of the platform instance
* stereo: 1=stereo, 0=mono  If stereo=1, each action will be performed twice on the input (output) and input+1 (output)+1
* baud: baud rate of serial port, 38400 (default), 9600, 19200, 57600
* XAPType: XAP unit type, either XAP800 (default) or XAP400

"""

import logging
import functools
import json
import shlex
import threading

import voluptuous as vol

from homeassistant.components.media_player import MediaPlayerEntity
import homeassistant.components.media_player as MP
from homeassistant.components.media_player.const import MediaPlayerEntityFeature as MPEF
from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import SupportsResponse
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
import homeassistant.helpers.config_validation as cv
from XAPX00 import __version__ as XAPVER, XAPX00, XAPCommError, XAPRespError

from .config_flow import (
    CONF_PATH, CONF_SOURCES, CONF_ZONES, CONF_TYPE, CONF_STEREO, CONF_BAUD,
    CONF_CONNECTION_TYPE, CONF_HOST, CONF_PORT, CONF_TELNET_USERNAME, CONF_TELNET_PASSWORD,
    CONF_SOURCE_TRIM,
)

DOMAIN = 'xap_controller'

_LOGGER = logging.getLogger(__name__)

SRC_OFF = 'Off'

# Processing blocks, addressed by letter rather than number. A zone can be fed
# input -> processing -> output, which leaves no direct input/output crosspoint for
# the plain matrix lookup to find.
PROC_BLOCKS = "ABCDEFGH"

SUPPORT_XAP_ZONE = (
    MPEF.VOLUME_MUTE | MPEF.VOLUME_SET |
    MPEF.TURN_ON | MPEF.TURN_OFF |
    MPEF.SELECT_SOURCE
)

SUPPORT_XAP_SOURCE = (
    MPEF.VOLUME_MUTE |
    MPEF.TURN_ON | MPEF.TURN_OFF
)

# Off by default; opt in per entry with `source_trim`.
#
# Input gain is a calibration control, not a volume control - it is where headroom lives,
# and an input left near its MAXGAIN clips the input stage. Exposing it as an ordinary
# volume slider makes it reachable by everything that treats a media_player as a speaker:
# media_player.volume_set from any automation, Assist, and the HomeKit/Alexa/Google
# bridges. The realistic accident is not someone dragging a calibration control on
# purpose, but a broad "turn the volume down" targeting an area sweeping up the inputs
# along with the speakers.
SUPPORT_XAP_SOURCE_WITH_TRIM = SUPPORT_XAP_SOURCE | MPEF.VOLUME_SET


def handle_xap_exceptions(func):
    @functools.wraps(func)
    async def wrapper(self, *args, **kwargs):
        try:
            return await func(self, *args, **kwargs)
        except XAPCommError as e:
            errstr = (f"Error in {func.__name__} for {self}: {e}")
            _LOGGER.warning(errstr)
            raise HomeAssistantError(errstr)
        except XAPRespError as e:
            errstr = (f"Error in {func.__name__} for {self}: {e}")
            _LOGGER.warning(errstr)
            raise HomeAssistantError(errstr)
    return wrapper


async def async_setup_platform(hass, config, async_add_entities, discovery_info=None):
    """Migrate legacy media_player YAML config to a config entry."""
    from homeassistant.config_entries import SOURCE_IMPORT
    from .config_flow import CONF_PATH, CONF_SOURCES, CONF_ZONES, CONF_TYPE, CONF_STEREO, CONF_BAUD
    from homeassistant.const import CONF_NAME
    # Only pass known serializable keys — HA injects internal values like
    # scan_interval (datetime.timedelta) that cannot be stored as JSON.
    _KNOWN_KEYS = {CONF_PATH, CONF_NAME, CONF_SOURCES, CONF_ZONES, CONF_TYPE, CONF_STEREO, CONF_BAUD}
    import_data = {k: v for k, v in config.items() if k in _KNOWN_KEYS}
    hass.async_create_task(
        hass.config_entries.flow.async_init(
            "xap_controller",
            context={"source": SOURCE_IMPORT},
            data=import_data,
        )
    )
    from homeassistant.components.persistent_notification import async_create as pn_create
    pn_create(
        hass,
        "XAP Controller is now configured via the UI. "
        "Please remove it from your configuration.yaml to avoid this message.",
        title="XAP Controller: remove YAML config",
        notification_id="xap_controller_yaml_deprecated",
    )


SERVICE_SEND_COMMAND = "send_command"

SEND_COMMAND_SCHEMA = vol.Schema(
    {
        vol.Required("command"): cv.string,
        vol.Optional("unit", default=0): vol.All(vol.Coerce(int), vol.Range(min=0, max=7)),
        # `rtnCount` is "keep the last N whitespace-separated tokens of the reply", so a
        # small value silently truncates: at 2, `LABEL 5 O` returns ["-", "Patio"] and
        # loses the "3L". 16 is past the longest reply seen, and asking for more tokens
        # than arrive simply returns what arrived â€” so the default shows the whole line.
        vol.Optional("return_count", default=16): vol.All(
            vol.Coerce(int), vol.Range(min=0, max=64)
        ),
        # Only needed with more than one XAP system configured as separate entries;
        # with one entry the connection is unambiguous and this can be omitted.
        vol.Optional("entry_id"): cv.string,
    }
)


def _connection_for(hass, entry_id=None):
    """The XAPX00 connection a service call should use.

    Resolved per call rather than captured at registration, so the service cannot end up
    bound to a connection whose config entry has since been unloaded.
    """
    conns = hass.data.get(DOMAIN, {})
    if not conns:
        raise ServiceValidationError("No XAP connection is currently set up")
    if entry_id is not None:
        if entry_id not in conns:
            raise ServiceValidationError(
                f"No set-up XAP config entry with id {entry_id}; "
                f"known ids: {', '.join(sorted(conns))}"
            )
        return conns[entry_id]
    if len(conns) > 1:
        # Guessing here would silently talk to whichever entry set up first. A chained
        # system is one entry and reaches its other units via the `unit` field; several
        # entries means several independent systems, and only the caller knows which.
        raise ServiceValidationError(
            "More than one XAP config entry is set up; pass entry_id. "
            f"Known ids: {', '.join(sorted(conns))}"
        )
    return next(iter(conns.values()))


def _register_send_command(hass):
    """Expose a raw command channel: `xap_controller.send_command`.

    The point is hands-on work on the unit — reading LABEL/MTRX/MAX, trying settings the
    entities do not model — without a second process opening the serial port behind this
    integration's back. XAPCommand already owns the framing, the device address, the
    response parsing and the lock, so going through it is both safer and less code than a
    side channel.

    The service is registered once and looks its connection up at call time; see
    `async_release_connection` for the teardown side.
    """
    if hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        return

    async def _handle(call):
        raw = call.data["command"].strip()
        if not raw:
            raise ServiceValidationError("command is empty")
        try:
            # shlex rather than str.split so a quoted argument survives: a label is a
            # command argument that legitimately contains spaces, and
            # `LABEL 5 O "Living Room"` is otherwise five tokens rather than three.
            parts = shlex.split(raw)
        except ValueError as err:
            raise ServiceValidationError(f"could not parse command: {err}") from err
        if not parts:
            raise ServiceValidationError("command is empty")
        verb, args = parts[0], parts[1:]
        xapconn = _connection_for(hass, call.data.get("entry_id"))

        def _run():
            with xapconn._lock:
                return xapconn.XAPCommand(
                    verb, *args,
                    unitCode=call.data["unit"],
                    rtnCount=call.data["return_count"],
                )

        try:
            result = await hass.async_add_executor_job(_run)
        except (XAPCommError, XAPRespError) as err:
            # A refused command is a normal outcome when probing an unfamiliar unit —
            # report it as the answer rather than as an integration failure.
            return {"command": raw, "error": str(err) or err.__class__.__name__}
        if isinstance(result, (list, tuple)):
            result = [str(x) for x in result]
        else:
            result = str(result)
        return {"command": raw, "response": result}

    hass.services.async_register(
        DOMAIN,
        SERVICE_SEND_COMMAND,
        _handle,
        schema=SEND_COMMAND_SCHEMA,
        supports_response=SupportsResponse.OPTIONAL,
    )
    _LOGGER.info("Registered %s.%s", DOMAIN, SERVICE_SEND_COMMAND)


def async_release_connection(hass, entry):
    """Drop an unloaded entry's connection, and the service with the last one.

    Without this the service outlives its connection: reloading or deleting the entry
    left `send_command` registered against a dead XAPX00, and the has_service guard meant
    no surviving entry could take it over, so it stayed broken until a full restart.
    """
    conns = hass.data.get(DOMAIN, {})
    conns.pop(entry.entry_id, None)
    if not conns and hass.services.has_service(DOMAIN, SERVICE_SEND_COMMAND):
        hass.services.async_remove(DOMAIN, SERVICE_SEND_COMMAND)
        _LOGGER.info("Removed %s.%s with the last config entry",
                     DOMAIN, SERVICE_SEND_COMMAND)


async def _prewarm_max_gain(hass, xapconn, zones):
    """Read every zone output channel's MAXGAIN once, to seed XAPX00's cache.

    setPropGain needs a channel's MAXGAIN to turn a 0-1 level into dB, and XAPX00 caches
    it (2026.09.03 onward) so that read happens once per channel per process rather than
    on every volume write. The question this function answers is *when* that one read
    happens, because the miss lands on whichever call touches the channel first.

    For a zone that is ON at startup, _firstConnect reaches _sync_volume_level, which
    writes every output channel and warms them all. For a zone that is OFF it does not:
    _sync_volume_level returns early on SRC_OFF, so only outputs[0] gets read by
    _get_volume_level and every other channel in that zone stays cold. The first real
    volume change then pays an extra round trip per channel - ~83 ms each over telnet,
    on a multi-channel zone, at exactly the moment someone is moving a slider.

    On a system whose zones are mostly off between uses that is the common case, so the
    reads are done here instead, where nothing is waiting on them.

    Best effort throughout: a channel that will not answer is simply left out of the
    cache and picked up by the normal path later. Nothing here is worth failing setup
    over, and none of it changes a single setting on the unit - these are queries.
    """
    if not xapconn.connectionLive:
        _LOGGER.debug("Not connected; skipping MAXGAIN pre-warm")
        return

    channels = []
    seen = set()
    for zone in zones:
        for output in zone._outputs:
            try:
                addr = zone.parse_output(output)
            except Exception:
                # parse_output raises a bare Exception on a malformed spec. The zone
                # itself reports that where it matters; duplicating the complaint from a
                # cache warmer would just be noise.
                continue
            if addr not in seen:
                seen.add(addr)
                channels.append(addr)

    if not channels:
        return

    def _read_all():
        # One acquisition for the whole batch rather than per channel: this runs before
        # async_add_entities, so nothing else is using the connection yet, and it keeps
        # ~24 queries from interleaving with anything that starts mid-way.
        with xapconn._lock:
            cached = 0
            for unit, chan in channels:
                try:
                    # stereo=0: getMaxGain is @stereo decorated, and letting it run would
                    # read chan+1 as well - double the traffic, and it caches channels
                    # nobody listed (a zone of [3, 4] would also fetch 4 and 5).
                    xapconn.getMaxGain(chan, group="O", unitCode=unit, stereo=0)
                    cached += 1
                except Exception:
                    _LOGGER.debug(
                        "MAXGAIN pre-warm: unit %s output %s did not answer", unit, chan)
            return cached

    cached = await hass.async_add_executor_job(_read_all)
    _LOGGER.debug(
        "MAXGAIN pre-warm: cached %s of %s zone output channels", cached, len(channels))


async def async_setup_entry(hass, entry, async_add_entities):
    """Set up XAP Controller media player entities from a config entry."""
    sources = json.loads(entry.data[CONF_SOURCES])
    zones   = json.loads(entry.data[CONF_ZONES])

    _LOGGER.debug("Conf file sources: {}".format(sources))
    _LOGGER.debug('xap_controller: XAPX00 version: {}'.format(XAPVER))
    _LOGGER.debug('XAP Type: {}'.format(entry.data.get(CONF_TYPE)))

    conn_type = entry.data.get(CONF_CONNECTION_TYPE, "serial")
    xap_type  = entry.data.get(CONF_TYPE, "XAP800")
    stereo    = 1 if entry.data.get(CONF_STEREO, False) else 0
    if stereo:
        # Deprecated: overlaps the explicit multi-channel list and is unsafe combined
        # with it -- a zone listed as [3, 4] with stereo on writes crosspoints 3&4 and
        # then 4&5. See https://github.com/jslove/xap_controller/issues/23
        _LOGGER.warning(
            "The 'stereo' option is deprecated and will be removed in a future release. "
            "List each channel explicitly instead: a zone of [3] with stereo on becomes "
            "a zone of [3, 4] with stereo off. See issue #23."
        )
    allow_trim = bool(entry.data.get(CONF_SOURCE_TRIM, False))

    # XAPX00.__init__ calls test_connection() internally, which uses
    # loop.run_until_complete() for telnet.  That must not run on HA's event
    # loop, so construct the object inside an executor thread.
    if conn_type == "telnet":
        conn_label = entry.data[CONF_HOST]
        def _make_conn():
            conn = XAPX00(
                connection_type="telnet",
                telnet_host=entry.data[CONF_HOST],
                telnet_port=entry.data.get(CONF_PORT, 23),
                telnet_username=entry.data.get(CONF_TELNET_USERNAME, "clearone"),
                telnet_password=entry.data.get(CONF_TELNET_PASSWORD, "converge"),
                XAPType=xap_type,
            )
            conn.stereo    = stereo
            conn.convertDb = 1
            conn.conn_id   = entry.data[CONF_HOST]
            conn._lock     = threading.Lock()
            return conn
    else:
        conn_label = entry.data[CONF_PATH]
        def _make_conn():
            # baudRate belongs in the constructor — see _build_xapconn in config_flow.
            conn = XAPX00(
                entry.data[CONF_PATH],
                baudRate=entry.data.get(CONF_BAUD, 38400),
                XAPType=xap_type,
            )
            conn.stereo    = stereo
            conn.convertDb = 1
            conn.conn_id   = entry.data[CONF_PATH]
            conn._lock     = threading.Lock()
            return conn

    xapconn = await hass.async_add_executor_job(_make_conn)

    # Entities can use xapconn.connectionLive to test connection state
    connected = await hass.async_add_executor_job(xapconn.test_connection)
    if not connected:
        _LOGGER.warning('Not connected to %s', conn_label)

    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = xapconn
    _register_send_command(hass)

    source_objs = []
    zonesources = {}
    for source_name, source_input in sources.items():
        sourceobj = XAPSource(hass, xapconn, source_name, source_input,
                              allow_trim=allow_trim)
        source_objs.append(sourceobj)
        zonesources[source_name] = sourceobj

    zonesources[SRC_OFF] = 0

    zone_objs = []
    for zone_name, outputs in zones.items():
        zone_objs.append(XAPZone(hass, xapconn, zonesources, zone_name, outputs))

    await _prewarm_max_gain(hass, xapconn, zone_objs)

    async_add_entities(source_objs + zone_objs)


class XAPSource(MediaPlayerEntity):
    """
    Represents one source
    """

    def __init__(self, hass, xapconn, source_name, source_inputs, unitCode=0,
                 allow_trim=False):
        """Initialise the XAPX00 source pseudo-device"""
        _LOGGER.debug("Setting Up Source %s" % source_name)
        self.hass = hass
        self._name = source_name
        self._xapx00 = xapconn
        self._allow_trim = allow_trim
        self._state = STATE_OFF
        self.xunit = 0
        self.xinput = None
        self.xgroup = "I"
        self.xbus = None
        self.xbusgroup = None
        self._inputs = []
        self.parse_source(source_inputs)
        self.numChannels = len(self._inputs)
        self._volume = 0
        self._isMuted = 1
        self._first_connect = 0
        channels = ",".join(str(i) for i in source_inputs)
        self._attr_unique_id = f"XAP-Source-{self._xapx00.conn_id}-{channels}"

    def __str__(self):
        return self._name

    def __repr__(self):
        return "{} ({})".format(self._name, self._inputs)

    def connectionLive(self):
        return self._xapx00.connectionLive

    async def _xap(self, fn):
        """Run fn in an executor thread while holding the connection lock."""
        def _locked():
            with self._xapx00._lock:
                return fn()
        return await self.hass.async_add_executor_job(_locked)

    async def async_added_to_hass(self):
        """Run after entity is added — safe place for blocking I/O."""
        if self.connectionLive():
            try:
                await self._firstConnect()
            except HomeAssistantError as e:
                _LOGGER.warning("source %s: firstConnect failed (%s), going offline", self, e)
                self._startOffline()
        else:
            self._startOffline()
        _LOGGER.info("source {} set up".format(self.__str__()))

    async def _firstConnect(self):
        if self._first_connect:
            return
        self._volume = await self._get_volume_level()
        await self.async_set_volume_level(self._volume)  # make sure synced
        await self._get_mute_status()
        if self._isMuted:
            self._state = STATE_OFF
        else:
            self._state = STATE_ON
        await self.async_mute_volume(self._isMuted)  # sync
        self._first_connect = 1
        _LOGGER.debug('%s: firstConnect complete' % self._name)

    def _startOffline(self):
        self._volume = 0
        self._isMuted = 1
        self._state = STATE_OFF
        _LOGGER.debug('%s: startOffline complete' % self._name)

    def parse_source(self, srcs):
        "Split into input unit, input #, expansion bus, expansion bus group"
        for src in srcs:
            inpdict={'UNIT':0,'CHAN':None,'BUS':None, 'BUSGRP':'E', 'INPGRP':'I'}
            if issubclass(type(src), int):
                inpdict['CHAN'] = src
            elif issubclass(type(src), str):
                if ":" in src:
                    comps = src.count(':')
                    if comps == 1:
                        inpdict['UNIT'], inpdict['CHAN']  =  src.split(":")
                    elif comps == 2:
                        inpdict['UNIT'], inpdict['CHAN'], inpdict['BUS'] = src.split(":")
                        XBUSGRP = 'E' # default to E
                    elif comps == 3:
                        inpdict['UNIT'], inpdict['CHAN'], inpdict['BUS'], inpdict['BUSGRP'] = src.split(":")
                    inpdict['CHAN'] = int(inpdict['CHAN'])
                    inpdict['UNIT'] = int(inpdict['UNIT'])
                elif src.isdigit():
                    inpdict['CHAN'] = int(src)
                else:
                    raise Exception('Invalid Input String')
            else:
                # shouldn't be able to get here
                raise Exception('Invalid Source Input config format')
            self._inputs.append(inpdict)
        return

    def getSource(self, outUnit, srcNum=0):
        outUnit = int(outUnit)
        srcNum = srcNum % self.numChannels  # wrap if request is greater than number of sources
        if outUnit == self._inputs[srcNum]['UNIT']:
            return  self._inputs[srcNum]['CHAN'],  self._inputs[srcNum]['INPGRP']
        else:
            if self._inputs[srcNum]['BUS'] is None:
                raise ServiceValidationError("Different unit but No Expansion Bus Defined")
            return self._inputs[srcNum]['BUS'], self._inputs[srcNum]['BUSGRP']

    @property
    def name(self):
        """Return the name of the source."""
        return "Source: " + self._name

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def supported_features(self):
        """Flag of media commands that are supported."""
        return SUPPORT_XAP_SOURCE_WITH_TRIM if self._allow_trim else SUPPORT_XAP_SOURCE

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self._volume

    @property
    def is_volume_muted(self):
        """ return bool mute status"""
        return bool(self._isMuted)

    @handle_xap_exceptions
    async def _get_volume_level(self):
        """ Blocking XAP call — run in executor."""
        if not self.connectionLive():
            return self._volume
        vinp = self._inputs[0]
        gain = await self._xap(
            lambda: self._xapx00.getPropGain(vinp['CHAN'], group="I", unitCode=vinp['UNIT'])
        )
        self._volume = gain
        return self._volume

    @handle_xap_exceptions
    async def async_set_volume_level(self, volume):
        """Set volume level, range 0..1.

        Every input is set from the *requested* level. This used to reassign the loop
        variable from setPropGain's return, so the second input was set from the value
        read back for the first - and since that return is a proportion of that
        channel's own MAXGAIN, two inputs with different ceilings landed at different
        dB. The level reported afterwards is the first input's readback, matching
        _get_volume_level, which also reads _inputs[0].
        """
        landed = None
        for s in self._inputs:
            result = await self._xap(
                lambda s=s: self._xapx00.setPropGain(s['CHAN'], volume,
                                                     isAbsolute=1, group="I", unitCode=s['UNIT'])
            )
            if landed is None:
                landed = result
        self._volume = volume if landed is None else landed

    @handle_xap_exceptions
    async def async_mute_volume(self, mute=2):
        """Blocking XAP call — run in executor."""
        self._isMuted = await self._xap(
            lambda: self._xapx00.setMute(self._inputs[0]['CHAN'], group="I",
                                         isMuted=int(mute), unitCode=self._inputs[0]['UNIT'])
        )
        for s in self._inputs[1:]:
            self._isMuted = await self._xap(
                lambda s=s: self._xapx00.setMute(s['CHAN'], group="I",
                                                 isMuted=self._isMuted, unitCode=s['UNIT'])
            )

    @handle_xap_exceptions
    async def _get_mute_status(self):
        self._isMuted = await self._xap(
            lambda: self._xapx00.getMute(self._inputs[0]['CHAN'], group="I",
                                         unitCode=self._inputs[0]['UNIT'])
        )
        return self._isMuted

    async def async_turn_on(self):
        """Turn the media player on."""
        if not self.connectionLive():
            live = await self._xap(self._xapx00.test_connection)
            if not live:
                return
        if not self._first_connect:
            await self._firstConnect()
        await self.async_mute_volume(mute=0)
        self._state = STATE_ON

    async def async_turn_off(self):
        """Turn off media player."""
        await self.async_mute_volume(mute=1)
        self._state = STATE_OFF

    async def async_update(self):
        """Re-read level and mute from the unit.

        Sources previously had no update method at all, so their state was whatever
        `_firstConnect` cached at setup. Anything that changed the unit afterwards - the
        front panel, G-Ware, a serial command - left the entity stale indefinitely, and
        a source showing "off" while its channel was plainly unmuted is a confusing
        place to start debugging silence. Zones already polled; this brings sources into
        line.
        """
        if not self.connectionLive():
            return
        await self._get_volume_level()
        await self._get_mute_status()
        self._state = STATE_OFF if self._isMuted else STATE_ON


class XAPZone(MediaPlayerEntity):
    """
    Represents one or more XAP outputs, either mono or stereo
    """
    def __init__(self, hass, xapconn, sources, zone_name, outputs, unitCode=0):
        """Initialise the XAPX00 zone pseudo-device"""
        self.hass = hass
        self._name = zone_name
        self._xapx00 = xapconn
        self._unitCode = unitCode
        self._sources = sources.copy() #dict of source name:source obj
        self._outputs = outputs.copy()
        # outputs is a list of outputs, each element can be a single int or
        # a string of "int:int" (unit:output)
        self._volume = 0
        self._isMuted = 1
        self._defaultMatrixLevel = 1
        self._active_source = SRC_OFF
        self._poweroff_source = SRC_OFF
        self._first_connect = 0
        # Processing block this zone is fed through, if any. Looked up once - the
        # scan costs one serial round trip per block and _get_source runs on a timer.
        # Processing block feeding each output, keyed (unit, output) and resolved on
        # first use. Per output, not per zone: the two halves of a stereo zone can be
        # fed by different blocks, and caching one answer for the whole zone routes
        # both halves into the first one.
        self._via_block = {}
        channels = ",".join(str(o) for o in self._outputs)
        self._attr_unique_id = f"XAP-Zone-{self._xapx00.conn_id}-{channels}"

    def __str__(self):
        return self._name

    def connectionLive(self):
        return self._xapx00.connectionLive

    async def _xap(self, fn):
        """Run fn in an executor thread while holding the connection lock."""
        def _locked():
            with self._xapx00._lock:
                return fn()
        return await self.hass.async_add_executor_job(_locked)

    async def async_added_to_hass(self):
        """Run after entity is added — safe place for blocking I/O."""
        if self.connectionLive():
            try:
                await self._firstConnect()
            except HomeAssistantError as e:
                _LOGGER.warning("zone %s: firstConnect failed (%s), going offline", self, e)
                await self._startOffline()
        else:
            await self._startOffline()
        _LOGGER.info("zone {} set up".format(self.__str__()))

    async def _firstConnect(self):
        if self._first_connect:
            return
        self._isMuted = await self._get_mute_status()
        self._active_source = await self._get_source()
        self._poweroff_source = self._active_source
        # make sure sources synced across outputs
        await self.async_select_source(self._active_source)
        await self._get_volume_level()
        await self._sync_volume_level()
        self._state = STATE_ON if self._active_source != SRC_OFF else STATE_OFF
        self._first_connect = 1
        _LOGGER.debug('%s: firstConnect complete' % self._name)

    async def _startOffline(self):
        self._isMuted = 1
        self._active_source = SRC_OFF
        self._poweroff_source = self._active_source
        await self.async_select_source(self._active_source)
        self._state = STATE_ON if self._active_source != SRC_OFF else STATE_OFF
        _LOGGER.debug('%s: startOffline complete' % self._name)

    def parse_output(self, output):
        "Returns (unit,output) "
        if issubclass(type(output), int):
            XUNIT = 0
            XOUT = output
        elif issubclass(type(output), str):
            if ":" in output:
                XUNIT, XOUT =  output.split(":")
            elif output.isdigit():
                # Unit 0, same as the bare int form. Without this XUNIT is never bound
                # and the return below raises UnboundLocalError - and a bare numeric
                # string is a shape _validate_sources_zones accepts and the README's own
                # examples mix in, so `{"Kitchen": ["3"]}` crashed setup.
                XUNIT = 0
                XOUT = int(output)
            else:
                raise Exception('Invalid Output String')
        else:
            # shouldn't be able to get here
            raise Exception('Invalid Output config format')
        return int(XUNIT), int(XOUT)

    async def async_update(self):
        pass  # can't be changed except by us, so can track state without calls

    @handle_xap_exceptions
    async def async_select_source(self, source):
        """Set the input source — blocking XAP calls run in executor."""
        if not self.connectionLive(): return
        actsrc = self._active_source  # a string
        _LOGGER.debug('select_source for zone={}: source={}, actsrc={}, self._sources={}'.format(
            self._name, source, actsrc, self._sources.keys()))
        if source not in self._sources:
            raise Exception("Requested source {} not in set up sources".format(source))
        cnt = 0
        for xOut in self._outputs:
            XUNIT, XOUT = self.parse_output(xOut)
            # Route into the processing block when the zone has one, not around it:
            # setting the direct crosspoint would leave the processed path closed too
            # and sum both feeds into the same output.
            blk = await self._feeding_block(XOUT, XUNIT)
            DEST, DESTGRP = (XOUT, "O") if blk is None else (blk, "P")
            if actsrc != SRC_OFF and actsrc != source:
                XIN, XINGRP = self._sources[actsrc].getSource(XUNIT, cnt)
                await self._xap(
                    lambda XIN=XIN, DEST=DEST, XINGRP=XINGRP, DESTGRP=DESTGRP, XUNIT=XUNIT:
                        self._xapx00.setMatrixRouting(XIN, DEST, 0, inGroup=XINGRP,
                                                     outGroup=DESTGRP, unitCode=XUNIT)
                )
                _LOGGER.debug('Turned off actsrc: {}'.format(actsrc))
            if source != SRC_OFF:
                XIN, XINGRP = self._sources[source].getSource(XUNIT, cnt)
                ON = 3 if (issubclass(type(XIN), int) and XIN <= (self._xapx00.matrixGeo-4)) else 1
                await self._xap(
                    lambda XIN=XIN, DEST=DEST, ON=ON, XINGRP=XINGRP, DESTGRP=DESTGRP, XUNIT=XUNIT:
                        self._xapx00.setMatrixRouting(XIN, DEST, ON, inGroup=XINGRP,
                                                     outGroup=DESTGRP, unitCode=XUNIT)
                )
                self._poweroff_source = source
            cnt += 1
        self._active_source = source

    @handle_xap_exceptions
    async def _feeding_block(self, XOUT, XUNIT):
        """The processing block feeding this zone's output, or None if wired direct.

        Without this, a zone running input -> processing -> output reports no source at
        all: the direct crosspoint really is 0, so `_get_source` falls through to
        SRC_OFF, the entity goes to STATE_OFF, and Home Assistant greys out its volume
        and mute. The audio is playing perfectly the whole time.
        """
        key = (XUNIT, XOUT)
        if key in self._via_block:
            return self._via_block[key]
        found = None
        for blk in PROC_BLOCKS:
            # stereo=0 is required, not an optimisation: the @stereo decorator repeats
            # the call with the channel argument incremented, which turns block "H"
            # into "I" and earns an Argument error that would fail the whole zone. This
            # is a probe of one channel, so the pairing is meaningless here anyway.
            try:
                state = await self._xap(
                    lambda b=blk: self._xapx00.getMatrixRouting(
                        b, XOUT, inGroup="P", outGroup="O", unitCode=XUNIT, stereo=0)
                )
            except (XAPCommError, XAPRespError):
                # A block this unit will not answer for is simply not the one feeding
                # us; never let probing take the zone offline.
                _LOGGER.debug("block %s not probeable for %s", blk, self._name)
                continue
            if int(state) > 0:
                found = blk
                break
        self._via_block[key] = found
        if found:
            _LOGGER.info("Zone %s output %s:%s is fed through processing block %s",
                         self._name, XUNIT, XOUT, found)
        return found

    async def _get_source(self):
        """Get first active source for outputs in this zone."""
        if not self.connectionLive():
            return SRC_OFF
        _LOGGER.debug("In get_source for {}".format(self))
        _LOGGER.debug("  Checking: {}".format(self._sources))
        XUNIT, XOUT = self.parse_output(self._outputs[0])
        blk = await self._feeding_block(XOUT, XUNIT)
        for xIn in self._sources.values():
            if xIn != self._sources[SRC_OFF]:
                XIN, XINGRP = xIn.getSource(XUNIT)
                # A zone behind a processing block is routed source -> block; the
                # block -> output leg is static and set up outside this integration.
                DEST, DESTGRP = (XOUT, "O") if blk is None else (blk, "P")
                z_state = int(await self._xap(
                    lambda XIN=XIN, DEST=DEST, XINGRP=XINGRP, DESTGRP=DESTGRP, XUNIT=XUNIT:
                        self._xapx00.getMatrixRouting(XIN, DEST, inGroup=XINGRP,
                                                      outGroup=DESTGRP, unitCode=XUNIT)
                ))
                _LOGGER.debug("matrix routing for {}={}".format(xIn, z_state))
                if z_state > 0:
                    self._active_source = xIn.__str__()
                    break
        _LOGGER.debug("get_source for %s = %s" % (self._name, self._active_source))
        return self._active_source

    @property
    def name(self):
        """Return the name of the zone."""
        return "Zone: " + self._name

    @property
    def state(self):
        """Return the state of the device."""
        return self._state

    @property
    def supported_features(self):
        """Flag of media commands that are supported."""
        return SUPPORT_XAP_ZONE

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self._volume

    @property
    def media_content_type(self):
        return MP.MediaType.MUSIC

    @property
    def media_title(self):
        """ Return current source"""
        return self._active_source

    @property
    def is_volume_muted(self):
        """ return mute status"""
        return bool(self._isMuted)

    async def async_turn_on(self):
        """Turn zone on"""
        _LOGGER.debug("turn_on {}".format(self))
        if not self.connectionLive():
            live = await self._xap(self._xapx00.test_connection)
            if not live:
                return
        if not self._first_connect:
            await self._firstConnect()
        await self.async_select_source(self._poweroff_source)        
        await self.async_mute_volume(mute=0)
        self._state = STATE_ON

    async def async_turn_off(self):
        """Turn off zone"""
        _LOGGER.debug("turn_off {}".format(self))
        if not self.connectionLive():
            live = await self._xap(self._xapx00.test_connection)
            if not live:
                return
        self._poweroff_source = self._active_source
        await self.async_mute_volume(mute=1)
        await self.async_select_source(SRC_OFF)
        self._state = STATE_OFF

    @handle_xap_exceptions
    async def async_mute_volume(self, mute=2):
        """Blocking XAP call — run in executor."""
        if not self.connectionLive(): return
        XUNIT, XOUT = self.parse_output(self._outputs[0])
        muted = await self._xap(
            lambda: self._xapx00.setMute(XOUT, group="O", isMuted=int(mute), unitCode=XUNIT)
        )
        for output in self._outputs[1:]:
            XUNIT, XOUT = self.parse_output(output)
            muted = await self._xap(
                lambda XOUT=XOUT, muted=muted, XUNIT=XUNIT:
                    self._xapx00.setMute(XOUT, group="O", isMuted=int(muted), unitCode=XUNIT)
            )
        self._isMuted = bool(muted)

    @handle_xap_exceptions
    async def _get_mute_status(self):
        if not self.connectionLive(): return
        XUNIT, XOUT = self.parse_output(self._outputs[0])
        self._isMuted = bool(await self._xap(
            lambda: self._xapx00.getMute(XOUT, group="O", unitCode=XUNIT)
        ))
        return self._isMuted

    @handle_xap_exceptions
    async def async_set_volume_level(self, volume):
        """Blocking XAP call — run in executor."""
        if not self.connectionLive(): return
        _LOGGER.debug("set_volume_level: {}:{}".format(self, volume))
        # `volume` is never reassigned in this loop. setPropGain returns the achieved
        # proportion for the channel it just wrote, relative to THAT channel's MAXGAIN,
        # so feeding it forward would set every output after the first from the previous
        # channel's read-back instead of from what the caller asked for. Harmless while
        # every channel shares one MAXGAIN and nothing clamps -- the round trip is a
        # fixed point -- and wrong as soon as either stops being true.
        reported = volume
        for index, output in enumerate(self._outputs):
            XUNIT, XOUT = self.parse_output(output)
            _LOGGER.debug("Set Volume for output {} to {}".format(output, volume))
            landed = await self._xap(
                lambda XOUT=XOUT, XUNIT=XUNIT, v=volume:
                    self._xapx00.setPropGain(XOUT, v, group="O", unitCode=XUNIT)
            )
            if index == 0:
                # Agree with _get_volume_level, which reads _outputs[0]. On a zone whose
                # channels have different ceilings there is no single honest answer, so
                # the getter and the setter reporting the same channel is the least
                # surprising of the available wrong answers.
                reported = landed
        self._volume = reported

    @handle_xap_exceptions
    async def _get_volume_level(self):
        """Blocking XAP call — run in executor."""
        if not self.connectionLive(): return
        XUNIT, XOUT = self.parse_output(self._outputs[0])
        gain = await self._xap(
            lambda: self._xapx00.getPropGain(XOUT, group="O", unitCode=XUNIT)
        )
        self._volume = gain
        return self._volume

    async def _sync_volume_level(self):
        """Set all outputs in zone to same level as the first one."""
        if not self.connectionLive(): return
        if self._active_source != SRC_OFF:
            await self._get_volume_level()
            await self.async_set_volume_level(self._volume)

    @handle_xap_exceptions
    async def setDefaultLevel(self):
        """Set all crosspoint levels to default."""
        if not self.connectionLive(): return
        cnt = 0
        for xOut in self._outputs:
            XUNIT, XOUT = self.parse_output(xOut)
            for xIn in self._sources.values():
                XIN, XINGRP = xIn.getSource(XUNIT, cnt)
                await self._xap(
                    lambda XIN=XIN, XOUT=XOUT, XINGRP=XINGRP, XUNIT=XUNIT:
                        self._xapx00.setMatrixLevel(XIN, XOUT, self._defaultMatrixLevel,
                                                    inGroup=XINGRP, unitCode=XUNIT)
                )
            cnt += 1

    @property
    def source_list(self):
        """List of available input sources."""
        return sorted(self._sources)

    @property
    def source(self):
        """ Current source"""
        return self._active_source
