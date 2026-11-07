"""The interface every weather data provider implements."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Protocol

from ..models import DailySeries, Location


class ProviderError(Exception):
    """Base class for provider failures."""


class ProviderConnectionError(ProviderError):
    """The provider could not be reached (network error, timeout, 5xx)."""


class ProviderRateLimitError(ProviderError):
    """The provider refused the request because of rate limiting."""


class ProviderResponseError(ProviderError):
    """The provider answered, but with an error or data we cannot use."""


@dataclass(slots=True)
class ProviderResult:
    """Daily data for one location, plus anything the user should know about it."""

    series: DailySeries
    today: date  # "today" in the location's own time zone
    warnings: list[str] = field(default_factory=list)


class WeatherProvider(Protocol):
    """Fetches daily environmental data for a location.

    Implementations return history (`past_days` complete days before today)
    and forecast (`forecast_days` days starting today), each value tagged with
    its `Source`.
    """

    name: str

    async def async_fetch(
        self, location: Location, *, past_days: int, forecast_days: int
    ) -> ProviderResult:
        """Fetch history and forecast for `location`."""
        ...
