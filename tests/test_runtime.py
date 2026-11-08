"""Fan runtime counters and the thermostat settings section."""

from datetime import timedelta

from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)

from homeassistant import config_entries
from homeassistant.core import HomeAssistant, State
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.setup import async_setup_component
from homeassistant.util import dt as dt_util

from custom_components.co2_ventilation.const import DOMAIN

FAN = "input_boolean.fan"
G = "binary_sensor.thermostat_fan_g"
W2 = "binary_sensor.thermostat_heat_strips_w2"
FILTER = "sensor.co2_ventilation_fan_runtime_since_filter_change"
TOTAL = "sensor.co2_ventilation_fan_runtime_total"
RESET = "button.co2_ventilation_reset_filter_runtime"
STATUS = "sensor.co2_ventilation_status"


async def _setup(hass: HomeAssistant, thermostat: dict | None = None) -> MockConfigEntry:
    await async_setup_component(hass, "homeassistant", {})
    await async_setup_component(hass, "input_boolean", {"input_boolean": {"fan": {}}})
    hass.states.async_set(
        "sensor.bedroom", "500", {"device_class": "carbon_dioxide", "unit_of_measurement": "ppm"}
    )
    hass.states.async_set(G, "off")
    hass.states.async_set(W2, "off")
    data = {"co2_sensors": ["sensor.bedroom"], "fan_entity": FAN, "startup_delay": 120}
    if thermostat is not None:
        data["thermostat"] = thermostat
    entry = MockConfigEntry(domain=DOMAIN, title="CO2 Ventilation", data=data, unique_id=FAN)
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def _advance(hass: HomeAssistant, freezer, minutes: float) -> None:
    freezer.tick(timedelta(minutes=minutes))
    async_fire_time_changed(hass, dt_util.utcnow())
    await hass.async_block_till_done()


def _hours(hass: HomeAssistant, entity_id: str) -> float:
    return float(hass.states.get(entity_id).state)


async def test_counts_thermostat_and_vent_fan(hass: HomeAssistant, freezer) -> None:
    await _setup(hass, {"call_g": G, "call_w2": W2})
    assert _hours(hass, FILTER) == 0
    assert _hours(hass, TOTAL) == 0

    # Thermostat fan call runs the blower for 30 minutes.
    hass.states.async_set(G, "on")
    await hass.async_block_till_done()
    await _advance(hass, freezer, 30)
    hass.states.async_set(G, "off")
    await hass.async_block_till_done()
    assert abs(_hours(hass, TOTAL) - 0.5) < 0.02

    # Off for an hour: no change.
    await _advance(hass, freezer, 60)
    assert abs(_hours(hass, TOTAL) - 0.5) < 0.02

    # Heat strips and the ventilation fan overlapping count once.
    hass.states.async_set(W2, "on")
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": FAN}, blocking=True)
    await hass.async_block_till_done()
    await _advance(hass, freezer, 60)
    hass.states.async_set(W2, "off")
    await hass.services.async_call("input_boolean", "turn_off", {"entity_id": FAN}, blocking=True)
    await hass.async_block_till_done()
    assert abs(_hours(hass, TOTAL) - 1.5) < 0.02
    assert abs(_hours(hass, FILTER) - 1.5) < 0.02
    assert hass.states.get(TOTAL).attributes["running"] is False


async def test_reset_filter_keeps_total(hass: HomeAssistant, freezer) -> None:
    await _setup(hass, {"call_g": G})
    hass.states.async_set(G, "on")
    await hass.async_block_till_done()
    await _advance(hass, freezer, 120)

    await hass.services.async_call("button", "press", {"entity_id": RESET}, blocking=True)
    await hass.async_block_till_done()
    assert _hours(hass, FILTER) == 0
    assert abs(_hours(hass, TOTAL) - 2) < 0.02
    assert hass.states.get(FILTER).attributes["last_reset_at"] is not None

    await _advance(hass, freezer, 60)
    assert abs(_hours(hass, FILTER) - 1) < 0.02
    assert abs(_hours(hass, TOTAL) - 3) < 0.02


async def test_without_thermostat_counts_vent_fan_only(hass: HomeAssistant, freezer) -> None:
    await _setup(hass)
    hass.states.async_set(G, "on")  # not configured, so ignored
    await hass.services.async_call("input_boolean", "turn_on", {"entity_id": FAN}, blocking=True)
    await hass.async_block_till_done()
    await _advance(hass, freezer, 45)
    assert abs(_hours(hass, TOTAL) - 0.75) < 0.02


async def test_counters_survive_restart(hass: HomeAssistant) -> None:
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State(FILTER, "12.5", {"last_reset_at": "2026-11-07T16:00:00+00:00"}),
                {"native_value": 12.5, "native_unit_of_measurement": "h"},
            ),
            (State(TOTAL, "40.25"), {"native_value": 40.25, "native_unit_of_measurement": "h"}),
        ],
    )
    await _setup(hass, {"call_g": G})
    assert _hours(hass, FILTER) == 12.5
    assert _hours(hass, TOTAL) == 40.25
    assert hass.states.get(FILTER).attributes["last_reset_at"].startswith("2026-11-07T16:00")


async def test_status_lists_thermostat_entities(hass: HomeAssistant) -> None:
    await _setup(hass, {"climate_entity": "climate.nest", "call_g": G})
    t = hass.states.get(STATUS).attributes["thermostat"]
    assert t["climate_entity"] == "climate.nest"
    assert t["call_g"] == G
    assert t["call_w2"] is None


async def test_options_flow_saves_thermostat_section(hass: HomeAssistant) -> None:
    entry = await _setup(hass)
    result = await hass.config_entries.options.async_init(entry.entry_id)
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "co2_sensors": ["sensor.bedroom"],
            "fan_entity": FAN,
            "startup_delay": 120,
            "thermostat": {"climate_entity": "climate.nest", "call_g": G, "call_w2": W2},
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert entry.options["thermostat"]["call_w2"] == W2
    t = hass.states.get(STATUS).attributes["thermostat"]
    assert t["climate_entity"] == "climate.nest"


async def test_user_flow_without_thermostat(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": config_entries.SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"],
        {"name": "House CO2", "co2_sensors": ["sensor.bedroom"], "fan_entity": "switch.x", "startup_delay": 120},
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
