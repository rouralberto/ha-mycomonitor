"""A fake aiohttp session serving the recorded Open-Meteo fixtures."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from custom_components.mycomonitor.core.models import Location
from custom_components.mycomonitor.core.providers import open_meteo
from custom_components.mycomonitor.core.providers.base import ProviderResult

FIXTURES = Path(__file__).parent / "fixtures" / "open_meteo"
FIXTURE_PAST_DAYS = 35  # what scripts/record_fixtures.py requested


def load(name: str) -> dict[str, Any]:
    return json.loads((FIXTURES / f"{name}.json").read_text())


class FakeResponse:
    def __init__(self, status: int, payload: Any) -> None:
        self.status = status
        self._payload = payload

    async def json(self, content_type: str | None = None) -> Any:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload

    async def __aenter__(self) -> FakeResponse:
        return self

    async def __aexit__(self, *args: object) -> None:
        return None


class FakeSession:
    """Answers forecast and archive URLs from canned responses, recording calls."""

    def __init__(self, responses: dict[str, FakeResponse | Exception]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def get(self, url: str, *, params: dict[str, Any], timeout: object) -> FakeResponse:
        self.calls.append((url, dict(params)))
        response = self.responses[url]
        if isinstance(response, Exception):
            raise response
        return response


def session_with(
    forecast: Any | None = None, archive: Any | None = None, status: int = 200
) -> FakeSession:
    return FakeSession(
        {
            open_meteo.FORECAST_URL: FakeResponse(status, forecast or load("urbasa_forecast")),
            open_meteo.ARCHIVE_URL: FakeResponse(status, archive or load("urbasa_archive")),
        }
    )


async def fixture_result() -> ProviderResult:
    """The provider result for the recorded Urbasa fixtures."""
    provider = open_meteo.OpenMeteoProvider(session_with())  # type: ignore[arg-type]
    return await provider.async_fetch(
        Location("Urbasa", 42.84, -2.17), past_days=FIXTURE_PAST_DAYS, forecast_days=16
    )
