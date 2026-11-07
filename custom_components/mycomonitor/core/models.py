"""Data model shared by providers, indicators and (later) the species engine.

Everything here is plain Python: no Home Assistant imports, so the core can be
tested in isolation and reused outside Home Assistant.
"""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import date, timedelta
from enum import StrEnum
import math


class Variable(StrEnum):
    """A daily environmental variable, in fixed units (see `UNITS`)."""

    PRECIPITATION = "precipitation"
    TEMPERATURE_MEAN = "temperature_mean"
    TEMPERATURE_MIN = "temperature_min"
    TEMPERATURE_MAX = "temperature_max"
    HUMIDITY_MEAN = "humidity_mean"
    ET0 = "et0"
    SOIL_MOISTURE_0_7CM = "soil_moisture_0_7cm"
    SOIL_MOISTURE_7_28CM = "soil_moisture_7_28cm"
    SOIL_TEMPERATURE_0_7CM = "soil_temperature_0_7cm"
    SOIL_TEMPERATURE_7_28CM = "soil_temperature_7_28cm"


UNITS: dict[Variable, str] = {
    Variable.PRECIPITATION: "mm",
    Variable.TEMPERATURE_MEAN: "°C",
    Variable.TEMPERATURE_MIN: "°C",
    Variable.TEMPERATURE_MAX: "°C",
    Variable.HUMIDITY_MEAN: "%",
    Variable.ET0: "mm",
    Variable.SOIL_MOISTURE_0_7CM: "m³/m³",
    Variable.SOIL_MOISTURE_7_28CM: "m³/m³",
    Variable.SOIL_TEMPERATURE_0_7CM: "°C",
    Variable.SOIL_TEMPERATURE_7_28CM: "°C",
}


class DataKind(StrEnum):
    """What a value is, so it is never mistaken for something stronger.

    MEASURED  a sensor at the location (a Home Assistant entity).
    STATION   an official weather station near the location (e.g. AEMET).
    ANALYSIS  a weather model's estimate of the past (analysis/reanalysis).
              Modelled, not measured.
    FORECAST  a weather model's prediction (today and later).
    """

    MEASURED = "measured"
    STATION = "station"
    ANALYSIS = "analysis"
    FORECAST = "forecast"


@dataclass(frozen=True, slots=True)
class Source:
    """Where a value came from: provider, kind and, for models, the grid cell used."""

    provider: str
    kind: DataKind
    model: str | None = None
    grid_latitude: float | None = None
    grid_longitude: float | None = None
    grid_elevation: float | None = None


@dataclass(frozen=True, slots=True)
class Reading:
    """One daily value with its provenance."""

    value: float
    source: Source


@dataclass(frozen=True, slots=True)
class Location:
    """A monitoring location.

    `altitude` is used to adjust model temperatures to the point; leave it None
    to let the provider use its terrain model.
    """

    name: str
    latitude: float
    longitude: float
    altitude: float | None = None

    def __post_init__(self) -> None:
        if not self.name.strip():
            raise ValueError("location name must not be empty")
        if not -90 <= self.latitude <= 90:
            raise ValueError(f"latitude out of range: {self.latitude}")
        if not -180 <= self.longitude <= 180:
            raise ValueError(f"longitude out of range: {self.longitude}")
        if self.altitude is not None and not -500 <= self.altitude <= 9000:
            raise ValueError(f"altitude out of range: {self.altitude}")


EARTH_RADIUS_KM = 6371.0088


def distance_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    """Great-circle (haversine) distance between two points, in km."""
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = phi2 - phi1
    dlmb = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlmb / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def grid_distance_km(location: Location, source: Source) -> float | None:
    """How far the model grid cell behind `source` is from `location`, if known."""
    if source.grid_latitude is None or source.grid_longitude is None:
        return None
    return distance_km(
        location.latitude, location.longitude, source.grid_latitude, source.grid_longitude
    )


def date_range(end: date, days: int) -> list[date]:
    """The `days` calendar dates ending at `end` (inclusive), oldest first."""
    if days < 1:
        raise ValueError("days must be >= 1")
    return [end - timedelta(days=offset) for offset in range(days - 1, -1, -1)]


class DailySeries:
    """Daily readings per variable, keyed by the location's local calendar date."""

    def __init__(self) -> None:
        self._data: dict[Variable, dict[date, Reading]] = {}

    def put(self, variable: Variable, day: date, reading: Reading) -> None:
        """Store a reading, replacing any existing one for that day."""
        self._data.setdefault(variable, {})[day] = reading

    def get(self, variable: Variable, day: date) -> Reading | None:
        """The reading for a day, or None when there is none."""
        return self._data.get(variable, {}).get(day)

    def window(self, variable: Variable, end: date, days: int) -> list[Reading | None]:
        """Readings for the `days` dates ending at `end`, oldest first; gaps are None."""
        values = self._data.get(variable, {})
        return [values.get(day) for day in date_range(end, days)]

    def variables(self) -> set[Variable]:
        """Variables with at least one reading."""
        return {variable for variable, values in self._data.items() if values}

    def dates(self, variable: Variable | None = None) -> list[date]:
        """Sorted dates with data, for one variable or for any."""
        if variable is not None:
            return sorted(self._data.get(variable, {}))
        return sorted({day for values in self._data.values() for day in values})

    def fill_gaps_from(
        self, other: DailySeries, *, where: Callable[[date], bool] | None = None
    ) -> None:
        """Copy readings from `other` only where this series has none.

        `where` optionally restricts which dates may be filled.
        """
        for variable, values in other._data.items():
            own = self._data.setdefault(variable, {})
            for day, reading in values.items():
                if day not in own and (where is None or where(day)):
                    own[day] = reading

    def sources(self) -> set[Source]:
        """Every distinct source contributing to the series."""
        return {r.source for values in self._data.values() for r in values.values()}

    def __len__(self) -> int:
        return sum(len(values) for values in self._data.values())

    @classmethod
    def from_values(
        cls,
        variable: Variable,
        start: date,
        values: Iterable[float | None],
        source: Source,
    ) -> DailySeries:
        """Build a single-variable series from consecutive daily values (None = gap)."""
        series = cls()
        for offset, value in enumerate(values):
            if value is not None:
                series.put(variable, start + timedelta(days=offset), Reading(value, source))
        return series
