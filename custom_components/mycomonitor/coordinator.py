"""One coordinator per monitoring location.

Each update merges, per day and variable, in priority order:

1. measured: the location's own Home Assistant sensors (long-term statistics),
2. station: the chosen AEMET station's precipitation (optional, experimental),
3. model: Open-Meteo history and forecast.

Then it computes the indicators and the species indices.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta
import logging
from typing import TYPE_CHECKING

from homeassistant.config_entries import ConfigSubentry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from .const import (
    CONF_AEMET_API_KEY,
    CONF_AEMET_STATION,
    CONF_ALTITUDE,
    DOMAIN,
    FORECAST_DAYS,
    PAST_DAYS,
    RETRY_INTERVAL,
    STALE_DATA_GRACE,
    STATION_REFRESH,
    UPDATE_INTERVAL,
)
from .core.indicators import Indicator
from .core.models import DailySeries, Location, Source, Variable
from .core.providers.aemet import AemetProvider
from .core.providers.base import ProviderError
from .core.providers.open_meteo import OpenMeteoProvider
from .core.species.engine import (
    SpeciesProfile,
    SpeciesResult,
    indicator_lookup,
    score_with_outlook,
)
from .local_sensors import LOCAL_SENSORS, async_fetch_local

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
    species: dict[str, SpeciesResult]
    measured_days: dict[str, int]  # variable -> days from local sensors
    station_days: int = 0  # precipitation days from the AEMET station
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
    """Fetches data for one location and computes its indicators and species indices."""

    config_entry: MycoMonitorConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: MycoMonitorConfigEntry,
        subentry: ConfigSubentry,
        profiles: dict[str, SpeciesProfile],
    ) -> None:
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=f"{DOMAIN} {subentry.title}",
            update_interval=UPDATE_INTERVAL,
        )
        session = async_get_clientsession(hass)
        self.subentry_id = subentry.subentry_id
        self.location = location_from_subentry(subentry)
        self.habitats: list[str] = list(subentry.data.get("habitats", []))
        self.provider = OpenMeteoProvider(session)
        self.all_profiles = profiles
        # Only species whose habitats match this location's.
        self.profiles = {
            pid: profile
            for pid, profile in profiles.items()
            if profile.compatible_with(self.habitats)
        }
        self.local_entities = {
            key: entity for key in LOCAL_SENSORS if (entity := subentry.data.get(key))
        }
        self.station_id: str | None = subentry.data.get(CONF_AEMET_STATION) or None
        api_key = entry.options.get(CONF_AEMET_API_KEY)
        self.aemet = AemetProvider(session, api_key) if api_key and self.station_id else None
        self._station_series = DailySeries()
        self._station_fetched: datetime | None = None

    def profile_for(self, species: str) -> SpeciesProfile | None:
        """Any bundled profile (observations may name species outside the habitats)."""
        return self.all_profiles.get(species)

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
        warnings = list(result.warnings)
        series = DailySeries()
        measured = await self._async_local(result.today, warnings)
        series.fill_gaps_from(measured)
        station = await self._async_station(result.today, warnings)
        series.fill_gaps_from(station)
        series.fill_gaps_from(result.series)

        for warning in warnings:
            _LOGGER.debug("%s: %s", self.location.name, warning)
        lookup = indicator_lookup(series)
        return LocationData(
            today=result.today,
            indicators=dict(lookup(result.today)),
            species={
                pid: score_with_outlook(profile, lookup, result.today)
                for pid, profile in self.profiles.items()
            },
            sources=tuple(
                sorted(series.sources(), key=lambda s: (s.kind, s.provider, s.model or ""))
            ),
            warnings=tuple(warnings),
            fetched_at=dt_util.utcnow(),
            measured_days={
                variable.value: len(measured.dates(variable)) for variable in measured.variables()
            },
            station_days=len(station.dates(Variable.PRECIPITATION)),
        )

    async def _async_local(self, today: date, warnings: list[str]) -> DailySeries:
        if not self.local_entities:
            return DailySeries()
        try:
            return await async_fetch_local(self.hass, self.local_entities, today, PAST_DAYS)
        except Exception as err:
            warnings.append(f"local sensors unavailable: {err!r}")
            return DailySeries()

    async def _async_station(self, today: date, warnings: list[str]) -> DailySeries:
        """AEMET precipitation, refreshed at most every STATION_REFRESH (data is daily)."""
        if self.aemet is None or self.station_id is None:
            return DailySeries()
        now = dt_util.utcnow()
        if self._station_fetched is None or now - self._station_fetched >= STATION_REFRESH:
            try:
                self._station_series = await self.aemet.async_fetch_daily(
                    self.station_id, today - timedelta(days=PAST_DAYS), today - timedelta(days=1)
                )
                self._station_fetched = now
            except (ProviderError, ValueError) as err:
                warnings.append(f"AEMET station {self.station_id}: {err}")
        return self._station_series
