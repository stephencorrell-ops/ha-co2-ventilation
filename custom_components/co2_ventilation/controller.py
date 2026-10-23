"""Ventilation logic: runs a fan from the highest CO2 reading."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
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
)
from homeassistant.helpers.start import async_at_started
from homeassistant.util import dt as dt_util

from .const import (
    CONF_CO2_SENSORS,
    CONF_FAN_ENTITY,
    CONF_STARTUP_DELAY,
    DEFAULT_MIN_RUN,
    DEFAULT_OFF_SETPOINT,
    DEFAULT_ON_SETPOINT,
    DEFAULT_STARTUP_DELAY,
    STATUS_DISABLED,
    STATUS_HOLDING,
    STATUS_IDLE,
    STATUS_MANUAL,
    STATUS_NO_DATA,
    STATUS_STARTING,
    STATUS_VENTILATING,
)

_LOGGER = logging.getLogger(__name__)


class Co2VentilationController:
    """Turns the fan on above the on setpoint and off below the off setpoint.

    The fan is only turned off automatically if this controller turned it on,
    so a fan someone switches on by hand stays on until they switch it off.
    """

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        self.hass = hass
        self.entry = entry

        self.on_setpoint: float = DEFAULT_ON_SETPOINT
        self.off_setpoint: float = DEFAULT_OFF_SETPOINT
        self.min_run_minutes: float = DEFAULT_MIN_RUN
        self.auto_enabled: bool = True

        self.ready = False
        self.max_co2: float | None = None
        self.max_source: str | None = None
        self.status: str = STATUS_STARTING

        self._we_turned_on = False
        self._on_since: datetime | None = None
        self._pending_off: CALLBACK_TYPE | None = None
        self._startup_timer: CALLBACK_TYPE | None = None
        self._unsubs: list[CALLBACK_TYPE] = []
        self._listeners: list[Callable[[], None]] = []

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
        self._unsubs.append(
            async_track_state_change_event(
                self.hass, [*self.sensors, self.fan_entity], self._handle_state_change
            )
        )

        if self.hass.state is CoreState.running:
            # Integration added or reloaded while Home Assistant is running:
            # adopt whatever the fan is doing now.
            fan = self.hass.states.get(self.fan_entity)
            if fan is not None and fan.state == STATE_ON:
                self._we_turned_on = True
                self._on_since = fan.last_changed
            self.ready = True
            self.evaluate()
        else:
            # Home Assistant is booting: wait for sensors to report, then
            # default the fan to off unless CO2 is already high.
            self._unsubs.append(async_at_started(self.hass, self._on_started))
        self._recompute()
        self._update_status()
        self._notify()

    @callback
    def async_stop(self) -> None:
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
        if self.auto_enabled:
            if self.max_co2 is not None and self.max_co2 >= self.on_setpoint:
                _LOGGER.debug("Startup: CO2 %s is high, fan on", self.max_co2)
                self._turn_fan(True)
            else:
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
                self._we_turned_on = False
                self._on_since = None
                self._cancel_pending_off()

        self.evaluate()

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

    @callback
    def evaluate(self) -> None:
        """Decide what the fan should do now."""
        self._recompute()

        if self.ready and self.auto_enabled and self.max_co2 is not None:
            fan_on = self._fan_is_on()
            if self.max_co2 >= self.on_setpoint:
                self._cancel_pending_off()
                if not fan_on:
                    self._turn_fan(True)
                else:
                    # Already running (maybe by hand): take over so it shuts
                    # off once CO2 is back down.
                    self._we_turned_on = True
            elif self.max_co2 < self.off_setpoint:
                if fan_on and self._we_turned_on:
                    remaining = self.min_run_remaining()
                    if remaining <= 0:
                        self._turn_fan(False)
                    elif self._pending_off is None:
                        self._pending_off = async_call_later(
                            self.hass, remaining, self._pending_off_fired
                        )
            else:
                # Between the setpoints: keep doing what we're doing.
                self._cancel_pending_off()
        elif not self.auto_enabled:
            self._cancel_pending_off()

        self._update_status()
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

    @callback
    def _turn_fan(self, on: bool) -> None:
        if on:
            self._we_turned_on = True
            if not self._fan_is_on():
                self._on_since = dt_util.utcnow()
        else:
            self._we_turned_on = False
            self._cancel_pending_off()
        self.hass.async_create_task(
            self.hass.services.async_call(
                "homeassistant",
                "turn_on" if on else "turn_off",
                {"entity_id": self.fan_entity},
                blocking=True,
            ),
            eager_start=True,
        )

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
