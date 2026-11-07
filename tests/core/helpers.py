"""Builders for synthetic series used across core tests."""

from __future__ import annotations

from datetime import date

from custom_components.mycomonitor.core.models import DailySeries, DataKind, Source, Variable

ANALYSIS = Source(provider="test", kind=DataKind.ANALYSIS)
FORECAST = Source(provider="test", kind=DataKind.FORECAST)
START = date(2026, 10, 1)


def series_of(
    values: dict[Variable, list[float | None]], start: date = START, source: Source = ANALYSIS
) -> DailySeries:
    """Several variables, each a list of consecutive daily values from `start`."""
    series = DailySeries()
    for variable, column in values.items():
        series.fill_gaps_from(DailySeries.from_values(variable, start, column, source))
    return series
