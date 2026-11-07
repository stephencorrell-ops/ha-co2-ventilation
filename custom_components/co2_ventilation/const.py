"""Constants for the CO2 Ventilation integration."""

from __future__ import annotations

DOMAIN = "co2_ventilation"

CONF_CO2_SENSORS = "co2_sensors"
CONF_FAN_ENTITY = "fan_entity"
CONF_STARTUP_DELAY = "startup_delay"

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
# Each speed is a step on the fan: low = speed 1, medium_low = 2, medium = 3.
SPEED_LOW = "low"
SPEED_MEDIUM_LOW = "medium_low"
SPEED_MEDIUM = "medium"
SPEEDS = [SPEED_LOW, SPEED_MEDIUM_LOW, SPEED_MEDIUM]
SPEED_LEVEL = {SPEED_LOW: 1, SPEED_MEDIUM_LOW: 2, SPEED_MEDIUM: 3}
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
