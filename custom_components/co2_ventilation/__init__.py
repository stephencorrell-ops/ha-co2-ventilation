"""CO2 Ventilation: run a fan when indoor CO2 gets high."""

from __future__ import annotations

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .controller import Co2VentilationController

PLATFORMS = [Platform.NUMBER, Platform.SWITCH, Platform.SENSOR]

type Co2VentilationConfigEntry = ConfigEntry[Co2VentilationController]


async def async_setup_entry(
    hass: HomeAssistant, entry: Co2VentilationConfigEntry
) -> bool:
    """Set up CO2 Ventilation from a config entry."""
    controller = Co2VentilationController(hass, entry)
    entry.runtime_data = controller

    # Entities restore setpoints and the auto toggle before logic starts.
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    await controller.async_start()

    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: Co2VentilationConfigEntry
) -> bool:
    """Unload a config entry."""
    unloaded = await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
    if unloaded:
        entry.runtime_data.async_stop()
    return unloaded


async def _async_update_listener(
    hass: HomeAssistant, entry: Co2VentilationConfigEntry
) -> None:
    await hass.config_entries.async_reload(entry.entry_id)
