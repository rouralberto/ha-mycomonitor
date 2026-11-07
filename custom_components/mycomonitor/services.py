"""Services: record, export and delete observations."""

from __future__ import annotations

from datetime import date
from typing import TYPE_CHECKING, Any

from homeassistant.core import HomeAssistant, ServiceCall, ServiceResponse, SupportsResponse
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import config_validation as cv
from homeassistant.util import dt as dt_util
import probatio as vol

from .const import DOMAIN, HABITATS
from .core.observations import OTHER_SPECIES, ExportOptions, Outcome, Quantity

if TYPE_CHECKING:
    from . import MycoMonitorData
    from .coordinator import LocationCoordinator

SERVICE_RECORD = "record_observation"
SERVICE_EXPORT = "export_observations"
SERVICE_DELETE = "delete_observation"

RECORD_SCHEMA = vol.Schema(
    {
        vol.Required("location"): cv.string,
        vol.Required("species"): cv.string,
        vol.Optional("date"): cv.date,
        vol.Required("outcome"): vol.In([o.value for o in Outcome]),
        vol.Optional("quantity"): vol.In([q.value for q in Quantity]),
        vol.Optional("habitat"): vol.In(HABITATS),
        vol.Optional("notes", default=""): cv.string,
        vol.Optional("latitude"): vol.All(vol.Coerce(float), vol.Range(min=-90, max=90)),
        vol.Optional("longitude"): vol.All(vol.Coerce(float), vol.Range(min=-180, max=180)),
        vol.Optional("photo"): cv.string,
    }
)
EXPORT_SCHEMA = vol.Schema(
    {
        vol.Optional("format", default="csv"): vol.In(["csv", "geojson"]),
        vol.Optional("include_coordinates", default=False): cv.boolean,
        vol.Optional("decimals", default=5): vol.All(vol.Coerce(int), vol.Range(min=0, max=6)),
        vol.Optional("location"): cv.string,
    }
)
DELETE_SCHEMA = vol.Schema({vol.Required("id"): cv.string})


def _data(hass: HomeAssistant) -> MycoMonitorData:
    entries = hass.config_entries.async_loaded_entries(DOMAIN)
    if not entries:
        raise ServiceValidationError(translation_domain=DOMAIN, translation_key="not_loaded")
    data: MycoMonitorData = entries[0].runtime_data
    return data


def find_location(data: MycoMonitorData, location: str) -> LocationCoordinator:
    """A location by sub-entry id or (case-insensitive) name."""
    if location in data.coordinators:
        return data.coordinators[location]
    for coordinator in data.coordinators.values():
        if coordinator.location.name.casefold() == location.strip().casefold():
            return coordinator
    raise ServiceValidationError(
        translation_domain=DOMAIN,
        translation_key="unknown_location",
        translation_placeholders={"location": location},
    )


def async_setup_services(hass: HomeAssistant) -> None:
    """Register the observation services."""

    async def record(call: ServiceCall) -> ServiceResponse:
        from .observations import ObservationError

        data = _data(hass)
        coordinator = find_location(data, call.data["location"])
        if call.data["species"] != OTHER_SPECIES and call.data["species"] not in data.profiles:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_species",
                translation_placeholders={"species": call.data["species"]},
            )
        try:
            obs = await data.observations.async_record(
                coordinator,
                species=call.data["species"],
                day=call.data.get("date") or dt_util.now().date(),
                outcome=call.data["outcome"],
                quantity=call.data.get("quantity"),
                habitat=call.data.get("habitat"),
                notes=call.data["notes"],
                latitude=call.data.get("latitude"),
                longitude=call.data.get("longitude"),
                photo=call.data.get("photo"),
            )
        except ObservationError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="invalid_observation",
                translation_placeholders={"error": str(err)},
            ) from err
        return {"id": obs.id, "has_snapshot": obs.snapshot is not None}

    async def export(call: ServiceCall) -> ServiceResponse:
        data = _data(hass)
        location_id = (
            find_location(data, call.data["location"]).subentry_id
            if call.data.get("location")
            else None
        )
        fmt = call.data["format"]
        if fmt == "geojson" and not call.data["include_coordinates"]:
            raise ServiceValidationError(
                translation_domain=DOMAIN, translation_key="geojson_needs_coordinates"
            )
        options = ExportOptions(
            include_coordinates=call.data["include_coordinates"], decimals=call.data["decimals"]
        )
        path, count = await data.observations.async_export(fmt, options, location_id)
        return {"path": str(path), "count": count}

    async def delete(call: ServiceCall) -> ServiceResponse:
        removed = await _data(hass).observations.async_delete([call.data["id"]])
        if not removed:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_observation",
                translation_placeholders={"id": call.data["id"]},
            )
        return {"deleted": removed}

    hass.services.async_register(
        DOMAIN, SERVICE_RECORD, record, RECORD_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, SERVICE_EXPORT, export, EXPORT_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )
    hass.services.async_register(
        DOMAIN, SERVICE_DELETE, delete, DELETE_SCHEMA, supports_response=SupportsResponse.OPTIONAL
    )


def parse_date(value: Any) -> date:
    """Accept a date or an ISO string (used by the options flow)."""
    return value if isinstance(value, date) else date.fromisoformat(str(value))
