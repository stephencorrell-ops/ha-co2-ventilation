"""Behaviour tests for the CO2 ventilation controller."""

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.const import EVENT_HOMEASSISTANT_STARTED
from homeassistant.core import CoreState, HomeAssistant
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.co2_ventilation.const import DOMAIN

FAN = "input_boolean.fan"
ON_NUM = "number.co2_ventilation_fan_on_at"
OFF_NUM = "number.co2_ventilation_fan_off_at"
MIN_NUM = "number.co2_ventilation_minimum_run_time"
AUTO = "switch.co2_ventilation_auto_ventilation"
STATUS = "sensor.co2_ventilation_status"
HIGHEST = "sensor.co2_ventilation_highest_co2"


def _co2(hass: HomeAssistant, entity_id: str, value) -> None:
    hass.states.async_set(
        entity_id,
        str(value),
        {"device_class": "carbon_dioxide", "unit_of_measurement": "ppm"},
    )


async def _setup(hass: HomeAssistant, fan_on: bool = False) -> MockConfigEntry:
    await async_setup_component(hass, "homeassistant", {})
    await async_setup_component(
        hass, "input_boolean", {"input_boolean": {"fan": {"initial": fan_on}}}
    )
    _co2(hass, "sensor.bedroom", 500)
    _co2(hass, "sensor.living", 500)
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="CO2 Ventilation",
        data={
            "co2_sensors": ["sensor.bedroom", "sensor.living"],
            "fan_entity": FAN,
            "startup_delay": 120,
        },
        unique_id=FAN,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _set_number(hass: HomeAssistant, entity_id: str, value) -> None:
    await hass.services.async_call(
        "number", "set_value", {"entity_id": entity_id, "value": value}, blocking=True
    )
    await hass.async_block_till_done()


async def _advance(hass: HomeAssistant, freezer, seconds: float) -> None:
    freezer.tick(timedelta(seconds=seconds))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def test_entities_created(hass: HomeAssistant) -> None:
    await _setup(hass)
    assert hass.states.get(ON_NUM).state == "900.0"
    assert hass.states.get(OFF_NUM).state == "700.0"
    assert hass.states.get(MIN_NUM).state == "20.0"
    assert hass.states.get(AUTO).state == "on"
    assert hass.states.get(HIGHEST).state == "500.0"
    assert hass.states.get(STATUS).state == "idle"


async def test_on_at_setpoint_off_after_min_run(hass: HomeAssistant, freezer) -> None:
    await _setup(hass)

    _co2(hass, "sensor.bedroom", 950)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "on"
    assert hass.states.get(STATUS).state == "ventilating"
    assert hass.states.get(HIGHEST).attributes["source"] == "sensor.bedroom"

    # Drops below off after 5 minutes: must keep running until 20 minutes.
    await _advance(hass, freezer, 300)
    _co2(hass, "sensor.bedroom", 650)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "on"
    assert hass.states.get(STATUS).state == "min_run_hold"

    await _advance(hass, freezer, 14 * 60)
    assert hass.states.get(FAN).state == "on"
    await _advance(hass, freezer, 61)
    assert hass.states.get(FAN).state == "off"
    assert hass.states.get(STATUS).state == "idle"


async def test_off_after_min_run_already_met(hass: HomeAssistant, freezer) -> None:
    await _setup(hass)
    _co2(hass, "sensor.bedroom", 950)
    await hass.async_block_till_done()
    await _advance(hass, freezer, 25 * 60)
    _co2(hass, "sensor.bedroom", 690)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "off"


async def test_any_sensor_high_keeps_fan_on(hass: HomeAssistant, freezer) -> None:
    await _setup(hass)
    await _set_number(hass, MIN_NUM, 0)
    _co2(hass, "sensor.bedroom", 950)
    await hass.async_block_till_done()
    _co2(hass, "sensor.living", 800)
    _co2(hass, "sensor.bedroom", 600)
    await hass.async_block_till_done()
    # Living is between setpoints, so the fan stays on.
    assert hass.states.get(FAN).state == "on"
    _co2(hass, "sensor.living", 650)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "off"


async def test_rebound_cancels_pending_off(hass: HomeAssistant, freezer) -> None:
    await _setup(hass)
    _co2(hass, "sensor.bedroom", 950)
    await hass.async_block_till_done()
    _co2(hass, "sensor.bedroom", 650)
    await hass.async_block_till_done()
    assert hass.states.get(STATUS).state == "min_run_hold"
    _co2(hass, "sensor.bedroom", 760)
    await hass.async_block_till_done()
    assert hass.states.get(STATUS).state == "ventilating"
    await _advance(hass, freezer, 21 * 60)
    assert hass.states.get(FAN).state == "on"


async def test_unavailable_sensor_ignored(hass: HomeAssistant) -> None:
    await _setup(hass)
    hass.states.async_set("sensor.bedroom", "unavailable")
    _co2(hass, "sensor.living", 920)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "on"
    assert hass.states.get(HIGHEST).state == "920.0"


async def test_manual_fan_left_alone(hass: HomeAssistant, freezer) -> None:
    await _setup(hass)
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": FAN}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(STATUS).state == "manual"
    await _advance(hass, freezer, 3600)
    _co2(hass, "sensor.bedroom", 450)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "on"


async def test_auto_off_does_nothing(hass: HomeAssistant) -> None:
    await _setup(hass)
    await hass.services.async_call(
        "switch", "turn_off", {"entity_id": AUTO}, blocking=True
    )
    _co2(hass, "sensor.bedroom", 1200)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "off"
    assert hass.states.get(STATUS).state == "disabled"

    await hass.services.async_call(
        "switch", "turn_on", {"entity_id": AUTO}, blocking=True
    )
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "on"


async def test_setpoint_change_reacts(hass: HomeAssistant) -> None:
    await _setup(hass)
    _co2(hass, "sensor.bedroom", 850)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "off"
    await _set_number(hass, ON_NUM, 800)
    assert hass.states.get(FAN).state == "on"


async def test_setpoints_cannot_cross(hass: HomeAssistant) -> None:
    await _setup(hass)
    with pytest.raises(ServiceValidationError):
        await _set_number(hass, OFF_NUM, 900)
    with pytest.raises(ServiceValidationError):
        await _set_number(hass, ON_NUM, 650)


async def test_startup_defaults_fan_off(hass: HomeAssistant, freezer) -> None:
    hass.set_state(CoreState.not_running)
    await _setup(hass, fan_on=True)
    assert hass.states.get(STATUS).state == "starting"

    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "on"

    await _advance(hass, freezer, 121)
    assert hass.states.get(FAN).state == "off"
    assert hass.states.get(STATUS).state == "idle"


async def test_startup_keeps_fan_on_when_high(hass: HomeAssistant, freezer) -> None:
    hass.set_state(CoreState.not_running)
    await _setup(hass)
    hass.set_state(CoreState.running)
    hass.bus.async_fire(EVENT_HOMEASSISTANT_STARTED)
    await hass.async_block_till_done()

    _co2(hass, "sensor.bedroom", 1000)
    await hass.async_block_till_done()
    # Still waiting out the startup delay: no action yet.
    assert hass.states.get(FAN).state == "off"

    await _advance(hass, freezer, 121)
    assert hass.states.get(FAN).state == "on"
    assert hass.states.get(STATUS).state == "ventilating"


async def test_takes_over_manual_fan_when_high(hass: HomeAssistant, freezer) -> None:
    await _setup(hass)
    await hass.services.async_call(
        "input_boolean", "turn_on", {"entity_id": FAN}, blocking=True
    )
    _co2(hass, "sensor.bedroom", 950)
    await hass.async_block_till_done()
    assert hass.states.get(STATUS).state == "ventilating"
    await _advance(hass, freezer, 21 * 60)
    _co2(hass, "sensor.bedroom", 600)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "off"
