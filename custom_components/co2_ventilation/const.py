"""Constants for the CO2 Ventilation integration."""

from __future__ import annotations

DOMAIN = "co2_ventilation"

CONF_CO2_SENSORS = "co2_sensors"
CONF_FAN_ENTITY = "fan_entity"
CONF_STARTUP_DELAY = "startup_delay"

# Optional thermostat monitoring, set under a collapsible "Thermostat" section.
CONF_THERMOSTAT = "thermostat"
CONF_CLIMATE = "climate_entity"
CONF_TEMPERATURE = "temperature_sensor"
CONF_HUMIDITY = "humidity_sensor"
CONF_CALL_G = "call_g"
CONF_CALL_Y = "call_y"
CONF_CALL_OB = "call_ob"
CONF_CALL_W2 = "call_w2"
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
ACTIVITY_FAN_ONLY = "fan_only"
ACTIVITY_VENTILATING = "ventilating"
ACTIVITY_FAN_MANUAL = "fan_manual"
ACTIVITIES = [
    ACTIVITY_IDLE,
    ACTIVITY_HEAT_PUMP,
    ACTIVITY_HEAT_PUMP_AUX,
    ACTIVITY_AUX_HEAT,
    ACTIVITY_COOLING,
    ACTIVITY_FAN_ONLY,
    ACTIVITY_VENTILATING,
    ACTIVITY_FAN_MANUAL,
]
CALLER_THERMOSTAT = "thermostat"
CALLER_CO2 = "co2"
CALLER_MANUAL = "manual"
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
