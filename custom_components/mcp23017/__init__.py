import logging
import asyncio
import functools
import threading
import time

import smbus2

from homeassistant.core import HomeAssistant
from homeassistant.config_entries import ConfigEntry
from homeassistant.helpers import device_registry
from homeassistant.const import EVENT_HOMEASSISTANT_START, EVENT_HOMEASSISTANT_STOP
from .const import DOMAIN, PLATFORMS, DEFAULT_SCAN_RATE, DEVICE_MANUFACTURER,DEFAULT_INVERT_LOGIC,CONF_I2C_ADDRESS, MAX_RETRY

import traceback

_LOGGER = logging.getLogger(__name__)
MCP23017_DATA_LOCK = asyncio.Lock()

PLATFORMS = ["binary_sensor", "switch"]


async def async_setup(hass: HomeAssistant, config: dict) -> bool:
    """Set up the MCP23017 component."""
    _LOGGER.debug("async_setup")
    # hass.data[DOMAIN] stores one entry for each MCP23017 instance using i2c address as a key
    hass.data.setdefault(DOMAIN, {})

    # Callback function to start polling when HA starts
    def start_polling(event):
        for component in hass.data[DOMAIN].values():
            if not component.is_alive():
                component.start_polling()

    # Callback function to stop polling when HA stops
    def stop_polling(event):
        for component in hass.data[DOMAIN].values():
            if component.is_alive():
                component.stop_polling()

    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_START, start_polling)
    hass.bus.async_listen_once(EVENT_HOMEASSISTANT_STOP, stop_polling)
    return True

async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Creation des entités à partir d'une configEntry"""

    _LOGGER.debug(
        "Appel de async_setup_entry entry: entry_id='%s', data='%s'",
        entry.entry_id,
        entry.data,
    )

    hass.data.setdefault(DOMAIN, {})
    entry.async_on_unload(entry.add_update_listener(update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True

async def async_unload_entry(hass, config_entry):
    """Unload MCP23017 switch entry corresponding to config_entry."""
    component = hass.data[DOMAIN][config_entry.data[CONF_I2C_ADDRESS]]
    component.reInit()

async def update_listener(hass: HomeAssistant, entry: ConfigEntry) -> None:
    """Fonction qui force le rechargement des entités associées à une configEntry"""
    component = hass.data[DOMAIN][entry.data[CONF_I2C_ADDRESS]]
    component.reInit()
    await hass.config_entries.async_reload(entry.entry_id)

async def async_get_or_create(hass, entity):
    """Get or create a MCP23017 component from entity bus and i2c address."""
    i2c_address = entity.address
    # DOMAIN data async mutex
    try:
        async with MCP23017_DATA_LOCK:
            if i2c_address in hass.data[DOMAIN]:
                component = hass.data[DOMAIN][i2c_address]
            else:
                # Try to create component when it doesn't exist
                component = await hass.async_add_executor_job(
                    functools.partial(MCP23017, hass,i2c_address)
                )
                hass.data[DOMAIN][i2c_address] = component

                # Start polling thread if hass is already running
                if hass.is_running:
                    component.start_polling()

                # Register a device combining all related entities
                devices = device_registry.async_get(hass)
                devices.async_get_or_create(
                    config_entry_id=entity._entry_infos.entry_id,
                    identifiers={(DOMAIN, i2c_address)},
                    manufacturer=DEVICE_MANUFACTURER,
                    model=DOMAIN,
                    name=f"{DOMAIN}@{i2c_address}",
                )

            # Link entity to component
            await hass.async_add_executor_job(
                functools.partial(component.register_entity, entity)
            )
    except ValueError as error:
        component = None
        await hass.config_entries.async_remove(entity._entry_infos.entry_id)

        hass.components.persistent_notification.create(
            f"Error: Unable to access {DOMAIN}{i2c_address} ({error})",
            title=f"{DOMAIN} Configuration",
            notification_id=f"{DOMAIN} notification",
        )

    return component



class MCP23017(threading.Thread):
    """MCP23017 component (device)"""

    IODIRA  = 0x00 # Pin direction register for port A
    IODIRB  = 0x01 # Pin direction register for port B
    IOPOLA  = 0x02 # Invert polarity for port A
    IOPOLB  = 0x03 # Invert polarity for port B
    GPINTENA= 0x04 # Enable interrupt for GPIO Port A
    GPINTENB= 0x05 # Enable interrupt for GPIO Port B
    DEFVALA = 0x06 # Reference values for the interruptions on port A
    DEFVALB = 0x07 # Reference values for the interruptions on port B
    INTCONA = 0x08 # Interruption mode -- 1:compare to DEFVAL, 0:compare to its old value
    INTCONB = 0x09 # Interruption mode -- 1:compare to DEFVAL, 0:compare to its old value
    IOCONA  = 0x0A # IO connection Port A
    IOCONB  = 0x0B # IO connection Port B
    GPPUA   = 0X0C # Pullup resistor Port A
    GPPUB   = 0X0D # Pullup resistor Port B
    INTFA   = 0x0E # 
    INTFB   = 0x0F #
    INTCAPA = 0x10 # value stored after an interruption
    INTCAPB = 0x11 # value stored after an interruption
    GPIOA   = 0x12 # GPA register for input
    GPIOB   = 0x13 # GPA register for input
    OLATA   = 0x14 #
    OLATB   = 0x15 #

    def __init__(self, hass,address):
        # Address is this form /dev/i2c-1@0x48
        self._hass     = hass
        self._bus      = int(address.split('@')[0][-1])
        self._address  = int(address.split('@')[1],16)
        self._full_address = address
        self._entities = [None for i in range(16)]
        self._device_lock = threading.Lock()
        self._run = False
        
        self._smbus = smbus2.SMBus(self._bus)
        
        # GPIO status
        self._to_init = True
        self._first_init = True
        self._last_state = None
        self._io_dir     = None 
        self._invert     = None
        self._pullup     = None
        self._hw_sync    = None

        # switch state
        self._switches_states     = [0b00000000,0b00000000]   
        # switch new_state
        self._new_switches_states = [0b00000000,0b00000000]   
        
        threading.Thread.__init__(self, name=self.unique_id)
        _LOGGER.info("%s device created", self.unique_id)

    def __enter__(self):
        """Lock access to device (with statement)."""
        self._device_lock.acquire()
        return self

    def __exit__(self, exception_type, exception_value, exception_traceback):
        """Unlock access to device (with statement)."""
        self._device_lock.release()
        return False

    def reInit(self):
        self._to_init = True
    
    @property
    def unique_id(self):
        """Return component unique id."""
        return f"{DOMAIN}{self._full_address}"

    @property
    def bus(self):
        """Return I2C bus number"""
        return self._bus

    @property
    def address(self):
        """Return I2C address"""
        return self._address

    def start_polling(self):
        """Start polling thread."""
        self._run = True
        self.start()

    def stop_polling(self):
        """Stop polling thread."""
        self._run = False
        self.join()

    def run(self):
        """Poll all ports once and call corresponding callback if a change is detected."""
        _LOGGER.info("%s start polling thread", self.unique_id)
        error_cpt=0
        while self._run:
            with self:
                try:
                    # Conf has changed
                    if not self._to_init and not self.checkConf():
                        self._to_init = True
                    # Reinitialisation needed
                    if self._to_init:
                        self.confGPIO()
                        reInit = True
                        time.sleep(1)

                    for port in range (2):
                            
                        status  = self._smbus.read_byte_data(self._address, self.GPIOA+port)
                        self._new_state[port]=status
                        changes = self._last_state[port]^status
                        
                        if reInit:
                            pin_nb = 0
                            statusStr=bin(status)[2:].rjust(8,'0')[::-1]
                            for s in  statusStr:
                                entity = self._entities[pin_nb+port*8]
                                if entity != None and type(entity).__name__ == 'MCP23017BinarySensor':
                                    asyncio.run_coroutine_threadsafe(entity.async_push_update(statusStr[pin_nb]=="1"), self._hass.loop)
                                    _LOGGER.debug("Pin %d Initial status set to %s"%((pin_nb+port*8),statusStr[pin_nb]))
                                pin_nb += 1
                            if port == 1:    
                                reInit = False
                        elif changes != 0:
                            pin_nb=0
                            statusStr=bin(status)[2:].rjust(8,'0')[::-1]
                            for s in bin(changes)[2:].rjust(8,'0')[::-1]:
                                if s == '1': # State changes on this pin
                                    if type(self._entities[pin_nb+port*8]).__name__ == 'MCP23017BinarySensor':
                                        asyncio.run_coroutine_threadsafe(self._entities[pin_nb+port*8].async_push_update(statusStr[pin_nb]=="1"), self._hass.loop)
                                    _LOGGER.debug("Pin %d change to %s"%((pin_nb+port*8),statusStr[pin_nb]))
                                pin_nb += 1
                            _LOGGER.debug("[%s] Last Inputs State:%s "%(self.unique_id,self.toBin(self._last_state)))
                            _LOGGER.debug("[%s] New  Inputs State:%s "%(self.unique_id,self.toBin(self._new_state)))
                        #write switch commands
                        if self._new_switches_states[port] != self._switches_states[port]:
                            _LOGGER.debug("-------------------------------")
                            _LOGGER.debug("[%s] New "%( self.toBin(self._new_switches_states)))
                            _LOGGER.debug("[%s] Current "%( self.toBin(self._switches_states)))
                            self._smbus.write_byte_data(self._address,self.OLATA+port,self._new_switches_states[port])
                            self._switches_states[port] = self._new_switches_states[port] 
                    self._last_state = self._new_state.copy()
                    error_cpt = 0
                except  Exception as error:
                    error_cpt += 1
                    if error_cpt > MAX_RETRY: 
                        _LOGGER.error(traceback.format_exc())
                        _LOGGER.error("Error polling device %s"%(self.unique_id))
                        _LOGGER.error(error)
                        self.reInit()
                        error_cpt = 0
                    
            time.sleep(DEFAULT_SCAN_RATE)
            
    def register_entity(self, entity):
        """Register entity to this device instance."""
        with self:
            if type(entity).__name__ == 'MCP23017Switch':
                entity.set_register(self._new_switches_states)
            self._entities[entity.pin] = entity
            self.reInit()
            _LOGGER.info(
                "%s(pin %d:'%s') attached to %s",
                type(entity).__name__,
                entity.pin,
                entity.name,
                self.unique_id,
            )
        return True


    def toBin(self,s):
        """Display binaries registers"""
        return  "[ %s , %s ]"%(bin(s[0])[2:].rjust(8,'0'),bin(s[1])[2:].rjust(8,'0'))
    
    def displayStatus(self):
        """Display configuration and states"""
        _LOGGER.info("########################################")
        _LOGGER.info('#               GPIOIA      GPIOB ')
        _LOGGER.info('# LastState: %s'%self.toBin(self._last_state))
        _LOGGER.info('# IO Direct: %s'%self.toBin(self._io_dir))
        _LOGGER.info('#    Invert: %s'%self.toBin(self._invert))
        _LOGGER.info('#    Pullup: %s'%self.toBin(self._pullup))
        _LOGGER.info('#   Hw sync: %s'%self.toBin(self._hw_sync))
 
    def checkConf(self):
        """CHeck conf has not changed"""
        try:
            for port in range(2):
                if (
                        (self._invert[port] & self._io_dir[port] != self._smbus.read_byte_data(self._address, self.IOPOLA+port)) or
                        (self._io_dir[port] != self._smbus.read_byte_data(self._address, self.IODIRA+port)) or 
                        (self._pullup[port] != self._smbus.read_byte_data(self._address, self.GPPUA+port))
                        ):
                    return False
        except:
            _LOGGER.error("Check conf")
        return True
        
    def confGPIO(self,newConf=True):
        """Configure GPIO"""
        if newConf:
            #                     GPIOIA      GPIOB
            self._last_state = [0b00000000,0b00000000]
            self._new_state  = [0b00000000,0b00000000]
            self._io_dir     = [0b00000000,0b00000000]
            self._invert     = [0b00000000,0b00000000]
            self._pullup     = [0b00000000,0b00000000]
            self._hw_sync    = [0b00000000,0b00000000]
            _LOGGER.info("########################################")
            _LOGGER.info("##############GPIO CONF#################")
            _LOGGER.info("## %s"%(self.unique_id))
            port = 0
            pin  = 0
            for entity in self._entities:
                if entity != None:
                    _LOGGER.info("%s (%d): %s"%(type(entity).__name__,entity.pin,entity.name))
                    if  entity.pin < 8:
                        pin = entity.pin
                    else:
                        pin  = entity.pin - 8
                        port = 1
                    if type(entity).__name__ == 'MCP23017Switch':
                        if entity.is_on:
                            self._new_state[port] =  self._new_state[port] | (1 << pin) 
                    elif type(entity).__name__ == 'MCP23017BinarySensor':
                        self._io_dir[port] =  self._io_dir[port] | (1 << pin)     
                        if entity._pullup == 'UP':
                            self._pullup[port] =  self._pullup[port] | (1 << pin)
                    else:
                        raise ("Try to configure an unsupported object: %s"%(type(entity).__name__ ))    
                    if entity._invert_logic:
                        self._invert[port] = self._invert[port] | (1 << pin)
        for port in range (2):
            inputs_invert = self._invert[port] & self._io_dir[port]
            self._smbus.write_byte_data(self._address, self.IOPOLA+port, inputs_invert)
            # switch invert
            switches_invert = self._invert[port] & ~ self._io_dir[port]
            #self._smbus.write_byte_data(self._address, self.OLATA+port, switches_invert)
            
            if self._first_init == True:
                self._switches_states[port] = switches_invert
                self._new_switches_states[port] = switches_invert
                if port == 1:
                    self._first_init = False
            
            self._smbus.write_byte_data(self._address,self.OLATA+port,self._new_switches_states[port])


            
            #set selected IO direction 
            self._smbus.write_byte_data(self._address, self.IODIRA+port, self._io_dir[port])
            #set pullup 
            self._smbus.write_byte_data(self._address, self.GPPUA+port, self._pullup[port])
            # TODO hw_sync
        _LOGGER.info("########################################")
        self._to_init = False
        self.displayStatus()

                
