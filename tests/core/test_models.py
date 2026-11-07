"""Tests for the core data model."""

from __future__ import annotations

from datetime import date

import pytest

from custom_components.mycomonitor.core.models import (
    DailySeries,
    DataKind,
    Location,
    Reading,
    Source,
    Variable,
    date_range,
    distance_km,
    grid_distance_km,
)

from .helpers import ANALYSIS, FORECAST, START, series_of

P = Variable.PRECIPITATION


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"name": " ", "latitude": 0, "longitude": 0}, "name"),
        ({"name": "x", "latitude": 91, "longitude": 0}, "latitude"),
        ({"name": "x", "latitude": 0, "longitude": -181}, "longitude"),
        ({"name": "x", "latitude": 0, "longitude": 0, "altitude": 10000}, "altitude"),
    ],
)
def test_location_rejects_invalid_values(kwargs: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        Location(**kwargs)  # type: ignore[arg-type]


def test_location_accepts_valid_values() -> None:
    location = Location("Urbasa", 42.84, -2.17, 916)
    assert location.altitude == 916


def test_date_range_is_inclusive_and_oldest_first() -> None:
    assert date_range(date(2026, 10, 3), 3) == [
        date(2026, 10, 1),
        date(2026, 10, 2),
        date(2026, 10, 3),
    ]
    with pytest.raises(ValueError, match="days"):
        date_range(date(2026, 10, 3), 0)


def test_window_marks_gaps_as_none() -> None:
    series = series_of({P: [1.0, None, 3.0]})
    window = series.window(P, date(2026, 10, 3), 4)
    assert [r.value if r else None for r in window] == [None, 1.0, None, 3.0]


def test_from_values_skips_none_and_counts_readings() -> None:
    series = series_of({P: [1.0, None, 3.0], Variable.ET0: [0.5]})
    assert len(series) == 3
    assert series.variables() == {P, Variable.ET0}
    assert series.dates(P) == [START, date(2026, 10, 3)]
    assert series.dates() == [START, date(2026, 10, 3)]
    assert series.sources() == {ANALYSIS}


def test_fill_gaps_never_overwrites_and_respects_where() -> None:
    own = series_of({P: [1.0, None, None]})
    other = series_of({P: [9.0, 9.0, 9.0]}, source=FORECAST)
    own.fill_gaps_from(other, where=lambda day: day < date(2026, 10, 3))
    assert [r.value if r else None for r in own.window(P, date(2026, 10, 3), 3)] == [
        1.0,
        9.0,
        None,
    ]
    assert own.get(P, START) == Reading(1.0, ANALYSIS)
    assert own.get(P, date(2026, 10, 2)) == Reading(9.0, FORECAST)


def test_get_missing_variable_returns_none() -> None:
    assert DailySeries().get(P, START) is None
    assert DailySeries().window(P, START, 2) == [None, None]


def test_distance_km() -> None:
    # Pamplona to Estella-Lizarra, in a straight line.
    assert distance_km(42.8125, -1.6458, 42.6713, -2.0310) == pytest.approx(34.8, abs=1)
    assert distance_km(42.84, -2.17, 42.84, -2.17) == 0


def test_grid_distance_km() -> None:
    location = Location("Urbasa", 42.84, -2.17)
    assert grid_distance_km(location, ANALYSIS) is None
    gridded = Source("p", DataKind.ANALYSIS, grid_latitude=42.84, grid_longitude=-2.08)
    assert grid_distance_km(location, gridded) == pytest.approx(7.36, abs=0.05)
