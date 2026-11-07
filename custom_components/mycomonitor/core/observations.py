"""Field observations (finds and empty visits) and the conditions that preceded them.

Each observation can carry a snapshot: the daily weather for the 92 days up
to the observation, the indicators on that day and the observed species'
index. Raw daily values are kept, not only derived features, so any future
model can recompute what it needs (see docs/observations.md).

Coordinates are optional and sensitive: they are only included in exports when
explicitly requested.
"""

from __future__ import annotations

from collections.abc import Iterable, Mapping
import csv
from dataclasses import dataclass, field, replace
from datetime import date, datetime, timedelta
from enum import StrEnum
import io
from typing import Any

from .indicators import compute_indicators
from .models import DailySeries, Location, Variable, grid_distance_km
from .species.engine import SpeciesProfile, indicator_lookup, score_species

SNAPSHOT_DAYS = 92
OTHER_SPECIES = "other"
EXPORT_INDICATORS = (
    "rain_7d",
    "rain_14d",
    "rain_30d",
    "api_30d",
    "water_balance_30d",
    "wet_days_14d",
    "dry_spell",
    "temperature_mean_14d",
    "temperature_min_7d",
    "frost_days_14d",
    "soil_moisture",
    "soil_moisture_trend_7d",
    "soil_temperature",
)


class Outcome(StrEnum):
    """Whether the species was found on the visit."""

    FOUND = "found"
    NOT_FOUND = "not_found"


class Quantity(StrEnum):
    """Approximate number of fruit bodies."""

    NONE = "none"
    FEW = "few"  # 1-5
    SOME = "some"  # 6-20
    MANY = "many"  # more than 20


@dataclass(frozen=True, slots=True)
class Snapshot:
    """Conditions leading up to an observation."""

    start: date
    daily: dict[str, list[float | None]]
    sources: list[dict[str, Any]]
    indicators: dict[str, float | None]
    species_index: float | None
    species_evidence: str | None
    created_at: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "start": self.start.isoformat(),
            "daily": self.daily,
            "sources": self.sources,
            "indicators": self.indicators,
            "species_index": self.species_index,
            "species_evidence": self.species_evidence,
            "created_at": self.created_at,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Snapshot:
        return cls(
            start=date.fromisoformat(data["start"]),
            daily={k: list(v) for k, v in data["daily"].items()},
            sources=list(data.get("sources", [])),
            indicators=dict(data.get("indicators", {})),
            species_index=data.get("species_index"),
            species_evidence=data.get("species_evidence"),
            created_at=str(data.get("created_at", "")),
        )


@dataclass(frozen=True, slots=True)
class Observation:
    """One visit: a find, or a search that found nothing."""

    id: str
    species: str
    day: date
    location_id: str
    location_name: str
    outcome: Outcome
    quantity: Quantity
    created_at: str
    habitat: str | None = None
    notes: str = ""
    latitude: float | None = None
    longitude: float | None = None
    photo: str | None = None
    snapshot: Snapshot | None = None

    def __post_init__(self) -> None:
        if (self.latitude is None) != (self.longitude is None):
            raise ValueError("give both latitude and longitude, or neither")
        if self.latitude is not None and not -90 <= self.latitude <= 90:
            raise ValueError("latitude out of range")
        if self.longitude is not None and not -180 <= self.longitude <= 180:
            raise ValueError("longitude out of range")
        if self.outcome is Outcome.NOT_FOUND and self.quantity is not Quantity.NONE:
            raise ValueError("a 'not found' visit has quantity 'none'")
        if self.outcome is Outcome.FOUND and self.quantity is Quantity.NONE:
            raise ValueError("a find needs a quantity")

    @property
    def has_coordinates(self) -> bool:
        return self.latitude is not None

    def with_snapshot(self, snapshot: Snapshot) -> Observation:
        return replace(self, snapshot=snapshot)

    def to_dict(self) -> dict[str, Any]:
        """Full record for storage (includes coordinates)."""
        return {
            "id": self.id,
            "species": self.species,
            "date": self.day.isoformat(),
            "location_id": self.location_id,
            "location_name": self.location_name,
            "outcome": self.outcome.value,
            "quantity": self.quantity.value,
            "created_at": self.created_at,
            "habitat": self.habitat,
            "notes": self.notes,
            "latitude": self.latitude,
            "longitude": self.longitude,
            "photo": self.photo,
            "snapshot": self.snapshot.to_dict() if self.snapshot else None,
        }

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> Observation:
        return cls(
            id=str(data["id"]),
            species=str(data["species"]),
            day=date.fromisoformat(data["date"]),
            location_id=str(data["location_id"]),
            location_name=str(data["location_name"]),
            outcome=Outcome(data["outcome"]),
            quantity=Quantity(data["quantity"]),
            created_at=str(data["created_at"]),
            habitat=data.get("habitat"),
            notes=str(data.get("notes") or ""),
            latitude=data.get("latitude"),
            longitude=data.get("longitude"),
            photo=data.get("photo"),
            snapshot=Snapshot.from_dict(data["snapshot"]) if data.get("snapshot") else None,
        )

    def summary(self) -> dict[str, Any]:
        """Safe to show anywhere: no coordinates, no notes, no photo."""
        return {
            "id": self.id,
            "date": self.day.isoformat(),
            "species": self.species,
            "outcome": self.outcome.value,
            "quantity": self.quantity.value,
            "location": self.location_name,
            "has_snapshot": self.snapshot is not None,
        }


def make_snapshot(
    series: DailySeries,
    day: date,
    location: Location,
    profile: SpeciesProfile | None,
    created_at: datetime,
) -> Snapshot:
    """Snapshot of the `SNAPSHOT_DAYS` days ending on `day`."""
    start = day - timedelta(days=SNAPSHOT_DAYS - 1)
    daily = {
        variable.value: [
            round(r.value, 3) if (r := series.get(variable, start + timedelta(days=n))) else None
            for n in range(SNAPSHOT_DAYS)
        ]
        for variable in Variable
    }
    sources = [
        {
            "provider": s.provider,
            "kind": s.kind.value,
            "model": s.model,
            "grid_distance_km": round(d, 1)
            if (d := grid_distance_km(location, s)) is not None
            else None,
            "grid_elevation_m": s.grid_elevation,
        }
        for s in sorted(series.sources(), key=lambda s: (s.kind, s.provider, s.model or ""))
    ]
    indicators = {
        key: round(i.value, 3) if i.value is not None else None
        for key, i in compute_indicators(series, day).items()
    }
    result = score_species(profile, indicator_lookup(series), day) if profile else None
    return Snapshot(
        start=start,
        daily=daily,
        sources=sources,
        indicators=indicators,
        species_index=result.index if result else None,
        species_evidence=result.evidence if result else None,
        created_at=created_at.isoformat(timespec="seconds"),
    )


@dataclass(frozen=True, slots=True)
class ExportOptions:
    """What an export may reveal."""

    include_coordinates: bool = False
    decimals: int = field(default=5)

    def __post_init__(self) -> None:
        if not 0 <= self.decimals <= 6:
            raise ValueError("decimals must be 0..6")


def _coordinates(obs: Observation, options: ExportOptions) -> tuple[float | None, float | None]:
    if not options.include_coordinates or obs.latitude is None or obs.longitude is None:
        return None, None
    return round(obs.latitude, options.decimals), round(obs.longitude, options.decimals)


def export_csv(observations: Iterable[Observation], options: ExportOptions) -> str:
    """One row per observation, with the indicators that preceded it."""
    columns = [
        "id",
        "date",
        "location",
        "species",
        "outcome",
        "quantity",
        "habitat",
        "notes",
        *(["latitude", "longitude"] if options.include_coordinates else []),
        "species_index",
        "species_evidence",
        *EXPORT_INDICATORS,
    ]
    buffer = io.StringIO()
    writer = csv.DictWriter(buffer, fieldnames=columns, lineterminator="\n")
    writer.writeheader()
    for obs in sorted(observations, key=lambda o: (o.day, o.created_at)):
        snapshot = obs.snapshot
        row: dict[str, Any] = {
            "id": obs.id,
            "date": obs.day.isoformat(),
            "location": obs.location_name,
            "species": obs.species,
            "outcome": obs.outcome.value,
            "quantity": obs.quantity.value,
            "habitat": obs.habitat or "",
            "notes": obs.notes,
            "species_index": snapshot.species_index if snapshot else "",
            "species_evidence": snapshot.species_evidence if snapshot else "",
        }
        if options.include_coordinates:
            row["latitude"], row["longitude"] = _coordinates(obs, options)
        for key in EXPORT_INDICATORS:
            value = snapshot.indicators.get(key) if snapshot else None
            row[key] = "" if value is None else value
        writer.writerow(row)
    return buffer.getvalue()


def export_geojson(observations: Iterable[Observation], options: ExportOptions) -> dict[str, Any]:
    """Observations with coordinates as a GeoJSON FeatureCollection.

    Only allowed with `include_coordinates`: a map without coordinates makes no sense,
    and coordinates must never be exported by default.
    """
    if not options.include_coordinates:
        raise ValueError("GeoJSON export needs include_coordinates")
    features = []
    for obs in sorted(observations, key=lambda o: (o.day, o.created_at)):
        lat, lon = _coordinates(obs, options)
        if lat is None or lon is None:
            continue
        properties = obs.summary() | {"habitat": obs.habitat, "notes": obs.notes}
        if obs.snapshot:
            properties["species_index"] = obs.snapshot.species_index
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lon, lat]},
                "properties": properties,
            }
        )
    return {"type": "FeatureCollection", "features": features}
