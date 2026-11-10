"""Shower humidity ventilation, and how it shares the fan with CO2."""

from datetime import timedelta

import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.co2_ventilation.const import DOMAIN

FAN = "fan.ventilation"
BATH = "sensor.bathroom_humidity"
NEST_HUM = "sensor.nest_humidity"
CO2 = "sensor.front_room"
EXHAUST = "input_boolean.bath_exhaust"
ACT = "sensor.co2_ventilation_hvac_activity"
DIFF = "sensor.co2_ventilation_bathroom_humidity_above_house"
SHOWER_SW = "switch.co2_ventilation_shower_ventilation"
SPEED = "select.co2_ventilation_ventilation_speed"
STEP = 25  # 4-speed fan: 25 % low ... 100 % med-high


def _fan(hass: HomeAssistant, on: bool, pct: int = 0) -> None:
    hass.states.async_set(FAN, "on" if on else "off", {"percentage_step": STEP, "percentage": pct if on else 0})


def _pct(hass: HomeAssistant) -> int:
    s = hass.states.get(FAN)
    return s.attributes["percentage"] if s.state == "on" else 0


async def _setup(hass: HomeAssistant, shower: dict | None = None, house_hum=40) -> list[ServiceCall]:
    calls: list[ServiceCall] = []

    async def turn_on(call: ServiceCall) -> None:
        calls.append(call)
        _fan(hass, True, call.data.get("percentage", 100))

    async def set_pct(call: ServiceCall) -> None:
        calls.append(call)
        _fan(hass, True, call.data["percentage"])

    async def turn_off(call: ServiceCall) -> None:
        calls.append(call)
        _fan(hass, False)

    hass.services.async_register("fan", "turn_on", turn_on)
    hass.services.async_register("fan", "set_percentage", set_pct)
    hass.services.async_register("fan", "turn_off", turn_off)
    await async_setup_component(hass, "homeassistant", {})
    await async_setup_component(hass, "input_boolean", {"input_boolean": {"bath_exhaust": {}}})

    _fan(hass, False)
    hass.states.async_set(CO2, "600", {"device_class": "carbon_dioxide", "unit_of_measurement": "ppm"})
    hass.states.async_set(NEST_HUM, str(house_hum), {"device_class": "humidity", "unit_of_measurement": "%"})
    hass.states.async_set(BATH, "41", {"device_class": "humidity", "unit_of_measurement": "%"})
    data = {
        "co2_sensors": [CO2],
        "fan_entity": FAN,
        "startup_delay": 120,
        "thermostat": {"humidity_sensor": NEST_HUM},
    }
    if shower is not None:
        data["shower"] = shower
    entry = MockConfigEntry(domain=DOMAIN, title="CO2 Ventilation", data=data, unique_id=FAN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return calls


async def _settle(hass: HomeAssistant) -> None:
    # Service calls made from state-change handlers land a loop pass later.
    for _ in range(3):
        await hass.async_block_till_done()


async def _bath(hass: HomeAssistant, value) -> None:
    hass.states.async_set(BATH, str(value), {"device_class": "humidity", "unit_of_measurement": "%"})
    await _settle(hass)


async def _co2(hass: HomeAssistant, value) -> None:
    hass.states.async_set(CO2, str(value), {"device_class": "carbon_dioxide", "unit_of_measurement": "ppm"})
    await _settle(hass)


async def _advance(hass: HomeAssistant, freezer, minutes: float) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


async def test_no_shower_entities_without_config(hass: HomeAssistant) -> None:
    await _setup(hass)
    assert hass.states.get(SHOWER_SW) is None
    assert hass.states.get(DIFF) is None


async def test_full_shower_cycle(hass: HomeAssistant, freezer) -> None:
    await _setup(hass, {"bathroom_humidity": BATH})
    assert hass.states.get(DIFF).state == "1.0"

    await _bath(hass, 47)  # +7: not yet
    assert hass.states.get(FAN).state == "off"

    await _bath(hass, 52)  # +12: high (top speed)
    assert _pct(hass) == 100
    state = hass.states.get(ACT)
    assert state.state == "ventilating"
    assert state.attributes["called_by"] == ["humidity"]
    assert state.attributes["fan_speed"] == "medium_high"

    await _bath(hass, 85)  # shower in full swing
    await _advance(hass, freezer, 10)
    await _bath(hass, 58)  # +18: under 20, been high 10 min -> low
    assert _pct(hass) == 25
    assert hass.states.get(DIFF).attributes["mode"] == "low"

    await _bath(hass, 46)  # +6: still low
    assert _pct(hass) == 25
    await _bath(hass, 44)  # +4: off
    assert hass.states.get(FAN).state == "off"
    assert hass.states.get(ACT).state == "idle"


async def test_short_shower_holds_high_five_minutes(hass: HomeAssistant, freezer) -> None:
    await _setup(hass, {"bathroom_humidity": BATH})
    await _bath(hass, 55)  # +15: high
    assert _pct(hass) == 100
    await _advance(hass, freezer, 2)
    assert _pct(hass) == 100  # below 20 but under the 5 minute minimum
    await _advance(hass, freezer, 4)
    assert _pct(hass) == 25  # the timer re-checks and drops to low


async def test_shares_fan_with_co2(hass: HomeAssistant, freezer) -> None:
    await _setup(hass, {"bathroom_humidity": BATH})
    await _co2(hass, 950)  # CO2 on at low
    assert _pct(hass) == 25

    await _bath(hass, 70)  # shower: bumps to high
    assert _pct(hass) == 100
    assert hass.states.get(ACT).attributes["called_by"] == ["co2", "humidity"]

    await _bath(hass, 42)  # shower over: back to CO2's speed, still on
    assert _pct(hass) == 25
    assert hass.states.get(ACT).attributes["called_by"] == ["co2"]

    await _advance(hass, freezer, 25)  # past the 20 minute minimum run
    await _co2(hass, 650)  # CO2 down: now off
    assert hass.states.get(FAN).state == "off"


async def test_co2_ending_does_not_stop_shower(hass: HomeAssistant, freezer) -> None:
    await _setup(hass, {"bathroom_humidity": BATH})
    await _co2(hass, 950)
    await _bath(hass, 70)
    await _advance(hass, freezer, 25)
    await _co2(hass, 650)  # CO2 is done, shower isn't
    assert _pct(hass) == 100
    assert hass.states.get(ACT).attributes["called_by"] == ["humidity"]


async def test_max_run_time_then_waits_to_dry(hass: HomeAssistant, freezer) -> None:
    await _setup(hass, {"bathroom_humidity": BATH})
    await _bath(hass, 75)
    await _advance(hass, freezer, 91)
    assert hass.states.get(FAN).state == "off"
    assert hass.states.get(DIFF).attributes["mode"] == "lockout"
    await _bath(hass, 74)  # still humid: stays off
    assert hass.states.get(FAN).state == "off"
    await _bath(hass, 43)  # dried out: ready again
    assert hass.states.get(DIFF).attributes["mode"] == "off"
    await _bath(hass, 60)
    assert _pct(hass) == 100


async def test_sensor_unavailable_stops(hass: HomeAssistant) -> None:
    await _setup(hass, {"bathroom_humidity": BATH})
    await _bath(hass, 70)
    assert hass.states.get(FAN).state == "on"
    await _bath(hass, "unavailable")
    assert hass.states.get(FAN).state == "off"


async def test_turned_off_by_hand_stays_off_for_this_shower(hass: HomeAssistant) -> None:
    await _setup(hass, {"bathroom_humidity": BATH})
    await _bath(hass, 70)
    _fan(hass, False)  # someone switches it off
    await hass.async_block_till_done()
    await _bath(hass, 72)
    assert hass.states.get(FAN).state == "off"
    await _bath(hass, 42)  # shower over
    await _bath(hass, 70)  # next shower works again
    assert hass.states.get(FAN).state == "on"


async def test_switch_off_disables(hass: HomeAssistant) -> None:
    await _setup(hass, {"bathroom_humidity": BATH})
    await _bath(hass, 70)
    await hass.services.async_call("switch", "turn_off", {"entity_id": SHOWER_SW}, blocking=True)
    await hass.async_block_till_done()
    assert hass.states.get(FAN).state == "off"
    await _bath(hass, 75)
    assert hass.states.get(FAN).state == "off"


CALL_Y, CALL_O, CALL_W2 = "binary_sensor.call_y", "binary_sensor.call_o", "binary_sensor.call_w2"
NEST = "climate.nest"
LAST_COOL = "sensor.co2_ventilation_last_cooling_run"


async def _setup_exhaust(hass: HomeAssistant, calls: bool = True):
    hass.states.async_set(CALL_Y, "off")
    hass.states.async_set(CALL_O, "off")
    hass.states.async_set(CALL_W2, "off")
    hass.states.async_set(NEST, "heat", {"hvac_action": "idle"})
    await _setup(hass, {"bathroom_humidity": BATH, "exhaust_fan": EXHAUST})
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    thermostat = {"humidity_sensor": NEST_HUM, "climate_entity": NEST}
    if calls:
        thermostat |= {"call_y": CALL_Y, "call_ob": CALL_O, "call_w2": CALL_W2}
    hass.config_entries.async_update_entry(entry, options={**entry.data, "thermostat": thermostat})
    await _settle(hass)


async def _cool(hass: HomeAssistant, freezer, minutes: float = 15) -> None:
    hass.states.async_set(CALL_Y, "on")
    hass.states.async_set(CALL_O, "on")
    await _settle(hass)
    await _advance(hass, freezer, minutes)
    hass.states.async_set(CALL_Y, "off")
    hass.states.async_set(CALL_O, "off")
    await _settle(hass)


async def test_exhaust_stays_off_in_heating_season(hass: HomeAssistant) -> None:
    await _setup_exhaust(hass)
    assert hass.states.get(LAST_COOL).state == "unknown"
    await _bath(hass, 70)
    assert hass.states.get(FAN).state == "on"  # the blower still spreads it
    assert hass.states.get(EXHAUST).state == "off"
    # Heat pump heating (Y without O) isn't cooling.
    hass.states.async_set(CALL_Y, "on")
    await _settle(hass)
    assert hass.states.get(LAST_COOL).state == "unknown"


async def test_exhaust_runs_after_recent_cooling(hass: HomeAssistant, freezer) -> None:
    await _setup_exhaust(hass)
    await _cool(hass, freezer)
    assert hass.states.get(LAST_COOL).state != "unknown"
    await _advance(hass, freezer, 60 * 24 * 3)  # 3 days later
    await _bath(hass, 70)
    assert hass.states.get(EXHAUST).state == "on"
    await _bath(hass, 42)
    assert hass.states.get(EXHAUST).state == "off"


async def test_exhaust_window_expires(hass: HomeAssistant, freezer) -> None:
    await _setup_exhaust(hass)
    await _cool(hass, freezer)
    await _advance(hass, freezer, 60 * 24 * 8)  # 8 days: past the 7 day window
    await _bath(hass, 70)
    assert hass.states.get(EXHAUST).state == "off"
    await _bath(hass, 42)
    # A longer window lets it run again.
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.co2_ventilation_exhaust_fan_cooling_window", "value": 14},
        blocking=True,
    )
    await _bath(hass, 70)
    assert hass.states.get(EXHAUST).state == "on"


async def test_exhaust_finishes_the_shower_it_started(hass: HomeAssistant, freezer) -> None:
    await _setup_exhaust(hass)
    await _cool(hass, freezer)
    await _advance(hass, freezer, 60 * 24 * 7 - 10)  # just inside the window
    await _bath(hass, 70)
    assert hass.states.get(EXHAUST).state == "on"
    await _advance(hass, freezer, 30)  # window closes mid-shower
    await _bath(hass, 68)
    assert hass.states.get(EXHAUST).state == "on"


async def test_cooling_from_thermostat_without_calls(hass: HomeAssistant, freezer) -> None:
    await _setup_exhaust(hass, calls=False)
    hass.states.async_set(NEST, "cool", {"hvac_action": "cooling"})
    await _settle(hass)
    await _advance(hass, freezer, 15)
    await _bath(hass, 70)
    assert hass.states.get(EXHAUST).state == "on"


async def test_last_cooling_survives_restart(hass: HomeAssistant) -> None:
    from homeassistant.core import State
    from pytest_homeassistant_custom_component.common import mock_restore_cache

    recent = (dt_util.utcnow() - timedelta(days=2)).isoformat()
    mock_restore_cache(hass, [State(LAST_COOL, recent)])
    await _setup_exhaust(hass)
    await _bath(hass, 70)
    assert hass.states.get(EXHAUST).state == "on"


async def test_house_sensor_override(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.hall", "30", {"device_class": "humidity"})
    await _setup(hass, {"bathroom_humidity": BATH, "house_humidity": "sensor.hall"})
    assert hass.states.get(DIFF).state == "11.0"  # 41 vs 30, not vs the Nest
    assert hass.states.get(FAN).state == "on"


async def test_threshold_validation(hass: HomeAssistant) -> None:
    await _setup(hass, {"bathroom_humidity": BATH})
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            "number", "set_value",
            {"entity_id": "number.co2_ventilation_shower_off_below", "value": 12},
            blocking=True,
        )
    await hass.services.async_call(
        "number", "set_value",
        {"entity_id": "number.co2_ventilation_shower_on_above_house", "value": 15},
        blocking=True,
    )
    await _bath(hass, 53)  # +13: under the new 15
    assert hass.states.get(FAN).state == "off"



async def test_defrost_is_not_cooling(hass: HomeAssistant, freezer) -> None:
    await _setup_exhaust(hass)
    # Defrost: Y + O with the heat strips, for longer than the 10 minutes.
    for e in (CALL_Y, CALL_O, CALL_W2):
        hass.states.async_set(e, "on")
    await _settle(hass)
    assert hass.states.get(ACT).state == "defrost"
    await _advance(hass, freezer, 15)
    for e in (CALL_Y, CALL_O, CALL_W2):
        hass.states.async_set(e, "off")
    await _settle(hass)
    assert hass.states.get(LAST_COOL).state == "unknown"
    await _bath(hass, 70)
    assert hass.states.get(EXHAUST).state == "off"


async def test_short_cooling_blip_does_not_count(hass: HomeAssistant, freezer) -> None:
    await _setup_exhaust(hass)
    await _cool(hass, freezer, minutes=3)  # e.g. calls landing out of order
    assert hass.states.get(LAST_COOL).state == "unknown"
    await _bath(hass, 70)
    assert hass.states.get(EXHAUST).state == "off"


async def test_long_cooling_run_counts_without_state_changes(hass: HomeAssistant, freezer) -> None:
    await _setup_exhaust(hass)
    hass.states.async_set(CALL_Y, "on")
    hass.states.async_set(CALL_O, "on")
    await _settle(hass)
    assert hass.states.get(ACT).state == "cooling"
    for _ in range(24):  # 12 minutes of half-minute ticks, nothing else changing
        await _advance(hass, freezer, 0.5)
    assert hass.states.get(LAST_COOL).state != "unknown"


async def test_house_sensors_averaged(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.hall", "30", {"device_class": "humidity"})
    hass.states.async_set("sensor.bedroom", "36", {"device_class": "humidity"})
    await _setup(
        hass, {"bathroom_humidity": BATH, "house_humidity": ["sensor.hall", "sensor.bedroom"]}
    )
    # Bathroom 41 vs. the average of 30 and 36 (33): +8, under the 10 to start.
    assert hass.states.get(DIFF).state == "8.0"
    assert hass.states.get(DIFF).attributes["house_humidity"] == 33.0
    assert hass.states.get(FAN).state == "off"

    # One house sensor drops out: the other carries on alone.
    hass.states.async_set("sensor.bedroom", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(DIFF).state == "11.0"
    assert hass.states.get(FAN).state == "on"


async def test_house_sensors_all_offline_stops(hass: HomeAssistant) -> None:
    hass.states.async_set("sensor.hall", "30", {"device_class": "humidity"})
    await _setup(hass, {"bathroom_humidity": BATH, "house_humidity": ["sensor.hall"]})
    assert hass.states.get(FAN).state == "on"
    hass.states.async_set("sensor.hall", "unavailable")
    await hass.async_block_till_done()
    assert hass.states.get(DIFF).state == "unknown"
