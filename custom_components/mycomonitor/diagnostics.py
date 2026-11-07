"""Diagnostics. Location coordinates are redacted; grid cells are given as distances."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.core import HomeAssistant

from .core.models import grid_distance_km

if TYPE_CHECKING:
    from . import MycoMonitorConfigEntry

TO_REDACT = {"latitude", "longitude"}


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: MycoMonitorConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for the hub and every location."""
    locations = []
    for subentry_id, coordinator in entry.runtime_data.coordinators.items():
        subentry = entry.subentries[subentry_id]
        data = coordinator.data
        location: dict[str, Any] = {
            "title": subentry.title,
            "config": async_redact_data(dict(subentry.data), TO_REDACT),
            "last_update_success": coordinator.last_update_success,
            "last_exception": repr(coordinator.last_exception)
            if coordinator.last_exception
            else None,
            "update_interval_s": coordinator.update_interval.total_seconds()
            if coordinator.update_interval
            else None,
        }
        if data is not None:
            location |= {
                "today": data.today.isoformat(),
                "fetched_at": data.fetched_at.isoformat(),
                "stale": data.stale,
                "warnings": list(data.warnings),
                "sources": [
                    {
                        "provider": s.provider,
                        "kind": s.kind.value,
                        "model": s.model,
                        "grid_distance_km": round(d, 1)
                        if (d := grid_distance_km(coordinator.location, s)) is not None
                        else None,
                        "grid_elevation_m": s.grid_elevation,
                        "location_altitude_m": coordinator.location.altitude,
                    }
                    for s in data.sources
                ],
                "indicators": {
                    key: {
                        "value": i.value,
                        "unit": i.unit,
                        "window": [i.start.isoformat(), i.end.isoformat()],
                        "coverage": i.coverage,
                        "kinds": sorted(k.value for k in i.kinds),
                    }
                    for key, i in data.indicators.items()
                },
            }
        locations.append(location)
    observations = entry.runtime_data.observations.observations
    return {
        "entry": {"title": entry.title, "version": entry.version},
        "options": {k: v for k, v in entry.options.items() if k != "aemet_api_key"},
        "locations": locations,
        # Counts only: observations hold sensitive coordinates and notes.
        "observations": {
            "total": len(observations),
            "with_coordinates": sum(1 for o in observations if o.has_coordinates),
            "without_snapshot": sum(1 for o in observations if o.snapshot is None),
        },
    }
