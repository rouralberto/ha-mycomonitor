"""Tests for the config flow and the location sub-entry flow."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mycomonitor.const import DOMAIN, SUBENTRY_LOCATION

FORM = {
    "name": " Urbasa ",
    "location": {"latitude": 42.84, "longitude": -2.17},
    "altitude": 916,
    "habitats": ["grassland", "beech"],
}


@pytest.fixture(autouse=True)
def no_setup() -> Generator[None]:
    with patch("custom_components.mycomonitor.async_setup_entry", return_value=True):
        yield


async def test_user_flow_creates_hub_with_first_location(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "MycoMonitor"

    entry = hass.config_entries.async_entries(DOMAIN)[0]
    (subentry,) = entry.subentries.values()
    assert subentry.subentry_type == SUBENTRY_LOCATION
    assert subentry.title == "Urbasa"
    assert subentry.unique_id == "42.840,-2.170"
    assert dict(subentry.data) == {
        "name": "Urbasa",
        "latitude": 42.84,
        "longitude": -2.17,
        "altitude": 916.0,
        "habitats": ["beech", "grassland"],  # canonical order
        "rain_entity": None,
        "temperature_entity": None,
        "humidity_entity": None,
        "soil_moisture_entity": None,
        "soil_temperature_entity": None,
        "aemet_station": None,
    }


async def test_user_flow_altitude_is_optional(hass: HomeAssistant) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    form = {k: v for k, v in FORM.items() if k != "altitude"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], form)
    entry = hass.config_entries.async_entries(DOMAIN)[0]
    assert next(iter(entry.subentries.values())).data["altitude"] is None


@pytest.mark.parametrize(
    ("change", "errors"),
    [
        ({"habitats": []}, {"habitats": "no_habitat"}),
        ({"name": "  "}, {"base": "invalid_location"}),
        ({"location": {"latitude": 95, "longitude": 0}}, {"base": "invalid_location"}),
    ],
)
async def test_user_flow_errors(
    hass: HomeAssistant, change: dict[str, Any], errors: dict[str, str]
) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    result = await hass.config_entries.flow.async_configure(result["flow_id"], FORM | change)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == errors


async def test_single_instance(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": SOURCE_USER})
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "single_instance_allowed"


async def test_add_location(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    result = await hass.config_entries.subentries.async_init(
        (config_entry.entry_id, SUBENTRY_LOCATION), context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    form = FORM | {
        "name": "Estella-Lizarra",
        "location": {"latitude": 42.6713, "longitude": -2.031},
    }
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], form)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert len(config_entry.subentries) == 3
    assert "Estella-Lizarra" in {s.title for s in config_entry.subentries.values()}


async def test_add_duplicate_location_aborts(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    result = await hass.config_entries.subentries.async_init(
        (config_entry.entry_id, SUBENTRY_LOCATION), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], FORM)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_add_location_errors(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    result = await hass.config_entries.subentries.async_init(
        (config_entry.entry_id, SUBENTRY_LOCATION), context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"], FORM | {"habitats": []}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"habitats": "no_habitat"}


def _subentry_id(entry: MockConfigEntry, title: str) -> str:
    return next(s.subentry_id for s in entry.subentries.values() if s.title == title)


async def test_reconfigure_location(hass: HomeAssistant, config_entry: MockConfigEntry) -> None:
    subentry_id = _subentry_id(config_entry, "Urbasa")
    result = await config_entry.start_subentry_reconfigure_flow(hass, subentry_id)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    form = FORM | {"name": "Urbasa (raso)", "altitude": 930}
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], form)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    subentry = config_entry.subentries[subentry_id]
    assert subentry.title == "Urbasa (raso)"
    assert subentry.data["altitude"] == 930


async def test_reconfigure_onto_another_location_aborts(
    hass: HomeAssistant, config_entry: MockConfigEntry
) -> None:
    result = await config_entry.start_subentry_reconfigure_flow(
        hass, _subentry_id(config_entry, "Montejurra")
    )
    result = await hass.config_entries.subentries.async_configure(result["flow_id"], FORM)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"
