"""Filter change: reset the filter runtime counter."""

from __future__ import annotations

from homeassistant.components.button import ButtonEntity
from homeassistant.core import HomeAssistant
try:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
except ImportError:  # Home Assistant before 2025.2
    from homeassistant.helpers.entity_platform import (
        AddEntitiesCallback as AddConfigEntryEntitiesCallback,
    )

from . import Co2VentilationConfigEntry
from .entity import Co2VentilationEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Co2VentilationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([ResetFilterButton(entry.runtime_data, "reset_filter")])


class ResetFilterButton(Co2VentilationEntity, ButtonEntity):
    """Press after changing the filter. The total runtime keeps counting."""

    _attr_icon = "mdi:air-filter"

    async def async_press(self) -> None:
        self.controller.runtime.reset_filter()
