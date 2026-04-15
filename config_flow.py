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

XAP_TYPES = ["XAP800", "XAP400", "CP880", "CP880T", "CP880TA"]
BAUD_RATES = [9600, 19200, 38400, 57600]
CONNECTION_TYPES = ["serial", "telnet"]

SOURCES_EXAMPLE = '{"Home Audio": [9], "TV": ["1:11:O:E"]}'
ZONES_EXAMPLE = '{"Kitchen": [3], "Office": ["2:1", "2:2"]}'


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
            if not isinstance(item, (int, str)):
                raise vol.Invalid(f"invalid_{label}")
    return data


def _build_xapconn(data):
    """Instantiate an XAPX00 connection object from config data (runs in executor)."""
    from XAPX00 import XAPX00

    conn_type = data.get(CONF_CONNECTION_TYPE, "serial")
    xap_type = data.get(CONF_TYPE, "XAP800")
    if conn_type == "telnet":
        xapconn = XAPX00.XAPX00(
            connection_type="telnet",
            telnet_host=data.get(CONF_HOST),
            telnet_port=data.get(CONF_PORT, 23),
            telnet_username=data.get(CONF_TELNET_USERNAME, "clearone"),
            telnet_password=data.get(CONF_TELNET_PASSWORD, "converge"),
            XAPType=xap_type,
        )
    else:
        xapconn = XAPX00.XAPX00(
            data.get(CONF_PATH, "/dev/ttyUSB0"),
            XAPType=xap_type,
        )
        xapconn.baudRate = data.get(CONF_BAUD, 38400)
    return xapconn


class XapControllerConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """Handle a config flow for XAP Controller."""

    VERSION = 1

    def __init__(self):
        self._connection_data = {}

    async def async_step_user(self, user_input=None):
        """Step 1: device type, name, stereo, and connection type."""
        errors = {}

        if user_input is not None:
            self._connection_data = user_input
            conn_type = user_input.get(CONF_CONNECTION_TYPE, "serial")
            if conn_type == "telnet":
                return await self.async_step_telnet()
            return await self.async_step_serial()

        schema = vol.Schema(
            {
                vol.Required(CONF_NAME, default="XAP"): str,
                vol.Optional(CONF_TYPE, default="XAP800"): vol.In(XAP_TYPES),
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
        description_placeholders = {"test_result": ""}
        errors = {}

        if user_input is not None:
            if user_input.get("test_connection"):
                # Run the test and show the result; redisplay the form.
                merged = {**self._connection_data, **user_input}
                try:
                    connected = await self.hass.async_add_executor_job(
                        lambda: _build_xapconn(merged).test_connection()
                    )
                    description_placeholders["test_result"] = (
                        "✓ Connection successful" if connected else "✗ Connection failed"
                    )
                    if not connected:
                        errors["base"] = "cannot_connect"
                except Exception as e:
                    description_placeholders["test_result"] = f"✗ Connection failed: {e}"
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
            description_placeholders=description_placeholders,
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

            if not errors:
                data = {**self._connection_data, **user_input}
                title = self._connection_data.get(
                    CONF_NAME,
                    self._connection_data.get(
                        CONF_PATH, self._connection_data.get(CONF_HOST, "XAP")
                    ),
                )
                return self.async_create_entry(title=title, data=data)

        schema = vol.Schema(
            {
                vol.Required(CONF_SOURCES, default=SOURCES_EXAMPLE): str,
                vol.Required(CONF_ZONES, default=ZONES_EXAMPLE): str,
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


class XapControllerOptionsFlow(config_entries.OptionsFlow):
    """Handle options (edit after setup)."""

    def __init__(self, config_entry):
        self._entry = config_entry
        self._connection_data = {}

    async def async_step_init(self, user_input=None):
        """Step 1: device type, name, stereo, and connection type."""
        errors = {}
        current = self._entry.data

        if user_input is not None:
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
            errors=errors,
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

            if not errors:
                new_data = {**self._entry.data, **self._connection_data, **user_input}
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
            }
        )

        return self.async_show_form(
            step_id="sources_zones",
            data_schema=schema,
            errors=errors,
        )
