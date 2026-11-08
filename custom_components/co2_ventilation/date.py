"""Date the HVAC filter was last changed."""

from __future__ import annotations

from datetime import date

from homeassistant.components.date import DateEntity
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ServiceValidationError
try:
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
except ImportError:  # Home Assistant before 2025.2
    from homeassistant.helpers.entity_platform import (
        AddEntitiesCallback as AddConfigEntryEntitiesCallback,
    )
from homeassistant.helpers.restore_state import RestoreEntity
from homeassistant.util import dt as dt_util

from . import Co2VentilationConfigEntry
from .const import DOMAIN
from .entity import Co2VentilationEntity


async def async_setup_entry(
    hass: HomeAssistant,
    entry: Co2VentilationConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([FilterChangedDate(entry.runtime_data, "filter_changed")])


class FilterChangedDate(Co2VentilationEntity, DateEntity, RestoreEntity):
    """Set automatically by Reset filter runtime, or entered by hand.

    Changing the date does not change the runtime hours.
    """

    _attr_icon = "mdi:calendar-check"

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        runtime = self.controller.runtime
        last = await self.async_get_last_state()
        if last is not None and runtime.filter_changed is None:
            try:
                runtime.filter_changed = date.fromisoformat(last.state)
            except ValueError:
                pass
        self.async_on_remove(runtime.add_listener(self.async_write_ha_state))

    @property
    def native_value(self) -> date | None:
        return self.controller.runtime.filter_changed

    async def async_set_value(self, value: date) -> None:
        if value > dt_util.now().date():
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="filter_date_future"
            )
        self.controller.runtime.set_filter_changed(value)
