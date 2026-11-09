"""Ventilation speed: runs a multi-speed fan at the selected speed."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component

from custom_components.co2_ventilation.const import DOMAIN

FAN = "fan.ventilation"
SPEED = "select.co2_ventilation_ventilation_speed"
STATUS = "sensor.co2_ventilation_status"

# A 3-speed fan like the ESPHome air handler node: 33.33% per step.
STEP = 100 / 3


def _co2(hass: HomeAssistant, entity_id: str, value) -> None:
    hass.states.async_set(
        entity_id,
        str(value),
        {"device_class": "carbon_dioxide", "unit_of_measurement": "ppm"},
    )


def _fan_state(hass: HomeAssistant, on: bool, percentage: int | None = None) -> None:
    hass.states.async_set(
        FAN,
        "on" if on else "off",
        {
            "percentage_step": STEP,
            "percentage": percentage if on else 0,
            "supported_features": 1,
        },
    )


async def _setup(hass: HomeAssistant, step: float | None = STEP) -> list[ServiceCall]:
    """Fake fan services that record calls and update the fan's state."""
    calls: list[ServiceCall] = []

    async def turn_on(call: ServiceCall) -> None:
        calls.append(call)
        _fan_state(hass, True, call.data.get("percentage", 100))

    async def set_percentage(call: ServiceCall) -> None:
        calls.append(call)
        _fan_state(hass, True, call.data["percentage"])

    async def turn_off(call: ServiceCall) -> None:
        calls.append(call)
        _fan_state(hass, False)

    hass.services.async_register("fan", "turn_on", turn_on)
    hass.services.async_register("fan", "set_percentage", set_percentage)
    hass.services.async_register("fan", "turn_off", turn_off)
    await async_setup_component(hass, "homeassistant", {})

    if step is None:
        hass.states.async_set(FAN, "off", {})
    else:
        _fan_state(hass, False)
    _co2(hass, "sensor.bedroom", 500)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="CO2 Ventilation",
        data={
            "co2_sensors": ["sensor.bedroom"],
            "fan_entity": FAN,
            "startup_delay": 120,
        },
        unique_id=FAN,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return calls


async def _select(hass: HomeAssistant, option: str) -> None:
    await hass.services.async_call(
        "select", "select_option", {"entity_id": SPEED, "option": option}, blocking=True
    )
    await hass.async_block_till_done()


async def test_default_speed_is_low(hass: HomeAssistant) -> None:
    calls = await _setup(hass)
    state = hass.states.get(SPEED)
    assert state.state == "low"
    assert state.attributes["options"] == ["low", "medium_low", "medium", "medium_high"]
    assert state.attributes["speed_supported"] is True

    _co2(hass, "sensor.bedroom", 950)
    await hass.async_block_till_done()
    assert calls[-1].service == "turn_on"
    assert calls[-1].data["percentage"] == 33
    assert hass.states.get(FAN).state == "on"


async def test_selected_speed_used_when_turning_on(hass: HomeAssistant) -> None:
    calls = await _setup(hass)
    await _select(hass, "medium_low")
    # Fan is off, so picking a speed doesn't start it.
    assert hass.states.get(FAN).state == "off"
    assert not calls

    _co2(hass, "sensor.bedroom", 950)
    await hass.async_block_till_done()
    assert calls[-1].data["percentage"] == 66


async def test_changing_speed_while_ventilating(hass: HomeAssistant) -> None:
    calls = await _setup(hass)
    _co2(hass, "sensor.bedroom", 950)
    await hass.async_block_till_done()
    assert calls[-1].data["percentage"] == 33

    await _select(hass, "medium")
    assert calls[-1].service == "set_percentage"
    assert calls[-1].data["percentage"] == 100
    assert hass.states.get(STATUS).state == "ventilating"


async def test_speed_change_leaves_manual_fan_alone(hass: HomeAssistant) -> None:
    calls = await _setup(hass)
    _fan_state(hass, True, 100)  # someone turned it on by hand at full speed
    await hass.async_block_till_done()
    assert hass.states.get(STATUS).state == "manual"

    await _select(hass, "low")
    assert not calls
    assert hass.states.get(FAN).attributes["percentage"] == 100


async def test_fan_without_speeds_just_turns_on(hass: HomeAssistant) -> None:
    calls = await _setup(hass, step=None)
    assert hass.states.get(SPEED).attributes["speed_supported"] is False
    _co2(hass, "sensor.bedroom", 950)
    await hass.async_block_till_done()
    assert calls[-1].service == "turn_on"
    assert "percentage" not in calls[-1].data
