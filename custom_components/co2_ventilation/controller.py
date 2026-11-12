"""Ventilation logic: runs a fan from the highest CO2 reading."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
import logging
from typing import Any

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import STATE_ON, STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import (
    CALLBACK_TYPE,
    CoreState,
    Event,
    EventStateChangedData,
    HomeAssistant,
    callback,
)
from homeassistant.helpers.event import (
    async_call_later,
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util
from homeassistant.util.percentage import ranged_value_to_percentage

from .const import (
    ACTIVITY_AUX_HEAT,
    ACTIVITY_COOLING,
    ACTIVITY_DEFROST,
    ACTIVITY_FAN_MANUAL,
    ACTIVITY_FAN_ONLY,
    ACTIVITY_FAN_REMOTE,
    ACTIVITY_HEAT_PUMP,
    ACTIVITY_HEAT_PUMP_AUX,
    ACTIVITY_IDLE,
    ACTIVITY_VENTILATING,
    AUX_HEAT_LEVEL,
    CALLER_CO2,
    CALLER_HUMIDITY,
    CALLER_MANUAL,
    CALLER_REMOTE,
    CALLER_THERMOSTAT,
    CONF_CALL_G,
    CONF_G_LABEL,
    CONF_CALL_OB,
    CONF_CALL_W2,
    CONF_CALL_Y,
    CONF_BATH_HUMIDITY,
    CONF_CLIMATE,
    CONF_EXHAUST_FAN,
    CONF_HOUSE_HUMIDITY,
    CONF_HUMIDITY,
    CONF_SHOWER,
    CONF_CO2_SENSORS,
    CONF_FAN_ENTITY,
    CONF_STARTUP_DELAY,
    CONF_THERMOSTAT,
    DEFAULT_MIN_RUN,
    DEFAULT_OFF_SETPOINT,
    DEFAULT_ON_SETPOINT,
    DEFAULT_SPEED,
    DEFAULT_STARTUP_DELAY,
    FAN_CALLER_CO2,
    FAN_CALLER_OFF,
    FAN_CALLER_SHOWER,
    SPEED_BY_LEVEL,
    SPEED_LEVEL,
    THERMOSTAT_CALL_LEVEL,
    STATUS_DISABLED,
    STATUS_HOLDING,
    STATUS_IDLE,
    STATUS_MANUAL,
    STATUS_NO_DATA,
    STATUS_STARTING,
    STATUS_VENTILATING,
    SHOWER_KEYS,
    THERMOSTAT_KEYS,
)
from .humidity import MODE_HIGH, MODE_LOW, ShowerHumidity
from .runtime import FanRuntimeTracker

# How often to re-check the shower timers (minimum high time, maximum run).
SHOWER_TICK = timedelta(seconds=30)
# Cooling has to run this long without the heat strips before it counts, so
# a defrost cycle (which also energizes Y and O) never looks like cooling.
COOLING_MIN = timedelta(minutes=10)

_LOGGER = logging.getLogger(__name__)


class Co2VentilationController:
    """Runs the fan for CO2 and, optionally, for shower humidity.

    CO2: on above the on setpoint, off below the off setpoint (after the
    minimum run). Shower: on high when the bathroom is well above the house,
    low as it dries out, off when it's back near the house.

    When both want the fan it runs at the higher speed, and it only turns off
    when neither does. The fan is only turned off automatically if this
    controller turned it on, so a fan switched on by hand stays on.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self.on_setpoint: float = DEFAULT_ON_SETPOINT
        self.off_setpoint: float = DEFAULT_OFF_SETPOINT
        self.min_run_minutes: float = DEFAULT_MIN_RUN
        self.auto_enabled: bool = True
        self.speed: str = DEFAULT_SPEED

        self.ready = False
        self.max_co2: float | None = None
        self.max_source: str | None = None
        self.status: str = STATUS_STARTING

        self._we_turned_on = False
        # Why this controller is running the fan.
        self._co2_on = False
        self._hum_driving = False
        # Someone turned the fan off by hand during a shower: don't turn it
        # back on for this shower.
        self._hum_suppressed = False
        self._target_level: int | None = None
        # The Remote fan switch and speed, for remote/button automations.
        self.remote_on = False
        self.remote_speed: str = DEFAULT_SPEED
        self._exhaust_requested = False
        self.shower = ShowerHumidity()
        # When the air conditioning last ran (gates the bathroom exhaust fan).
        self.last_cooling: datetime | None = None
        self._cooling_since: datetime | None = None
        self._on_since: datetime | None = None
        self._pending_off: CALLBACK_TYPE | None = None
        self._startup_timer: CALLBACK_TYPE | None = None
        self._unsubs: list[CALLBACK_TYPE] = []
        self._listeners: list[Callable[[], None]] = []
        self.runtime = FanRuntimeTracker(hass, self._runtime_watched)

    # ----- configuration -------------------------------------------------

    def _conf(self, key: str, default: Any = None) -> Any:
        return self.entry.options.get(key, self.entry.data.get(key, default))

    @property
    def sensors(self) -> list[str]:
        return list(self._conf(CONF_CO2_SENSORS, []))

    @property
    def fan_entity(self) -> str:
        return self._conf(CONF_FAN_ENTITY)

    @property
    def startup_delay(self) -> float:
        return float(self._conf(CONF_STARTUP_DELAY, DEFAULT_STARTUP_DELAY))

    @property
    def thermostat(self) -> dict[str, str | None]:
        """Optional thermostat entities (Nest climate, sensors, 24 V call inputs)."""
        section = self._conf(CONF_THERMOSTAT) or {}
        return {key: section.get(key) or None for key in THERMOSTAT_KEYS}

    @property
    def g_label(self) -> str | None:
        """Custom name for a G-only call, or None for the default "Fan only"."""
        label = ((self._conf(CONF_THERMOSTAT) or {}).get(CONF_G_LABEL) or "").strip()
        return label or None

    @property
    def shower_config(self) -> dict[str, Any]:
        """Optional shower humidity entities. House humidity is a list (one
        or more sensors, averaged); older setups stored a single entity."""
        section = self._conf(CONF_SHOWER) or {}
        config: dict[str, Any] = {key: section.get(key) or None for key in SHOWER_KEYS}
        house = config[CONF_HOUSE_HUMIDITY]
        if isinstance(house, str):
            house = [house]
        config[CONF_HOUSE_HUMIDITY] = [e for e in (house or []) if e] or None
        return config

    @property
    def shower_configured(self) -> bool:
        return bool(self.shower_config[CONF_BATH_HUMIDITY])

    def house_humidity_sources(self) -> list[str]:
        """The house reference: the chosen sensors (averaged), else the
        thermostat's humidity."""
        chosen = self.shower_config[CONF_HOUSE_HUMIDITY]
        if chosen:
            return list(chosen)
        fallback = self.thermostat[CONF_HUMIDITY] or self.thermostat[CONF_CLIMATE]
        return [fallback] if fallback else []

    def house_humidity(self) -> float | None:
        """Average of the house sensors that have a reading right now."""
        readings = [
            v for v in (self._humidity_of(e) for e in self.house_humidity_sources()) if v is not None
        ]
        if not readings:
            return None
        return round(sum(readings) / len(readings), 1)

    def _humidity_of(self, entity_id: str | None) -> float | None:
        if not entity_id:
            return None
        state = self.hass.states.get(entity_id)
        if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
            return None
        raw = (
            state.attributes.get("current_humidity")
            if entity_id.startswith("climate.")
            else state.state
        )
        try:
            return float(raw)
        except (TypeError, ValueError):
            return None

    def humidity_diff(self) -> float | None:
        """Bathroom minus house, in humidity points."""
        bath = self._humidity_of(self.shower_config[CONF_BATH_HUMIDITY])
        house = self.house_humidity()
        if bath is None or house is None:
            return None
        return round(bath - house, 1)

    def _runtime_watched(self) -> list[str]:
        """Entities that mean the blower is running when any of them is on."""
        t = self.thermostat
        return [e for e in (t[CONF_CALL_G], t[CONF_CALL_W2], self.fan_entity) if e]

    # ----- listeners for entities ----------------------------------------

    @callback
    def add_listener(self, update: Callable[[], None]) -> CALLBACK_TYPE:
        self._listeners.append(update)

        @callback
        def remove() -> None:
            self._listeners.remove(update)

        return remove

    @callback
    def _notify(self) -> None:
        for update in list(self._listeners):
            update()

    # ----- lifecycle -----------------------------------------------------

    async def async_start(self) -> None:
        """Start tracking. Call after the entities have restored their state."""
        watched = [*self.sensors, self.fan_entity]
        if self.shower_configured:
            watched += [self.shower_config[CONF_BATH_HUMIDITY], *self.house_humidity_sources()]
            if self.shower_config[CONF_EXHAUST_FAN]:
                # Watch for cooling, which decides whether the exhaust may run.
                t = self.thermostat
                watched += [
                    e
                    for e in (t[CONF_CALL_Y], t[CONF_CALL_OB], t[CONF_CALL_W2], t[CONF_CLIMATE])
                    if e
                ]
            self._unsubs.append(
                async_track_time_interval(self.hass, self._shower_tick, SHOWER_TICK)
            )
        self._unsubs.append(
            async_track_state_change_event(
                self.hass, list(dict.fromkeys(watched)), self._handle_state_change
            )
        )

        if self.hass.state is CoreState.running:
            # Integration added or reloaded while Home Assistant is running:
            # adopt whatever the fan is doing now.
            fan = self.hass.states.get(self.fan_entity)
            if fan is not None and fan.state == STATE_ON:
                self._we_turned_on = True
                self._co2_on = True
                self._on_since = fan.last_changed
            self.ready = True
            self.evaluate()
        else:
            # Home Assistant is booting: wait for sensors to report, then
            # default the fan to off unless CO2 is already high.
            self._unsubs.append(async_at_started(self.hass, self._on_started))
        self.runtime.async_start()
        self._recompute()
        self._update_status()
        self._notify()

    @callback
    def async_stop(self) -> None:
        self.runtime.async_stop()
        self._cancel_pending_off()
        if self._startup_timer:
            self._startup_timer()
            self._startup_timer = None
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    @callback
    def _on_started(self, hass: HomeAssistant) -> None:
        self._startup_timer = async_call_later(
            hass, self.startup_delay, self._startup_check
        )

    @callback
    def _startup_check(self, _now: datetime) -> None:
        self._startup_timer = None
        self.ready = True
        self._recompute()
        self._update_shower()
        self._co2_on = bool(
            self.auto_enabled
            and self.max_co2 is not None
            and self.max_co2 >= self.on_setpoint
        )
        if self._co2_on:
            _LOGGER.debug("Startup: CO2 %s is high, fan on", self.max_co2)
            self._we_turned_on = False  # take it over below
        if self._co2_on or self._shower_level() or self.remote_on:
            self._apply(force=True)
        elif self.auto_enabled:
            _LOGGER.debug("Startup: defaulting fan off")
            self._turn_fan(False)
        self._update_status()
        self._notify()

    # ----- state handling ------------------------------------------------

    @callback
    def _handle_state_change(self, event: Event[EventStateChangedData]) -> None:
        entity_id = event.data["entity_id"]
        new_state = event.data["new_state"]
        old_state = event.data["old_state"]

        if entity_id == self.fan_entity:
            was_on = old_state is not None and old_state.state == STATE_ON
            is_on = new_state is not None and new_state.state == STATE_ON
            if is_on and not was_on:
                self._on_since = new_state.last_changed
            elif was_on and not is_on:
                # Turned off (by hand or anything else): the remote request
                # ends too, so the Remote fan switch goes off with it.
                self.remote_on = False
                if self.shower.active:
                    # Turned off during a shower: leave it off for this shower.
                    self._hum_suppressed = True
                self._we_turned_on = False
                self._co2_on = False
                self._hum_driving = False
                self._target_level = None
                self._on_since = None
                self._cancel_pending_off()

        self.evaluate()

    def fan_caller(self) -> str:
        """Who has the fan on: the remote switch, CO2, shower, by hand, or off."""
        if not self._fan_is_on():
            return FAN_CALLER_OFF
        if not self._we_turned_on:
            return CALLER_MANUAL
        if self.remote_on:
            return CALLER_REMOTE
        if self._hum_driving and not self._co2_on:
            return FAN_CALLER_SHOWER
        return FAN_CALLER_CO2

    @callback
    def _recompute(self) -> None:
        best: float | None = None
        source: str | None = None
        for entity_id in self.sensors:
            state = self.hass.states.get(entity_id)
            if state is None or state.state in (STATE_UNKNOWN, STATE_UNAVAILABLE):
                continue
            try:
                value = float(state.state)
            except ValueError:
                continue
            if best is None or value > best:
                best, source = value, entity_id
        self.max_co2 = best
        self.max_source = source

    def _fan_is_on(self) -> bool:
        state = self.hass.states.get(self.fan_entity)
        return state is not None and state.state == STATE_ON

    def _fan_speed_count(self) -> int:
        """How many speeds the fan has (0 = not a multi-speed fan)."""
        if not self.fan_entity or not self.fan_entity.startswith("fan."):
            return 0
        state = self.hass.states.get(self.fan_entity)
        if state is None:
            return 0
        step = state.attributes.get("percentage_step")
        try:
            step = float(step)
        except (TypeError, ValueError):
            return 0
        if step <= 0 or step >= 100:
            return 0
        return max(1, round(100 / step))

    @property
    def speed_supported(self) -> bool:
        return self._fan_speed_count() > 1

    def _fan_level(self) -> int | None:
        """Which speed (1..N) the fan is running at, from its percentage."""
        if not self._fan_is_on():
            return None
        count = self._fan_speed_count()
        if count <= 1:
            return None
        state = self.hass.states.get(self.fan_entity)
        try:
            pct = float(state.attributes.get("percentage"))
        except (TypeError, ValueError):
            return None
        if pct <= 0:
            return None
        return max(1, min(count, round(pct * count / 100)))

    def _call_on(self, key: str) -> bool:
        entity_id = self.thermostat.get(key)
        if not entity_id:
            return False
        state = self.hass.states.get(entity_id)
        return state is not None and state.state == STATE_ON

    def hvac_activity(self) -> dict[str, Any]:
        """What the HVAC is doing, who asked for it, and the blower speed.

        Thermostat calls come from the 24 V inputs; the ventilation fan was
        turned on either by this integration (CO2) or by hand (manual).
        """
        g, y = self._call_on(CONF_CALL_G), self._call_on(CONF_CALL_Y)
        o, w2 = self._call_on(CONF_CALL_OB), self._call_on(CONF_CALL_W2)
        fan_on = self._fan_is_on()
        we_did = fan_on and self._we_turned_on

        if y and o and w2:
            activity = ACTIVITY_DEFROST
        elif y and w2:
            activity = ACTIVITY_HEAT_PUMP_AUX
        elif w2:
            activity = ACTIVITY_AUX_HEAT
        elif y and o:
            activity = ACTIVITY_COOLING
        elif y:
            activity = ACTIVITY_HEAT_PUMP
        elif g:
            activity = ACTIVITY_FAN_ONLY
        elif fan_on:
            if not we_did:
                activity = ACTIVITY_FAN_MANUAL
            elif self.remote_on:
                activity = ACTIVITY_FAN_REMOTE
            else:
                activity = ACTIVITY_VENTILATING
        else:
            activity = ACTIVITY_IDLE

        called_by: list[str] = []
        if g or y or w2:
            called_by.append(CALLER_THERMOSTAT)
        if fan_on:
            if not we_did:
                called_by.append(CALLER_MANUAL)
            else:
                if self.remote_on:
                    called_by.append(CALLER_REMOTE)
                if self._co2_on or not (self._hum_driving or self.remote_on):
                    called_by.append(CALLER_CO2)
                if self._hum_driving:
                    called_by.append(CALLER_HUMIDITY)

        # The motor runs the highest tap that's energized.
        levels = []
        if g or y:
            levels.append(THERMOSTAT_CALL_LEVEL)
        if w2:
            levels.append(AUX_HEAT_LEVEL)
        fan_level = self._fan_level()
        if fan_level:
            levels.append(fan_level)
        elif fan_on:
            levels.append(1)
        level = max(levels) if levels else None

        climate = self.thermostat.get(CONF_CLIMATE)
        climate_state = self.hass.states.get(climate) if climate else None
        return {
            "activity": activity,
            "called_by": called_by,
            "thermostat_name": climate_state.name if climate_state else None,
            "g_label": self.g_label,
            "ventilating": we_did,
            "fan_speed": SPEED_BY_LEVEL.get(level) if level else None,
            "fan_level": level,
            "calls": {"g": g, "y": y, "o": o, "w2": w2},
            "co2_source": self.max_source if we_did and CALLER_CO2 in called_by else None,
            "co2_ppm": self.max_co2 if we_did and CALLER_CO2 in called_by else None,
            "humidity_diff": self.shower.diff if self.shower_configured else None,
            "shower_mode": self.shower.mode if self.shower_configured else None,
        }

    def speed_percentage(self) -> int | None:
        """Fan percentage for the selected speed, or None if not a speed fan."""
        count = self._fan_speed_count()
        if count <= 1:
            return None
        level = min(SPEED_LEVEL.get(self.speed, 1), count)
        return ranged_value_to_percentage((1, count), level)

    @callback
    def evaluate(self) -> None:
        """Decide what the fan should do now."""
        self._recompute()
        if self.ready:
            self._update_shower()
            self._decide_co2()
            self._apply()
        self._update_status()
        self._notify()

    @callback
    def _decide_co2(self) -> None:
        """Does CO2 want the fan? Keeps hysteresis and the minimum run."""
        if self.auto_enabled and self.max_co2 is not None:
            if self.max_co2 >= self.on_setpoint:
                self._cancel_pending_off()
                self._co2_on = True
            elif self.max_co2 < self.off_setpoint:
                if self._co2_on:
                    remaining = self.min_run_remaining() if self._fan_is_on() else 0
                    if remaining <= 0:
                        self._co2_on = False
                        self._cancel_pending_off()
                    elif self._pending_off is None:
                        self._pending_off = async_call_later(
                            self.hass, remaining, self._pending_off_fired
                        )
            else:
                # Between the setpoints: keep doing what we're doing.
                self._cancel_pending_off()
        elif not self.auto_enabled:
            self._cancel_pending_off()

    @callback
    def _update_shower(self) -> None:
        if not self.shower_configured:
            return
        now = dt_util.utcnow()
        self._track_cooling(now)
        self.shower.update(self.humidity_diff(), now)
        if not self.shower.active:
            self._hum_suppressed = False
        self._apply_exhaust()

    @callback
    def _track_cooling(self, now: datetime) -> None:
        """Record cooling once it has run COOLING_MIN without a break."""
        if not self.shower_config[CONF_EXHAUST_FAN]:
            return
        if not self._cooling_now():
            self._cooling_since = None
            return
        if self._cooling_since is None:
            self._cooling_since = now
        if now - self._cooling_since >= COOLING_MIN:
            self.last_cooling = now

    def _cooling_now(self) -> bool:
        """Is the air conditioning running? From the 24 V calls, else the thermostat.

        Y + O alone is cooling; Y + O with W2 is a defrost cycle.
        """
        if self.thermostat[CONF_CALL_Y] and self.thermostat[CONF_CALL_OB]:
            return (
                self._call_on(CONF_CALL_Y)
                and self._call_on(CONF_CALL_OB)
                and not self._call_on(CONF_CALL_W2)
            )
        climate = self.thermostat[CONF_CLIMATE]
        state = self.hass.states.get(climate) if climate else None
        return state is not None and state.attributes.get("hvac_action") == "cooling"

    def exhaust_allowed(self) -> bool:
        """The exhaust fan may start only if cooling ran recently."""
        if self.last_cooling is None:
            return False
        window = timedelta(days=self.shower.settings.exhaust_cooling_days)
        return dt_util.utcnow() - self.last_cooling <= window

    def _shower_level(self) -> int | None:
        """Fan speed the shower wants: top speed on high, speed 1 on low."""
        if not self.shower_configured or self._hum_suppressed:
            return None
        if self.shower.mode == MODE_HIGH:
            return max(self._fan_speed_count(), 1)
        if self.shower.mode == MODE_LOW:
            return 1
        return None

    @callback
    def _apply(self, force: bool = False) -> None:
        """Run the fan at the highest speed anything wants, or turn it off."""
        levels: list[int] = []
        if self._co2_on:
            levels.append(SPEED_LEVEL.get(self.speed, 1))
        shower = self._shower_level()
        if shower:
            levels.append(shower)
        if self.remote_on:
            levels.append(SPEED_LEVEL.get(self.remote_speed, 1))
        fan_on = self._fan_is_on()

        if levels:
            target = max(levels)
            if not fan_on:
                self._hum_driving = bool(shower)
                self._turn_fan(True, target)
            elif self._we_turned_on:
                self._hum_driving = bool(shower)
                if target != self._target_level:
                    self._set_level(target)
            elif self.remote_on:
                # The remote asked for it: take the fan over at its speed.
                self._we_turned_on = True
                self._hum_driving = bool(shower)
                self._set_level(target)
            elif self._co2_on and not shower:
                # Already running by hand: take over so it shuts off once CO2
                # is back down, but leave its speed alone.
                self._we_turned_on = True
                self._target_level = self._fan_level()
            elif force:
                self._we_turned_on = True
                self._hum_driving = bool(shower)
                self._set_level(target)
            # Otherwise a fan someone turned on by hand is left as it is.
        elif fan_on and self._we_turned_on:
            self._turn_fan(False)
        else:
            self._hum_driving = False

    @callback
    def _apply_exhaust(self) -> None:
        """Run the bathroom exhaust fan for the shower, in cooling season only.

        It starts only if the air conditioning ran within the cooling window;
        once started it runs to the end of that shower.
        """
        exhaust = self.shower_config[CONF_EXHAUST_FAN]
        if not exhaust:
            return
        want = self.shower.active and (self._exhaust_requested or self.exhaust_allowed())
        if want == self._exhaust_requested:
            return
        self._exhaust_requested = want
        state = self.hass.states.get(exhaust)
        if want and (state is None or state.state != STATE_ON):
            service = "turn_on"
        elif not want and state is not None and state.state == STATE_ON:
            service = "turn_off"
        else:
            return
        self.hass.async_create_task(
            self.hass.services.async_call(
                "homeassistant", service, {"entity_id": exhaust}, blocking=True
            ),
            eager_start=True,
        )

    @callback
    def _shower_tick(self, now: datetime) -> None:
        if self.shower.mode != "off":
            self.evaluate()
        elif self._cooling_since is not None:
            # A long cooling run has no state changes; check its length here.
            had = self.last_cooling
            self._track_cooling(dt_util.utcnow())
            if self.last_cooling != had:
                self._notify()

    def min_run_remaining(self) -> float:
        """Seconds left before the fan may be turned off."""
        if self._on_since is None:
            return 0
        ran = (dt_util.utcnow() - self._on_since).total_seconds()
        return max(self.min_run_minutes * 60 - ran, 0)

    @callback
    def _pending_off_fired(self, _now: datetime) -> None:
        self._pending_off = None
        self.evaluate()

    @callback
    def _cancel_pending_off(self) -> None:
        if self._pending_off is not None:
            self._pending_off()
            self._pending_off = None

    def _level_percentage(self, level: int) -> int | None:
        count = self._fan_speed_count()
        if count <= 1:
            return None
        return ranged_value_to_percentage((1, count), min(max(level, 1), count))

    @callback
    def _set_level(self, level: int) -> None:
        self._target_level = level
        percentage = self._level_percentage(level)
        if percentage is None:
            return
        self.hass.async_create_task(
            self.hass.services.async_call(
                "fan",
                "set_percentage",
                {"entity_id": self.fan_entity, "percentage": percentage},
                blocking=True,
            ),
            eager_start=True,
        )

    @callback
    def _turn_fan(self, on: bool, level: int | None = None) -> None:
        if on:
            self._we_turned_on = True
            if not self._fan_is_on():
                self._on_since = dt_util.utcnow()
            if level is None:
                level = SPEED_LEVEL.get(self.speed, 1)
            self._target_level = level
        else:
            self._we_turned_on = False
            self._co2_on = False
            self._hum_driving = False
            self._target_level = None
            self._cancel_pending_off()

        percentage = self._level_percentage(level) if on else None
        if percentage is not None:
            # Multi-speed fan: run it at the selected ventilation speed.
            call = self.hass.services.async_call(
                "fan",
                "turn_on",
                {"entity_id": self.fan_entity, "percentage": percentage},
                blocking=True,
            )
        else:
            call = self.hass.services.async_call(
                "homeassistant",
                "turn_on" if on else "turn_off",
                {"entity_id": self.fan_entity},
                blocking=True,
            )
        self.hass.async_create_task(call, eager_start=True)

    @callback
    def _update_status(self) -> None:
        if not self.ready:
            self.status = STATUS_STARTING
        elif not self.auto_enabled:
            self.status = STATUS_DISABLED
        elif self._fan_is_on():
            if not self._we_turned_on:
                self.status = STATUS_MANUAL
            elif self._pending_off is not None:
                self.status = STATUS_HOLDING
            else:
                self.status = STATUS_VENTILATING
        elif self.max_co2 is None:
            self.status = STATUS_NO_DATA
        else:
            self.status = STATUS_IDLE

    # ----- setters used by the entities ----------------------------------

    @callback
    def set_speed(self, speed: str) -> None:
        """Pick the CO2 ventilation speed; applies right away if CO2 is running the fan."""
        self.speed = speed
        if self.ready and self._we_turned_on and self._fan_is_on():
            self._apply()
        self._notify()

    @callback
    def set_remote(self, on: bool | None = None, speed: str | None = None) -> None:
        """Remote fan switch and speed, for button/remote automations.

        On runs the fan at the remote speed (or higher if CO2 or the shower
        want more); off turns it off unless CO2 or the shower still need it.
        """
        if speed is not None:
            self.remote_speed = speed
        if on is not None:
            self.remote_on = on
        self.evaluate()

    @callback
    def set_shower_enabled(self, enabled: bool) -> None:
        self.shower.enabled = enabled
        self.evaluate()

    @callback
    def set_shower_settings(self, **values: float) -> None:
        for key, value in values.items():
            setattr(self.shower.settings, key, value)
        self.evaluate()

    @callback
    def set_auto_enabled(self, enabled: bool) -> None:
        self.auto_enabled = enabled
        self.evaluate()

    @callback
    def set_setpoints(
        self,
        on_setpoint: float | None = None,
        off_setpoint: float | None = None,
        min_run_minutes: float | None = None,
    ) -> None:
        if on_setpoint is not None:
            self.on_setpoint = on_setpoint
        if off_setpoint is not None:
            self.off_setpoint = off_setpoint
        if min_run_minutes is not None:
            self.min_run_minutes = min_run_minutes
            # Re-plan any pending shutoff with the new minimum.
            self._cancel_pending_off()
        self.evaluate()
