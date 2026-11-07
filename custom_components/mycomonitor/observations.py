"""Observation log: storage, snapshots, export.

Stored in `.storage/mycomonitor.observations` (file mode 0600). Coordinates
never leave this file except in an export that explicitly asks for them.
"""

from __future__ import annotations

from collections.abc import Iterable
from datetime import date
import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING, Any
import uuid

from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_send
from homeassistant.helpers.storage import Store
from homeassistant.util import dt as dt_util

from .const import DOMAIN
from .core.observations import (
    OTHER_SPECIES,
    SNAPSHOT_DAYS,
    ExportOptions,
    Observation,
    Outcome,
    Quantity,
    export_csv,
    export_geojson,
    make_snapshot,
)
from .core.providers.base import ProviderError
from .core.species.engine import SpeciesProfile

if TYPE_CHECKING:
    from .coordinator import LocationCoordinator

_LOGGER = logging.getLogger(__name__)

STORAGE_VERSION = 1
STORAGE_KEY = f"{DOMAIN}.observations"
SIGNAL_OBSERVATIONS_UPDATED = f"{DOMAIN}_observations_updated"
EXPORT_DIR = ("mycomonitor", "exports")
MAX_BACKFILL_PER_UPDATE = 3


class ObservationError(ValueError):
    """Invalid observation input. `key` is a translation key."""

    def __init__(self, key: str, message: str) -> None:
        super().__init__(message)
        self.key = key


class ObservationManager:
    """Owns the observation list and its persistence."""

    def __init__(self, hass: HomeAssistant, profiles: dict[str, SpeciesProfile]) -> None:
        self.hass = hass
        self._profiles = profiles
        self._store: Store[dict[str, Any]] = Store(
            hass, STORAGE_VERSION, STORAGE_KEY, private=True, atomic_writes=True
        )
        self._observations: dict[str, Observation] = {}

    async def async_load(self) -> None:
        data = await self._store.async_load() or {}
        for raw in data.get("observations", []):
            try:
                obs = Observation.from_dict(raw)
            except (KeyError, ValueError) as err:
                _LOGGER.warning("Skipping unreadable observation: %s", err)
                continue
            self._observations[obs.id] = obs

    @property
    def observations(self) -> list[Observation]:
        return sorted(self._observations.values(), key=lambda o: (o.day, o.created_at))

    def for_location(self, location_id: str) -> list[Observation]:
        return [o for o in self.observations if o.location_id == location_id]

    def get(self, observation_id: str) -> Observation | None:
        return self._observations.get(observation_id)

    async def async_record(
        self,
        coordinator: LocationCoordinator,
        *,
        species: str,
        day: date,
        outcome: str,
        quantity: str | None = None,
        habitat: str | None = None,
        notes: str = "",
        latitude: float | None = None,
        longitude: float | None = None,
        photo: str | None = None,
    ) -> Observation:
        """Validate, snapshot (best effort) and store an observation."""
        if species != OTHER_SPECIES and species not in self._profiles:
            raise ObservationError("unknown_species", f"unknown species: {species}")
        if day > dt_util.now().date():
            raise ObservationError("future_date", "the date is in the future")
        if day < date(1950, 1, 1):
            raise ObservationError("invalid_date", "the date is too old")
        result = Outcome(outcome)
        if quantity is None:
            quantity = Quantity.NONE if result is Outcome.NOT_FOUND else Quantity.FEW
        try:
            obs = Observation(
                id=uuid.uuid4().hex,
                species=species,
                day=day,
                location_id=coordinator.subentry_id,
                location_name=coordinator.location.name,
                outcome=result,
                quantity=Quantity(quantity),
                created_at=dt_util.utcnow().isoformat(timespec="seconds"),
                habitat=habitat or None,
                notes=(notes or "").strip(),
                latitude=latitude,
                longitude=longitude,
                photo=photo or None,
            )
        except ValueError as err:
            raise ObservationError("invalid_observation", str(err)) from err

        obs = await self._async_with_snapshot(coordinator, obs)
        self._observations[obs.id] = obs
        await self._async_save()
        return obs

    async def async_delete(self, ids: Iterable[str]) -> int:
        removed = sum(1 for i in ids if self._observations.pop(i, None) is not None)
        if removed:
            await self._async_save()
        return removed

    async def async_backfill(self, coordinator: LocationCoordinator) -> None:
        """Retry snapshots that failed when recorded (a few per update)."""
        pending = [
            o
            for o in self.for_location(coordinator.subentry_id)
            if o.snapshot is None and o.day >= date(1950, 1, 1)
        ][:MAX_BACKFILL_PER_UPDATE]
        changed = False
        for obs in pending:
            updated = await self._async_with_snapshot(coordinator, obs)
            if updated.snapshot is not None:
                self._observations[obs.id] = updated
                changed = True
        if changed:
            await self._async_save()

    async def _async_with_snapshot(
        self, coordinator: LocationCoordinator, obs: Observation
    ) -> Observation:
        try:
            series = await coordinator.provider.async_fetch_history(
                coordinator.location, end=obs.day, days=SNAPSHOT_DAYS
            )
        except ProviderError as err:
            _LOGGER.warning("Observation %s saved without a snapshot (will retry): %s", obs.id, err)
            return obs
        snapshot = make_snapshot(
            series,
            obs.day,
            coordinator.location,
            coordinator.profile_for(obs.species),
            dt_util.utcnow(),
        )
        return obs.with_snapshot(snapshot)

    async def async_export(
        self, fmt: str, options: ExportOptions, location_id: str | None = None
    ) -> tuple[Path, int]:
        """Write an export file under <config>/mycomonitor/exports/; return path and count."""
        observations = (
            self.for_location(location_id) if location_id is not None else self.observations
        )
        if fmt == "geojson":
            document = export_geojson(observations, options)
            text = json.dumps(document, ensure_ascii=False, indent=2) + "\n"
            count = len(document["features"])
        else:
            text = export_csv(observations, options)
            count = len(observations)
        stamp = dt_util.now().strftime("%Y%m%d-%H%M%S")
        path = Path(self.hass.config.path(*EXPORT_DIR)) / f"observations-{stamp}.{fmt}"

        def write() -> None:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text(text, encoding="utf-8")

        await self.hass.async_add_executor_job(write)
        return path, count

    async def _async_save(self) -> None:
        await self._store.async_save({"observations": [o.to_dict() for o in self.observations]})
        self._notify()

    @callback
    def _notify(self) -> None:
        async_dispatcher_send(self.hass, SIGNAL_OBSERVATIONS_UPDATED)
