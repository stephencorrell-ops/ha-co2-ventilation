"""HVAC activity sensor: what's running, who called for it, and the blower speed."""

from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.core import HomeAssistant, ServiceCall
from homeassistant.setup import async_setup_component

from custom_components.co2_ventilation.const import DOMAIN

FAN = "fan.ventilation"
ACT = "sensor.co2_ventilation_hvac_activity"
SPEED = "select.co2_ventilation_ventilation_speed"
G, Y, O, W2 = (f"binary_sensor.call_{k}" for k in ("g", "y", "o", "w2"))
NEST = "climate.nest"
STEP = 25  # 4-speed fan, like the ESPHome air handler node


def _fan(hass: HomeAssistant, on: bool, pct: int = 0) -> None:
    hass.states.async_set(FAN, "on" if on else "off", {"percentage_step": STEP, "percentage": pct if on else 0})


async def _setup(hass: HomeAssistant, **thermostat_extra: str) -> None:
    async def turn_on(call: ServiceCall) -> None:
        _fan(hass, True, call.data.get("percentage", 100))

    async def set_pct(call: ServiceCall) -> None:
        _fan(hass, True, call.data["percentage"])

    async def turn_off(call: ServiceCall) -> None:
        _fan(hass, False)

    hass.services.async_register("fan", "turn_on", turn_on)
    hass.services.async_register("fan", "set_percentage", set_pct)
    hass.services.async_register("fan", "turn_off", turn_off)
    await async_setup_component(hass, "homeassistant", {})
    _fan(hass, False)
    for e in (G, Y, O, W2):
        hass.states.async_set(e, "off")
    hass.states.async_set(NEST, "heat", {"friendly_name": "Nest"})
    hass.states.async_set("sensor.front_room", "600", {"device_class": "carbon_dioxide", "unit_of_measurement": "ppm"})
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="CO2 Ventilation",
        data={
            "co2_sensors": ["sensor.front_room"],
            "fan_entity": FAN,
            "startup_delay": 120,
            "thermostat": {"climate_entity": NEST, "call_g": G, "call_y": Y, "call_ob": O, "call_w2": W2, **thermostat_extra},
        },
        unique_id=FAN,
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def _set(hass: HomeAssistant, **calls: bool) -> None:
    for k, v in calls.items():
        hass.states.async_set({"g": G, "y": Y, "o": O, "w2": W2}[k], "on" if v else "off")
    await hass.async_block_till_done()


def _act(hass: HomeAssistant):
    s = hass.states.get(ACT)
    return s.state, s.attributes


async def test_idle(hass: HomeAssistant) -> None:
    await _setup(hass)
    state, a = _act(hass)
    assert state == "idle"
    assert a["called_by"] == []
    assert a["fan_speed"] is None
    assert a["thermostat_name"] == "Nest"


async def test_nest_heat_pump(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _set(hass, g=True, y=True)
    state, a = _act(hass)
    assert state == "heat_pump"
    assert a["called_by"] == ["thermostat"]
    assert a["fan_speed"] == "medium"


async def test_heat_strips_run_high(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _set(hass, g=True, y=True, w2=True)
    state, a = _act(hass)
    assert state == "heat_pump_aux"
    assert a["fan_speed"] == "high"
    await _set(hass, y=False)
    assert _act(hass)[0] == "aux_heat"


async def test_cooling_and_fan_only(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _set(hass, g=True, y=True, o=True)
    assert _act(hass)[0] == "cooling"
    await _set(hass, y=False, o=False)
    assert _act(hass)[0] == "fan_only"


async def test_co2_ventilation_at_low(hass: HomeAssistant) -> None:
    await _setup(hass)
    hass.states.async_set("sensor.front_room", "950", {"device_class": "carbon_dioxide", "unit_of_measurement": "ppm"})
    await hass.async_block_till_done()
    state, a = _act(hass)
    assert state == "ventilating"
    assert a["called_by"] == ["co2"]
    assert a["fan_speed"] == "low"
    assert a["co2_source"] == "sensor.front_room"
    assert a["co2_ppm"] == 950


async def test_nest_and_co2_together_highest_wins(hass: HomeAssistant) -> None:
    await _setup(hass)
    hass.states.async_set("sensor.front_room", "950", {"device_class": "carbon_dioxide", "unit_of_measurement": "ppm"})
    await _set(hass, g=True, y=True)
    state, a = _act(hass)
    assert state == "heat_pump"
    assert a["called_by"] == ["thermostat", "co2"]
    assert a["ventilating"] is True
    assert a["fan_speed"] == "medium"

    # Ventilation at med-high beats the thermostat's medium.
    await hass.services.async_call("select", "select_option", {"entity_id": SPEED, "option": "medium_high"}, blocking=True)
    await hass.async_block_till_done()
    assert _act(hass)[1]["fan_speed"] == "medium_high"
    assert hass.states.get(FAN).attributes["percentage"] == 100


async def test_manual_fan(hass: HomeAssistant) -> None:
    await _setup(hass)
    _fan(hass, True, 50)
    await hass.async_block_till_done()
    state, a = _act(hass)
    assert state == "fan_manual"
    assert a["called_by"] == ["manual"]
    assert a["fan_speed"] == "medium_low"


async def test_g_label_defaults_to_none(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _set(hass, g=True)
    state, a = _act(hass)
    assert state == "fan_only"
    assert a["g_label"] is None


async def test_g_label_from_settings(hass: HomeAssistant) -> None:
    """A humidifier also calls G, so the user names G-only calls."""
    await _setup(hass, g_label="  Fan/Humidifier ")
    await _set(hass, g=True)
    state, a = _act(hass)
    assert state == "fan_only"
    assert a["g_label"] == "Fan/Humidifier"
    assert a["called_by"] == ["thermostat"]
