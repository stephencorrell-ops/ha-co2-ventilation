"""Counts how long the HVAC blower has run: since the last filter change, and in total."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta

from homeassistant.const import STATE_ON
from homeassistant.core import CALLBACK_TYPE, HomeAssistant, callback
from homeassistant.helpers.event import (
    async_track_state_change_event,
    async_track_time_interval,
)
from homeassistant.util import dt as dt_util

TICK = timedelta(minutes=1)


class FanRuntimeTracker:
    """The blower is running when any of the watched entities is on.

    Watched: the thermostat's fan call (G) and heat-strip call (W2), which run
    the blower on their own, plus the fan this integration controls. If no
    thermostat inputs are configured, only the controlled fan is counted.
    """

    def __init__(self, hass: HomeAssistant, watched: Callable[[], list[str]]) -> None:
        self.hass = hass
        self._watched = watched
        self.filter_seconds: float = 0.0
        self.total_seconds: float = 0.0
        self.filter_reset_at: datetime | None = None
        self._last_tick: datetime | None = None
        self._unsubs: list[CALLBACK_TYPE] = []
        self._listeners: list[Callable[[], None]] = []

    # ----- state -----------------------------------------------------------

    @property
    def running(self) -> bool:
        for entity_id in self._watched():
            state = self.hass.states.get(entity_id)
            if state is not None and state.state == STATE_ON:
                return True
        return False

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

    # ----- lifecycle -------------------------------------------------------

    @callback
    def async_start(self) -> None:
        watched = [e for e in self._watched() if e]
        if watched:
            self._unsubs.append(
                async_track_state_change_event(self.hass, watched, self._changed)
            )
        self._unsubs.append(async_track_time_interval(self.hass, self._tick, TICK))
        self._last_tick = dt_util.utcnow() if self.running else None
        self._notify()

    @callback
    def async_stop(self) -> None:
        self._accumulate()
        for unsub in self._unsubs:
            unsub()
        self._unsubs.clear()

    # ----- counting --------------------------------------------------------

    @callback
    def _accumulate(self) -> None:
        now = dt_util.utcnow()
        if self._last_tick is not None:
            elapsed = max((now - self._last_tick).total_seconds(), 0)
            self.filter_seconds += elapsed
            self.total_seconds += elapsed
        self._last_tick = now if self.running else None

    @callback
    def _changed(self, _event) -> None:
        # Close out time up to now under the old state, then start (or stop)
        # counting from now under the new one.
        was_counting = self._last_tick is not None
        self._accumulate()
        if was_counting != (self._last_tick is not None):
            self._notify()

    @callback
    def _tick(self, _now: datetime) -> None:
        if self._last_tick is not None:
            self._accumulate()
            self._notify()

    @callback
    def reset_filter(self) -> None:
        self._accumulate()
        self.filter_seconds = 0.0
        self.filter_reset_at = dt_util.utcnow()
        self._notify()
