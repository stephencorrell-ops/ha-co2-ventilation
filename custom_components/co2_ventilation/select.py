"""Ventilation speed picker."""

from __future__ import annotations

from typing import Any

from homeassistant.components.select import SelectEntity
from homeassistant.core import HomeAssistant
try:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
except ImportError:  # Home Assistant before 2025.2
    from homeassistant.helpers.entity_platform import (
        AddEntitiesCallback as AddConfigEntryEntitiesCallback,
    )
from homeassistant.helpers.restore_state import RestoreEntity

from . import Co2VentilationConfigEntry
from .const import SPEEDS
from .entity import Co2VentilationEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Co2VentilationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([VentilationSpeedSelect(entry.runtime_data, "speed")])


class VentilationSpeedSelect(Co2VentilationEntity, SelectEntity, RestoreEntity):
    """Which fan speed the CO2 routine uses. Defaults to low.

    Only takes effect when the fan is a multi-speed fan entity; a plain
    switch or input boolean just turns on.
    """

    _attr_options = SPEEDS

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None and last.state in SPEEDS:
            self.controller.speed = last.state

    @property
    def current_option(self) -> str:
        return self.controller.speed

    @property
    def icon(self) -> str:
        return {
            "low": "mdi:fan-speed-1",
            "medium_low": "mdi:fan-speed-2",
            "medium": "mdi:fan-speed-3",
            "medium_high": "mdi:fan-plus",
        }.get(self.controller.speed, "mdi:fan")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        return {
            "speed_supported": self.controller.speed_supported,
            "percentage": self.controller.speed_percentage(),
        }

    async def async_select_option(self, option: str) -> None:
        self.controller.set_speed(option)
