from homeassistant.const import Platform

DOMAIN = "mcp23017"

DEVICE_MANUFACTURER="MicroChip"

CONF_FLOW_PLATFORM = "platform"

PLATFORMS: list[Platform] = [Platform.SENSOR, Platform.SWITCH]

CONF_I2C_BUS="i2c_bus"
CONF_DEFAULT_I2C_BUS='/dev/i2c-1'
SKIP_I2C_BUSES=['/dev/i2c-0','/dev/i2c-2']

CONF_I2C_ADDRESS="i2c_address"
DEFAULT_I2C_ADDRESS=0x20

CONF_PINS = "pins"
CONF_FLOW_PIN_NUMBER = "pin_number"
CONF_FLOW_PIN_NAME = "pin_name"

CONF_INVERT_LOGIC = "invert_logic"
CONF_PULL_MODE = "pull_mode"
CONF_HW_SYNC = "hw_sync"

MODE_UP = "UP"
MODE_DOWN = "NONE"

DEFAULT_HW_SYNC = True
DEFAULT_INVERT_LOGIC = False
DEFAULT_PULL_MODE = MODE_UP

DEFAULT_SCAN_RATE = .2#.1 #seconds

MAX_RETRY = 3
