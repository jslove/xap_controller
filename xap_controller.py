# pylint: disable = E0126
"""
Support for interfacing with ClearOne XAP800 and XAP400 units via serial port.

For more details about this platform, please refer to the documentation at
https://home-assistant.io/components/media_player.xap_controller/


There are two components in the platform: output Zones and input Sources.  The input sources are assumed to be XAP type I inputs, 
the output zones type O outpurs.  The system can assume that the channels are set up for stereo, so that there are 2 channels paired 
together.  If stereo=1, the module will take each action twice, once on the listed source/zone number and again on the source/zone + 1.

For each source or zone, indicate the channel to use on the XAP unit.

The platform will create individual media_player controls for each source and zone.  Each source will be shown with a volume slider, adjusting the 
gain for that input.  Each Zone will be shown with a dropbox to select from the available zones and a volume slider to adjust the gain for that output.

Basic configuration:

media_player:
   - platform: xap_controller
     path: /dev/ttyUSB-XAP800
     name: MyXAP
     scan_interval: 30
     stereo: 1
     baud: 9600
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
         - 11
     sources:
       'Home Audio': 9
       'Family TV Audio': 11

zones: a list of output zone names, with a list one or more outputs for each zone
sources: a list of source names, with a list of one source input number per source name.
path: serial device path (can be a virtual serial port, using socat for example)
name: the name of the platform instance
stereo: 1=stereo, 0=mono  If stereo=1, each action will be performed twice on the output and output+1
baud: baud rate of serial port, default=38400
scan_interval: how often to scane the unit for changes

"""

import time
import logging
import voluptuous as vol

from homeassistant.components.media_player import (
    SUPPORT_TURN_OFF, SUPPORT_TURN_ON, SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET, SUPPORT_SELECT_SOURCE, MediaPlayerDevice,
    PLATFORM_SCHEMA, MEDIA_TYPE_MUSIC)

from homeassistant.const import (
    STATE_OFF, STATE_ON, CONF_NAME)

import homeassistant.helpers.config_validation as cv

REQUIREMENTS = [
    'https://github.com/jslove/XAPX00/archive/0.1.1.zip'
    '#XAPX00==0.1.1']

testing = 0

DOMAIN = 'xap_controller'

_LOGGER = logging.getLogger(__name__)

CONF_ZONES   = 'zones'
CONF_SOURCES = 'sources'
CONF_PATH    = 'path'
CONF_STEREO  = 'stereo'
CONF_BAUD    = 'baud'

SRC_OFF = 'Off'

SUPPORT_XAP_ZONE = \
                   SUPPORT_VOLUME_MUTE | SUPPORT_VOLUME_SET | \
                   SUPPORT_TURN_ON | SUPPORT_TURN_OFF | \
                   SUPPORT_SELECT_SOURCE

SUPPORT_XAP_SOURCE = SUPPORT_VOLUME_MUTE | SUPPORT_VOLUME_SET | \
                     SUPPORT_TURN_ON | SUPPORT_TURN_OFF


OUTPUT_SCHEMA = vol.Schema({
    vol.Required(CONF_NAME): cv.string,
})

SOURCE_SCHEMA = vol.Schema({
    cv.string: int,
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_PATH): cv.string,
    vol.Required(CONF_ZONES): vol.Schema({cv.string:
                                          vol.All(cv.ensure_list, [int])}),
    vol.Required(CONF_SOURCES): SOURCE_SCHEMA,
})


def setup_platform(hass, config, add_devices, discovery_info=None):
    """Setup the XAPX00 platform."""
    path = config.get(CONF_PATH)

    if path is None:
        _LOGGER.error("Invalid config. Expected %s",
                      CONF_PATH)
        return False

    from XAPX00 import XAPX00

    xapconn = XAPX00.XAPX00(path)

    if config.get(CONF_STEREO, 1) == 0:
        xapconn.stereo = 0
    else:
        xapconn.stereo = 1

    xapconn.baud = config.get(CONF_BAUD, 38400)

    xapconn.convertDb = 1
    xapconn.connect()

    sources = config[CONF_SOURCES]
    if xapconn.connected:
        for source_name, source_input in sources.items():
                add_devices([XAPSource(
                    hass, xapconn, source_name, source_input)])
    else:
        _LOGGER.error('Not connected to %s', path)

    sources[SRC_OFF] = 0

    if xapconn.connected:
        for zone_name, outputs in config[CONF_ZONES].items():
            add_devices([XAPZone(
                hass, xapconn, sources, zone_name, outputs)])
    else:
        _LOGGER.error('Not connected to %s', path)


class XAPSource(MediaPlayerDevice):
    """
    Represents one source
    """

    def __init__(self, hass, xapconn, source_name, source_input, unitCode=0):
        """Initialise the XAPX00 source pseudo-device"""
        _LOGGER.debug("Setting Up Source %s" % source_name)
        self._name = source_name
        self._xapx00 = xapconn
        self._state = STATE_ON
        self._input = source_input
        self._volume = self.get_volume_level()
        self._isMuted = self.get_mute_status()

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
        return SUPPORT_XAP_SOURCE

    @property
    def volume_level(self):
        """Volume level of the media player (0..1)."""
        return self._volume

    @property
    def is_volume_muted(self):
        """ return bool mute status"""
        return bool(self._isMuted)

    def get_volume_level(self):
        """Volume level of the media player (0..1)."""
        gain = self._xapx00.getPropGain(self._input, group="I")
        self._volume = gain
        return self._volume

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        volume = self._xapx00.setPropGain(self._input, volume,
                                          isAbsolute=1, group="I")
        self._volume = volume

    def turn_on(self):
        """Turn the media player on."""
        if self._xapx00.getMute(self._input) == 1:
            self._isMuted = self._xapx00.setMute(self._input, isMuted=0)
        self._state = STATE_ON

    def turn_off(self):
        """Turn off media player."""
        if self._xapx00.getMute(self._input) == 0:
            self._isMuted = self._xapx00.setMute(self._input, group="I",
                                                 isMuted=1)
        self._state = STATE_OFF

    def mute_volume(self, mute):
        """Toggle mute"""
        self._isMuted = self._xapx00.setMute(self._input, group="I", isMuted=2)

    def get_mute_status(self):
        self._isMuted = self._xapx00.getMute(self._input, group="I")
        return self._isMuted


class XAPZone(MediaPlayerDevice):
    """
    Represents one or more XAP outputs, either mono or stereo
    """
    def __init__(self, hass, xapconn, sources, zone_name, outputs, unitCode=0):
        """Initialise the XAPX00 zone pseudo-device"""
        self._name = zone_name
        self._xapx00 = xapconn
        self._unitCode = unitCode
        self._sources = sources  # a dict, source name to input #
        self._sources_reverse = {v: k for k, v in sources.items()}
        self._outputs = outputs  # a list of ouputs
        self._volume = 0
        self._defaultMatrixLevel = 1
        self._isMuted = self.get_mute_status()
        self._active_source = SRC_OFF
        self._active_source = self.get_source()
        # make sure sources synced across outputs
        self.select_source(self._active_source)
        self._sync_volume_level()
        self._state = STATE_ON if self._active_source != SRC_OFF else STATE_OFF
        _LOGGER.info("zone {} set up".format(zone_name))
        self._poweroff_source = SRC_OFF

    def update(self):
        self.get_mute_status()
        self.get_source()
        self.get_volume_level()

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
        return MEDIA_TYPE_MUSIC

    @property
    def media_title(self):
        """ Return current source"""
        return self._active_source

    @property
    def is_volume_muted(self):
        """ return mute status"""
        return bool(self._isMuted)

    def setDefaultLevel(self):
        """  set all crosspoint levels to default """
        for xOut in self._outputs:
            for source in self._sources:
                self._xapx00.setMatrixLevel(self._sources[source],
                                            self._outputs[xOut],
                                            self._defaultMatrixLevel)

    def clear_matrix(self):
        """ set all crosspoints to off"""
        for xOut in self._outputs:
            for xIn in self._xapx00.input_range:
                self._xapx00.setMatrixRouting(xIn, xOut, 0)

    def get_source(self):
        """ Get first active source for outputs in this zone """
        _LOGGER.debug("In get_source")
        for i in self._sources.keys():
            if i != SRC_OFF:
                z_state = self._xapx00.getMatrixRouting(self._sources[i],
                                                        self._outputs[0])
                _LOGGER.debug("matrix rounting for {}={}". format(i, z_state))
                if z_state == 1:
                    self._active_source = i
                    break
            # if testing:
            #     actsrc = self._sources_reverse[1]
        _LOGGER.debug("get_source = %s" % self._active_source)
        return self._active_source

    def _sync_volume_level(self):
        """set all level of all outputs in zone to the same
        level as the first one in zone"""
        if self._active_source != SRC_OFF:
            volume = self._xapx00.getPropGain(self._outputs[0], group="O",
                                              unitCode=self._unitCode)
            # volume = self._xapx00.getMatrixLevel(self._sources[
            # self._active_source], self._outputs[0])
            self.set_volume_level(volume)

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        for output in self._outputs:
            _LOGGER.debug("Set Volume for output {}".format(output))
            volume = self._xapx00.setPropGain(output, volume, group="O",
                                              unitCode=self._unitCode)
            # self._xapx00.setMatrixLevel(self._sources[self._active_source],
            # output, volume)
        self._volume = volume

    def get_volume_level(self):
        """Volume level of the media player (0..1)."""
        gain = self._xapx00.getPropGain(self._outputs[0], group="O")
        self._volume = gain
        return self._volume

    def turn_on(self):
        """Turn zone on"""
        self._state = STATE_ON
        self.select_source(self._poweroff_source)
        self.mute_volume(0)

    def turn_off(self):
        """Turn off zone"""
        self._state = STATE_OFF
        self._poweroff_source = self._active_source
        self.select_source(SRC_OFF)
        self.mute_volume(1)

    def mute_volume(self, mute=2):
        """Send mute command, mute is bool from hass, default is 2 (toggle)"""
        for output in self._outputs:
            muted = self._xapx00.setMute(output, group="O", isMuted=int(mute),
                                         unitCode=self._unitCode)
        self._isMuted = bool(muted)

    def get_mute_status(self):
        self._isMuted = bool(self._xapx00.getMute(self._outputs[0], group="O"))
        return self._isMuted

    def select_source(self, source):
        """Set the input source"""
        actsrc = self._active_source
        for xOut in self._outputs:
            if actsrc != SRC_OFF:
                self._xapx00.setMatrixRouting(self._sources[actsrc], xOut, 0)
            self._active_source = SRC_OFF
            if source in self._sources and source != SRC_OFF:
                self._xapx00.setMatrixRouting(self._sources[source], xOut, 1)
                self._active_source = source

    @property
    def source_list(self):
        """List of available input sources."""
        _LOGGER.debug("Source List, Active Source: {}".format(
            self._active_source))
        return list(self._sources.keys())

    @property
    def source(self):
        """ Current source"""
        _LOGGER.debug("property: source: {}".format(self._active_source))
        return self._active_source

