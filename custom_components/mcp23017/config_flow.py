"""Config flow for MCP23017 component."""

import voluptuous as vol
import glob
import logging

import smbus2 

from homeassistant import config_entries
from homeassistant.core import callback

from .const import (
    DOMAIN,
    CONF_FLOW_PLATFORM,
    CONF_I2C_BUS,
    CONF_DEFAULT_I2C_BUS,
    SKIP_I2C_BUSES,
    DEFAULT_I2C_ADDRESS,
    CONF_I2C_ADDRESS,
    CONF_PINS,
    CONF_FLOW_PIN_NUMBER,
    CONF_FLOW_PIN_NAME,
    CONF_INVERT_LOGIC,
    DEFAULT_INVERT_LOGIC,
    CONF_PULL_MODE,
    DEFAULT_PULL_MODE,
    DEFAULT_HW_SYNC,
    CONF_HW_SYNC,
    MODE_UP,
    MODE_DOWN,
)

PLATFORMS = ["binary_sensor","switch"]

_LOGGER = logging.getLogger(__name__)


class MCP23017ConfigFlow(config_entries.ConfigFlow, domain=DOMAIN):
    """MCP23017 config flow."""

    VERSION = 1
    CONNECTION_CLASS = config_entries.CONN_CLASS_LOCAL_POLL

    def _title(self, user_input):
        return "%s:pin %d ('%s')" % (
            user_input[CONF_I2C_ADDRESS],
            user_input[CONF_FLOW_PIN_NUMBER],
            user_input[CONF_FLOW_PIN_NAME],
        )

    def _unique_id(self, user_input):
        return "%s.%s.%d" % (
            DOMAIN,
            user_input[CONF_I2C_ADDRESS],
            user_input[CONF_FLOW_PIN_NUMBER],
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry):
        """Add support for config flow options."""
        return MCP23017OptionsFlowHandler(config_entry)

    async def async_step_import(self, user_input=None):
        """Create a new entity from configuration.yaml import."""

        config_entry =  await self.async_set_unique_id(self._unique_id(user_input))
        # Remove entry (from storage) matching the same unique id
        if config_entry:
            self.hass.config_entries.async_remove(config_entry.entry_id)

        return self.async_create_entry(
            title=self._title(user_input),
            data=user_input,
        )


    async def async_step_user(self, user_input=None):
        """Create a new entity from UI."""

        if user_input is not None:
            await self.async_set_unique_id(self._unique_id(user_input))
            self._abort_if_unique_id_configured()

            if CONF_FLOW_PIN_NAME not in user_input:
                user_input[CONF_FLOW_PIN_NAME] = " pin %s:%d" % (
                    user_input[CONF_I2C_ADDRESS],
                    user_input[CONF_FLOW_PIN_NUMBER],
                )

            return self.async_create_entry(
                title=self._title(user_input),
                data=user_input,
            )

        devices_detected=[]
        i2c_buses=glob.glob('/dev/i2c-?')
        for sbus in i2c_buses:
            if sbus not in SKIP_I2C_BUSES:
                bus = smbus2.SMBus(int(sbus[-1]))
                for device in range (0x20,0x28):
                    try:
                        bus.read_byte(device)
                        devices_detected+=[sbus+'@'+str(hex(device))]
                    except:
                        pass
        if len(devices_detected) == 0:
            _LOGGER.error("No MCP23017 detected")
            return self.async_show_form(
                step_id="user",
                data_schema=vol.Schema(
                    {
                        vol.Required(
                            CONF_I2C_ADDRESS, default=DEFAULT_I2C_ADDRESS
                        ): vol.In(["No MCP23017 device detected"]),
                    }
                ),
            )
        return self.async_show_form(
            step_id="user",
            data_schema=vol.Schema(
                {
                    vol.Required(
                        CONF_I2C_ADDRESS, default=DEFAULT_I2C_ADDRESS
                    ): vol.In(devices_detected),
                    vol.Required(
                        CONF_FLOW_PLATFORM,
                        default=PLATFORMS[0],
                    ): vol.In(PLATFORMS),
                    vol.Required(CONF_FLOW_PIN_NUMBER, default=0): vol.All(
                        vol.Coerce(int), vol.Range(min=0, max=15)
                    ),
                    vol.Optional(CONF_FLOW_PIN_NAME): str,
                }
            ),
        )

class MCP23017OptionsFlowHandler(config_entries.OptionsFlow):
    """MCP23017 config flow options."""

    def __init__(self, config_entry):
        """Initialize options flow."""
        self.config_entry = config_entry

    async def async_step_init(self, user_input=None):
        """Manage entity options."""

        if user_input is not None:
            return self.async_create_entry(title="", data=user_input)
        data_schema = vol.Schema(
            {
                vol.Optional(
                    CONF_INVERT_LOGIC,
                    default=self.config_entry.options.get(
                        CONF_INVERT_LOGIC, DEFAULT_INVERT_LOGIC
                    ),
                ): bool,
            }
        )
        if self.config_entry.data[CONF_FLOW_PLATFORM] == "binary_sensor":
            data_schema = data_schema.extend(
                {
                    vol.Optional(
                        CONF_PULL_MODE,
                        default=self.config_entry.options.get(
                            CONF_PULL_MODE, DEFAULT_PULL_MODE
                        ),
                    ): vol.In([MODE_UP, MODE_DOWN]),
                }
            )

        if self.config_entry.data[CONF_FLOW_PLATFORM] == "switch":
            data_schema = data_schema.extend(
                {
                    vol.Optional(
                        CONF_HW_SYNC,
                        default=self.config_entry.options.get(
                            CONF_HW_SYNC, DEFAULT_HW_SYNC
                        ),
                    ): bool,
                }
            )
        return self.async_show_form(step_id="init", data_schema=data_schema)
