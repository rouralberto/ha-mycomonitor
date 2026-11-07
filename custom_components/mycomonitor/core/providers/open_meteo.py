"""Open-Meteo provider (https://open-meteo.com), free tier, no API key.

Two requests per fetch:

1. Forecast API: today onwards (`forecast_days`), plus a few past days that
   only serve as a fallback if the archive lags.
2. Historical Weather API (archive): the `past_days` complete days before
   today. Its default `best_match` (ECMWF IFS 9 km, then ERA5/ERA5-Land) is
   gap-free up to today, unlike the forecast API's `past_days`, which only
   reaches back about two months with `best_match`.

Both APIs serve the same soil layers (0-7 cm, 7-28 cm), so history and
forecast join without changing depth band. Open-Meteo returns `timezone=auto`
data in the location's own time zone, and adjusts temperatures to `elevation`.

Data is licensed CC BY 4.0: show "Weather data by Open-Meteo.com".
"""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable, Mapping
from datetime import date, timedelta
from typing import Any

import aiohttp

from ..models import DailySeries, DataKind, Location, Reading, Source, Variable
from .base import (
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
    ProviderResult,
)

FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
ATTRIBUTION = "Weather data by Open-Meteo.com (CC BY 4.0)"
PROVIDER = "open_meteo"
DEFAULT_MODEL = "best_match"

# Open-Meteo daily variable -> (our variable, expected unit)
DAILY_VARIABLES: dict[str, tuple[Variable, str]] = {
    "precipitation_sum": (Variable.PRECIPITATION, "mm"),
    "temperature_2m_mean": (Variable.TEMPERATURE_MEAN, "°C"),
    "temperature_2m_min": (Variable.TEMPERATURE_MIN, "°C"),
    "temperature_2m_max": (Variable.TEMPERATURE_MAX, "°C"),
    "relative_humidity_2m_mean": (Variable.HUMIDITY_MEAN, "%"),
    "et0_fao_evapotranspiration": (Variable.ET0, "mm"),
}

# Hourly variables, averaged to daily means.
HOURLY_VARIABLES: dict[str, tuple[Variable, str]] = {
    "soil_moisture_0_to_7cm": (Variable.SOIL_MOISTURE_0_7CM, "m³/m³"),
    "soil_moisture_7_to_28cm": (Variable.SOIL_MOISTURE_7_28CM, "m³/m³"),
    "soil_temperature_0_to_7cm": (Variable.SOIL_TEMPERATURE_0_7CM, "°C"),
    "soil_temperature_7_to_28cm": (Variable.SOIL_TEMPERATURE_7_28CM, "°C"),
}

# A daily mean of hourly values needs at least this many hours of data.
MIN_HOURS_PER_DAY = 18
# Past days requested from the forecast API, used only to fill archive gaps.
FORECAST_FALLBACK_PAST_DAYS = 7
MAX_PAST_DAYS = 366
MAX_FORECAST_DAYS = 16


class OpenMeteoProvider:
    """Daily history and forecast from Open-Meteo."""

    name = PROVIDER

    def __init__(
        self,
        session: aiohttp.ClientSession,
        *,
        forecast_model: str = DEFAULT_MODEL,
        timeout: float = 30.0,
        forecast_url: str = FORECAST_URL,
        archive_url: str = ARCHIVE_URL,
    ) -> None:
        self._session = session
        self._forecast_model = forecast_model
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._forecast_url = forecast_url
        self._archive_url = archive_url

    async def async_fetch(
        self, location: Location, *, past_days: int = 92, forecast_days: int = 16
    ) -> ProviderResult:
        """Fetch `past_days` of history before today and `forecast_days` from today."""
        if not 1 <= past_days <= MAX_PAST_DAYS:
            raise ValueError(f"past_days must be 1..{MAX_PAST_DAYS}")
        if not 1 <= forecast_days <= MAX_FORECAST_DAYS:
            raise ValueError(f"forecast_days must be 1..{MAX_FORECAST_DAYS}")

        forecast_payload = await self._get(
            self._forecast_url,
            {
                **_common_params(location),
                "models": self._forecast_model,
                "past_days": FORECAST_FALLBACK_PAST_DAYS,
                "forecast_days": forecast_days,
            },
        )
        today = _first_forecast_day(forecast_payload)

        archive_payload = await self._get(
            self._archive_url,
            {
                **_common_params(location),
                "start_date": (today - timedelta(days=past_days)).isoformat(),
                "end_date": (today - timedelta(days=1)).isoformat(),
            },
        )

        history = parse_response(
            archive_payload, kind_for_day=lambda _day: DataKind.ANALYSIS, model=DEFAULT_MODEL
        )
        forecast = parse_response(
            forecast_payload,
            kind_for_day=lambda day: DataKind.FORECAST if day >= today else DataKind.ANALYSIS,
            model=self._forecast_model,
        )

        # The archive covers the past; the forecast covers today onwards and
        # fills any days the archive is missing.
        series = DailySeries()
        series.fill_gaps_from(history, where=lambda day: day < today)
        series.fill_gaps_from(forecast)

        warnings = [
            f"{variable}: no history from {missing[0]} to {missing[-1]}"
            for variable in sorted(series.variables())
            if (missing := _missing_days(series, variable, today, past_days))
        ]
        return ProviderResult(series=series, today=today, warnings=warnings)

    async def async_fetch_history(
        self, location: Location, *, end: date, days: int = 92
    ) -> DailySeries:
        """Archive data only, for the `days` days ending on `end` (e.g. observation snapshots)."""
        if not 1 <= days <= MAX_PAST_DAYS:
            raise ValueError(f"days must be 1..{MAX_PAST_DAYS}")
        payload = await self._get(
            self._archive_url,
            {
                **_common_params(location),
                "start_date": (end - timedelta(days=days - 1)).isoformat(),
                "end_date": end.isoformat(),
            },
        )
        return parse_response(
            payload, kind_for_day=lambda _day: DataKind.ANALYSIS, model=DEFAULT_MODEL
        )

    async def _get(self, url: str, params: Mapping[str, str | int | float]) -> dict[str, Any]:
        try:
            async with self._session.get(url, params=params, timeout=self._timeout) as response:
                if response.status == 429:
                    raise ProviderRateLimitError("Open-Meteo rate limit reached")
                if response.status >= 500:
                    raise ProviderConnectionError(f"Open-Meteo HTTP {response.status}")
                try:
                    payload = await response.json(content_type=None)
                except (aiohttp.ContentTypeError, ValueError) as err:
                    raise ProviderResponseError(
                        f"Open-Meteo returned invalid JSON (HTTP {response.status})"
                    ) from err
        except (TimeoutError, aiohttp.ClientError) as err:
            raise ProviderConnectionError(f"cannot reach Open-Meteo: {err!r}") from err

        if not isinstance(payload, dict):
            raise ProviderResponseError("Open-Meteo returned an unexpected payload")
        if payload.get("error") or response.status >= 400:
            reason = payload.get("reason", f"HTTP {response.status}")
            raise ProviderResponseError(f"Open-Meteo rejected the request: {reason}")
        return payload


def _common_params(location: Location) -> dict[str, str | int | float]:
    params: dict[str, str | int | float] = {
        "latitude": round(location.latitude, 5),
        "longitude": round(location.longitude, 5),
        "timezone": "auto",
        "cell_selection": "land",
        "daily": ",".join(DAILY_VARIABLES),
        "hourly": ",".join(HOURLY_VARIABLES),
    }
    if location.altitude is not None:
        params["elevation"] = location.altitude
    return params


def _first_forecast_day(payload: Mapping[str, Any]) -> date:
    """Today in the location's time zone: the first forecast day after the past days."""
    times = _section(payload, "daily")["time"]
    if len(times) <= FORECAST_FALLBACK_PAST_DAYS:
        raise ProviderResponseError("Open-Meteo forecast has no days after the past days")
    return _parse_date(times[FORECAST_FALLBACK_PAST_DAYS])


def _missing_days(
    series: DailySeries, variable: Variable, today: date, past_days: int
) -> list[date]:
    return [
        today - timedelta(days=offset)
        for offset in range(past_days, 0, -1)
        if series.get(variable, today - timedelta(days=offset)) is None
    ]


def parse_response(
    payload: Mapping[str, Any],
    *,
    kind_for_day: Callable[[date], DataKind],
    model: str,
) -> DailySeries:
    """Turn an Open-Meteo forecast or archive response into a `DailySeries`.

    Daily variables are used as they are; hourly ones are averaged per local
    calendar day when at least `MIN_HOURS_PER_DAY` hours have data. Units are
    checked so a changed default never slips through silently.
    """
    grid = {
        "grid_latitude": _optional_float(payload.get("latitude")),
        "grid_longitude": _optional_float(payload.get("longitude")),
        "grid_elevation": _optional_float(payload.get("elevation")),
    }
    sources: dict[DataKind, Source] = {}

    def source_for(day: date) -> Source:
        kind = kind_for_day(day)
        if kind not in sources:
            sources[kind] = Source(provider=PROVIDER, kind=kind, model=model, **grid)
        return sources[kind]

    series = DailySeries()

    daily = _section(payload, "daily")
    _check_units(payload.get("daily_units", {}), DAILY_VARIABLES)
    days = [_parse_date(t) for t in daily["time"]]
    for key, (variable, _unit) in DAILY_VARIABLES.items():
        for day, value in zip(days, _column(daily, key, len(days)), strict=True):
            if value is not None:
                series.put(variable, day, Reading(float(value), source_for(day)))

    hourly = _section(payload, "hourly")
    _check_units(payload.get("hourly_units", {}), HOURLY_VARIABLES)
    hours = [_parse_date(t[:10]) for t in hourly["time"]]
    for key, (variable, _unit) in HOURLY_VARIABLES.items():
        by_day: dict[date, list[float]] = defaultdict(list)
        for day, value in zip(hours, _column(hourly, key, len(hours)), strict=True):
            if value is not None:
                by_day[day].append(float(value))
        for day, values in by_day.items():
            if len(values) >= MIN_HOURS_PER_DAY:
                series.put(variable, day, Reading(sum(values) / len(values), source_for(day)))

    return series


def _section(payload: Mapping[str, Any], name: str) -> Mapping[str, Any]:
    section = payload.get(name)
    if not isinstance(section, Mapping) or not isinstance(section.get("time"), list):
        raise ProviderResponseError(f"Open-Meteo response has no '{name}' data")
    return section


def _column(section: Mapping[str, Any], key: str, length: int) -> list[Any]:
    values = section.get(key)
    if values is None:
        return [None] * length
    if not isinstance(values, list) or len(values) != length:
        raise ProviderResponseError(f"Open-Meteo '{key}' does not match its time axis")
    return values


def _check_units(units: Mapping[str, str], expected: Mapping[str, tuple[Variable, str]]) -> None:
    for key, (_variable, unit) in expected.items():
        if key in units and units[key] != unit:
            raise ProviderResponseError(f"Open-Meteo '{key}' is in {units[key]}, expected {unit}")


def _parse_date(value: Any) -> date:
    try:
        return date.fromisoformat(str(value))
    except ValueError as err:
        raise ProviderResponseError(f"Open-Meteo returned an invalid date: {value!r}") from err


def _optional_float(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) else None


__all__ = ["ATTRIBUTION", "OpenMeteoProvider", "parse_response"]
