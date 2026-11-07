"""MycoMonitor: favourable mushroom-fruiting conditions for Home Assistant.

One config entry (the hub) with one sub-entry per monitoring location. Each
location gets its own coordinator and device. The environmental logic lives
in `core/`, which has no Home Assistant dependencies.
"""

from __future__ import annotations

import asyncio

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import DOMAIN, SUBENTRY_LOCATION
from .coordinator import LocationCoordinator

PLATFORMS: list[Platform] = [Platform.SENSOR]

type MycoMonitorConfigEntry = ConfigEntry[dict[str, LocationCoordinator]]


async def async_setup_entry(hass: HomeAssistant, entry: MycoMonitorConfigEntry) -> bool:
    """Set up a coordinator per location, then the platforms."""
    coordinators = {
        subentry.subentry_id: LocationCoordinator(hass, entry, subentry)
        for subentry in entry.get_subentries_of_type(SUBENTRY_LOCATION)
    }
    # Refresh (not first_refresh) so one failing location doesn't block the
    # others; a failed location retries soon and its entities stay unavailable.
    await asyncio.gather(*(c.async_refresh() for c in coordinators.values()))
    if coordinators and not any(c.last_update_success for c in coordinators.values()):
        raise ConfigEntryNotReady(translation_domain=DOMAIN, translation_key="no_data")

    entry.runtime_data = coordinators
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_update_listener(hass: HomeAssistant, entry: MycoMonitorConfigEntry) -> None:
    """Reload when locations are added, changed or removed."""
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MycoMonitorConfigEntry) -> bool:
    """Unload the platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
