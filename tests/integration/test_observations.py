"""Observation log: services, options flow steps, sensor, privacy, persistence."""

from __future__ import annotations

from collections.abc import Generator
import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, patch

from freezegun.api import FrozenDateTimeFactory
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.mycomonitor.const import DOMAIN
from custom_components.mycomonitor.core.providers.base import (
    ProviderConnectionError,
    ProviderResult,
)
from custom_components.mycomonitor.observations import STORAGE_KEY

SPOT = {"latitude": 42.8456789, "longitude": -2.1654321}


@pytest.fixture
def mock_history(provider_result: ProviderResult) -> Generator[AsyncMock]:
    with patch(
        "custom_components.mycomonitor.coordinator.OpenMeteoProvider.async_fetch_history",
        AsyncMock(return_value=provider_result.series),
    ) as mock:
        yield mock


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def record(hass: HomeAssistant, **data: Any) -> dict[str, Any]:
    payload = {"location": "Urbasa", "species": "hydnum_repandum", "outcome": "found"} | data
    response = await hass.services.async_call(
        DOMAIN, "record_observation", payload, blocking=True, return_response=True
    )
    assert isinstance(response, dict)
    return response


async def test_record_via_service(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    mock_history: AsyncMock,
    hass_storage: dict[str, Any],
) -> None:
    await setup(hass, config_entry)
    response = await record(hass, date="2026-11-05", quantity="some", notes="musgo", **SPOT)
    assert response["has_snapshot"] is True
    assert mock_history.await_args.kwargs["end"].isoformat() == "2026-11-05"

    state = hass.states.get("sensor.mycomonitor_urbasa_observations")
    assert state.state == "1"
    assert state.attributes["found"] == 1
    assert state.attributes["last_find"]["species"] == "hydnum_repandum"
    assert "42.845" not in json.dumps(dict(state.attributes))
    assert hass.states.get("sensor.mycomonitor_montejurra_observations").state == "0"

    await hass.async_block_till_done()
    stored = hass_storage[STORAGE_KEY]["data"]["observations"][0]
    assert stored["latitude"] == SPOT["latitude"]
    assert stored["snapshot"]["species_evidence"] == "C"
    assert stored["notes"] == "musgo"


async def test_location_by_name_is_case_insensitive(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    mock_history: AsyncMock,
) -> None:
    await setup(hass, config_entry)
    await record(hass, location="montejurra", outcome="not_found")
    state = hass.states.get("sensor.mycomonitor_montejurra_observations")
    assert state.state == "1"
    assert state.attributes["not_found"] == 1
    assert state.attributes["last_observation"]["quantity"] == "none"


@pytest.mark.parametrize(
    ("data", "key"),
    [
        ({"location": "Nowhere"}, "unknown_location"),
        ({"species": "amanita_phalloides"}, "unknown_species"),
        ({"date": "2099-01-01"}, "invalid_observation"),
        ({"latitude": 42.8}, "invalid_observation"),
        ({"outcome": "not_found", "quantity": "many"}, "invalid_observation"),
    ],
)
async def test_record_validation(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    mock_history: AsyncMock,
    data: dict[str, Any],
    key: str,
) -> None:
    await setup(hass, config_entry)
    with pytest.raises(ServiceValidationError) as err:
        await record(hass, **data)
    assert err.value.translation_key == key


async def test_snapshot_backfilled_after_failure(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    mock_history: AsyncMock,
    freezer: FrozenDateTimeFactory,
    hass_storage: dict[str, Any],
) -> None:
    await setup(hass, config_entry)
    series = mock_history.return_value
    mock_history.side_effect = ProviderConnectionError("down")
    response = await record(hass)
    assert response["has_snapshot"] is False

    mock_history.side_effect = None
    mock_history.return_value = series
    freezer.tick(3 * 3600 + 60)
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    attrs = hass.states.get("sensor.mycomonitor_urbasa_observations").attributes
    assert attrs["last_observation"]["has_snapshot"] is True


async def test_export_and_delete(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    mock_history: AsyncMock,
) -> None:
    await setup(hass, config_entry)
    first = await record(hass, **SPOT)
    await record(hass, location="Montejurra", species="lactarius_deliciosus")

    result = await hass.services.async_call(
        DOMAIN, "export_observations", {}, blocking=True, return_response=True
    )
    assert result["count"] == 2
    text = await hass.async_add_executor_job(Path(result["path"]).read_text)
    assert Path(result["path"]).parent == Path(hass.config.path("mycomonitor", "exports"))
    assert "latitude" not in text
    assert "42.845" not in text

    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "export_observations",
            {"format": "geojson"},
            blocking=True,
            return_response=True,
        )
    result = await hass.services.async_call(
        DOMAIN,
        "export_observations",
        {"format": "geojson", "include_coordinates": True, "decimals": 3, "location": "Urbasa"},
        blocking=True,
        return_response=True,
    )
    doc = json.loads(await hass.async_add_executor_job(Path(result["path"]).read_text))
    assert result["count"] == 1
    assert doc["features"][0]["geometry"]["coordinates"] == [-2.165, 42.846]

    deleted = await hass.services.async_call(
        DOMAIN, "delete_observation", {"id": first["id"]}, blocking=True, return_response=True
    )
    assert deleted == {"deleted": 1}
    with pytest.raises(ServiceValidationError):
        await hass.services.async_call(
            DOMAIN,
            "delete_observation",
            {"id": first["id"]},
            blocking=True,
            return_response=True,
        )
    assert hass.states.get("sensor.mycomonitor_urbasa_observations").state == "0"


async def test_services_need_loaded_entry(hass: HomeAssistant) -> None:
    assert await async_setup_component(hass, DOMAIN, {})
    with pytest.raises(ServiceValidationError) as err:
        await record(hass)
    assert err.value.translation_key == "not_loaded"


async def test_observations_persist_across_reload(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    mock_history: AsyncMock,
) -> None:
    await setup(hass, config_entry)
    await record(hass)
    await hass.config_entries.async_reload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert len(config_entry.runtime_data.observations.observations) == 1


async def _options_step(hass: HomeAssistant, entry: MockConfigEntry, step: str):  # type: ignore[no-untyped-def]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": step}
    )


async def test_options_record_without_coordinates(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    mock_history: AsyncMock,
) -> None:
    await setup(hass, config_entry)
    result = await _options_step(hass, config_entry, "record_observation")
    assert result["type"] is FlowResultType.FORM
    montejurra = next(
        sid
        for sid, c in config_entry.runtime_data.coordinators.items()
        if c.location.name == "Montejurra"
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "site": montejurra,
            "species": "lactarius_deliciosus",
            "date": "2026-11-06",
            "outcome": "found",
            "quantity": "many",
            "save_coordinates": False,
            "location": SPOT,
        },
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "observation_recorded"
    (obs,) = config_entry.runtime_data.observations.observations
    assert obs.location_name == "Montejurra"
    assert obs.quantity.value == "many"
    assert not obs.has_coordinates  # box not ticked


async def test_options_record_not_found_and_coordinates(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    mock_history: AsyncMock,
) -> None:
    await setup(hass, config_entry)
    result = await _options_step(hass, config_entry, "record_observation")
    site = next(iter(config_entry.runtime_data.coordinators))
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "site": site,
            "species": "other",
            "date": "2026-11-06",
            "outcome": "not_found",
            "quantity": "many",  # ignored for an empty visit
            "save_coordinates": True,
            "location": SPOT,
        },
    )
    assert result["reason"] == "observation_recorded"
    (obs,) = config_entry.runtime_data.observations.observations
    assert obs.quantity.value == "none"
    assert obs.latitude == SPOT["latitude"]


async def test_options_record_future_date_error(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    mock_history: AsyncMock,
) -> None:
    await setup(hass, config_entry)
    result = await _options_step(hass, config_entry, "record_observation")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {
            "site": next(iter(config_entry.runtime_data.coordinators)),
            "species": "lepista_nuda",
            "date": "2099-01-01",
            "outcome": "found",
            "quantity": "few",
            "save_coordinates": False,
        },
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "future_date"}


async def test_options_manage_observations(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    mock_history: AsyncMock,
) -> None:
    await setup(hass, config_entry)
    result = await _options_step(hass, config_entry, "manage_observations")
    assert result["reason"] == "no_observations"

    first = await record(hass)
    await record(hass, species="lepista_nuda")
    result = await _options_step(hass, config_entry, "manage_observations")
    assert result["type"] is FlowResultType.FORM
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"delete": [first["id"]]}
    )
    assert result["reason"] == "observations_deleted"
    remaining = config_entry.runtime_data.observations.observations
    assert [o.species for o in remaining] == ["lepista_nuda"]


async def test_diagnostics_count_observations_only(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    mock_history: AsyncMock,
) -> None:
    assert await async_setup_component(hass, "diagnostics", {})
    await setup(hass, config_entry)
    await record(hass, notes="secret place", **SPOT)
    result = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)
    text = json.dumps(result)
    assert "42.845" not in text
    assert "secret place" not in text
    assert result["observations"] == {"total": 1, "with_coordinates": 1, "without_snapshot": 0}
