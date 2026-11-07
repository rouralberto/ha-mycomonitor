"""MycoMonitor: favourable mushroom-fruiting conditions for Home Assistant.

One config entry (the hub) with one sub-entry per monitoring location. Each
location gets its own coordinator and device. The environmental logic lives
in `core/`, which has no Home Assistant dependencies.
"""

from __future__ import annotations

import asyncio
import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryNotReady

from .const import CONF_SPECIES_OVERRIDES, DOMAIN, SUBENTRY_LOCATION
from .coordinator import LocationCoordinator
from .core.species.engine import ProfileError, SpeciesProfile
from .core.species.loader import load_profiles

PLATFORMS: list[Platform] = [Platform.BINARY_SENSOR, Platform.SENSOR]

_LOGGER = logging.getLogger(__name__)

type MycoMonitorConfigEntry = ConfigEntry[dict[str, LocationCoordinator]]


async def async_setup_entry(hass: HomeAssistant, entry: MycoMonitorConfigEntry) -> bool:
    """Set up a coordinator per location, then the platforms."""
    profiles = _apply_overrides(
        await hass.async_add_executor_job(load_profiles),
        entry.options.get(CONF_SPECIES_OVERRIDES, {}),
    )
    coordinators = {
        subentry.subentry_id: LocationCoordinator(hass, entry, subentry, profiles)
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


def _apply_overrides(
    profiles: dict[str, SpeciesProfile], overrides: dict[str, dict[str, object]]
) -> dict[str, SpeciesProfile]:
    """Apply the user's threshold overrides; ignore (and log) any that became invalid."""
    result = {}
    for pid, profile in profiles.items():
        try:
            result[pid] = profile.with_overrides(overrides.get(pid))
        except ProfileError as err:
            _LOGGER.warning("Ignoring invalid overrides for %s: %s", pid, err)
            result[pid] = profile
    return result


async def _async_update_listener(hass: HomeAssistant, entry: MycoMonitorConfigEntry) -> None:
    """Reload when options or locations change."""
    hass.config_entries.async_schedule_reload(entry.entry_id)


async def async_unload_entry(hass: HomeAssistant, entry: MycoMonitorConfigEntry) -> bool:
    """Unload the platforms."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
