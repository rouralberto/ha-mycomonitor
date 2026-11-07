"""Config flow: the hub entry, plus one sub-entry per monitoring location.

The initial setup creates the hub together with its first location. More
locations are added (and edited) from the integration page as sub-entries.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, override

from homeassistant.config_entries import (
    ConfigEntry,
    ConfigFlow,
    ConfigFlowResult,
    ConfigSubentryData,
    ConfigSubentryFlow,
    OptionsFlow,
    SubentryFlowResult,
)
from homeassistant.const import CONF_NAME
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.selector import (
    BooleanSelector,
    DateSelector,
    LocationSelector,
    LocationSelectorConfig,
    MediaSelector,
    MediaSelectorConfig,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectOptionDict,
    SelectSelector,
    SelectSelectorConfig,
    SelectSelectorMode,
    TextSelector,
    TextSelectorConfig,
)
from homeassistant.util import dt as dt_util
import probatio as vol

from .const import (
    CONF_ALTITUDE,
    CONF_FAVORABLE_THRESHOLD,
    CONF_HABITATS,
    CONF_LOCATION,
    CONF_SPECIES_OVERRIDES,
    DEFAULT_FAVORABLE_THRESHOLD,
    DOMAIN,
    HABITATS,
    SUBENTRY_LOCATION,
)
from .core.models import Location
from .core.observations import OTHER_SPECIES, Outcome, Quantity
from .core.species.engine import Curve, ProfileError, SpeciesProfile
from .core.species.loader import load_profiles

SEASON_FIELDS = ("start", "peak_start", "peak_end", "end")
CONF_HABITATS_SINGLE = "habitat"


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

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: ConfigEntry) -> MycoMonitorOptionsFlow:
        """Hub options: settings and species thresholds."""
        return MycoMonitorOptionsFlow()

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


def format_curve(curve: Curve) -> str:
    """Curve as editable text: "10:0.05, 40:0.5, 80:1"."""
    return ", ".join(f"{x:g}:{y:g}" for x, y in curve)


def parse_curve(text: str) -> list[list[float]]:
    """Parse "x:y, x:y" text; raises ProfileError on bad input."""
    try:
        points = [[float(v) for v in pair.split(":")] for pair in text.split(",") if pair.strip()]
    except ValueError as err:
        raise ProfileError(f"not a number in {text!r}") from err
    if any(len(p) != 2 for p in points):
        raise ProfileError(f"use x:y pairs separated by commas: {text!r}")
    return points


class MycoMonitorOptionsFlow(OptionsFlow):
    """Settings and per-species thresholds. The entry reloads when options change."""

    def __init__(self) -> None:
        self._species: str | None = None
        self._profiles: dict[str, SpeciesProfile] = {}

    async def async_step_init(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        """Menu."""
        return self.async_show_menu(
            step_id="init",
            menu_options=["record_observation", "manage_observations", "settings", "species"],
        )

    async def async_step_settings(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """General settings."""
        if user_input is not None:
            return self.async_create_entry(
                data={
                    **self.config_entry.options,
                    CONF_FAVORABLE_THRESHOLD: int(user_input[CONF_FAVORABLE_THRESHOLD]),
                }
            )
        schema = vol.Schema(
            {
                vol.Required(
                    CONF_FAVORABLE_THRESHOLD,
                    default=self.config_entry.options.get(
                        CONF_FAVORABLE_THRESHOLD, DEFAULT_FAVORABLE_THRESHOLD
                    ),
                ): NumberSelector(
                    NumberSelectorConfig(min=1, max=100, step=1, mode=NumberSelectorMode.SLIDER)
                ),
            }
        )
        return self.async_show_form(step_id="settings", data_schema=schema)

    async def async_step_species(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Pick the species to edit."""
        self._profiles = await self.hass.async_add_executor_job(load_profiles)
        if user_input is not None:
            self._species = user_input["species"]
            return await self.async_step_species_edit()
        schema = vol.Schema(
            {
                vol.Required("species"): SelectSelector(
                    SelectSelectorConfig(options=list(self._profiles), translation_key="species")
                )
            }
        )
        return self.async_show_form(step_id="species", data_schema=schema)

    async def async_step_species_edit(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Edit one species' season and response curves."""
        assert self._species is not None
        default = self._profiles[self._species]
        all_overrides: dict[str, Any] = dict(
            self.config_entry.options.get(CONF_SPECIES_OVERRIDES, {})
        )
        current = default.with_overrides(all_overrides.get(self._species))
        errors: dict[str, str] = {}
        detail = ""

        if user_input is not None:
            if user_input.get("reset"):
                all_overrides.pop(self._species, None)
                return self._save_overrides(all_overrides)
            try:
                overrides = self._overrides_from_form(default, user_input)
                default.with_overrides(overrides)  # validates
            except ProfileError as err:
                errors["base"] = "invalid_override"
                detail = str(err)
            else:
                if overrides:
                    all_overrides[self._species] = overrides
                else:
                    all_overrides.pop(self._species, None)
                return self._save_overrides(all_overrides)

        fields: dict[Any, Any] = {}
        for name in SEASON_FIELDS:
            fields[vol.Required(f"season_{name}", default=getattr(current.season, name))] = (
                TextSelector()
            )
        for factor in current.factors:
            fields[vol.Required(f"curve_{factor.id}", default=format_curve(factor.curve))] = (
                TextSelector()
            )
        fields[vol.Optional("reset", default=False)] = BooleanSelector()
        return self.async_show_form(
            step_id="species_edit",
            data_schema=vol.Schema(fields),
            errors=errors,
            description_placeholders={
                "species": default.scientific_name,
                "factors": "\n".join(
                    f"- {f.id}: {f.indicator}"
                    + (f", {f.lag} d earlier" if f.lag else "")
                    + f" ({f.role.value}, grade {f.grade})"
                    for f in default.factors
                ),
                "error": detail,
            },
        )

    @staticmethod
    def _overrides_from_form(default: SpeciesProfile, user_input: dict[str, Any]) -> dict[str, Any]:
        """Only what differs from the bundled profile."""
        overrides: dict[str, Any] = {}
        season = {
            name: str(user_input[f"season_{name}"]).strip()
            for name in SEASON_FIELDS
            if str(user_input[f"season_{name}"]).strip() != getattr(default.season, name)
        }
        if season:
            overrides["season"] = season
        curves = {}
        for factor in default.factors:
            points = parse_curve(str(user_input[f"curve_{factor.id}"]))
            if tuple((float(x), float(y)) for x, y in points) != factor.curve:
                curves[factor.id] = points
        if curves:
            overrides["curves"] = curves
        return overrides

    def _save_overrides(self, overrides: dict[str, Any]) -> ConfigFlowResult:
        return self.async_create_entry(
            data={**self.config_entry.options, CONF_SPECIES_OVERRIDES: overrides}
        )

    async def async_step_record_observation(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Record a find or an empty visit."""
        from .observations import ObservationError

        data = self.config_entry.runtime_data
        if not data.coordinators:
            return self.async_abort(reason="no_locations")
        errors: dict[str, str] = {}
        detail = ""
        if user_input is not None:
            coordinator = data.coordinators[user_input["site"]]
            outcome = Outcome(user_input["outcome"])
            position = user_input.get(CONF_LOCATION) if user_input.get("save_coordinates") else None
            photo = user_input.get("photo")
            try:
                obs = await data.observations.async_record(
                    coordinator,
                    species=user_input["species"],
                    day=date.fromisoformat(user_input["date"]),
                    outcome=outcome,
                    quantity=Quantity.NONE
                    if outcome is Outcome.NOT_FOUND
                    else user_input.get("quantity", Quantity.FEW),
                    habitat=user_input.get(CONF_HABITATS_SINGLE),
                    notes=user_input.get("notes", ""),
                    latitude=position["latitude"] if position else None,
                    longitude=position["longitude"] if position else None,
                    photo=photo.get("media_content_id") if isinstance(photo, dict) else None,
                )
            except ObservationError as err:
                errors["base"] = err.key
                detail = str(err)
            else:
                return self.async_abort(
                    reason="observation_recorded"
                    if obs.snapshot
                    else "observation_recorded_no_snapshot"
                )

        first = next(iter(data.coordinators.values())).location
        locations = [
            SelectOptionDict(value=sid, label=c.location.name)
            for sid, c in data.coordinators.items()
        ]
        schema = vol.Schema(
            {
                vol.Required("site", default=locations[0]["value"]): SelectSelector(
                    SelectSelectorConfig(options=locations, mode=SelectSelectorMode.DROPDOWN)
                ),
                vol.Required("species"): SelectSelector(
                    SelectSelectorConfig(
                        options=[*data.profiles, OTHER_SPECIES], translation_key="species"
                    )
                ),
                vol.Required("date", default=dt_util.now().date().isoformat()): DateSelector(),
                vol.Required("outcome", default=Outcome.FOUND.value): SelectSelector(
                    SelectSelectorConfig(
                        options=[o.value for o in Outcome], translation_key="outcome"
                    )
                ),
                vol.Required("quantity", default=Quantity.FEW.value): SelectSelector(
                    SelectSelectorConfig(
                        options=[q.value for q in Quantity if q is not Quantity.NONE],
                        translation_key="quantity",
                    )
                ),
                vol.Optional(CONF_HABITATS_SINGLE): SelectSelector(
                    SelectSelectorConfig(options=HABITATS, translation_key="habitat")
                ),
                vol.Optional("notes"): TextSelector(TextSelectorConfig(multiline=True)),
                vol.Required("save_coordinates", default=False): BooleanSelector(),
                vol.Optional(
                    CONF_LOCATION,
                    default={"latitude": first.latitude, "longitude": first.longitude},
                ): LocationSelector(LocationSelectorConfig(radius=False)),
                vol.Optional("photo"): MediaSelector(MediaSelectorConfig(accept=["image/*"])),
            }
        )
        return self.async_show_form(
            step_id="record_observation",
            data_schema=self.add_suggested_values_to_schema(schema, user_input or {}),
            errors=errors,
            description_placeholders={"error": detail},
        )

    async def async_step_manage_observations(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Delete observations."""
        manager = self.config_entry.runtime_data.observations
        observations = manager.observations
        if not observations:
            return self.async_abort(reason="no_observations")
        if user_input is not None:
            removed = await manager.async_delete(user_input.get("delete", []))
            return self.async_abort(
                reason="observations_deleted", description_placeholders={"count": str(removed)}
            )
        profiles = self.config_entry.runtime_data.profiles
        language = self.hass.config.language
        options = [
            SelectOptionDict(
                value=o.id,
                label=" · ".join(
                    [
                        o.day.isoformat(),
                        o.location_name,
                        profiles[o.species].name(language) if o.species in profiles else o.species,
                        o.outcome.value,
                    ]
                ),
            )
            for o in reversed(observations[-100:])
        ]
        schema = vol.Schema(
            {
                vol.Optional("delete", default=[]): SelectSelector(
                    SelectSelectorConfig(
                        options=options, multiple=True, mode=SelectSelectorMode.LIST
                    )
                )
            }
        )
        return self.async_show_form(
            step_id="manage_observations",
            data_schema=schema,
            description_placeholders={"count": str(len(observations))},
        )
