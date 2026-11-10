"""Config flow for CO2 Ventilation."""

from __future__ import annotations

from typing import Any

import voluptuous as vol

from homeassistant.components.sensor import SensorDeviceClass
from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlow,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import callback
from homeassistant.data_entry_flow import section
from homeassistant.helpers import selector

from .const import (
    CONF_CALL_G,
    CONF_CALL_OB,
    CONF_CALL_W2,
    CONF_CALL_Y,
    CONF_CLIMATE,
    CONF_CO2_SENSORS,
    CONF_FAN_ENTITY,
    CONF_BATH_HUMIDITY,
    CONF_EXHAUST_FAN,
    CONF_HOUSE_HUMIDITY,
    CONF_HUMIDITY,
    CONF_SHOWER,
    CONF_STARTUP_DELAY,
    CONF_TEMPERATURE,
    CONF_THERMOSTAT,
    DEFAULT_NAME,
    DEFAULT_STARTUP_DELAY,
    DOMAIN,
)


def _schema(defaults: dict[str, Any], include_name: bool) -> vol.Schema:
    fields: dict[Any, Any] = {}
    if include_name:
        fields[vol.Required(CONF_NAME, default=defaults.get(CONF_NAME, DEFAULT_NAME))] = (
            selector.TextSelector()
        )
    fields[
        vol.Required(CONF_CO2_SENSORS, default=defaults.get(CONF_CO2_SENSORS, []))
    ] = selector.EntitySelector(
        selector.EntitySelectorConfig(
            domain="sensor",
            device_class=SensorDeviceClass.CO2,
            multiple=True,
        )
    )
    fan_key = (
        vol.Required(CONF_FAN_ENTITY, default=defaults[CONF_FAN_ENTITY])
        if CONF_FAN_ENTITY in defaults
        else vol.Required(CONF_FAN_ENTITY)
    )
    fields[fan_key] = selector.EntitySelector(
        selector.EntitySelectorConfig(domain=["switch", "fan", "input_boolean"])
    )
    fields[
        vol.Required(
            CONF_STARTUP_DELAY,
            default=defaults.get(CONF_STARTUP_DELAY, DEFAULT_STARTUP_DELAY),
        )
    ] = selector.NumberSelector(
        selector.NumberSelectorConfig(
            min=0,
            max=900,
            step=10,
            unit_of_measurement="s",
            mode=selector.NumberSelectorMode.BOX,
        )
    )
    fields[vol.Optional(CONF_THERMOSTAT)] = section(
        _thermostat_schema(defaults.get(CONF_THERMOSTAT) or {}),
        {"collapsed": True},
    )
    fields[vol.Optional(CONF_SHOWER)] = section(
        _shower_schema(defaults.get(CONF_SHOWER) or {}),
        {"collapsed": True},
    )
    return vol.Schema(fields)


def _shower_schema(current: dict[str, Any]) -> vol.Schema:
    """Optional entities for shower humidity ventilation."""
    humidity = selector.EntitySelector(
        selector.EntitySelectorConfig(domain="sensor", device_class=SensorDeviceClass.HUMIDITY)
    )
    return vol.Schema(
        {
            _optional(CONF_BATH_HUMIDITY, current): humidity,
            _optional(CONF_HOUSE_HUMIDITY, current): humidity,
            _optional(CONF_EXHAUST_FAN, current): selector.EntitySelector(
                selector.EntitySelectorConfig(domain=["switch", "fan", "light", "input_boolean"])
            ),
        }
    )


def _optional(key: str, current: dict[str, Any]) -> vol.Optional:
    value = current.get(key)
    return vol.Optional(key, description={"suggested_value": value} if value else None)


def _thermostat_schema(current: dict[str, Any]) -> vol.Schema:
    """Optional entities for the thermostat history card and fan runtime."""
    call = selector.EntitySelector(selector.EntitySelectorConfig(domain="binary_sensor"))
    return vol.Schema(
        {
            _optional(CONF_CLIMATE, current): selector.EntitySelector(
                selector.EntitySelectorConfig(domain="climate")
            ),
            _optional(CONF_TEMPERATURE, current): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class=SensorDeviceClass.TEMPERATURE
                )
            ),
            _optional(CONF_HUMIDITY, current): selector.EntitySelector(
                selector.EntitySelectorConfig(
                    domain="sensor", device_class=SensorDeviceClass.HUMIDITY
                )
            ),
            _optional(CONF_CALL_G, current): call,
            _optional(CONF_CALL_Y, current): call,
            _optional(CONF_CALL_OB, current): call,
            _optional(CONF_CALL_W2, current): call,
        }
    )


class Co2VentilationConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle setup from the UI."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_CO2_SENSORS]:
                errors[CONF_CO2_SENSORS] = "no_sensors"
            else:
                await self.async_set_unique_id(user_input[CONF_FAN_ENTITY])
                self._abort_if_unique_id_configured()
                name = user_input.pop(CONF_NAME)
                return self.async_create_entry(title=name, data=user_input)

        return self.async_show_form(
            step_id="user",
            data_schema=_schema(user_input or {}, include_name=True),
            errors=errors,
        )

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> OptionsFlow:
        return Co2VentilationOptionsFlow()


class Co2VentilationOptionsFlow(OptionsFlow):
    """Change sensors, fan, or startup delay later."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            if not user_input[CONF_CO2_SENSORS]:
                errors[CONF_CO2_SENSORS] = "no_sensors"
            else:
                return self.async_create_entry(data=user_input)

        current = {**self.config_entry.data, **self.config_entry.options}
        return self.async_show_form(
            step_id="init",
            data_schema=_schema(user_input or current, include_name=False),
            errors=errors,
        )
