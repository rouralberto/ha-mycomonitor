"""Per location: are conditions favourable for at least one species?"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from homeassistant.components.binary_sensor import BinarySensorEntity
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .const import CONF_FAVORABLE_THRESHOLD, DEFAULT_FAVORABLE_THRESHOLD
from .coordinator import LocationCoordinator
from .entity import MycoMonitorEntity

if TYPE_CHECKING:
    from . import MycoMonitorConfigEntry


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MycoMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """One binary sensor per location."""
    threshold = float(entry.options.get(CONF_FAVORABLE_THRESHOLD, DEFAULT_FAVORABLE_THRESHOLD))
    for subentry_id, coordinator in entry.runtime_data.items():
        async_add_entities(
            [FavorableConditionsSensor(coordinator, threshold)], config_subentry_id=subentry_id
        )


class FavorableConditionsSensor(MycoMonitorEntity, BinarySensorEntity):
    """On when any species' index reaches the configured threshold."""

    _attr_translation_key = "favorable_conditions"
    _unrecorded_attributes = frozenset({"favorable_species", "threshold"})

    def __init__(self, coordinator: LocationCoordinator, threshold: float) -> None:
        super().__init__(coordinator, Platform.BINARY_SENSOR, "favorable_conditions")
        self._threshold = threshold

    def _ranked(self) -> list[tuple[str, float]]:
        ranked = [
            (pid, result.index)
            for pid, result in self.coordinator.data.species.items()
            if result.index is not None
        ]
        return sorted(ranked, key=lambda item: item[1], reverse=True)

    @property
    def is_on(self) -> bool | None:
        ranked = self._ranked()
        if not ranked:
            return None
        return ranked[0][1] >= self._threshold

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        ranked = self._ranked()
        return {
            "threshold": self._threshold,
            "best_species": ranked[0][0] if ranked else None,
            "best_index": ranked[0][1] if ranked else None,
            "favorable_species": [
                {"species": pid, "index": index}
                for pid, index in ranked
                if index >= self._threshold
            ],
        }
