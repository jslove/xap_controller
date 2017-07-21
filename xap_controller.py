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
         - "1:11"
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
from string import ascii_uppercase
from homeassistant.components.media_player import (
    SUPPORT_TURN_OFF, SUPPORT_TURN_ON, SUPPORT_VOLUME_MUTE,
    SUPPORT_VOLUME_SET, SUPPORT_SELECT_SOURCE, MediaPlayerDevice,
    PLATFORM_SCHEMA, MEDIA_TYPE_MUSIC)

from homeassistant.const import (
    STATE_OFF, STATE_ON, CONF_NAME)

import homeassistant.helpers.config_validation as cv

#REQUIREMENTS = [
#    'https://github.com/jslove/XAPX00/archive/0.2.1.zip'
#    '#XAPX00==0.2.1']

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
    cv.string: vol.Any(int,str),
})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
    vol.Required(CONF_PATH): cv.string,
    vol.Required(CONF_ZONES): vol.Schema({cv.string:
                                          vol.All(cv.ensure_list, [vol.Any(int,str)])}),
    vol.Required(CONF_SOURCES): SOURCE_SCHEMA,
})
# PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend({
#     vol.Required(CONF_PATH): cv.string,
#     vol.Required(CONF_ZONES): vol.Schema({cv.string:
#                                           vol.All(cv.ensure_list, [int])}),
#     vol.Required(CONF_SOURCES): SOURCE_SCHEMA,
# })


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
    if not xapconn.connected:
        _LOGGER.error('Not connected to %s', path)
        return
        

    sources = config[CONF_SOURCES]
    source_objs=[]
    zonesources = {}
    for source_name, source_input in sources.items():
        sourceobj = XAPSource(
            hass, xapconn, source_name, source_input)
        add_devices([sourceobj])
        source_objs.append(sourceobj)
        zonesources[source_name] = sourceobj

    zonesources[SRC_OFF] = 0

    for zone_name, outputs in config[CONF_ZONES].items():
        add_devices([XAPZone(
            hass, xapconn, zonesources, zone_name, outputs)])


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
        self.xunit = 0
        self.xinput = None
        self.xgroup = "I"
        self.xbus = None
        self.xbusgroup = None
        self.parse_source(source_input)
        self._volume = self.get_volume_level()
        self._isMuted = self.get_mute_status()
        _LOGGER.info("source {} set up".format(self.__str__()))

    def __str__(self):
        return self._name

    def __repr__(self):
        return "{} (Unit:{}, Input:{}, Bus:{}, Group:{})".format(self._name, self.xunit,
                                                                self.xinput, self.xbus, self.xbusgrp)

    def parse_source(self, src):
        "Fill in self's input #, input unit, expansion bus, expansion bus group"
        XBUS = None
        XBUSGRP = None
        XUNIT = 0
        if type(src) is int:
            XCHAN = src
        elif type(src) is str:
            if ":" in src:
                comps = src.count(':')
                if comps == 1:
                    XCHAN, XUNIT =  src.split(":")
                elif comps == 2:
                    XCHAN, XUNIT, XBUS = src.split(":")
                    XBUSGRP = 'E' # default to E
                elif comps == 3:
                    XCHAN, XUNIT, XBUS, XBUSGRP = src.split(":")                    
                XCHAN = int(XCHAN)
                XUNIT = int(XUNIT)
            elif src.isdigit():
                XCHAN = int(src)
            else:
                raise Exception('Invalid Input String')
        else:
            # shouldn't be able to get here
            raise Exception('Invalid Source Input config format')
        self.xinput = XCHAN
        self.xunit = XUNIT
        self.xbus = XBUS
        self.xbusgrp = XBUSGRP
        return

    def getSource(self, outUnit):
        if outUnit == self.xunit:
            return self.xinput, self.xgroup
        else:
            if self.xbus is None:
                raise Exception("Different unit but No Expansion Bus Defined")
            return self.xbus, self.xbusgrp
    
    def source_for_zones(self):
        if self.xbus is not None:
            # either expansoin or processing
            group = 'E' if self.xbus in self._xapx00.ExpansionChannels else 'P'
            channel = self.xbus
        else:
            channel = self.xinput
            group = "I"
        return channel, group
    
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
        gain = self._xapx00.getPropGain(self.xinput, group="I", unitCode = self.xunit)
        self._volume = gain
        return self._volume

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        volume = self._xapx00.setPropGain(self.xinput, volume,
                                          isAbsolute=1, group="I", unitCode = self.xunit)
        self._volume = volume

    def turn_on(self):
        """Turn the media player on."""
        if self._xapx00.getMute(self.xinput, unitCode = self.xunit) == 1:
            self._isMuted = self._xapx00.setMute(self.xinput, isMuted=0, unitCode = self.xunit)
        self._state = STATE_ON

    def turn_off(self):
        """Turn off media player."""
        if self._xapx00.getMute(self._input, unitCode=self.xunit) == 0:
            self._isMuted = self._xapx00.setMute(self.xinput, group="I",
                                                 isMuted=1, unitCode = self.xunit)
        self._state = STATE_OFF

    def mute_volume(self, mute):
        """Toggle mute"""
        self._isMuted = self._xapx00.setMute(self.xinput, group="I", isMuted=2, unitCode = self.xunit)

    def get_mute_status(self):
        self._isMuted = self._xapx00.getMute(self.xinput, group="I", unitCode= self.xunit)
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
        self._sources = sources #dict of source name:source obj
        self._outputs = outputs
        # outputs is a list of outputs, each element can be a single int or
        # a string of "int:int" (unit:output)
        self._volume = 0
        self._defaultMatrixLevel = 1
        self._isMuted = self.get_mute_status()
        self._active_source = SRC_OFF
        self._active_source = self.get_source()
        # make sure sources synced across outputs
        self.select_source(self._active_source)
        self._sync_volume_level()
        self._state = STATE_ON if self._active_source != SRC_OFF else STATE_OFF
        _LOGGER.info("zone {} set up".format(self.__str__()))
        self._poweroff_source = self._active_source

    def __str__(self):
        return self._name
        
    def parse_output(self, output):
        " return (unit,output) "
        if type(output) is int:
            XUNIT = 0
            XOUT = output
        elif type(output) is str:
            if ":" in output:
                XOUT, XUNIT =  output.split(":")
            elif output.isdigit():
                XUNIT = 0
            else:
                raise Exception('Invalid Output String')
        else:
            # shouldn't be able to get here
            raise Exception('Invalid Output config format')
        return int(XOUT), int(XUNIT)
            
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
            XOUT, XUNIT = self.parse_output(xOut)
            for xIn in self._sources.values():
                XIN, XINGRP = xIn.getSource(XUNIT)
                self._xapx00.setMatrixLevel(XIN,
                                            XOUT,
                                            self._defaultMatrixLevel,
                                            inGroup =  XINGRP,
                                            unitCode = XUNIT)
#   not used
    def clear_matrix(self):
        """ set all crosspoints to off"""
        for xOut in self._outputs:
            XOUT, XUNIT = self.parse_output(xOut)
            for xIn in self._xapx00.input_range:
                self._xapx00.setMatrixRouting(xIn, xOut, 0, unitCode=XUNIT)
            for xIn in list(ascii_uppercase[ascii_uppercase.find('O'):]):
                self._xapx00.setMatrixRouting(xIn, xOut, 0, inGroup='E', unitCode=XUNIT)


    def get_source(self):
        """ Get first active source for outputs in this zone """
        _LOGGER.debug("In get_source for {}".format(self))
        _LOGGER.debug("  Checking: {}".format(self._sources))
        for xIn in self._sources.values():
            if xIn != self._sources[SRC_OFF]:
                XOUT, XUNIT = self.parse_output(self._outputs[0])
                XIN, XINGRP = xIn.getSource(XUNIT)
                z_state = int(self._xapx00.getMatrixRouting(XIN,
                                                            XOUT,
                                                            inGroup = XINGRP,
                                                            unitCode = XUNIT))
                _LOGGER.debug("matrix routing for {}={}". format(xIn, z_state))
                if z_state > 0:
                    self._active_source = xIn.__str__()
                    break
        _LOGGER.debug("get_source for %s = %s" % (self._name, self._active_source))
        return self._active_source

    def _sync_volume_level(self):
        """set all level of all outputs in zone to the same
        level as the first one in zone"""
        if self._active_source != SRC_OFF:
            XOUT, XUNIT = self.parse_output(self._outputs[0])
            volume = self._xapx00.getPropGain(XOUT, group="O",
                                              unitCode = XUNIT)
            self.set_volume_level(volume)

    def set_volume_level(self, volume):
        """Set volume level, range 0..1."""
        for output in self._outputs:
            XOUT, XUNIT = self.parse_output(output)
            _LOGGER.debug("Set Volume for output {}".format(output))
            volume = self._xapx00.setPropGain(XOUT, volume, group="O",
                                              unitCode = XUNIT)
        self._volume = volume

    def get_volume_level(self):
        """Volume level of the media player (0..1)."""
        XOUT, XUNIT = self.parse_output(self._outputs[0])
        gain = self._xapx00.getPropGain(XOUT, group="O", unitCode = XUNIT)
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
            XOUT, XUNIT = self.parse_output(output)
            muted = self._xapx00.setMute(XOUT, group="O", isMuted=int(mute),
                                         unitCode = XUNIT)
        self._isMuted = bool(muted)

    def get_mute_status(self):
        XOUT, XUNIT = self.parse_output(self._outputs[0])
        self._isMuted = bool(self._xapx00.getMute(XOUT, group="O", unitCode=XUNIT))
        return self._isMuted

    def select_source(self, source):
        """Set the input source"""
        actsrc = self._active_source  # a string
        _LOGGER.debug('select_source: source={}, actsrc = {}, self._sources={}'.format(
            source, actsrc, self._sources))
        for xOut in self._outputs:
            XOUT, XUNIT = self.parse_output(xOut)
            if actsrc != SRC_OFF and actsrc != source:
                XIN, XINGRP = self._sources[actsrc].getSource(XUNIT)
                self._xapx00.setMatrixRouting(XIN, XOUT, 0, inGroup = XINGRP, unitCode = XUNIT) #turn current off
            self._active_source = SRC_OFF
            if source != SRC_OFF and source in self._sources:
                XIN, XINGRP = self._sources[source].getSource(XUNIT)
                ON=3 if (type(XIN) is int and XIN < 9) else 1  # if a mike input
                self._xapx00.setMatrixRouting(XIN, XOUT, ON, inGroup = XINGRP, unitCode = XUNIT)
                self._active_source = source

    @property
    def source_list(self):
        """List of available input sources."""
        return list(self._sources.keys())

    @property
    def source(self):
        """ Current source"""
        _LOGGER.debug("property: source: {}".format(self._active_source))
        return self._active_source

