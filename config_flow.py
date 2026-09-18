"""Config flow for ClearOne XAP Controller."""

import json
import logging

import voluptuous as vol

from homeassistant import config_entries
from homeassistant.const import CONF_NAME
from homeassistant.core import callback

_LOGGER = logging.getLogger(__name__)

DOMAIN = "xap_controller"

CONF_PATH = "path"
CONF_SOURCES = "sources"
CONF_ZONES = "zones"
CONF_TYPE = "XAPType"
CONF_STEREO = "stereo"
CONF_BAUD = "baud"
CONF_CONNECTION_TYPE = "connection_type"
CONF_HOST = "host"
CONF_PORT = "port"
CONF_TELNET_USERNAME = "telnet_username"
CONF_TELNET_PASSWORD = "telnet_password"
CONF_EXPOSE_SOURCE_GAIN = "expose_source_gain"
CONF_MAX_GAIN = "max_gain"
CONF_UNIT_TYPES = "unit_types"

XAP_TYPES = ["XAP800", "XAP400", "CP880", "CP880T", "CP880TA"]
BAUD_RATES = [9600, 19200, 38400, 57600]
CONNECTION_TYPES = ["serial", "telnet"]

SOURCES_EXAMPLE = '{"Home Audio": [9], "TV": ["1:11:O:E"]}'
ZONES_EXAMPLE = '{"Kitchen": [3], "Office": ["2:1", "2:2"]}'
MAX_GAIN_EXAMPLE = '{"7": -15, "8": -15, "1:1": -12}'
UNIT_TYPES_EXAMPLE = "2:CP880"

# The XAP800 output gain range. MAXGAIN is the ceiling GAIN may be set to, and it is
# what a 1.0 volume_level means: getPropGain/setPropGain express level as a ratio
# against it, so leaving it at the +20 factory default squeezes every realistic
# listening level into the bottom 2% of a Home Assistant slider.
MAX_GAIN_MIN_DB = -65.0
MAX_GAIN_MAX_DB = 20.0


def parse_channel_key(key) -> tuple:
    """A max_gain key -> (unit, channel).

    Accepts the same shapes the zone/source channel lists do: a bare channel meaning
    unit 0, or "<unit>:<channel>". Raises ValueError on anything else, so callers can
    turn that into whatever error suits them.
    """
    text = str(key).strip()
    if ":" in text:
        unit_text, _, chan_text = text.partition(":")
    else:
        unit_text, chan_text = "0", text
    unit, channel = int(unit_text), int(chan_text)
    if not 0 <= unit <= 7:
        raise ValueError(f"unit {unit} out of range 0-7")
    if channel < 1:
        raise ValueError(f"channel {channel} must be 1 or greater")
    return unit, channel


def _validate_unit_types(text: str) -> dict:
    """Parse "unit:type, unit:type" into {unit: type}. Blank means every unit is XAPType.

    The command prefix is "#<type><id>" and the type is per MODEL - an 880T answers
    "#D<id>", a plain 880 "#1<id>" - so a chain that mixes models needs a type per
    unit. Saving sources & zones fills this in from the chain (_discover_unit_types),
    so by hand it is only for a unit that is off at the time: the entry is the first
    guess tried, and what the unit is addressed as once it comes back.
    """
    if not text or not text.strip():
        return {}
    result = {}
    for item in text.split(","):
        item = item.strip()
        if not item:
            continue
        unit_text, sep, type_text = item.partition(":")
        unit_text, type_text = unit_text.strip(), type_text.strip()
        if not sep or not unit_text.isdigit() or not 0 <= int(unit_text) <= 7:
            raise vol.Invalid("invalid_unit_types")
        if type_text not in XAP_TYPES or int(unit_text) in result:
            raise vol.Invalid("invalid_unit_types")
        result[int(unit_text)] = type_text
    return result


def _validate_max_gain(json_str: str) -> dict:
    """Parse and validate the per-channel max-gain JSON. Returns the parsed dict.

    Keys are output channels, values a ceiling in dB. A key is either a bare channel on
    unit 0 or "<unit>:<channel>", matching how zones and sources already address a
    chained system. Blank means "leave the unit alone", which is the old behaviour.
    """
    if not json_str or not json_str.strip():
        return {}
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        raise vol.Invalid("invalid_max_gain")
    if not isinstance(data, dict):
        raise vol.Invalid("invalid_max_gain")
    seen = set()
    for key, val in data.items():
        try:
            addr = parse_channel_key(key)
        except (TypeError, ValueError):
            raise vol.Invalid("invalid_max_gain")
        if addr in seen:
            # "7" and "0:7" are the same channel; two ceilings for it is a mistake
            # worth catching here rather than letting the last one win at setup.
            raise vol.Invalid("invalid_max_gain")
        seen.add(addr)
        if isinstance(val, bool) or not isinstance(val, (int, float)):
            raise vol.Invalid("invalid_max_gain")
        if not MAX_GAIN_MIN_DB <= float(val) <= MAX_GAIN_MAX_DB:
            raise vol.Invalid("invalid_max_gain")
    return data


# How many colon-separated components a channel spec may carry. A zone output is
# "<unit>:<channel>"; a source may also name an expansion bus and its group,
# "<unit>:<channel>:<bus>:<busgroup>".
_MAX_SPEC_PARTS = {"zones": 2, "sources": 4}


def _validate_channel_spec(spec, label: str) -> None:
    """Reject a channel spec the parsers cannot make sense of.

    Checking only the item type let malformed specs through to setup, where they surfaced
    as a crash rather than as a config error: "1:2:3" reached parse_output and raised
    ValueError unpacking three parts into two, and "1:2:3:4:5" reached parse_source,
    matched none of its comps branches, and hit int(None).

    Deliberately loose about the expansion-bus fields - only the component count and the
    numeric parts are checked - so that a working configuration using a bus letter or
    group this does not know about is not locked out at the config screen.
    """
    if isinstance(spec, bool) or not isinstance(spec, (int, str)):
        raise vol.Invalid(f"invalid_{label}")
    if isinstance(spec, int):
        return
    text = spec.strip()
    if not text:
        raise vol.Invalid(f"invalid_{label}")
    parts = text.split(":")
    if len(parts) > _MAX_SPEC_PARTS.get(label, 4):
        raise vol.Invalid(f"invalid_{label}")
    if len(parts) == 1:
        if not text.isdigit():
            raise vol.Invalid(f"invalid_{label}")
        return
    unit, channel = parts[0].strip(), parts[1].strip()
    if not unit.isdigit() or not channel.isdigit():
        raise vol.Invalid(f"invalid_{label}")
    if any(not part.strip() for part in parts[2:]):
        raise vol.Invalid(f"invalid_{label}")


def _validate_sources_zones(json_str: str, label: str) -> dict:
    """Parse and validate a JSON sources/zones string. Returns the parsed dict."""
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        raise vol.Invalid(f"invalid_{label}")
    if not isinstance(data, dict):
        raise vol.Invalid(f"invalid_{label}")
    for key, val in data.items():
        if not isinstance(key, str):
            raise vol.Invalid(f"invalid_{label}")
        if not isinstance(val, list):
            raise vol.Invalid(f"invalid_{label}")
        for item in val:
            _validate_channel_spec(item, label)
    return data


def _referenced_units(sources: dict, zones: dict) -> list:
    """Every unit id the sources and zones address.

    A bare channel is unit 0; "<unit>:..." names the unit. Malformed specs are
    skipped here - the validators and entity constructors report them.
    """
    units = set()
    for specs in list(sources.values()) + list(zones.values()):
        for spec in specs:
            if isinstance(spec, int):
                units.add(0)
            elif isinstance(spec, str):
                head, sep, _ = spec.partition(":")
                units.add(int(head) if sep and head.strip().isdigit() else 0)
    return sorted(units)


def _unit_types_text(unit_types: dict) -> str:
    """{2: "CP880"} -> "2:CP880", the field's own format."""
    return ", ".join(f"{u}:{t}" for u, t in sorted(unit_types.items()))


def _discover_unit_types(data: dict, units) -> str:
    """Ask each unit the sources and zones use what model it is; return the field text.

    This is what makes the "Unit types" field fill itself in. The command prefix is
    per model - an 880T is #D<id>, a plain 880 is #1<id> - and a unit is silent under
    any other model's prefix, so rather than have the operator know that, every unit
    the config addresses is asked VER under each prefix. The configured type, or the
    field's own entry, is tried first, so a correct description costs one command
    per unit and a wrong one a timeout per model. A unit that answers nothing (off,
    off the expansion bus, at another id) keeps whatever the field said: discovery
    adds, it does not forget. Runs in the executor.
    """
    known = dict(_validate_unit_types(data.get(CONF_UNIT_TYPES, "")))
    xapconn = _build_xapconn(data)
    if not xapconn.test_connection():
        _LOGGER.warning("unit discovery skipped: not connected")
        return _unit_types_text(known)
    default = data.get(CONF_TYPE, "XAP800")
    for unit in units:
        found = xapconn.discoverUnitType(unit)
        if found is None:
            _LOGGER.warning("unit %s did not answer as any model; its sources and "
                            "zones will not work until it does", unit)
        elif found == default:
            known.pop(unit, None)  # the device type covers it
        else:
            known[unit] = found
    _LOGGER.info("unit discovery: %s -> unit types %r", units, _unit_types_text(known))
    return _unit_types_text(known)


def _build_xapconn(data):
    """Instantiate an XAPX00 connection object from config data (runs in executor)."""
    from XAPX00 import XAPX00

    conn_type = data.get(CONF_CONNECTION_TYPE, "serial")
    xap_type = data.get(CONF_TYPE, "XAP800")
    unit_types = _validate_unit_types(data.get(CONF_UNIT_TYPES, ""))
    if conn_type == "telnet":
        xapconn = XAPX00(
            connection_type="telnet",
            telnet_host=data.get(CONF_HOST),
            telnet_port=data.get(CONF_PORT, 23),
            telnet_username=data.get(CONF_TELNET_USERNAME, "clearone"),
            telnet_password=data.get(CONF_TELNET_PASSWORD, "converge"),
            XAPType=xap_type,
            unit_types=unit_types,
        )
    else:
        # baudRate must be a constructor argument, not assigned afterwards: the
        # constructor opens the port, so a later assignment leaves the link running at
        # the 38400 default and every exchange times out.
        xapconn = XAPX00(
            data.get(CONF_PATH, "/dev/ttyUSB0"),
            baudRate=data.get(CONF_BAUD, 38400),
            XAPType=xap_type,
            unit_types=unit_types,
        )
    return xapconn


class _DiscoveryMixin:
    """Fill in "Unit types" from the chain itself, for the units the config addresses."""

    async def _discover(self, data):
        units = _referenced_units(
            json.loads(data[CONF_SOURCES]), json.loads(data[CONF_ZONES])
        )
        try:
            return await self.hass.async_add_executor_job(
                _discover_unit_types, data, units
            )
        except Exception:  # noqa: BLE001 - discovery is a convenience, never a blocker
            _LOGGER.exception("unit discovery failed; keeping the field as entered")
            return data.get(CONF_UNIT_TYPES, "")


class XapControllerConfigFlow(_DiscoveryMixin, config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for XAP Controller."""

    VERSION = 1

    def __init__(self):
        self._connection_data = {}

    async def async_step_user(self, user_input=None):
        """Step 1: device type, name, stereo, and connection type."""
        errors = {}

        if user_input is not None:
            try:
                _validate_unit_types(user_input.get(CONF_UNIT_TYPES, ""))
            except vol.Invalid:
                errors[CONF_UNIT_TYPES] = "invalid_unit_types"
            if not errors:
                self._connection_data = user_input
                conn_type = user_input.get(CONF_CONNECTION_TYPE, "serial")
                if conn_type == "telnet":
                    return await self.async_step_telnet()
                return await self.async_step_serial()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="XAP"): str,
                vol.Optional(CONF_TYPE, default="XAP800"): vol.In(XAP_TYPES),
                vol.Optional(CONF_UNIT_TYPES, default=""): str,
                vol.Optional(CONF_STEREO, default=False): bool,
                vol.Optional(CONF_CONNECTION_TYPE, default="serial"): vol.In(
                    CONNECTION_TYPES
                ),
            }
        )

        return self.async_show_form(
            step_id="user",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_serial(self, user_input=None):
        """Step 2a: serial connection parameters."""
        errors = {}

        if user_input is not None:
            merged = {**self._connection_data, **user_input}
            try:
                connected = await self.hass.async_add_executor_job(
                    lambda: _build_xapconn(merged).test_connection()
                )
                if not connected:
                    errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("XAP connection test failed")
                errors["base"] = "cannot_connect"

            if not errors or user_input.get("proceed_anyway"):
                self._connection_data = merged
                return await self.async_step_sources_zones()

        schema = vol.Schema(
            {
                vol.Required(CONF_PATH, default="/dev/ttyUSB0"): str,
                vol.Optional(CONF_BAUD, default=38400): vol.In(BAUD_RATES),
                vol.Optional("proceed_anyway", default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="serial",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_telnet(self, user_input=None):
        """Step 2b: telnet connection parameters (new setup only)."""
        errors = {}

        if user_input is not None:
            if user_input.get("test_connection"):
                # Run the test and redisplay the form with the result.
                merged = {**self._connection_data, **user_input}
                try:
                    connected = await self.hass.async_add_executor_job(
                        lambda: _build_xapconn(merged).test_connection()
                    )
                    if not connected:
                        errors["base"] = "cannot_connect"
                except Exception:
                    _LOGGER.exception("XAP connection test failed")
                    errors["base"] = "cannot_connect"
            else:
                self._connection_data = {**self._connection_data, **user_input}
                return await self.async_step_sources_zones()

        host = user_input.get(CONF_HOST, "") if user_input else ""
        port = user_input.get(CONF_PORT, 23) if user_input else 23
        username = user_input.get(CONF_TELNET_USERNAME, "clearone") if user_input else "clearone"
        password = user_input.get(CONF_TELNET_PASSWORD, "converge") if user_input else "converge"

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=host): str,
                vol.Optional(CONF_PORT, default=port): int,
                vol.Optional(CONF_TELNET_USERNAME, default=username): str,
                vol.Optional(CONF_TELNET_PASSWORD, default=password): str,
                vol.Optional("test_connection", default=False): bool,
            }
        )

        return self.async_show_form(
            step_id="telnet",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_sources_zones(self, user_input=None):
        """Step 3: sources and zones as JSON."""
        errors = {}

        if user_input is not None:
            try:
                _validate_sources_zones(user_input[CONF_SOURCES], "sources")
            except vol.Invalid:
                errors[CONF_SOURCES] = "invalid_sources"

            try:
                _validate_sources_zones(user_input[CONF_ZONES], "zones")
            except vol.Invalid:
                errors[CONF_ZONES] = "invalid_zones"

            try:
                _validate_max_gain(user_input.get(CONF_MAX_GAIN, ""))
            except vol.Invalid:
                errors[CONF_MAX_GAIN] = "invalid_max_gain"

            if not errors:
                data = {**self._connection_data, **user_input}
                data[CONF_UNIT_TYPES] = await self._discover(data)
                title = self._connection_data.get(
                    CONF_NAME,
                    self._connection_data.get(
                        CONF_PATH, self._connection_data.get(CONF_HOST, "XAP")
                    ),
                )
                unique_id = self._connection_data.get(CONF_HOST) or self._connection_data.get(CONF_PATH, "xap")
                await self.async_set_unique_id(unique_id)
                self._abort_if_unique_id_configured()
                return self.async_create_entry(title=title, data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCES, default=SOURCES_EXAMPLE): str,
                vol.Required(CONF_ZONES, default=ZONES_EXAMPLE): str,
                vol.Optional(CONF_EXPOSE_SOURCE_GAIN, default=False): bool,
                vol.Optional(CONF_MAX_GAIN, default=""): str,
            }
        )

        return self.async_show_form(
            step_id="sources_zones",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_import(self, import_data):
        """Handle import from configuration.yaml (always serial)."""
        await self.async_set_unique_id(import_data[CONF_PATH])
        self._abort_if_unique_id_configured()

        data = {
            k: v for k, v in import_data.items() if k not in (CONF_SOURCES, CONF_ZONES)
        }
        data[CONF_SOURCES] = json.dumps(import_data[CONF_SOURCES])
        data[CONF_ZONES] = json.dumps(import_data[CONF_ZONES])
        data[CONF_CONNECTION_TYPE] = "serial"

        title = import_data.get(CONF_NAME, import_data[CONF_PATH])
        _LOGGER.info(
            "Importing xap_controller entry '%s' from configuration.yaml", title
        )
        return self.async_create_entry(title=title, data=data)

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        return XapControllerOptionsFlow(config_entry)


class XapControllerOptionsFlow(_DiscoveryMixin, config_entries.OptionsFlow):
    """Handle options (edit after setup)."""

    def __init__(self, config_entry):
        self._entry = config_entry
        self._connection_data = {}

    async def async_step_init(self, user_input=None):
        """Step 1: device type, name, stereo, and connection type."""
        errors = {}
        current = self._entry.data

        if user_input is not None:
            try:
                _validate_unit_types(user_input.get(CONF_UNIT_TYPES, ""))
            except vol.Invalid:
                errors[CONF_UNIT_TYPES] = "invalid_unit_types"
            if not errors:
                self._connection_data = user_input
                conn_type = user_input.get(CONF_CONNECTION_TYPE, "serial")
                if conn_type == "telnet":
                    return await self.async_step_telnet()
                return await self.async_step_serial()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default=current.get(CONF_NAME, "XAP")): str,
                vol.Optional(
                    CONF_TYPE, default=current.get(CONF_TYPE, "XAP800")
                ): vol.In(XAP_TYPES),
                vol.Optional(
                    CONF_UNIT_TYPES, default=current.get(CONF_UNIT_TYPES, "")
                ): str,
                vol.Optional(
                    CONF_STEREO, default=current.get(CONF_STEREO, False)
                ): bool,
                vol.Optional(
                    CONF_CONNECTION_TYPE,
                    default=current.get(CONF_CONNECTION_TYPE, "serial"),
                ): vol.In(CONNECTION_TYPES),
            }
        )

        return self.async_show_form(
            step_id="init",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_serial(self, user_input=None):
        """Step 2a: serial connection parameters."""
        errors = {}
        current = self._entry.data

        if user_input is not None:
            merged = {**self._connection_data, **user_input}
            try:
                connected = await self.hass.async_add_executor_job(
                    lambda: _build_xapconn(merged).test_connection()
                )
                if not connected:
                    errors["base"] = "cannot_connect"
            except Exception:
                _LOGGER.exception("XAP connection test failed")
                errors["base"] = "cannot_connect"

            if not errors:
                self._connection_data = merged
                return await self.async_step_sources_zones()

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_PATH, default=current.get(CONF_PATH, "/dev/ttyUSB0")
                ): str,
                vol.Optional(CONF_BAUD, default=current.get(CONF_BAUD, 38400)): vol.In(
                    BAUD_RATES
                ),
            }
        )

        return self.async_show_form(
            step_id="serial",
            data_schema=schema,
            errors=errors,
        )

    async def async_step_telnet(self, user_input=None):
        """Step 2b: telnet connection parameters."""
        # No connection test — see ConfigFlow.async_step_telnet for rationale.
        current = self._entry.data

        if user_input is not None:
            self._connection_data = {**self._connection_data, **user_input}
            return await self.async_step_sources_zones()

        schema = vol.Schema(
            {
                vol.Required(CONF_HOST, default=current.get(CONF_HOST, "")): str,
                vol.Optional(CONF_PORT, default=current.get(CONF_PORT, 23)): int,
                vol.Optional(
                    CONF_TELNET_USERNAME,
                    default=current.get(CONF_TELNET_USERNAME, "clearone"),
                ): str,
                vol.Optional(
                    CONF_TELNET_PASSWORD,
                    default=current.get(CONF_TELNET_PASSWORD, "converge"),
                ): str,
            }
        )

        return self.async_show_form(
            step_id="telnet",
            data_schema=schema,
            errors={},
        )

    async def async_step_sources_zones(self, user_input=None):
        """Step 3: sources and zones."""
        errors = {}
        current = self._entry.data

        if user_input is not None:
            try:
                _validate_sources_zones(user_input[CONF_SOURCES], "sources")
            except vol.Invalid:
                errors[CONF_SOURCES] = "invalid_sources"

            try:
                _validate_sources_zones(user_input[CONF_ZONES], "zones")
            except vol.Invalid:
                errors[CONF_ZONES] = "invalid_zones"

            try:
                _validate_max_gain(user_input.get(CONF_MAX_GAIN, ""))
            except vol.Invalid:
                errors[CONF_MAX_GAIN] = "invalid_max_gain"

            if not errors:
                new_data = {**self._entry.data, **self._connection_data, **user_input}
                new_data[CONF_UNIT_TYPES] = await self._discover(new_data)
                self.hass.config_entries.async_update_entry(self._entry, data=new_data)
                return self.async_create_entry(title="", data={})

        schema = vol.Schema(
            {
                vol.Required(
                    CONF_SOURCES, default=current.get(CONF_SOURCES, SOURCES_EXAMPLE)
                ): str,
                vol.Required(
                    CONF_ZONES, default=current.get(CONF_ZONES, ZONES_EXAMPLE)
                ): str,
                vol.Optional(
                    CONF_EXPOSE_SOURCE_GAIN,
                    default=current.get(CONF_EXPOSE_SOURCE_GAIN, False),
                ): bool,
                vol.Optional(
                    CONF_MAX_GAIN, default=current.get(CONF_MAX_GAIN, "")
                ): str,
            }
        )

        return self.async_show_form(
            step_id="sources_zones",
            data_schema=schema,
            errors=errors,
        )
