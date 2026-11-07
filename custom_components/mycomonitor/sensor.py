"""Indicator sensors, one set per location."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING, Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    Platform,
    UnitOfPrecipitationDepth,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.dispatcher import async_dispatcher_connect
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LocationCoordinator, LocationData
from .core.models import DataKind
from .core.species.engine import Category, SpeciesProfile
from .entity import MycoMonitorEntity
from .observations import SIGNAL_OBSERVATIONS_UPDATED, ObservationManager

if TYPE_CHECKING:
    from . import MycoMonitorConfigEntry

MM = UnitOfPrecipitationDepth.MILLIMETERS
CELSIUS = UnitOfTemperature.CELSIUS
DAYS = UnitOfTime.DAYS
MEASUREMENT = SensorStateClass.MEASUREMENT


@dataclass(frozen=True, kw_only=True)
class IndicatorSensorDescription(SensorEntityDescription):
    """A sensor showing one core indicator."""

    scale: float = 1.0  # core value × scale = native value (m³/m³ → %)


def _indicator(
    key: str,
    unit: str | None,
    *,
    device_class: SensorDeviceClass | None = None,
    precision: int = 1,
    enabled: bool = True,
    scale: float = 1.0,
) -> IndicatorSensorDescription:
    return IndicatorSensorDescription(
        key=key,
        translation_key=key,
        native_unit_of_measurement=unit,
        device_class=device_class,
        state_class=MEASUREMENT,
        suggested_display_precision=precision,
        entity_registry_enabled_default=enabled,
        scale=scale,
    )


PRECIP = SensorDeviceClass.PRECIPITATION
TEMP = SensorDeviceClass.TEMPERATURE

INDICATOR_SENSORS: tuple[IndicatorSensorDescription, ...] = (
    _indicator("rain_3d", MM, device_class=PRECIP, enabled=False),
    _indicator("rain_7d", MM, device_class=PRECIP),
    _indicator("rain_14d", MM, device_class=PRECIP),
    _indicator("rain_21d", MM, device_class=PRECIP, enabled=False),
    _indicator("rain_30d", MM, device_class=PRECIP),
    _indicator("api_30d", MM, enabled=False),
    _indicator("water_balance_14d", MM, enabled=False),
    _indicator("water_balance_30d", MM),
    _indicator("wet_days_14d", DAYS, precision=0, enabled=False),
    _indicator("dry_spell", DAYS, device_class=SensorDeviceClass.DURATION, precision=0),
    _indicator(
        "wet_streak", DAYS, device_class=SensorDeviceClass.DURATION, precision=0, enabled=False
    ),
    _indicator("temperature_mean_7d", CELSIUS, device_class=TEMP, enabled=False),
    _indicator("temperature_mean_14d", CELSIUS, device_class=TEMP),
    _indicator("temperature_mean_21d", CELSIUS, device_class=TEMP, enabled=False),
    _indicator("temperature_min_7d", CELSIUS, device_class=TEMP),
    _indicator("temperature_max_7d", CELSIUS, device_class=TEMP, enabled=False),
    _indicator("frost_days_7d", DAYS, precision=0, enabled=False),
    _indicator("frost_days_14d", DAYS, precision=0),
    _indicator(
        "humidity_mean_7d", PERCENTAGE, device_class=SensorDeviceClass.HUMIDITY, enabled=False
    ),
    _indicator("soil_moisture", PERCENTAGE, device_class=SensorDeviceClass.MOISTURE, scale=100),
    _indicator(
        "soil_moisture_deep",
        PERCENTAGE,
        device_class=SensorDeviceClass.MOISTURE,
        scale=100,
        enabled=False,
    ),
    # Trends are changes, not levels: no device class (a temperature device
    # class would convert a °C difference to °F as if it were absolute).
    _indicator("soil_moisture_trend_7d", PERCENTAGE, scale=100),
    _indicator("soil_temperature", CELSIUS, device_class=TEMP),
    _indicator("soil_temperature_trend_7d", CELSIUS, enabled=False),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: MycoMonitorConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Add each location's sensors to its sub-entry."""
    for subentry_id, coordinator in entry.runtime_data.coordinators.items():
        entities: list[SensorEntity] = [
            IndicatorSensor(coordinator, description) for description in INDICATOR_SENSORS
        ]
        entities.extend(
            SpeciesSensor(coordinator, profile) for profile in coordinator.profiles.values()
        )
        entities.append(ObservationsSensor(coordinator, entry.runtime_data.observations))
        entities.append(LastUpdateSensor(coordinator))
        async_add_entities(entities, config_subentry_id=subentry_id)


class IndicatorSensor(MycoMonitorEntity, SensorEntity):
    """One indicator for one location."""

    entity_description: IndicatorSensorDescription
    _unrecorded_attributes = frozenset({"window_start", "window_end", "coverage", "data"})

    def __init__(
        self, coordinator: LocationCoordinator, description: IndicatorSensorDescription
    ) -> None:
        super().__init__(coordinator, Platform.SENSOR, description.key)
        self.entity_description = description

    @property
    def native_value(self) -> float | None:
        indicator = self.coordinator.data.indicators.get(self.entity_description.key)
        if indicator is None or indicator.value is None:
            return None
        return indicator.value * self.entity_description.scale

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        indicator = self.coordinator.data.indicators.get(self.entity_description.key)
        if indicator is None:
            return {}
        return {
            "window_start": indicator.start.isoformat(),
            "window_end": indicator.end.isoformat(),
            "coverage": round(indicator.coverage, 2),
            "data": sorted(kind.value for kind in indicator.kinds),
            "includes_forecast": DataKind.FORECAST in indicator.kinds,
        }


class SpeciesSensor(MycoMonitorEntity, SensorEntity):
    """Suitability index (0-100) for one species at one location. Not a probability."""

    _attr_state_class = SensorStateClass.MEASUREMENT
    _attr_suggested_display_precision = 0
    _unrecorded_attributes = frozenset(
        {"factors", "outlook", "scientific_name", "evidence", "data", "limiting_factor"}
    )

    def __init__(self, coordinator: LocationCoordinator, profile: SpeciesProfile) -> None:
        super().__init__(coordinator, Platform.SENSOR, profile.id)
        self._profile = profile
        self._attr_translation_key = profile.id

    @property
    def native_value(self) -> float | None:
        result = self.coordinator.data.species.get(self._profile.id)
        return result.index if result is not None else None

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        result = self.coordinator.data.species.get(self._profile.id)
        if result is None:
            return {}
        return {
            "category": result.category.value if result.category else None,
            "in_season": result.category is not Category.OUT_OF_SEASON,
            "limiting_factor": result.limiting_factor,
            "evidence": result.evidence,
            "scientific_name": self._profile.scientific_name,
            "data": sorted(kind.value for kind in result.kinds),
            "includes_forecast": DataKind.FORECAST in result.kinds,
            "factors": [
                {
                    "id": f.id,
                    "indicator": f.indicator,
                    "lag_days": f.lag,
                    "value": round(f.value, 2) if f.value is not None else None,
                    "unit": f.unit,
                    "score": round(f.score, 2) if f.score is not None else None,
                    "role": f.role.value,
                    "grade": f.grade,
                }
                for f in result.factors
            ],
            "outlook": [{"date": day.isoformat(), "index": index} for day, index in result.outlook],
        }


class ObservationsSensor(MycoMonitorEntity, SensorEntity):
    """How many observations were recorded at this location (no coordinates exposed)."""

    _attr_translation_key = "observations"
    _attr_suggested_display_precision = 0

    def __init__(self, coordinator: LocationCoordinator, manager: ObservationManager) -> None:
        super().__init__(coordinator, Platform.SENSOR, "observations")
        self._manager = manager

    @property
    def available(self) -> bool:
        return True  # the log is local; it doesn't depend on the weather data

    async def async_added_to_hass(self) -> None:
        await super().async_added_to_hass()
        self.async_on_remove(
            async_dispatcher_connect(self.hass, SIGNAL_OBSERVATIONS_UPDATED, self._refresh)
        )

    @callback
    def _refresh(self) -> None:
        self.async_write_ha_state()

    @property
    def native_value(self) -> int:
        return len(self._manager.for_location(self.coordinator.subentry_id))

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        observations = self._manager.for_location(self.coordinator.subentry_id)
        found = [o for o in observations if o.outcome.value == "found"]
        last = observations[-1].summary() if observations else None
        last_find = found[-1].summary() if found else None
        return {
            "found": len(found),
            "not_found": len(observations) - len(found),
            "last_observation": last,
            "last_find": last_find,
        }


@dataclass(frozen=True, kw_only=True)
class _Diagnostic(SensorEntityDescription):
    value: Callable[[LocationData], datetime]


LAST_UPDATE = _Diagnostic(
    key="last_update",
    translation_key="last_update",
    device_class=SensorDeviceClass.TIMESTAMP,
    entity_category=EntityCategory.DIAGNOSTIC,
    value=lambda data: data.fetched_at,
)


class LastUpdateSensor(MycoMonitorEntity, SensorEntity):
    """When the location's data was last fetched successfully."""

    entity_description: _Diagnostic

    def __init__(self, coordinator: LocationCoordinator) -> None:
        super().__init__(coordinator, Platform.SENSOR, LAST_UPDATE.key)
        self.entity_description = LAST_UPDATE

    @property
    def native_value(self) -> datetime:
        return self.entity_description.value(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        data = self.coordinator.data
        return {"stale": data.stale, "today": data.today.isoformat()}
