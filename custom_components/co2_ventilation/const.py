"""Constants for the CO2 Ventilation integration."""

from __future__ import annotations

DOMAIN = "co2_ventilation"

CONF_CO2_SENSORS = "co2_sensors"
CONF_FAN_ENTITY = "fan_entity"
CONF_STARTUP_DELAY = "startup_delay"
# Optional buttons/remotes whose automations run the fan. A fan turned on
# within REMOTE_WINDOW_S of a press is shown as turned on by remote.
CONF_FAN_REMOTES = "fan_remotes"
REMOTE_WINDOW_S = 30

# Optional thermostat monitoring, set under a collapsible "Thermostat" section.
CONF_THERMOSTAT = "thermostat"
CONF_CLIMATE = "climate_entity"
CONF_TEMPERATURE = "temperature_sensor"
CONF_HUMIDITY = "humidity_sensor"
CONF_CALL_G = "call_g"
CONF_CALL_Y = "call_y"
CONF_CALL_OB = "call_ob"
CONF_CALL_W2 = "call_w2"
# Name shown when only G is on (e.g. "Fan/Humidifier" when a humidifier
# also calls G). Blank keeps "Fan only".
CONF_G_LABEL = "g_label"
# Optional shower humidity section.
CONF_SHOWER = "shower"
CONF_BATH_HUMIDITY = "bathroom_humidity"
CONF_HOUSE_HUMIDITY = "house_humidity"
CONF_EXHAUST_FAN = "exhaust_fan"
SHOWER_KEYS = (CONF_BATH_HUMIDITY, CONF_HOUSE_HUMIDITY, CONF_EXHAUST_FAN)
CALLER_HUMIDITY = "humidity"

THERMOSTAT_KEYS = (
    CONF_CLIMATE,
    CONF_TEMPERATURE,
    CONF_HUMIDITY,
    CONF_CALL_G,
    CONF_CALL_Y,
    CONF_CALL_OB,
    CONF_CALL_W2,
)

DEFAULT_NAME = "CO2 Ventilation"
DEFAULT_ON_SETPOINT = 900
DEFAULT_OFF_SETPOINT = 700
DEFAULT_MIN_RUN = 20
DEFAULT_STARTUP_DELAY = 120

SETPOINT_MIN = 400
SETPOINT_MAX = 2000
SETPOINT_STEP = 25
MIN_RUN_MAX = 120

# Ventilation speed, used when the fan is a multi-speed fan entity.
# Each speed is a step on the fan: low = speed 1 ... medium_high = 4.
SPEED_LOW = "low"
SPEED_MEDIUM_LOW = "medium_low"
SPEED_MEDIUM = "medium"
SPEED_MEDIUM_HIGH = "medium_high"
SPEEDS = [SPEED_LOW, SPEED_MEDIUM_LOW, SPEED_MEDIUM, SPEED_MEDIUM_HIGH]
SPEED_LEVEL = {SPEED_LOW: 1, SPEED_MEDIUM_LOW: 2, SPEED_MEDIUM: 3, SPEED_MEDIUM_HIGH: 4}

# What the HVAC system is doing, for the HVAC activity sensor.
ACTIVITY_IDLE = "idle"
ACTIVITY_HEAT_PUMP = "heat_pump"
ACTIVITY_HEAT_PUMP_AUX = "heat_pump_aux"
ACTIVITY_AUX_HEAT = "aux_heat"
ACTIVITY_COOLING = "cooling"
# Y + O + W2: the heat pump is defrosting its outdoor coil (running in
# reverse) with the heat strips on. Not cooling.
ACTIVITY_DEFROST = "defrost"
ACTIVITY_FAN_ONLY = "fan_only"
ACTIVITY_VENTILATING = "ventilating"
ACTIVITY_FAN_MANUAL = "fan_manual"
ACTIVITY_FAN_REMOTE = "fan_remote"
ACTIVITIES = [
    ACTIVITY_IDLE,
    ACTIVITY_HEAT_PUMP,
    ACTIVITY_HEAT_PUMP_AUX,
    ACTIVITY_AUX_HEAT,
    ACTIVITY_COOLING,
    ACTIVITY_DEFROST,
    ACTIVITY_FAN_ONLY,
    ACTIVITY_VENTILATING,
    ACTIVITY_FAN_MANUAL,
    ACTIVITY_FAN_REMOTE,
]
CALLER_THERMOSTAT = "thermostat"
CALLER_CO2 = "co2"
CALLER_MANUAL = "manual"
CALLER_REMOTE = "remote"
# Who turned the fan on, for the Fan turned on by sensor (and its history,
# which the thermostat card uses to split CO2 runs from remote ones).
FAN_CALLER_OFF = "off"
FAN_CALLER_CO2 = "co2"
FAN_CALLER_SHOWER = "shower"
FAN_CALLERS = [FAN_CALLER_OFF, FAN_CALLER_CO2, FAN_CALLER_SHOWER, CALLER_REMOTE, CALLER_MANUAL]
# Blower speed (tap) for each thermostat call, as wired at the air handler:
# G and Y run medium (tap 3), the heat strips (W2) run high (tap 5).
THERMOSTAT_CALL_LEVEL = 3
AUX_HEAT_LEVEL = 5
SPEED_BY_LEVEL = {1: "low", 2: "medium_low", 3: "medium", 4: "medium_high", 5: "high"}
DEFAULT_SPEED = SPEED_LOW

STATUS_STARTING = "starting"
STATUS_DISABLED = "disabled"
STATUS_IDLE = "idle"
STATUS_VENTILATING = "ventilating"
STATUS_HOLDING = "min_run_hold"
STATUS_MANUAL = "manual"
STATUS_NO_DATA = "no_data"

STATUSES = [
    STATUS_STARTING,
    STATUS_DISABLED,
    STATUS_IDLE,
    STATUS_VENTILATING,
    STATUS_HOLDING,
    STATUS_MANUAL,
    STATUS_NO_DATA,
]
