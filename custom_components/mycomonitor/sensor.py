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
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .coordinator import LocationCoordinator, LocationData
from .core.models import DataKind
from .entity import MycoMonitorEntity

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
    for subentry_id, coordinator in entry.runtime_data.items():
        entities: list[SensorEntity] = [
            IndicatorSensor(coordinator, description) for description in INDICATOR_SENSORS
        ]
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
