"""Remote fan select (Off or a speed): for button/remote automations."""

from homeassistant.core import HomeAssistant

from .test_activity import ACT, FAN, _act, _fan, _setup

REMOTE = "select.co2_ventilation_remote_fan"
CALLER = "sensor.co2_ventilation_fan_turned_on_by"
CO2 = "sensor.front_room"


async def _remote(hass: HomeAssistant, option: str) -> None:
    await hass.services.async_call("select", "select_option", {"entity_id": REMOTE, "option": option}, blocking=True)
    await hass.async_block_till_done()


async def _co2(hass: HomeAssistant, ppm: int) -> None:
    hass.states.async_set(CO2, str(ppm), {"device_class": "carbon_dioxide", "unit_of_measurement": "ppm"})
    await hass.async_block_till_done()


def _pct(hass: HomeAssistant) -> int:
    return hass.states.get(FAN).attributes["percentage"]


async def test_remote_runs_fan_at_its_speed(hass: HomeAssistant) -> None:
    await _setup(hass)
    assert hass.states.get(REMOTE).state == "off"
    await _remote(hass, "medium")
    assert hass.states.get(FAN).state == "on"
    assert _pct(hass) == 75
    state, a = _act(hass)
    assert state == "fan_remote"
    assert a["called_by"] == ["remote"]
    assert hass.states.get(CALLER).state == "remote"
    assert hass.states.get(REMOTE).state == "medium"


async def test_speed_change_while_on_applies(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _remote(hass, "low")
    assert _pct(hass) == 25
    await _remote(hass, "medium_high")
    assert _pct(hass) == 100


async def test_remote_off_turns_fan_off(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _remote(hass, "low")
    await _remote(hass, "off")
    assert hass.states.get(FAN).state == "off"
    assert hass.states.get(CALLER).state == "off"
    assert _act(hass)[0] == "idle"


async def test_remote_off_leaves_co2_running(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _co2(hass, 950)
    await _remote(hass, "medium")
    assert _pct(hass) == 75
    assert _act(hass)[1]["called_by"] == ["remote", "co2"]
    await _remote(hass, "off")
    assert hass.states.get(FAN).state == "on"
    assert _pct(hass) == 25  # back to the CO2 speed (low)
    assert hass.states.get(CALLER).state == "co2"
    assert hass.states.get(ACT).state == "ventilating"


async def test_fan_turned_off_elsewhere_sets_remote_off(hass: HomeAssistant) -> None:
    await _setup(hass)
    await _remote(hass, "low")
    _fan(hass, False)
    await hass.async_block_till_done()
    assert hass.states.get(REMOTE).state == "off"
    assert hass.states.get(FAN).state == "off"


async def test_remote_takes_over_a_hand_started_fan(hass: HomeAssistant) -> None:
    await _setup(hass)
    _fan(hass, True, 25)
    await hass.async_block_till_done()
    assert hass.states.get(CALLER).state == "manual"
    await _remote(hass, "medium_low")
    assert _pct(hass) == 50
    assert hass.states.get(CALLER).state == "remote"
    await _remote(hass, "off")
    assert hass.states.get(FAN).state == "off"


async def test_remote_works_with_auto_off(hass: HomeAssistant) -> None:
    await _setup(hass)
    await hass.services.async_call("switch", "turn_off", {"entity_id": "switch.co2_ventilation_auto_ventilation"}, blocking=True)
    await _remote(hass, "low")
    assert hass.states.get(FAN).state == "on"
    await _remote(hass, "off")
    assert hass.states.get(FAN).state == "off"
