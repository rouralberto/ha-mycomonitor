"""Fixtures for the Home Assistant integration tests."""

from __future__ import annotations

from collections.abc import Generator
from typing import Any
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import ConfigSubentryData
from homeassistant.core import HomeAssistant
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mycomonitor.const import DOMAIN, SUBENTRY_LOCATION
from custom_components.mycomonitor.core.providers.base import ProviderResult

from ..fake_open_meteo import fixture_result

URBASA = {
    "name": "Urbasa",
    "latitude": 42.84,
    "longitude": -2.17,
    "altitude": 916.0,
    "habitats": ["beech", "grassland"],
}
MONTEJURRA = {
    "name": "Montejurra",
    "latitude": 42.6275,
    "longitude": -2.05,
    "altitude": None,
    "habitats": ["pine", "oak", "mixed"],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Let Home Assistant load custom_components/mycomonitor."""


def location_subentry(data: dict[str, Any]) -> ConfigSubentryData:
    return ConfigSubentryData(
        data=data,
        subentry_type=SUBENTRY_LOCATION,
        title=data["name"],
        unique_id=f"{data['latitude']:.3f},{data['longitude']:.3f}",
    )


@pytest.fixture
def config_entry(hass: HomeAssistant) -> MockConfigEntry:
    """A hub entry with Urbasa and Montejurra."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        title="MycoMonitor",
        data={},
        subentries_data=[location_subentry(URBASA), location_subentry(MONTEJURRA)],
    )
    entry.add_to_hass(hass)
    return entry


@pytest.fixture
async def provider_result() -> ProviderResult:
    return await fixture_result()


@pytest.fixture
def mock_fetch(provider_result: ProviderResult) -> Generator[AsyncMock]:
    """Every location gets the recorded Urbasa data."""
    with patch(
        "custom_components.mycomonitor.coordinator.OpenMeteoProvider.async_fetch",
        AsyncMock(return_value=provider_result),
    ) as mock:
        yield mock
