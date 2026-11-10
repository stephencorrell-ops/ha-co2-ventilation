"""Shower humidity: run the fan when the bathroom is much more humid than the house."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta

# What the shower logic wants from the fan.
MODE_OFF = "off"
MODE_HIGH = "high"
MODE_LOW = "low"
# Hit the maximum run time; waits for the bathroom to dry out before it can
# start again, so a stuck sensor can't run the fan all night.
MODE_LOCKOUT = "lockout"
MODES = [MODE_OFF, MODE_HIGH, MODE_LOW, MODE_LOCKOUT]

DEFAULT_ON_DELTA = 10.0
DEFAULT_HIGH_UNTIL = 20.0
DEFAULT_OFF_DELTA = 5.0
DEFAULT_MAX_RUN = 90.0  # minutes
# The bathroom exhaust fan only runs if the air conditioning has run within
# this many days: in heating season the shower's moisture is left in the
# house to help the humidifier.
DEFAULT_EXHAUST_COOLING_DAYS = 7.0
EXHAUST_COOLING_DAYS_MAX = 60.0
DELTA_MAX = 50.0
MAX_RUN_MAX = 240.0
# Stay on high at least this long, so a short shower that peaks below the
# "high until" point doesn't drop straight to low.
MIN_HIGH = timedelta(minutes=5)
# From low, go back to high only if the bathroom climbs this far past
# "high until" (a second shower), so it doesn't flicker around the line.
REHIGH_MARGIN = 5.0


@dataclass
class ShowerSettings:
    on_delta: float = DEFAULT_ON_DELTA
    high_until: float = DEFAULT_HIGH_UNTIL
    off_delta: float = DEFAULT_OFF_DELTA
    max_run_minutes: float = DEFAULT_MAX_RUN
    exhaust_cooling_days: float = DEFAULT_EXHAUST_COOLING_DAYS


class ShowerHumidity:
    """Off -> high above +on; high -> low below +high_until; off below +off.

    Differences are in humidity points: bathroom 52 % against a house at
    40 % is +12.
    """

    def __init__(self) -> None:
        self.settings = ShowerSettings()
        self.enabled = True
        self.mode = MODE_OFF
        self.diff: float | None = None
        self.started: datetime | None = None
        self._high_since: datetime | None = None

    @property
    def active(self) -> bool:
        return self.mode in (MODE_HIGH, MODE_LOW)

    def run_remaining(self, now: datetime) -> float | None:
        """Minutes left before the maximum run time stops it."""
        if not self.active or self.started is None:
            return None
        left = self.settings.max_run_minutes - (now - self.started).total_seconds() / 60
        return max(left, 0.0)

    def update(self, diff: float | None, now: datetime) -> str:
        """Feed in the latest bathroom-minus-house difference; returns the mode."""
        s = self.settings
        self.diff = diff

        if not self.enabled or diff is None:
            # Turned off, or a sensor went unavailable: stop.
            self._stop()
            return self.mode

        if self.mode == MODE_LOCKOUT:
            if diff < s.off_delta:
                self._stop()
            return self.mode

        if self.active and self.started is not None:
            if now - self.started >= timedelta(minutes=s.max_run_minutes):
                self.mode = MODE_LOCKOUT
                self.started = None
                self._high_since = None
                return self.mode

        if self.mode == MODE_OFF:
            if diff >= s.on_delta:
                self.mode = MODE_HIGH
                self.started = now
                self._high_since = now
        elif self.mode == MODE_HIGH:
            if diff < s.off_delta:
                self._stop()
            elif diff < s.high_until and now - (self._high_since or now) >= MIN_HIGH:
                self.mode = MODE_LOW
        elif self.mode == MODE_LOW:
            if diff < s.off_delta:
                self._stop()
            elif diff >= s.high_until + REHIGH_MARGIN:
                self.mode = MODE_HIGH
                self._high_since = now
        return self.mode

    def _stop(self) -> None:
        self.mode = MODE_OFF
        self.started = None
        self._high_since = None
