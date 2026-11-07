"""AEMET OpenData provider (Spain's state weather agency), experimental.

Built from AEMET's OpenAPI specification and field descriptors, not yet
verified against a live API key. Every AEMET call is two-step: the first
response carries a `datos` URL that must then be fetched.

Used for **precipitation only**: station temperatures can be hundreds of
metres from the location's altitude, while model temperatures are adjusted to
it. AEMET's daily precipitation runs 07:00 to 07:00 UTC, so it is shifted by
up to a day relative to calendar days; for 7-30 day sums that rarely matters.

Data: "© AEMET". Reuse is allowed citing AEMET as the source.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
import json
import re
from typing import Any

import aiohttp

from ..models import DailySeries, DataKind, Reading, Source, Variable, distance_km
from .base import (
    ProviderConnectionError,
    ProviderError,
    ProviderRateLimitError,
    ProviderResponseError,
)

BASE_URL = "https://opendata.aemet.es/opendata/api"
PROVIDER = "aemet"
ATTRIBUTION = "© AEMET"
MAX_DAYS_PER_REQUEST = 180  # AEMET limits daily climatology requests to about six months
TRACE_PRECIPITATION_MM = 0.0  # "Ip": less than 0.1 mm


class AemetAuthError(ProviderError):
    """The API key was rejected."""


@dataclass(frozen=True, slots=True)
class Station:
    """An AEMET climatological station."""

    id: str
    name: str
    province: str
    latitude: float
    longitude: float
    altitude: float | None

    def distance_km(self, latitude: float, longitude: float) -> float:
        return distance_km(latitude, longitude, self.latitude, self.longitude)


_DMS = re.compile(r"^(\d{2,3})(\d{2})(\d{2})([NSEW])$")


def parse_dms(value: str) -> float:
    """AEMET coordinates: "424910N" = 42°49'10" N, "013909W" = -1°39'09"."""
    match = _DMS.match(value.strip())
    if not match:
        raise ProviderResponseError(f"AEMET returned invalid coordinates: {value!r}")
    degrees, minutes, seconds, hemisphere = match.groups()
    decimal = int(degrees) + int(minutes) / 60 + int(seconds) / 3600
    return -decimal if hemisphere in "SW" else decimal


def parse_number(value: Any) -> float | None:
    """AEMET numbers are strings with a decimal comma; "Ip" is trace rain; "Acum" is unknown."""
    if value is None:
        return None
    if isinstance(value, int | float):
        return float(value)
    text = str(value).strip()
    if text == "Ip":
        return TRACE_PRECIPITATION_MM
    if not text or text in {"Acum", "Varias"}:
        return None
    try:
        return float(text.replace(",", "."))
    except ValueError:
        return None


def parse_daily(records: list[Mapping[str, Any]], station: Station | None = None) -> DailySeries:
    """Daily climatology records -> precipitation series (kind STATION)."""
    source = Source(
        provider=PROVIDER,
        kind=DataKind.STATION,
        model=str(records[0].get("indicativo")) if records else None,
        grid_latitude=station.latitude if station else None,
        grid_longitude=station.longitude if station else None,
        grid_elevation=station.altitude if station else None,
    )
    series = DailySeries()
    for record in records:
        try:
            day = date.fromisoformat(str(record["fecha"]))
        except KeyError, ValueError:
            continue
        value = parse_number(record.get("prec"))
        if value is not None and value >= 0:
            series.put(Variable.PRECIPITATION, day, Reading(value, source))
    return series


def parse_stations(records: list[Mapping[str, Any]]) -> list[Station]:
    """Station inventory records -> stations (skipping malformed ones)."""
    stations = []
    for record in records:
        try:
            stations.append(
                Station(
                    id=str(record["indicativo"]),
                    name=str(record.get("nombre", "")).strip().title(),
                    province=str(record.get("provincia", "")).strip().title(),
                    latitude=parse_dms(str(record["latitud"])),
                    longitude=parse_dms(str(record["longitud"])),
                    altitude=parse_number(record.get("altitud")),
                )
            )
        except KeyError, ProviderResponseError:
            continue
    return stations


class AemetProvider:
    """AEMET OpenData client."""

    name = PROVIDER

    def __init__(
        self,
        session: aiohttp.ClientSession,
        api_key: str,
        *,
        timeout: float = 30.0,
        base_url: str = BASE_URL,
    ) -> None:
        self._session = session
        self._api_key = api_key
        self._timeout = aiohttp.ClientTimeout(total=timeout)
        self._base_url = base_url

    async def async_stations(self) -> list[Station]:
        """All climatological stations."""
        records = await self._two_step(
            "/valores/climatologicos/inventarioestaciones/todasestaciones"
        )
        return parse_stations(records)

    async def async_fetch_daily(
        self, station_id: str, start: date, end: date, station: Station | None = None
    ) -> DailySeries:
        """Daily precipitation for one station between two dates (inclusive)."""
        if not re.fullmatch(r"[0-9A-Z]{4,7}", station_id):
            raise ValueError(f"invalid AEMET station id: {station_id!r}")
        if not 0 <= (end - start).days < MAX_DAYS_PER_REQUEST:
            raise ValueError(f"AEMET accepts at most {MAX_DAYS_PER_REQUEST} days per request")
        path = (
            "/valores/climatologicos/diarios/datos"
            f"/fechaini/{start.isoformat()}T00:00:00UTC"
            f"/fechafin/{end.isoformat()}T23:59:59UTC/estacion/{station_id}"
        )
        records = await self._two_step(path)
        return parse_daily(records, station)

    async def _two_step(self, path: str) -> list[Mapping[str, Any]]:
        meta = await self._get_json(f"{self._base_url}{path}", authenticated=True)
        if not isinstance(meta, Mapping):
            raise ProviderResponseError("AEMET returned an unexpected payload")
        status = int(meta.get("estado", 0) or 0)
        if status == 404:
            return []  # "No hay datos que satisfagan esos criterios"
        if status == 401:
            raise AemetAuthError("AEMET rejected the API key")
        if status == 429:
            raise ProviderRateLimitError("AEMET rate limit reached")
        if status != 200 or not meta.get("datos"):
            raise ProviderResponseError(
                f"AEMET error {status}: {meta.get('descripcion', 'no description')}"
            )
        data = await self._get_json(str(meta["datos"]), authenticated=False)
        if not isinstance(data, list):
            raise ProviderResponseError("AEMET data is not a list")
        return data

    async def _get_json(self, url: str, *, authenticated: bool) -> Any:
        headers = {"api_key": self._api_key, "Accept": "application/json"} if authenticated else {}
        try:
            async with self._session.get(url, headers=headers, timeout=self._timeout) as response:
                if response.status == 401:
                    raise AemetAuthError("AEMET rejected the API key")
                if response.status == 429:
                    raise ProviderRateLimitError("AEMET rate limit reached")
                if response.status >= 500:
                    raise ProviderConnectionError(f"AEMET HTTP {response.status}")
                if response.status >= 400:
                    raise ProviderResponseError(f"AEMET HTTP {response.status}")
                raw = await response.read()
                charset = response.charset or "latin-1"  # AEMET serves ISO-8859-15
        except (TimeoutError, aiohttp.ClientError) as err:
            raise ProviderConnectionError(f"cannot reach AEMET: {err!r}") from err
        try:
            return json.loads(raw.decode(charset, errors="replace"))
        except (LookupError, ValueError) as err:
            raise ProviderResponseError("AEMET returned invalid JSON") from err
