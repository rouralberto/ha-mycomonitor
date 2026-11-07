"""Tests for the Open-Meteo provider, against responses recorded for Urbasa."""

from __future__ import annotations

import copy
from datetime import date, timedelta
from typing import Any

import aiohttp
import pytest

from custom_components.mycomonitor.core.indicators import compute_indicators
from custom_components.mycomonitor.core.models import DataKind, Location, Variable
from custom_components.mycomonitor.core.providers import open_meteo
from custom_components.mycomonitor.core.providers.base import (
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
)

from ..fake_open_meteo import FIXTURE_PAST_DAYS, FakeResponse, FakeSession, load, session_with

URBASA = Location("Urbasa", 42.84, -2.17)
TODAY = date(2026, 11, 7)  # the day the fixtures were recorded
PAST_DAYS = FIXTURE_PAST_DAYS


def provider(session: FakeSession, **kwargs: Any) -> open_meteo.OpenMeteoProvider:
    return open_meteo.OpenMeteoProvider(session, **kwargs)  # type: ignore[arg-type]


# --- parsing ---------------------------------------------------------------


def test_parse_archive_fixture() -> None:
    payload = load("urbasa_archive")
    series = open_meteo.parse_response(
        payload, kind_for_day=lambda _d: DataKind.ANALYSIS, model="best_match"
    )
    days = [date.fromisoformat(t) for t in payload["daily"]["time"]]
    assert len(days) == PAST_DAYS
    for variable in Variable:
        assert series.dates(variable) == days, variable

    first = days[0]
    expected_rain = payload["daily"]["precipitation_sum"][0]
    reading = series.get(Variable.PRECIPITATION, first)
    assert reading is not None
    assert reading.value == expected_rain
    assert reading.source.kind is DataKind.ANALYSIS
    assert reading.source.provider == "open_meteo"
    assert reading.source.grid_latitude == payload["latitude"]

    hourly = payload["hourly"]["soil_moisture_0_to_7cm"][:24]
    soil = series.get(Variable.SOIL_MOISTURE_0_7CM, first)
    assert soil is not None
    assert soil.value == pytest.approx(sum(hourly) / 24)


def test_parse_skips_days_with_too_few_hours() -> None:
    payload = copy.deepcopy(load("urbasa_archive"))
    column = payload["hourly"]["soil_moisture_0_to_7cm"]
    for hour in range(open_meteo.MIN_HOURS_PER_DAY - 1, 24):  # leaves 17 hours on day one
        column[hour] = None
    series = open_meteo.parse_response(
        payload, kind_for_day=lambda _d: DataKind.ANALYSIS, model="best_match"
    )
    first = date.fromisoformat(payload["daily"]["time"][0])
    assert series.get(Variable.SOIL_MOISTURE_0_7CM, first) is None
    assert series.get(Variable.SOIL_MOISTURE_7_28CM, first) is not None


def test_parse_rejects_unexpected_units() -> None:
    payload = copy.deepcopy(load("urbasa_archive"))
    payload["daily_units"]["precipitation_sum"] = "inch"
    with pytest.raises(ProviderResponseError, match="inch"):
        open_meteo.parse_response(payload, kind_for_day=lambda _d: DataKind.ANALYSIS, model="m")


def test_parse_rejects_misaligned_columns() -> None:
    payload = copy.deepcopy(load("urbasa_archive"))
    payload["daily"]["precipitation_sum"].pop()
    with pytest.raises(ProviderResponseError, match="time axis"):
        open_meteo.parse_response(payload, kind_for_day=lambda _d: DataKind.ANALYSIS, model="m")


def test_parse_rejects_missing_section() -> None:
    with pytest.raises(ProviderResponseError, match="daily"):
        open_meteo.parse_response({}, kind_for_day=lambda _d: DataKind.ANALYSIS, model="m")


# --- fetching --------------------------------------------------------------


async def test_fetch_requests_forecast_then_archive() -> None:
    session = session_with()
    result = await provider(session).async_fetch(
        Location("Urbasa", 42.84, -2.17, 916), past_days=PAST_DAYS, forecast_days=16
    )
    assert result.today == TODAY

    (forecast_url, forecast_params), (archive_url, archive_params) = session.calls
    assert forecast_url == open_meteo.FORECAST_URL
    assert forecast_params["models"] == "best_match"
    assert forecast_params["forecast_days"] == 16
    assert forecast_params["past_days"] == open_meteo.FORECAST_FALLBACK_PAST_DAYS
    assert forecast_params["elevation"] == 916
    assert forecast_params["timezone"] == "auto"
    assert archive_url == open_meteo.ARCHIVE_URL
    assert archive_params["start_date"] == (TODAY - timedelta(days=PAST_DAYS)).isoformat()
    assert archive_params["end_date"] == (TODAY - timedelta(days=1)).isoformat()
    assert "models" not in archive_params


async def test_fetch_omits_elevation_without_altitude() -> None:
    session = session_with()
    await provider(session).async_fetch(URBASA, past_days=PAST_DAYS, forecast_days=16)
    assert all("elevation" not in params for _url, params in session.calls)


async def test_fetch_splits_history_and_forecast_at_today() -> None:
    session = session_with()
    result = await provider(session).async_fetch(URBASA, past_days=PAST_DAYS, forecast_days=16)
    series = result.series
    archive = load("urbasa_archive")
    forecast = load("urbasa_forecast")

    yesterday = series.get(Variable.PRECIPITATION, TODAY - timedelta(days=1))
    assert yesterday is not None
    assert yesterday.source.kind is DataKind.ANALYSIS
    assert yesterday.value == archive["daily"]["precipitation_sum"][-1]

    today = series.get(Variable.PRECIPITATION, TODAY)
    assert today is not None
    assert today.source.kind is DataKind.FORECAST
    index = forecast["daily"]["time"].index(TODAY.isoformat())
    assert today.value == forecast["daily"]["precipitation_sum"][index]

    assert series.dates(Variable.PRECIPITATION)[0] == TODAY - timedelta(days=PAST_DAYS)
    assert result.warnings == []


async def test_fetch_fills_recent_archive_gap_from_forecast() -> None:
    archive = copy.deepcopy(load("urbasa_archive"))
    archive["daily"]["precipitation_sum"][-1] = None
    forecast = load("urbasa_forecast")
    session = session_with(forecast=forecast, archive=archive)
    result = await provider(session).async_fetch(URBASA, past_days=PAST_DAYS, forecast_days=16)

    yesterday = TODAY - timedelta(days=1)
    reading = result.series.get(Variable.PRECIPITATION, yesterday)
    assert reading is not None
    assert reading.source.kind is DataKind.ANALYSIS
    index = forecast["daily"]["time"].index(yesterday.isoformat())
    assert reading.value == forecast["daily"]["precipitation_sum"][index]
    assert result.warnings == []


async def test_fetch_warns_about_old_gaps() -> None:
    archive = copy.deepcopy(load("urbasa_archive"))
    archive["daily"]["precipitation_sum"][0] = None
    session = session_with(archive=archive)
    result = await provider(session).async_fetch(URBASA, past_days=PAST_DAYS, forecast_days=16)
    gap = (TODAY - timedelta(days=PAST_DAYS)).isoformat()
    assert result.warnings == [f"precipitation: no history from {gap} to {gap}"]


async def test_real_data_indicators_match_raw_sums() -> None:
    """End-to-end: indicators from the recorded fixtures equal sums done by hand."""
    session = session_with()
    result = await provider(session).async_fetch(URBASA, past_days=PAST_DAYS, forecast_days=16)
    indicators = compute_indicators(result.series, result.today)

    archive = load("urbasa_archive")["daily"]["precipitation_sum"]
    forecast = load("urbasa_forecast")
    today_rain = forecast["daily"]["precipitation_sum"][
        forecast["daily"]["time"].index(TODAY.isoformat())
    ]
    assert indicators["rain_7d"].value == pytest.approx(sum(archive[-6:]) + today_rain)
    assert indicators["rain_30d"].value == pytest.approx(sum(archive[-29:]) + today_rain)
    assert indicators["rain_7d"].kinds == {DataKind.ANALYSIS, DataKind.FORECAST}
    assert all(i.available for i in indicators.values()), [
        k for k, i in indicators.items() if not i.available
    ]

    # The outlook works the same way, on forecast days.
    outlook = compute_indicators(result.series, TODAY + timedelta(days=7))
    assert outlook["rain_7d"].kinds == {DataKind.FORECAST}


# --- errors ----------------------------------------------------------------


async def test_rate_limit() -> None:
    session = session_with(status=429)
    with pytest.raises(ProviderRateLimitError):
        await provider(session).async_fetch(URBASA, past_days=PAST_DAYS, forecast_days=16)


async def test_server_error_is_a_connection_error() -> None:
    session = session_with(status=503)
    with pytest.raises(ProviderConnectionError):
        await provider(session).async_fetch(URBASA, past_days=PAST_DAYS, forecast_days=16)


async def test_api_error_reason_is_reported() -> None:
    session = session_with(
        forecast={"error": True, "reason": "Latitude must be in range"}, status=400
    )
    with pytest.raises(ProviderResponseError, match="Latitude must be in range"):
        await provider(session).async_fetch(URBASA, past_days=PAST_DAYS, forecast_days=16)


async def test_invalid_json() -> None:
    session = FakeSession({open_meteo.FORECAST_URL: FakeResponse(200, ValueError("not json"))})
    with pytest.raises(ProviderResponseError, match="invalid JSON"):
        await provider(session).async_fetch(URBASA, past_days=PAST_DAYS, forecast_days=16)


@pytest.mark.parametrize("error", [aiohttp.ClientConnectionError("down"), TimeoutError()])
async def test_network_errors(error: Exception) -> None:
    session = FakeSession({open_meteo.FORECAST_URL: error})
    with pytest.raises(ProviderConnectionError):
        await provider(session).async_fetch(URBASA, past_days=PAST_DAYS, forecast_days=16)


@pytest.mark.parametrize(("past", "future"), [(0, 16), (400, 16), (92, 0), (92, 17)])
async def test_rejects_out_of_range_days(past: int, future: int) -> None:
    with pytest.raises(ValueError, match="_days must be"):
        await provider(session_with()).async_fetch(URBASA, past_days=past, forecast_days=future)
