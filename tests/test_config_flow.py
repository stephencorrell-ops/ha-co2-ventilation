"""Config flow tests."""

from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from custom_components.co2_ventilation.const import DOMAIN


async def test_user_flow(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "House CO2",
            "co2_sensors": ["sensor.bedroom"],
            "fan_entity": "switch.house_fan_control",
            "startup_delay": 120,
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "House CO2"
    assert result["data"]["fan_entity"] == "switch.house_fan_control"


async def test_needs_a_sensor(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {
            "name": "House CO2",
            "co2_sensors": [],
            "fan_entity": "switch.house_fan_control",
            "startup_delay": 120,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"co2_sensors": "no_sensors"}
