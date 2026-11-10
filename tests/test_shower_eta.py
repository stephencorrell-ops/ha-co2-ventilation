"""Shower peak and time-to-off estimate."""

from datetime import datetime, timedelta, timezone
import math

from custom_components.co2_ventilation.humidity import ShowerHumidity

T0 = datetime(2026, 11, 9, 7, 0, tzinfo=timezone.utc)


def _feed(sh: ShowerHumidity, values, start=T0, step=0.5):
    t = start
    for v in values:
        sh.update(v, t)
        t += timedelta(minutes=step)
    return t - timedelta(minutes=step)


def test_peak_tracks_and_clears():
    sh = ShowerHumidity()
    last = _feed(sh, [12, 20, 28, 25, 18])
    assert sh.peak == 28
    assert sh.active
    sh.update(3, last + timedelta(minutes=1))
    assert sh.mode == "off"
    assert sh.peak is None


def test_no_estimate_while_rising():
    sh = ShowerHumidity()
    last = _feed(sh, [12, 15, 18, 21, 24, 27, 30, 32])
    assert sh.eta_off(last) is None


def test_estimate_on_exponential_drying():
    sh = ShowerHumidity()
    sh.settings.max_run_minutes = 240
    # Dries as 30 * e^(-0.05 t): reaches the 5-point off mark at ln(6)/0.05 = 35.8 min.
    values = [30 * math.exp(-0.05 * m * 0.5) for m in range(13)]  # 6 minutes
    last = _feed(sh, values)
    eta = sh.eta_off(last)
    expected = math.log(values[-1] / 5) / 0.05
    assert eta is not None and abs(eta - expected) < 0.5


def test_estimate_capped_by_max_run():
    sh = ShowerHumidity()
    sh.settings.max_run_minutes = 20
    values = [30 * math.exp(-0.01 * m * 0.5) for m in range(13)]  # very slow drying
    last = _feed(sh, values)
    assert abs(sh.eta_off(last) - (20 - 6)) < 0.01
