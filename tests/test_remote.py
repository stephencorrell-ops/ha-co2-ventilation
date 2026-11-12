"""Fan remotes: a fan turned on right after a remote press shows as remote."""

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory

from homeassistant.core import HomeAssistant

from .test_activity import ACT, FAN, _act, _fan, _setup

REMOTE = "event.hall_button"
CALLER = "sensor.co2_ventilation_fan_turned_on_by"


async def _press(hass: HomeAssistant, when: str) -> None:
    hass.states.async_set(REMOTE, when, {"event_type": "short_release"})
    await hass.async_block_till_done()


async def _setup_remote(hass: HomeAssistant) -> None:
    hass.states.async_set(REMOTE, "2026-11-01T00:00:00+00:00")
    await _setup(hass)
    entry = hass.config_entries.async_entries("co2_ventilation")[0]
    hass.config_entries.async_update_entry(entry, options={**entry.data, "fan_remotes": [REMOTE]})
    await hass.async_block_till_done()


async def test_press_then_fan_is_remote(hass: HomeAssistant) -> None:
    await _setup_remote(hass)
    await _press(hass, "2026-11-12T13:00:00+00:00")
    _fan(hass, True, 50)
    await hass.async_block_till_done()
    state, a = _act(hass)
    assert state == "fan_remote"
    assert a["called_by"] == ["remote"]
    assert hass.states.get(CALLER).state == "remote"


async def test_press_just_after_fan_on_is_remote(hass: HomeAssistant) -> None:
    await _setup_remote(hass)
    _fan(hass, True, 25)
    await hass.async_block_till_done()
    assert _act(hass)[0] == "fan_manual"
    await _press(hass, "2026-11-12T13:00:00+00:00")
    assert _act(hass)[0] == "fan_remote"
    assert hass.states.get(CALLER).state == "remote"


async def test_old_press_is_by_hand(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    await _setup_remote(hass)
    await _press(hass, "2026-11-12T13:00:00+00:00")
    freezer.tick(timedelta(minutes=5))
    _fan(hass, True, 25)
    await hass.async_block_till_done()
    assert _act(hass)[0] == "fan_manual"
    assert hass.states.get(CALLER).state == "manual"


async def test_remote_coming_back_online_is_not_a_press(hass: HomeAssistant) -> None:
    await _setup_remote(hass)
    hass.states.async_set(REMOTE, "unavailable")
    await hass.async_block_till_done()
    hass.states.async_set(REMOTE, "2026-11-01T00:00:00+00:00")
    await hass.async_block_till_done()
    _fan(hass, True, 25)
    await hass.async_block_till_done()
    assert _act(hass)[0] == "fan_manual"


async def test_off_clears_remote_and_caller(hass: HomeAssistant) -> None:
    await _setup_remote(hass)
    await _press(hass, "2026-11-12T13:00:00+00:00")
    _fan(hass, True, 25)
    await hass.async_block_till_done()
    _fan(hass, False)
    await hass.async_block_till_done()
    assert _act(hass)[0] == "idle"
    assert hass.states.get(CALLER).state == "off"


async def test_without_remotes_configured_it_is_by_hand(hass: HomeAssistant) -> None:
    await _setup(hass)
    hass.states.async_set(REMOTE, "2026-11-12T13:00:00+00:00")
    await hass.async_block_till_done()
    _fan(hass, True, 25)
    await hass.async_block_till_done()
    assert _act(hass)[0] == "fan_manual"
    assert hass.states.get(CALLER).state == "manual"


async def test_caller_is_co2_when_ventilating(hass: HomeAssistant) -> None:
    await _setup_remote(hass)
    hass.states.async_set("sensor.front_room", "950", {"device_class": "carbon_dioxide", "unit_of_measurement": "ppm"})
    await hass.async_block_till_done()
    assert hass.states.get(ACT).state == "ventilating"
    assert hass.states.get(CALLER).state == "co2"
    assert FAN
