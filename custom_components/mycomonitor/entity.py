"""Base entity: one device per monitoring location."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceEntryType, DeviceInfo
from homeassistant.helpers.update_coordinator import CoordinatorEntity
from homeassistant.util import slugify

from .const import DOMAIN
from .coordinator import LocationCoordinator
from .core.providers.open_meteo import ATTRIBUTION


class MycoMonitorEntity(CoordinatorEntity[LocationCoordinator]):
    """An entity belonging to one location's device."""

    _attr_has_entity_name = True
    _attr_attribution = ATTRIBUTION

    def __init__(self, coordinator: LocationCoordinator, platform: str, key: str) -> None:
        super().__init__(coordinator)
        location = coordinator.location
        self._attr_unique_id = f"{coordinator.subentry_id}_{key}"
        # Language-independent entity IDs, e.g. sensor.mycomonitor_urbasa_rain_7d,
        # so example dashboards work whatever the UI language.
        self.entity_id = f"{platform}.{DOMAIN}_{slugify(location.name)}_{key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, coordinator.subentry_id)},
            name=location.name,
            manufacturer="MycoMonitor",
            model="Monitoring location",
            entry_type=DeviceEntryType.SERVICE,
        )
