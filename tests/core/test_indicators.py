"""Tests for the indicator engine, on synthetic series with known answers."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from custom_components.mycomonitor.core import indicators as ind
from custom_components.mycomonitor.core.models import DataKind, Variable

from .helpers import FORECAST, START, series_of

P = Variable.PRECIPITATION
TMIN = Variable.TEMPERATURE_MIN
SM = Variable.SOIL_MOISTURE_0_7CM


def day(n: int) -> date:
    """The n-th day of the synthetic series (day(0) == START)."""
    return START + timedelta(days=n)


def test_rolling_sum_window_and_value() -> None:
    series = series_of({P: [1, 2, 3, 4, 5, 6, 7, 8]})
    result = ind.rolling_sum(series, P, day(7), 7, "rain_7d")
    assert result.value == 2 + 3 + 4 + 5 + 6 + 7 + 8
    assert (result.start, result.end) == (day(1), day(7))
    assert result.unit == "mm"
    assert result.coverage == 1
    assert result.kinds == {DataKind.ANALYSIS}
    assert result.available


def test_rolling_sum_requires_every_day() -> None:
    series = series_of({P: [1, 2, None, 4, 5, 6, 7]})
    result = ind.rolling_sum(series, P, day(6), 7, "rain_7d")
    assert result.value is None
    assert not result.available
    assert result.coverage == pytest.approx(6 / 7)


def test_rolling_mean_honours_min_coverage() -> None:
    two_missing = series_of(
        {Variable.TEMPERATURE_MEAN: [10, None, 10, 10, None, 10, 10, 10, 10, 10]}
    )
    assert ind.rolling_mean(two_missing, Variable.TEMPERATURE_MEAN, day(9), 10, "t").value == 10
    three_missing = series_of(
        {Variable.TEMPERATURE_MEAN: [10, None, None, 10, None, 10, 10, 10, 10, 10]}
    )
    assert ind.rolling_mean(three_missing, Variable.TEMPERATURE_MEAN, day(9), 10, "t").value is None


def test_rolling_min_and_max() -> None:
    series = series_of({TMIN: [3, -2, 5], Variable.TEMPERATURE_MAX: [10, 18, 12]})
    assert ind.rolling_min(series, TMIN, day(2), 3, "tmin").value == -2
    assert ind.rolling_max(series, Variable.TEMPERATURE_MAX, day(2), 3, "tmax").value == 18


def test_frost_days_use_strictly_below_zero() -> None:
    series = series_of({TMIN: [-1, 0, 2, -0.5]})
    result = ind.count_days(series, TMIN, day(3), 4, "frost", lambda v: v < ind.FROST_DAY_C)
    assert result.value == 2
    assert result.unit == "d"


def test_count_days_requires_every_day() -> None:
    series = series_of({P: [5, None, 5]})
    assert ind.count_days(series, P, day(2), 3, "wet", lambda v: v >= 1).value is None


def test_dry_spell_counts_back_to_last_wet_day() -> None:
    series = series_of({P: [5, 0, 0.5, 0, 0.9]})
    dry = ind.trailing_run(series, P, day(4), "dry", lambda v: v < ind.WET_DAY_MM)
    wet = ind.trailing_run(series, P, day(4), "wet", lambda v: v >= ind.WET_DAY_MM)
    assert dry.value == 4
    assert (dry.start, dry.end) == (day(1), day(4))
    assert wet.value == 0


def test_run_stops_at_gap_and_caps() -> None:
    gap = series_of({P: [0, None, 0, 0]})
    assert ind.trailing_run(gap, P, day(3), "dry", lambda v: v < 1).value == 2
    long_dry = series_of({P: [0.0] * 70})
    assert ind.trailing_run(long_dry, P, day(69), "dry", lambda v: v < 1, cap=60).value == 60


def test_run_is_none_when_end_day_missing() -> None:
    series = series_of({P: [0, 0, None]})
    assert ind.trailing_run(series, P, day(2), "dry", lambda v: v < 1).value is None


def test_api_weights_recent_rain_more() -> None:
    today_rain = series_of({P: [0.0] * 29 + [10.0]})
    week_old = series_of({P: [0.0] * 22 + [10.0] + [0.0] * 7})
    assert ind.antecedent_precipitation_index(today_rain, day(29)).value == pytest.approx(10)
    assert ind.antecedent_precipitation_index(week_old, day(29)).value == pytest.approx(10 * 0.9**7)


def test_api_constant_rain_is_geometric_sum() -> None:
    series = series_of({P: [10.0] * 30})
    expected = 10 * (1 - 0.9**30) / (1 - 0.9)
    assert ind.antecedent_precipitation_index(series, day(29)).value == pytest.approx(expected)


def test_water_balance() -> None:
    series = series_of({P: [2.0] * 14, Variable.ET0: [1.0] * 13 + [3.0]})
    result = ind.water_balance(series, day(13), 14, "wb")
    assert result.value == pytest.approx(14 * 2 - 13 - 3)
    assert result.coverage == 1


def test_water_balance_needs_both_variables_every_day() -> None:
    series = series_of({P: [2.0] * 14, Variable.ET0: [1.0] * 13})
    result = ind.water_balance(series, day(13), 14, "wb")
    assert result.value is None
    assert result.coverage == pytest.approx(13 / 14)


def test_trend_is_change_per_week() -> None:
    rising = series_of({SM: [0.20 + 0.01 * i for i in range(7)]})
    assert ind.trend(rising, SM, day(6), 7, "t").value == pytest.approx(0.07)
    flat = series_of({SM: [0.3] * 7})
    assert ind.trend(flat, SM, day(6), 7, "t").value == pytest.approx(0)


def test_trend_needs_coverage() -> None:
    sparse = series_of({SM: [0.2, None, None, 0.3, None, None, 0.4]})
    assert ind.trend(sparse, SM, day(6), 7, "t").value is None


def test_latest() -> None:
    series = series_of({SM: [0.2, 0.25]})
    assert ind.latest(series, SM, day(1), "sm").value == 0.25
    assert ind.latest(series, SM, day(2), "sm").value is None


def test_kinds_report_forecast_in_window() -> None:
    series = series_of({P: [1.0, 1.0]})
    series.fill_gaps_from(series_of({P: [1.0]}, start=day(2), source=FORECAST))
    assert ind.rolling_sum(series, P, day(2), 3, "r").kinds == {
        DataKind.ANALYSIS,
        DataKind.FORECAST,
    }


EXPECTED_KEYS = {
    "rain_3d",
    "rain_7d",
    "rain_14d",
    "rain_21d",
    "rain_30d",
    "api_30d",
    "water_balance_14d",
    "water_balance_30d",
    "wet_days_14d",
    "dry_spell",
    "wet_streak",
    "temperature_mean_7d",
    "temperature_mean_14d",
    "temperature_mean_21d",
    "temperature_min_7d",
    "temperature_max_7d",
    "frost_days_7d",
    "frost_days_14d",
    "humidity_mean_7d",
    "soil_moisture",
    "soil_moisture_deep",
    "soil_moisture_trend_7d",
    "soil_temperature",
    "soil_temperature_trend_7d",
}


def test_compute_indicators_full_set() -> None:
    n = 40
    series = series_of({variable: [1.0] * n for variable in Variable})
    result = ind.compute_indicators(series, day(n - 1))
    assert set(result) == EXPECTED_KEYS
    assert all(indicator.available for indicator in result.values())
    assert result["rain_30d"].value == 30
    assert result["water_balance_30d"].value == 0
    assert result["wet_streak"].value == n


def test_compute_indicators_short_history_leaves_long_windows_empty() -> None:
    series = series_of({variable: [1.0] * 10 for variable in Variable})
    result = ind.compute_indicators(series, day(9))
    assert result["rain_7d"].available
    assert not result["rain_14d"].available
    assert not result["rain_30d"].available
