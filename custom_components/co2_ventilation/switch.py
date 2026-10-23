"""Auto ventilation on/off switch."""

from __future__ import annotations

from typing import Any

from homeassistant.components.switch import SwitchEntity
from homeassistant.const import STATE_OFF
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import RestoreEntity

from . import Co2VentilationConfigEntry
from .entity import Co2VentilationEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Co2VentilationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([AutoVentilationSwitch(entry.runtime_data, "auto")])


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
