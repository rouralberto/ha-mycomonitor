"""Environmental indicators derived from a `DailySeries`.

All windows are inclusive of their end date: a 7-day window ending on the
7th covers the 1st to the 7th. Ending a window today includes today's
(partly forecast) value; the indicator's `kinds` says so.

Missing data never gets silently filled in: sums need every day of the
window, means and extremes need `min_coverage` of it, otherwise the value is
None. See docs/indicators.md for definitions and references.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, timedelta

from .models import UNITS, DailySeries, DataKind, Reading, Variable

WET_DAY_MM = 1.0  # ETCCDI wet day: precipitation >= 1 mm
FROST_DAY_C = 0.0  # ETCCDI frost day: minimum temperature < 0 °C
API_DECAY = 0.9  # daily decay of the antecedent precipitation index
DEFAULT_MIN_COVERAGE = 0.8
RUN_CAP_DAYS = 60  # longest dry spell / wet streak we look back for


@dataclass(frozen=True, slots=True)
class Indicator:
    """A derived value with the window and data it was computed from."""

    key: str
    value: float | None
    unit: str | None
    start: date
    end: date
    coverage: float
    kinds: frozenset[DataKind]

    @property
    def available(self) -> bool:
        """Whether there was enough data to compute a value."""
        return self.value is not None


def _make(
    key: str,
    value: float | None,
    unit: str | None,
    end: date,
    days: int,
    readings: list[Reading | None],
) -> Indicator:
    present = [r for r in readings if r is not None]
    return Indicator(
        key=key,
        value=value,
        unit=unit,
        start=end - timedelta(days=days - 1),
        end=end,
        coverage=len(present) / len(readings) if readings else 0.0,
        kinds=frozenset(r.source.kind for r in present),
    )


def rolling_sum(
    series: DailySeries, variable: Variable, end: date, days: int, key: str
) -> Indicator:
    """Sum over the window; None unless every day has data."""
    readings = series.window(variable, end, days)
    complete = all(r is not None for r in readings)
    value = sum(r.value for r in readings if r is not None) if complete else None
    return _make(key, value, UNITS[variable], end, days, readings)


def _aggregate(
    series: DailySeries,
    variable: Variable,
    end: date,
    days: int,
    key: str,
    func: Callable[[list[float]], float],
    min_coverage: float,
) -> Indicator:
    readings = series.window(variable, end, days)
    values = [r.value for r in readings if r is not None]
    value = func(values) if values and len(values) / days >= min_coverage else None
    return _make(key, value, UNITS[variable], end, days, readings)


def rolling_mean(
    series: DailySeries,
    variable: Variable,
    end: date,
    days: int,
    key: str,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> Indicator:
    """Mean of the available days, if they cover `min_coverage` of the window."""
    return _aggregate(series, variable, end, days, key, lambda v: sum(v) / len(v), min_coverage)


def rolling_min(
    series: DailySeries,
    variable: Variable,
    end: date,
    days: int,
    key: str,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> Indicator:
    """Lowest value in the window."""
    return _aggregate(series, variable, end, days, key, min, min_coverage)


def rolling_max(
    series: DailySeries,
    variable: Variable,
    end: date,
    days: int,
    key: str,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> Indicator:
    """Highest value in the window."""
    return _aggregate(series, variable, end, days, key, max, min_coverage)


def count_days(
    series: DailySeries,
    variable: Variable,
    end: date,
    days: int,
    key: str,
    predicate: Callable[[float], bool],
) -> Indicator:
    """Number of days meeting `predicate`; None unless every day has data."""
    readings = series.window(variable, end, days)
    complete = all(r is not None for r in readings)
    value = (
        float(sum(1 for r in readings if r is not None and predicate(r.value)))
        if complete
        else None
    )
    return _make(key, value, "d", end, days, readings)


def trailing_run(
    series: DailySeries,
    variable: Variable,
    end: date,
    key: str,
    predicate: Callable[[float], bool],
    cap: int = RUN_CAP_DAYS,
) -> Indicator:
    """Consecutive days up to and including `end` that meet `predicate`.

    Stops at the first day that fails (or has no data). Reaching `cap` returns
    `cap`, meaning "at least". None if `end` itself has no data.
    """
    readings = series.window(variable, end, cap)
    if readings[-1] is None:
        return _make(key, None, "d", end, 1, readings[-1:])
    run = 0
    for reading in reversed(readings):
        if reading is None or not predicate(reading.value):
            break
        run += 1
    window = max(run, 1)
    return _make(key, float(run), "d", end, window, readings[-window:])


def antecedent_precipitation_index(
    series: DailySeries, end: date, days: int = 30, k: float = API_DECAY, key: str = "api_30d"
) -> Indicator:
    """API = sum of P(end - i) * k^i for i in 0..days-1 (Kohler & Linsley, 1951).

    Recent rain counts more than older rain; with k = 0.9, rain 7 days ago
    weighs about half as much as today's. None unless every day has data.
    """
    readings = series.window(Variable.PRECIPITATION, end, days)
    complete = all(r is not None for r in readings)
    value = (
        sum(r.value * k**age for age, r in enumerate(reversed(readings)) if r is not None)
        if complete
        else None
    )
    return _make(key, value, "mm", end, days, readings)


def water_balance(series: DailySeries, end: date, days: int, key: str) -> Indicator:
    """Climatic water balance: sum of (precipitation - ET0) over the window.

    Negative means the atmosphere demanded more water than fell (Ágreda et
    al., 2015 found this a better predictor of fungal yield than rain alone).
    None unless both variables cover every day.
    """
    rain = series.window(Variable.PRECIPITATION, end, days)
    et0 = series.window(Variable.ET0, end, days)
    pairs = [(p, e) for p, e in zip(rain, et0, strict=True) if p is not None and e is not None]
    value = sum(p.value - e.value for p, e in pairs) if len(pairs) == days else None
    return Indicator(
        key=key,
        value=value,
        unit="mm",
        start=end - timedelta(days=days - 1),
        end=end,
        coverage=len(pairs) / days,
        kinds=frozenset(r.source.kind for r in rain + et0 if r is not None),
    )


def trend(
    series: DailySeries,
    variable: Variable,
    end: date,
    days: int,
    key: str,
    min_coverage: float = DEFAULT_MIN_COVERAGE,
) -> Indicator:
    """Least-squares slope over the window, expressed as change per 7 days."""
    readings = series.window(variable, end, days)
    points = [(x, r.value) for x, r in enumerate(readings) if r is not None]
    value: float | None = None
    if len(points) >= 2 and len(points) / days >= min_coverage:
        n = len(points)
        mean_x = sum(x for x, _ in points) / n
        mean_y = sum(y for _, y in points) / n
        sxx = sum((x - mean_x) ** 2 for x, _ in points)
        sxy = sum((x - mean_x) * (y - mean_y) for x, y in points)
        value = sxy / sxx * 7
    return _make(key, value, UNITS[variable], end, days, readings)


def latest(series: DailySeries, variable: Variable, end: date, key: str) -> Indicator:
    """The value on `end` itself."""
    readings = series.window(variable, end, 1)
    value = readings[0].value if readings[0] is not None else None
    return _make(key, value, UNITS[variable], end, 1, readings)


def compute_indicators(series: DailySeries, as_of: date) -> dict[str, Indicator]:
    """The standard indicator set for one day (today, a past day or a forecast day)."""
    p = Variable.PRECIPITATION
    indicators = [
        *(rolling_sum(series, p, as_of, n, f"rain_{n}d") for n in (3, 7, 14, 21, 30)),
        antecedent_precipitation_index(series, as_of),
        water_balance(series, as_of, 14, "water_balance_14d"),
        water_balance(series, as_of, 30, "water_balance_30d"),
        count_days(series, p, as_of, 14, "wet_days_14d", lambda v: v >= WET_DAY_MM),
        trailing_run(series, p, as_of, "dry_spell", lambda v: v < WET_DAY_MM),
        trailing_run(series, p, as_of, "wet_streak", lambda v: v >= WET_DAY_MM),
        *(
            rolling_mean(series, Variable.TEMPERATURE_MEAN, as_of, n, f"temperature_mean_{n}d")
            for n in (7, 14, 21)
        ),
        rolling_min(series, Variable.TEMPERATURE_MIN, as_of, 7, "temperature_min_7d"),
        rolling_max(series, Variable.TEMPERATURE_MAX, as_of, 7, "temperature_max_7d"),
        *(
            count_days(
                series,
                Variable.TEMPERATURE_MIN,
                as_of,
                n,
                f"frost_days_{n}d",
                lambda v: v < FROST_DAY_C,
            )
            for n in (7, 14)
        ),
        rolling_mean(series, Variable.HUMIDITY_MEAN, as_of, 7, "humidity_mean_7d"),
        latest(series, Variable.SOIL_MOISTURE_0_7CM, as_of, "soil_moisture"),
        latest(series, Variable.SOIL_MOISTURE_7_28CM, as_of, "soil_moisture_deep"),
        trend(series, Variable.SOIL_MOISTURE_0_7CM, as_of, 7, "soil_moisture_trend_7d"),
        latest(series, Variable.SOIL_TEMPERATURE_0_7CM, as_of, "soil_temperature"),
        trend(series, Variable.SOIL_TEMPERATURE_0_7CM, as_of, 7, "soil_temperature_trend_7d"),
    ]
    return {indicator.key: indicator for indicator in indicators}
