"""CO2 Ventilation: run a fan when indoor CO2 gets high."""

from __future__ import annotations

import json
import logging
from pathlib import Path

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import config_validation as cv
from homeassistant.helpers.start import async_at_started
from homeassistant.helpers.typing import ConfigType

from .const import DOMAIN
from .controller import Co2VentilationController

_LOGGER = logging.getLogger(__name__)

PLATFORMS = [Platform.NUMBER, Platform.SWITCH, Platform.SENSOR]
CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)

CARD_URL = "/co2_ventilation/co2-ventilation-card.js"
CARD_PATH = Path(__file__).parent / "www" / "co2-ventilation-card.js"
CARD_REGISTERED = f"{DOMAIN}_card_registered"

type Co2VentilationConfigEntry = ConfigEntry[Co2VentilationController]


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Serve the dashboard card and load it on every dashboard."""

    async def _register(_hass: HomeAssistant | None = None) -> None:
        if hass.data.get(CARD_REGISTERED):
            return
        if getattr(hass, "http", None) is None:
            _LOGGER.debug("HTTP not available; dashboard card not registered")
            return
        try:
            from homeassistant.components.frontend import add_extra_js_url
            from homeassistant.components.http import StaticPathConfig

            version = await hass.async_add_executor_job(_read_version)
            await hass.http.async_register_static_paths(
                [StaticPathConfig(CARD_URL, str(CARD_PATH), cache_headers=False)]
            )
            add_extra_js_url(hass, f"{CARD_URL}?v={version}")
            hass.data[CARD_REGISTERED] = True
            _LOGGER.info("CO2 Ventilation card registered at %s", CARD_URL)
        except Exception:  # noqa: BLE001 - the card is optional; never block setup
            _LOGGER.exception("Could not register the CO2 Ventilation card")

    if "frontend" in hass.config.components:
        await _register()
    else:
        # The web frontend may finish loading after this integration.
        async_at_started(hass, _register)
    return True


def _read_version() -> str:
    manifest = Path(__file__).parent / "manifest.json"
    return json.loads(manifest.read_text())["version"]


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
