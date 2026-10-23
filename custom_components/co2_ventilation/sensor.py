"""Highest CO2 and status sensors."""

from __future__ import annotations

from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorStateClass,
)
from homeassistant.const import CONCENTRATION_PARTS_PER_MILLION
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import Co2VentilationConfigEntry
from .const import STATUSES
from .entity import Co2VentilationEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Co2VentilationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    controller = entry.runtime_data
    async_add_entities(
        [HighestCo2Sensor(controller, "highest_co2"), StatusSensor(controller, "status")]
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
        }
