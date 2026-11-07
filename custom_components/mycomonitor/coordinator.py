"""One coordinator per monitoring location."""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime
import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_ALTITUDE,
    DOMAIN,
    FORECAST_DAYS,
    PAST_DAYS,
    RETRY_INTERVAL,
    STALE_DATA_GRACE,
    UPDATE_INTERVAL,
)
from .core.indicators import Indicator, compute_indicators
from .core.models import Location, Source
from .core.providers.base import ProviderError
from .core.providers.open_meteo import OpenMeteoProvider

if TYPE_CHECKING:
    from . import MycoMonitorConfigEntry

_LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class LocationData:
    """The latest computed state of one location."""

    today: date
    indicators: dict[str, Indicator]
    sources: tuple[Source, ...]
    warnings: tuple[str, ...]
    fetched_at: datetime
    stale: bool = False


def location_from_subentry(subentry: ConfigSubentry) -> Location:
    """Build the core `Location` from a location sub-entry."""
    return Location(
        name=subentry.title,
        latitude=subentry.data["latitude"],
        longitude=subentry.data["longitude"],
        altitude=subentry.data.get(CONF_ALTITUDE),
    )


class LocationCoordinator(DataUpdateCoordinator[LocationData]):
    """Fetches weather data for one location and computes its indicators."""

    config_entry: MycoMonitorConfigEntry

    def __init__(
        self, hass: HomeAssistant, entry: MycoMonitorConfigEntry, subentry: ConfigSubentry
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title}",
            update_interval=UPDATE_INTERVAL,
        )
        self.subentry_id = subentry.subentry_id
        self.location = location_from_subentry(subentry)
        self.habitats: list[str] = list(subentry.data.get("habitats", []))
        self.provider = OpenMeteoProvider(async_get_clientsession(hass))

    async def _async_update_data(self) -> LocationData:
        try:
            result = await self.provider.async_fetch(
                self.location, past_days=PAST_DAYS, forecast_days=FORECAST_DAYS
            )
        except ProviderError as err:
            if self.data is not None and dt_util.utcnow() - self.data.fetched_at < STALE_DATA_GRACE:
                _LOGGER.warning(
                    "%s: update failed (%s); keeping data from %s",
                    self.location.name,
                    err,
                    self.data.fetched_at.isoformat(timespec="minutes"),
                )
                self.update_interval = RETRY_INTERVAL
                return replace(self.data, stale=True)
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="update_failed",
                translation_placeholders={"location": self.location.name, "error": str(err)},
                retry_after=RETRY_INTERVAL.total_seconds(),
            ) from err

        self.update_interval = UPDATE_INTERVAL
        for warning in result.warnings:
            _LOGGER.debug("%s: %s", self.location.name, warning)
        return LocationData(
            today=result.today,
            indicators=compute_indicators(result.series, result.today),
            sources=tuple(
                sorted(result.series.sources(), key=lambda s: (s.kind, s.provider, s.model or ""))
            ),
            warnings=tuple(result.warnings),
            fetched_at=dt_util.utcnow(),
        )
