"""Highest CO2, status, HVAC activity and fan runtime sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION, UnitOfTime
from homeassistant.util import dt as dt_util
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.event import async_track_state_change_event
from homeassistant.helpers.restore_state import RestoreEntity
try:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
except ImportError:  # Home Assistant before 2025.2
    from homeassistant.helpers.entity_platform import (
        AddEntitiesCallback as AddConfigEntryEntitiesCallback,
    )

from . import Co2VentilationConfigEntry
from .const import ACTIVITIES, CONF_CLIMATE, STATUSES, THERMOSTAT_KEYS
from .entity import Co2VentilationEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Co2VentilationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    controller = entry.runtime_data
    async_add_entities(
        [
            HighestCo2Sensor(controller, "highest_co2"),
            StatusSensor(controller, "status"),
            HvacActivitySensor(controller, "hvac_activity"),
            *(
                [ShowerHumiditySensor(controller, "shower_humidity_diff")]
                if controller.shower_configured
                else []
            ),
            *(
                [LastCoolingSensor(controller, "last_cooling")]
                if controller.shower_configured and controller.shower_config.get("exhaust_fan")
                else []
            ),
            FanRuntimeSensor(controller, "filter_runtime"),
            FanRuntimeSensor(controller, "total_runtime"),
        ]
    )


class HighestCo2Sensor(Co2VentilationEntity, SensorEntity):
    """The reading the controller is acting on."""

    _attr_device_class = SensorDeviceClass.CO2
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_native_unit_of_measurement = CONCENTRATION_PARTS_PER_MILLION

    @property
    def native_value(self) -> float | None:
        return self.controller.max_co2

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {"source": self.controller.max_source}


class StatusSensor(Co2VentilationEntity, SensorEntity):
    """What the controller is doing right now."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = STATUSES
    _attr_icon = "mdi:fan-auto"

    @property
    def native_value(self) -> str:
        return self.controller.status

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        remaining = self.controller.min_run_remaining()
        return {
            "on_setpoint": self.controller.on_setpoint,
            "off_setpoint": self.controller.off_setpoint,
            "min_run_remaining_s": round(remaining) if remaining else 0,
            "co2_sensors": self.controller.sensors,
            "fan_entity": self.controller.fan_entity,
            "speed": self.controller.speed,
            "thermostat": self.controller.thermostat,
            "shower": self.controller.shower_config,
        }


class FanRuntimeSensor(Co2VentilationEntity, RestoreSensor):
    """Blower run hours: since the last filter change, or lifetime total."""

    _attr_device_class = SensorDeviceClass.DURATION
    _attr_state_class = SensorStateClass.TOTAL_INCREASING
    _attr_native_unit_of_measurement = UnitOfTime.HOURS
    _attr_suggested_display_precision = 1

    def __init__(self, controller, key: str) -> None:
        super().__init__(controller, key)
        self._is_filter = key == "filter_runtime"
        self._attr_icon = "mdi:air-filter" if self._is_filter else "mdi:fan-clock"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        runtime = self.controller.runtime
        last = await self.async_get_last_sensor_data()
        if last is not None and last.native_value is not None:
            try:
                seconds = float(last.native_value) * 3600
            except (TypeError, ValueError):
                seconds = 0.0
            if self._is_filter:
                runtime.filter_seconds = seconds
            else:
                runtime.total_seconds = seconds
        if self._is_filter:
            state = await self.async_get_last_state()
            reset = state.attributes.get("last_reset_at") if state else None
            if reset:
                runtime.filter_reset_at = dt_util.parse_datetime(reset)
        self.async_on_remove(runtime.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> float:
        runtime = self.controller.runtime
        seconds = runtime.filter_seconds if self._is_filter else runtime.total_seconds
        return round(seconds / 3600, 3)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        runtime = self.controller.runtime
        attrs: dict[str, Any] = {"running": runtime.running}
        if self._is_filter:
            reset = runtime.filter_reset_at
            attrs["last_reset_at"] = reset.isoformat() if reset else None
            changed = runtime.filter_changed
            attrs["filter_changed"] = changed.isoformat() if changed else None
        return attrs


class HvacActivitySensor(Co2VentilationEntity, SensorEntity):
    """What the HVAC is doing right now, who called for it, and the blower speed."""

    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ACTIVITIES

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        t = self.controller.thermostat
        watched = [t[k] for k in THERMOSTAT_KEYS if k != CONF_CLIMATE and t[k]]
        if t[CONF_CLIMATE]:
            watched.append(t[CONF_CLIMATE])
        if self.controller.fan_entity:
            watched.append(self.controller.fan_entity)
        if watched:

            @callback
            def _changed(_event) -> None:
                self.async_write_ha_state()

            self.async_on_remove(
                async_track_state_change_event(self.hass, list(set(watched)), _changed)
            )

    @property
    def native_value(self) -> str:
        return self.controller.hvac_activity()["activity"]

    @property
    def icon(self) -> str:
        return {
            "idle": "mdi:fan-off",
            "heat_pump": "mdi:heat-pump",
            "heat_pump_aux": "mdi:fire",
            "aux_heat": "mdi:fire",
            "cooling": "mdi:snowflake",
            "defrost": "mdi:snowflake-melt",
            "fan_only": "mdi:fan",
            "ventilating": "mdi:molecule-co2",
            "fan_manual": "mdi:fan",
        }.get(self.native_value, "mdi:hvac")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        info = self.controller.hvac_activity()
        info.pop("activity")
        return info


class ShowerHumiditySensor(Co2VentilationEntity, SensorEntity):
    """How far the bathroom's humidity is above the house, in points."""

    _attr_icon = "mdi:shower"
    _attr_native_unit_of_measurement = "%"
    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0

    @property
    def native_value(self) -> float | None:
        return self.controller.shower.diff

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        shower = self.controller.shower
        remaining = shower.run_remaining(dt_util.utcnow())
        return {
            "mode": shower.mode,
            "enabled": shower.enabled,
            "run_remaining_min": round(remaining) if remaining is not None else None,
            "exhaust_fan": self.controller.shower_config.get("exhaust_fan"),
            "exhaust_allowed": self.controller.exhaust_allowed(),
            "bathroom_sensor": self.controller.shower_config.get("bathroom_humidity"),
            "house_sensor": self.controller._house_humidity_source(),
        }


class LastCoolingSensor(Co2VentilationEntity, RestoreEntity, SensorEntity):
    """When the air conditioning last ran. The bathroom exhaust fan only runs
    for a shower if this is within the cooling window."""

    _attr_device_class = SensorDeviceClass.TIMESTAMP
    _attr_icon = "mdi:snowflake-clock"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and self.controller.last_cooling is None:
            self.controller.last_cooling = dt_util.parse_datetime(last.state)

    @property
    def native_value(self):
        return self.controller.last_cooling
