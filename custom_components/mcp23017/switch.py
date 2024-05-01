"""Platform for mcp23017-based switch."""

import asyncio
import functools
import logging

import voluptuous as vol

from . import async_get_or_create
from homeassistant.components.switch import PLATFORM_SCHEMA, ToggleEntity
from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.config_entries import SOURCE_IMPORT
from homeassistant.core import callback
import homeassistant.helpers.config_validation as cv
from homeassistant.helpers.entity_platform import (
    AddEntitiesCallback,
    async_get_current_platform,
)

from .const import (
    CONF_FLOW_PIN_NAME,
    CONF_FLOW_PIN_NUMBER,
    CONF_FLOW_PLATFORM,
    CONF_I2C_ADDRESS,
    CONF_INVERT_LOGIC,
    CONF_HW_SYNC,
    CONF_PINS,
    DEFAULT_I2C_ADDRESS,
    DEFAULT_INVERT_LOGIC,
    DEFAULT_HW_SYNC,
    DOMAIN,
    DEVICE_MANUFACTURER,
)

_LOGGER = logging.getLogger(__name__)

_SWITCHES_SCHEMA = vol.Schema({cv.positive_int: cv.string})

PLATFORM_SCHEMA = PLATFORM_SCHEMA.extend(
    {
        vol.Required(CONF_PINS): _SWITCHES_SCHEMA,
        vol.Optional(CONF_INVERT_LOGIC, default=DEFAULT_INVERT_LOGIC): cv.boolean,
        vol.Optional(CONF_HW_SYNC, default=DEFAULT_HW_SYNC): cv.boolean,
        vol.Optional(CONF_I2C_ADDRESS, default=DEFAULT_I2C_ADDRESS): vol.Coerce(int),
    }
)


async def async_setup_entry(hass, entry_infos, async_add_entities):
    """Set up a MCP23017 switch entry."""
    if(entry_infos.data[CONF_FLOW_PLATFORM])=='switch':
        entity = MCP23017Switch(hass, entry_infos)
        async_add_entities([entity], True)
        platform = async_get_current_platform()
        await async_get_or_create(hass, entity)


class MCP23017Switch(ToggleEntity):
    """Represent a switch that uses MCP23017."""

    def __init__(self, hass, entry_infos):
        """Initialize the MCP23017 switch."""
        self._state = False
        self._hass = hass
        self._entry_infos=entry_infos
        self._i2c_address = entry_infos.data[CONF_I2C_ADDRESS]
        self._pin_name = entry_infos.data[CONF_FLOW_PIN_NAME]
        self._pin_number = entry_infos.data[CONF_FLOW_PIN_NUMBER]

        if self._pin_number < 8:
            self._gpio =self._pin_number
            self._port = 0
        else:
            self._gpio =self._pin_number - 8
            self._port = 1
        
        self._register = None
        
        # Get invert_logic from config flow (options) or import (data)
        self._invert_logic = entry_infos.options.get(
            CONF_INVERT_LOGIC,
            entry_infos.data.get(
                CONF_INVERT_LOGIC,
                DEFAULT_INVERT_LOGIC
            )
        )

        # Get hw_sync from config flow (options) or import (data)
        self._hw_sync = entry_infos.options.get(
            CONF_HW_SYNC,
            entry_infos.data.get(
                CONF_HW_SYNC,
                DEFAULT_HW_SYNC
            )
        )

        #Subscribe to updates of config entry options
        self._unsubscribe_update_listener = entry_infos.add_update_listener(
           self.async_config_update
        )

        # Get invert_logic from config flow (options) or import (data)
        _LOGGER.info(
            "%s(pin %d:'%s') created",
            type(self).__name__,
            self._pin_number,
            self._pin_name,
        )

    @property
    def icon(self):
        """Return device icon for this entity."""
        return "mdi:light-switch"

    @property
    def unique_id(self):
        """Return a unique_id for this entity."""
        return f"{self.address}-{self._pin_number:02x}"

    @property
    def name(self):
        """Return the name of the switch."""
        return self._pin_name

    @property
    def is_on(self):
        """Return true if device is on."""
        return self._state

    @property
    def pin(self):
        """Return the pin number of the entity."""
        return self._pin_number

    @property
    def address(self):
        """Return the i2c address of the entity."""
        return self._i2c_address

    @property
    def device_info(self) -> DeviceInfo:
        """Device info."""
        return DeviceInfo(
            entry_type=DeviceEntryType.SERVICE,
            identifiers={(DOMAIN,self.address)},
            name=self.address,
            manufacturer=DEVICE_MANUFACTURER,
            model=DOMAIN,
        )

    async def async_push_update(self, state):
        LOGGER.debug("async_push_update")
        if self._hw_sync:
            if state != self._state:
                if state:
                    await self.async_turn_on()
                else:
                    await self.async_turn_off()
    
    def set_register(self,register):
        self._register = register
    
    def register_cmd(self,state):
        _LOGGER.debug("%s : %s"%(self.unique_id,state))
        if state:
            n_state = self._register[self._port] | (1 << self._gpio)
        else:
            n_state = self._register[self._port]  & (~ (1 << self._gpio) )
        self._register[self._port] = n_state
    
    async def async_turn_on(self, **kwargs):
        """Turn the device on."""
        _LOGGER.debug("Turn On: %s"%(self.unique_id))
        self._state = True
        self.register_cmd(self._state != self._invert_logic)
        self.schedule_update_ha_state()

    async def async_turn_off(self, **kwargs):
        """Turn the device off."""
        _LOGGER.debug("Turn Off: %s"%(self.unique_id))
        self._state = False
        self.register_cmd(self._state != self._invert_logic)
        self.schedule_update_ha_state()

    @callback
    async def async_config_update(self, hass, entry_infos):
        """Handle update from config entry options."""
        _LOGGER.debug("[%s] async_config_update"%(self.unique_id))
        old_logic = self._invert_logic 
        self._invert_logic = entry_infos.options[CONF_INVERT_LOGIC]
        if old_logic != self._invert_logic:
            self._state = False
            _LOGGER.debug("[%s] New invert logic value set: %s"%(self.unique_id,self._invert_logic ))
        self.async_schedule_update_ha_state()

    
    def unsubscribe_update_listener(self):
        """Remove listener from config entry options."""
        self._unsubscribe_update_listener()

    async def async_unload_entry(hass, config_entry):
        """Unload MCP23017 switch entry corresponding to config_entry."""
        _LOGGER.warning("[FIXME] async_unload_entry not implemented")

    async def async_on_unload_entry(hass, config_entry):
        """On Unload MCP23017 switch entry corresponding to config_entry."""
        _LOGGER.warning("[FIXME] async_unload_entry not implemented")

