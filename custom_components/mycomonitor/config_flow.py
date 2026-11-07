"""Config flow: the hub entry, plus one sub-entry per monitoring location.

The initial setup creates the hub together with its first location. More
locations are added (and edited) from the integration page as sub-entries.
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any, override

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    LocationSelector,
    LocationSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)
import probatio as vol

from .const import CONF_ALTITUDE, CONF_HABITATS, CONF_LOCATION, DOMAIN, HABITATS, SUBENTRY_LOCATION
from .core.models import Location


def _schema() -> vol.Schema:
    return vol.Schema(
        {
            vol.Required(CONF_NAME): TextSelector(),
            vol.Required(CONF_LOCATION): LocationSelector(LocationSelectorConfig(radius=False)),
            vol.Optional(CONF_ALTITUDE): NumberSelector(
                NumberSelectorConfig(
                    min=-500, max=9000, step=1, unit_of_measurement="m", mode=NumberSelectorMode.BOX
                )
            ),
            vol.Required(CONF_HABITATS): SelectSelector(
                SelectSelectorConfig(options=HABITATS, multiple=True, translation_key="habitat")
            ),
        }
    )


def _suggested(hass: HomeAssistant, data: Mapping[str, Any] | None) -> dict[str, Any]:
    """Form values: from existing data, or Home Assistant's home location."""
    if data is None:
        return {
            CONF_NAME: hass.config.location_name,
            CONF_LOCATION: {"latitude": hass.config.latitude, "longitude": hass.config.longitude},
            CONF_HABITATS: [],
        }
    suggested = {
        CONF_NAME: data[CONF_NAME],
        CONF_LOCATION: {"latitude": data["latitude"], "longitude": data["longitude"]},
        CONF_HABITATS: data[CONF_HABITATS],
    }
    if data.get(CONF_ALTITUDE) is not None:
        suggested[CONF_ALTITUDE] = data[CONF_ALTITUDE]
    return suggested


def _validate(user_input: Mapping[str, Any]) -> tuple[dict[str, Any], dict[str, str]]:
    """Turn form input into sub-entry data, or errors."""
    name = str(user_input[CONF_NAME]).strip()
    position = user_input[CONF_LOCATION]
    altitude = user_input.get(CONF_ALTITUDE)
    data: dict[str, Any] = {
        CONF_NAME: name,
        "latitude": round(float(position["latitude"]), 5),
        "longitude": round(float(position["longitude"]), 5),
        CONF_ALTITUDE: float(altitude) if altitude is not None else None,
        CONF_HABITATS: [h for h in HABITATS if h in user_input.get(CONF_HABITATS, [])],
    }
    errors: dict[str, str] = {}
    try:
        Location(name, data["latitude"], data["longitude"], data[CONF_ALTITUDE])
    except ValueError:
        errors["base"] = "invalid_location"
    if not data[CONF_HABITATS]:
        errors[CONF_HABITATS] = "no_habitat"
    return data, errors


def _unique_id(data: Mapping[str, Any]) -> str:
    """Two locations at the same point (to ~100 m) are duplicates."""
    return f"{data['latitude']:.3f},{data['longitude']:.3f}"


def _subentry(data: dict[str, Any]) -> ConfigSubentryData:
    return ConfigSubentryData(
        subentry_type=SUBENTRY_LOCATION,
        title=data[CONF_NAME],
        unique_id=_unique_id(data),
        data=data,
    )


class MycoMonitorConfigFlow(ConfigFlow, domain=DOMAIN):
    """Set up MycoMonitor and its first location."""

    VERSION = 1

    @classmethod
    @callback
    @override
    def async_get_supported_subentry_types(
        cls, config_entry: ConfigEntry
    ) -> dict[str, type[ConfigSubentryFlow]]:
        """Locations are sub-entries."""
        return {SUBENTRY_LOCATION: LocationSubentryFlow}

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Ask for the first location."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = _validate(user_input)
            if not errors:
                return self.async_create_entry(
                    title="MycoMonitor",
                    data={},
                    subentries=[_subentry(data)],
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _schema(), user_input or _suggested(self.hass, None)
            ),
            errors=errors,
        )


class LocationSubentryFlow(ConfigSubentryFlow):
    """Add or edit a monitoring location."""

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> SubentryFlowResult:
        """Add a location."""
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = _validate(user_input)
            if not errors:
                unique_id = _unique_id(data)
                if any(s.unique_id == unique_id for s in self._get_entry().subentries.values()):
                    return self.async_abort(reason="already_configured")
                return self.async_create_entry(
                    title=data[CONF_NAME], data=data, unique_id=unique_id
                )
        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                _schema(), user_input or _suggested(self.hass, None)
            ),
            errors=errors,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> SubentryFlowResult:
        """Edit a location."""
        entry = self._get_entry()
        subentry = self._get_reconfigure_subentry()
        errors: dict[str, str] = {}
        if user_input is not None:
            data, errors = _validate(user_input)
            if not errors:
                unique_id = _unique_id(data)
                if any(
                    s.unique_id == unique_id and s.subentry_id != subentry.subentry_id
                    for s in entry.subentries.values()
                ):
                    return self.async_abort(reason="already_configured")
                # The entry's update listener reloads it.
                return self.async_update_and_abort(
                    entry, subentry, title=data[CONF_NAME], data=data, unique_id=unique_id
                )
        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                _schema(), user_input or _suggested(self.hass, subentry.data)
            ),
            errors=errors,
        )
