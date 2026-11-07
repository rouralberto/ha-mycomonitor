"""Tests for the AEMET provider, against payloads in AEMET's documented format."""

from __future__ import annotations

from datetime import date
import json
from typing import Any

import aiohttp
import pytest

from custom_components.mycomonitor.core.models import DataKind, Variable
from custom_components.mycomonitor.core.providers import aemet
from custom_components.mycomonitor.core.providers.base import (
    ProviderConnectionError,
    ProviderRateLimitError,
    ProviderResponseError,
)

DATA_URL = "https://opendata.aemet.es/opendata/sh/abc123"
DAILY = [
    {"fecha": "2026-11-01", "indicativo": "9263D", "prec": "12,4", "tmed": "9,8"},
    {"fecha": "2026-11-02", "indicativo": "9263D", "prec": "Ip"},
    {"fecha": "2026-11-03", "indicativo": "9263D", "prec": "Acum"},
    {"fecha": "2026-11-04", "indicativo": "9263D", "prec": "0,0"},
    {"fecha": "2026-11-05", "indicativo": "9263D"},
    {"fecha": "bad", "indicativo": "9263D", "prec": "1,0"},
]
STATIONS = [
    {
        "latitud": "424610N",
        "provincia": "NAVARRA",
        "altitud": "459",
        "indicativo": "9263D",
        "nombre": "PAMPLONA AEROPUERTO",
        "longitud": "013909W",
    },
    {"latitud": "broken", "longitud": "013909W", "indicativo": "X1"},
]


class Response:
    def __init__(self, status: int, body: Any, charset: str | None = "ISO-8859-15") -> None:
        self.status = status
        self.charset = charset
        self._raw = body if isinstance(body, bytes) else json.dumps(body).encode(charset or "utf-8")

    async def read(self) -> bytes:
        return self._raw

    async def __aenter__(self) -> Response:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class Session:
    def __init__(self, responses: list[Response | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    def get(self, url: str, *, headers: dict[str, str], timeout: object) -> Response:
        self.calls.append((url, headers))
        response = self.responses.pop(0)
        if isinstance(response, Exception):
            raise response
        return response


def meta(status: int = 200) -> dict[str, Any]:
    return {"descripcion": "exito", "estado": status, "datos": DATA_URL, "metadatos": "x"}


def provider(session: Session) -> aemet.AemetProvider:
    return aemet.AemetProvider(session, "KEY")  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("value", "expected"),
    [("424610N", 42 + 46 / 60 + 10 / 3600), ("013909W", -(1 + 39 / 60 + 9 / 3600))],
)
def test_parse_dms(value: str, expected: float) -> None:
    assert aemet.parse_dms(value) == pytest.approx(expected)


def test_parse_dms_rejects_garbage() -> None:
    with pytest.raises(ProviderResponseError):
        aemet.parse_dms("42.8")


@pytest.mark.parametrize(
    ("value", "expected"),
    [("12,4", 12.4), ("Ip", 0.0), ("Acum", None), ("", None), (None, None), (3, 3.0), ("x", None)],
)
def test_parse_number(value: Any, expected: float | None) -> None:
    assert aemet.parse_number(value) == expected


def test_parse_daily() -> None:
    series = aemet.parse_daily(DAILY)
    values = {d.isoformat(): series.get(Variable.PRECIPITATION, d).value for d in series.dates()}
    assert values == {"2026-11-01": 12.4, "2026-11-02": 0.0, "2026-11-04": 0.0}
    reading = series.get(Variable.PRECIPITATION, date(2026, 11, 1))
    assert reading.source.kind is DataKind.STATION
    assert reading.source.model == "9263D"
    assert series.variables() == {Variable.PRECIPITATION}  # temperatures are not used


def test_parse_stations() -> None:
    (station,) = aemet.parse_stations(STATIONS)
    assert station.id == "9263D"
    assert station.name == "Pamplona Aeropuerto"
    assert station.altitude == 459
    assert station.distance_km(42.6713, -2.031) == pytest.approx(33, abs=2)


async def test_fetch_daily_two_steps() -> None:
    session = Session([Response(200, meta()), Response(200, DAILY)])
    series = await provider(session).async_fetch_daily("9263D", date(2026, 8, 7), date(2026, 11, 6))
    (url1, headers1), (url2, headers2) = session.calls
    assert url1.endswith(
        "/valores/climatologicos/diarios/datos/fechaini/2026-08-07T00:00:00UTC"
        "/fechafin/2026-11-06T23:59:59UTC/estacion/9263D"
    )
    assert headers1["api_key"] == "KEY"
    assert url2 == DATA_URL
    assert "api_key" not in headers2
    assert len(series.dates()) == 3


async def test_no_data_is_empty() -> None:
    session = Session([Response(200, meta(404) | {"datos": None})])
    series = await provider(session).async_fetch_daily(
        "9263D", date(2026, 11, 1), date(2026, 11, 6)
    )
    assert len(series) == 0


@pytest.mark.parametrize(
    ("responses", "error"),
    [
        ([Response(200, meta(401))], aemet.AemetAuthError),
        ([Response(401, {})], aemet.AemetAuthError),
        ([Response(200, meta(429))], ProviderRateLimitError),
        ([Response(429, {})], ProviderRateLimitError),
        ([Response(503, {})], ProviderConnectionError),
        ([Response(400, {})], ProviderResponseError),
        ([Response(200, meta(500))], ProviderResponseError),
        ([Response(200, b"not json")], ProviderResponseError),
        ([Response(200, meta()), Response(200, {"not": "a list"})], ProviderResponseError),
        ([aiohttp.ClientConnectionError("down")], ProviderConnectionError),
    ],
)
async def test_errors(responses: list[Response | Exception], error: type[Exception]) -> None:
    with pytest.raises(error):
        await provider(Session(responses)).async_stations()


async def test_latin1_payload() -> None:
    body = json.dumps([STATIONS[0] | {"nombre": "LEKUNBERRI MONTAÑA"}], ensure_ascii=False)
    session = Session(
        [Response(200, meta()), Response(200, body.encode("iso-8859-15"), charset=None)]
    )
    (station,) = await provider(session).async_stations()
    assert station.name == "Lekunberri Montaña"


@pytest.mark.parametrize(
    ("station", "start", "end"),
    [
        ("92-63", date(2026, 11, 1), date(2026, 11, 6)),
        ("9263D", date(2026, 1, 1), date(2026, 11, 6)),
        ("9263D", date(2026, 11, 6), date(2026, 11, 1)),
    ],
)
async def test_fetch_daily_validation(station: str, start: date, end: date) -> None:
    with pytest.raises(ValueError, match="AEMET"):
        await provider(Session([])).async_fetch_daily(station, start, end)
