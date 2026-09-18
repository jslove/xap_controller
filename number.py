"""Source input trim, as a dB number entity.

Input trim is a calibration control. It is where headroom lives: an input sitting near
its MAXGAIN clips the input stage, and a wrong value there is not audible as "wrong" -
on one XAP800 a +10.89 dB input trim presented in an impulse measurement as a second
loudspeaker six metres away.

Reaching it through `media_player` made it look like a volume, which is the problem. Not
the dashboard slider so much as everything else that treats a media_player as a speaker:
`media_player.volume_set` from a broad automation targeting an area, voice assistants,
and the HomeKit/Alexa/Google bridges. A `number` in the CONFIG category is out of reach
of all of those by default, and says "trim" without a sentence in the docs asking people
to read it as one.

Expressed in dB rather than the 0-1 proportion `volume_level` uses. A proportion is a
fraction of that channel's MAXGAIN, which is not the number anyone wants to type, is not
what the Console app shows, and is unstable in exactly the case that matters: move
MAXGAIN and every proportion silently means something else.
"""

import json
import logging
import math

from homeassistant.components.number import NumberEntity
from homeassistant.const import EntityCategory
from homeassistant.exceptions import ServiceValidationError

from .config_flow import CONF_SOURCES
from .media_player import (
    DOMAIN,
    _connection_for,
    handle_xap_exceptions,
    parse_source_specs,
)

_LOGGER = logging.getLogger(__name__)

# How far below its own ceiling a trim may be taken from here.
#
# Bounded deliberately, rather than offering the hardware's full -65..20 dB. The ceiling
# is the top because the unit enforces it, and 20 dB below is more trim than a calibrated
# input should ever need - so a slip costs a couple of dB instead of a clipped input
# stage or a silent channel.
TRIM_RANGE_DB = 20.0
TRIM_STEP_DB = 0.5


async def async_setup_entry(hass, entry, async_add_entities):
    """One trim entity per input channel."""
    sources = json.loads(entry.data[CONF_SOURCES])

    entities = []
    for source_name, specs in sources.items():
        try:
            inputs = parse_source_specs(specs)
        except Exception:  # noqa: BLE001 - the media_player entity reports this properly
            _LOGGER.debug("source %s: unparseable specs, no trim entities", source_name)
            continue
        for index, inp in enumerate(inputs):
            entities.append(XAPSourceTrim(hass, entry, source_name, inp, index, len(inputs)))

    async_add_entities(entities)


class XAPSourceTrim(NumberEntity):
    """The input gain of one channel, in dB.

    One entity per *channel*, not per source, which is the one place this departs from
    the issue as filed. A source can carry several inputs, and a stereo pair trimmed
    apart for channel balance is precisely what a calibration control is for - a single
    number per source cannot express that, and writing it would flatten the pair the way
    `_firstConnect` used to. For the common single-input source the two are identical.
    """

    _attr_entity_category = EntityCategory.CONFIG
    _attr_native_unit_of_measurement = "dB"
    _attr_native_step = TRIM_STEP_DB
    _attr_has_entity_name = False
    # Off until someone goes looking for it. Turning trim on is then a toggle in the
    # entity's own settings dialog, per channel, rather than a trip through the config
    # flow to enable it globally and another trip to put it back.
    _attr_entity_registry_enabled_default = False

    def __init__(self, hass, entry, source_name, inp, index, of_many):
        self.hass = hass
        self._entry_id = entry.entry_id
        self._source_name = source_name
        self._input = inp
        self._max_db = None
        self._attr_native_value = None
        # Until the ceiling is known, offer the hardware range rather than a guess; it
        # narrows on the first update.
        self._attr_native_min_value = -65.0
        self._attr_native_max_value = 20.0
        suffix = "" if of_many == 1 else f" {inp['UNIT']}:{inp['CHAN']}"
        self._attr_name = f"Source: {source_name} trim{suffix}"
        self._attr_unique_id = (
            f"XAP-Trim-{entry.entry_id}-{inp['UNIT']}-{inp['CHAN']}"
        )

    def __str__(self):
        return self._attr_name

    def _conn(self):
        """Resolved per call, never captured.

        The connection belongs to the config entry, and holding one here would outlive a
        reload the way `send_command` used to. It also means this platform does not care
        whether it set up before or after media_player.
        """
        return _connection_for(self.hass, self._entry_id)

    async def _xap(self, fn):
        conn = self._conn()

        def _locked():
            with conn._lock:
                return fn(conn)

        return await self.hass.async_add_executor_job(_locked)

    @property
    def available(self):
        # Only the "no connection for this entry" case is swallowed - that is a real
        # state during setup and teardown. Anything else propagates so Home Assistant
        # logs it: a bare `except Exception` here turns any mistake in this class into a
        # permanently unavailable entity with nothing in the log to say why.
        try:
            conn = self._conn()
        except ServiceValidationError:
            return False
        return bool(conn.connectionLive)

    @handle_xap_exceptions
    async def async_update(self):
        """Read the channel's ceiling and its gain, and report the gain in dB."""
        if not self.available:
            return
        chan, unit = self._input['CHAN'], self._input['UNIT']
        self._max_db = float(await self._xap(
            lambda c: c.getMaxGain(chan, group="I", unitCode=unit, stereo=0)
        ))
        prop = await self._xap(
            lambda c: c.getPropGain(chan, group="I", unitCode=unit, stereo=0)
        )
        self._attr_native_max_value = self._max_db
        self._attr_native_min_value = self._max_db - TRIM_RANGE_DB
        # getPropGain is a ratio against MAXGAIN, so this is the absolute gain in dB.
        self._attr_native_value = (
            None if prop <= 0 else round(self._max_db + 20.0 * math.log10(prop), 2)
        )

    @handle_xap_exceptions
    async def async_set_native_value(self, value):
        """Write an absolute dB gain, expressed back as a proportion of the ceiling."""
        if self._max_db is None:
            await self.async_update()
        if self._max_db is None:
            return
        target = min(max(float(value), self._max_db - TRIM_RANGE_DB), self._max_db)
        chan, unit = self._input['CHAN'], self._input['UNIT']
        prop = 10.0 ** ((target - self._max_db) / 20.0)
        # No stereo=0 here, deliberately, unlike the reads above. On a connection in
        # stereo mode the decorator writes chan+1 as well, and XAPSource's own volume
        # write already behaves that way - so forcing stereo=0 would make this entity
        # the one thing that trims half a pair and leaves the other side behind, without
        # saying so. Reads keep stereo=0 because the decorator returns the first
        # channel's value either way, so pairing them only doubles the traffic.
        landed = await self._xap(
            lambda c: c.setPropGain(chan, prop, isAbsolute=1, group="I", unitCode=unit)
        )
        self._attr_native_value = (
            target if landed is None or landed <= 0
            else round(self._max_db + 20.0 * math.log10(landed), 2)
        )
