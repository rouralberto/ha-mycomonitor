"""Tests for setup, sensors, failure handling and diagnostics."""

from __future__ import annotations

from datetime import timedelta
import json
from types import MappingProxyType
from unittest.mock import AsyncMock

from freezegun.api import FrozenDateTimeFactory
from homeassistant.config_entries import ConfigEntryState, ConfigSubentry
from homeassistant.const import STATE_UNAVAILABLE, STATE_UNKNOWN
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import entity_registry as er
from homeassistant.setup import async_setup_component
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry, async_fire_time_changed
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from custom_components.mycomonitor.const import DOMAIN
from custom_components.mycomonitor.core.indicators import compute_indicators
from custom_components.mycomonitor.core.providers.base import (
    ProviderConnectionError,
    ProviderResult,
)
from custom_components.mycomonitor.sensor import INDICATOR_SENSORS

from .conftest import location_subentry

ENABLED = [d.key for d in INDICATOR_SENSORS if d.entity_registry_enabled_default]
DISABLED = [d.key for d in INDICATOR_SENSORS if not d.entity_registry_enabled_default]


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_sensors_show_indicators(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    provider_result: ProviderResult,
) -> None:
    await setup(hass, config_entry)
    assert config_entry.state is ConfigEntryState.LOADED
    expected = compute_indicators(provider_result.series, provider_result.today)

    rain = hass.states.get("sensor.mycomonitor_urbasa_rain_7d")
    assert rain is not None
    assert float(rain.state) == pytest.approx(expected["rain_7d"].value)
    assert rain.attributes["unit_of_measurement"] == "mm"
    assert rain.attributes["state_class"] == "measurement"
    assert rain.attributes["includes_forecast"] is True
    assert rain.attributes["data"] == ["analysis", "forecast"]
    assert rain.attributes["window_end"] == "2026-11-07"
    assert rain.attributes["friendly_name"] == "Urbasa Rainfall 7 days"
    assert "Open-Meteo" in rain.attributes["attribution"]

    soil = hass.states.get("sensor.mycomonitor_urbasa_soil_moisture")
    assert soil is not None
    assert soil.attributes["unit_of_measurement"] == "%"
    assert float(soil.state) == pytest.approx(expected["soil_moisture"].value * 100)

    for key in ENABLED:
        for location in ("urbasa", "montejurra"):
            state = hass.states.get(f"sensor.mycomonitor_{location}_{key}")
            assert state is not None, key
            assert state.state not in (STATE_UNAVAILABLE, STATE_UNKNOWN), key
    updated = hass.states.get("sensor.mycomonitor_urbasa_last_update")
    assert updated is not None
    assert updated.attributes["stale"] is False


async def test_disabled_by_default(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    entity_registry: er.EntityRegistry,
) -> None:
    await setup(hass, config_entry)
    for key in DISABLED:
        entity_id = f"sensor.mycomonitor_urbasa_{key}"
        assert hass.states.get(entity_id) is None
        entry = entity_registry.async_get(entity_id)
        assert entry is not None, key
        assert entry.disabled_by is er.RegistryEntryDisabler.INTEGRATION


async def test_one_device_per_location(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
) -> None:
    await setup(hass, config_entry)
    devices = dr.async_entries_for_config_entry(device_registry, config_entry.entry_id)
    assert sorted(d.name for d in devices) == ["Montejurra", "Urbasa"]
    for subentry_id, subentry in config_entry.subentries.items():
        device = device_registry.async_get_device_by_identifier(
            (DOMAIN, subentry_id), config_entry.entry_id
        )
        assert device is not None
        assert device.name == subentry.title
        assert device.config_entry_id == config_entry.entry_id
        assert device.config_subentry_id == subentry_id
        entity = entity_registry.async_get(f"sensor.mycomonitor_{subentry.title.lower()}_rain_7d")
        assert entity is not None
        assert entity.unique_id == f"{subentry_id}_rain_7d"
        assert entity.config_subentry_id == subentry_id


async def test_failing_location_does_not_block_others(
    hass: HomeAssistant, config_entry: MockConfigEntry, provider_result: ProviderResult
) -> None:
    async def fetch(location, **kwargs):  # type: ignore[no-untyped-def]
        if location.name == "Montejurra":
            raise ProviderConnectionError("down")
        return provider_result

    mock_fetch = AsyncMock(side_effect=fetch)
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(
            "custom_components.mycomonitor.coordinator.OpenMeteoProvider.async_fetch", mock_fetch
        )
        await setup(hass, config_entry)
        assert config_entry.state is ConfigEntryState.LOADED
        assert hass.states.get("sensor.mycomonitor_urbasa_rain_7d").state != STATE_UNAVAILABLE
        assert hass.states.get("sensor.mycomonitor_montejurra_rain_7d").state == STATE_UNAVAILABLE


async def test_all_locations_failing_retries_setup(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_fetch: AsyncMock
) -> None:
    mock_fetch.side_effect = ProviderConnectionError("down")
    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_keeps_stale_data_through_short_outage(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    freezer: FrozenDateTimeFactory,
) -> None:
    await setup(hass, config_entry)
    entity_id = "sensor.mycomonitor_urbasa_rain_7d"
    before = hass.states.get(entity_id).state
    mock_fetch.side_effect = ProviderConnectionError("down")

    freezer.tick(timedelta(hours=3, minutes=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == before
    assert hass.states.get("sensor.mycomonitor_urbasa_last_update").attributes["stale"] is True

    # Retries every 15 minutes; after 12 hours without success, give up.
    for _ in range(40):
        freezer.tick(timedelta(minutes=16))
        async_fire_time_changed(hass)
        await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == STATE_UNAVAILABLE

    mock_fetch.side_effect = None
    freezer.tick(timedelta(minutes=16))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()
    assert hass.states.get(entity_id).state == before


async def test_adding_location_reloads(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_fetch: AsyncMock
) -> None:
    await setup(hass, config_entry)
    data = {
        "name": "Estella-Lizarra",
        "latitude": 42.6713,
        "longitude": -2.031,
        "altitude": None,
        "habitats": ["oak"],
    }
    sub = location_subentry(data)
    hass.config_entries.async_add_subentry(
        config_entry,
        ConfigSubentry(
            data=MappingProxyType(sub["data"]),
            subentry_type=sub["subentry_type"],
            title=sub["title"],
            unique_id=sub["unique_id"],
        ),
    )
    await hass.async_block_till_done()
    assert hass.states.get("sensor.mycomonitor_estella_lizarra_rain_7d") is not None


async def test_unload(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_fetch: AsyncMock
) -> None:
    await setup(hass, config_entry)
    assert await hass.config_entries.async_unload(config_entry.entry_id)
    await hass.async_block_till_done()
    assert config_entry.state is ConfigEntryState.NOT_LOADED


async def test_diagnostics_redact_coordinates(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
) -> None:
    assert await async_setup_component(hass, "diagnostics", {})
    await setup(hass, config_entry)
    result = await get_diagnostics_for_config_entry(hass, hass_client, config_entry)

    text = json.dumps(result)
    for secret in ("42.84", "-2.17", "42.6275", "-2.05"):
        assert secret not in text, secret
    urbasa = next(loc for loc in result["locations"] if loc["title"] == "Urbasa")
    assert urbasa["config"]["latitude"] == "**REDACTED**"
    assert urbasa["config"]["habitats"] == ["beech", "grassland"]
    assert urbasa["last_update_success"] is True
    assert urbasa["indicators"]["rain_7d"]["unit"] == "mm"
    assert all("grid_distance_km" in s for s in urbasa["sources"])
    assert all("grid_latitude" not in s for s in urbasa["sources"])
