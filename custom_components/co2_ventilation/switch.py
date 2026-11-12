"""Auto ventilation and shower ventilation switches."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
try:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
except ImportError:  # Home Assistant before 2025.2
    from homeassistant.helpers.entity_platform import (
        AddEntitiesCallback as AddConfigEntryEntitiesCallback,
    )
from homeassistant.helpers.restore_state import RestoreEntity

from . import Co2VentilationConfigEntry
from .entity import Co2VentilationEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Co2VentilationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    controller = entry.runtime_data
    entities: list[SwitchEntity] = [AutoVentilationSwitch(controller, "auto")]
    if controller.shower_configured:
        entities.append(ShowerVentilationSwitch(controller, "shower"))
    async_add_entities(entities)


class AutoVentilationSwitch(Co2VentilationEntity, SwitchEntity, RestoreEntity):
    """Turns the CO2 routine on or off. Off leaves the fan alone."""

    _attr_icon = "mdi:robot"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self.controller.auto_enabled = last.state != STATE_OFF

    @property
    def is_on(self) -> bool:
        return self.controller.auto_enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.controller.set_auto_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.controller.set_auto_enabled(False)


class ShowerVentilationSwitch(Co2VentilationEntity, SwitchEntity, RestoreEntity):
    """Turns shower humidity ventilation on or off."""

    _attr_icon = "mdi:shower-head"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        last = await self.async_get_last_state()
        if last is not None:
            self.controller.shower.enabled = last.state != STATE_OFF

    @property
    def is_on(self) -> bool:
        return self.controller.shower.enabled

    async def async_turn_on(self, **kwargs: Any) -> None:
        self.controller.set_shower_enabled(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        self.controller.set_shower_enabled(False)

