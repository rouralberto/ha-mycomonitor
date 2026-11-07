"""Local sensors (long-term statistics), the AEMET station step and source merging."""

from __future__ import annotations

from collections.abc import Generator
from datetime import UTC, date, datetime, timedelta
from unittest.mock import AsyncMock, patch

from homeassistant.config_entries import SOURCE_USER
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mycomonitor.const import DOMAIN, SUBENTRY_LOCATION
from custom_components.mycomonitor.core.models import (
    DailySeries,
    DataKind,
    Reading,
    Source,
    Variable,
)
from custom_components.mycomonitor.core.providers.aemet import AemetAuthError, Station
from custom_components.mycomonitor.core.providers.base import ProviderConnectionError
from custom_components.mycomonitor.local_sensors import (
    CONF_RAIN_ENTITY,
    CONF_SOIL_MOISTURE_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    rows_to_series,
)

from .conftest import URBASA, location_subentry

TODAY = date(2026, 11, 7)
STATIONS = [
    Station("9263D", "Pamplona Aeropuerto", "Navarra", 42.7694, -1.6525, 459),
    Station("9171K", "Estella", "Navarra", 42.67, -2.03, 470),
]


def ts(day: date) -> float:
    # Noon UTC: the same calendar day in any time zone within ±11 h.
    return datetime.combine(day, datetime.min.time(), UTC).timestamp() + 12 * 3600


def test_rows_to_series_maps_and_scales() -> None:
    rows = {
        "sensor.rain": [{"start": ts(TODAY - timedelta(days=2)), "change": 4.2}],
        "sensor.temp": [
            {"start": ts(TODAY - timedelta(days=1)), "mean": 10.0, "min": 3.0, "max": 16.0},
            {"start": ts(TODAY), "mean": 99.0},  # today is partial: ignored
        ],
        "sensor.soil": [{"start": ts(TODAY - timedelta(days=1)), "mean": 31.0}],
    }
    mapping = {
        CONF_RAIN_ENTITY: "sensor.rain",
        CONF_TEMPERATURE_ENTITY: "sensor.temp",
        CONF_SOIL_MOISTURE_ENTITY: "sensor.soil",
    }
    series = rows_to_series(rows, mapping, TODAY)
    yesterday = TODAY - timedelta(days=1)
    assert series.get(Variable.PRECIPITATION, TODAY - timedelta(days=2)).value == 4.2
    assert series.get(Variable.TEMPERATURE_MIN, yesterday).value == 3.0
    assert series.get(Variable.TEMPERATURE_MAX, yesterday).value == 16.0
    assert series.get(Variable.SOIL_MOISTURE_0_7CM, yesterday).value == pytest.approx(0.31)
    assert series.get(Variable.TEMPERATURE_MEAN, TODAY) is None
    assert (
        series.get(Variable.PRECIPITATION, TODAY - timedelta(days=2)).source.kind
        is DataKind.MEASURED
    )


def measured(day: date, variable: Variable, value: float, kind: DataKind) -> DailySeries:
    series = DailySeries()
    series.put(variable, day, Reading(value, Source("test", kind)))
    return series


async def test_measured_and_station_take_priority(
    hass: HomeAssistant, mock_fetch: AsyncMock, provider_result
) -> None:
    yesterday = provider_result.today - timedelta(days=1)
    two_days = provider_result.today - timedelta(days=2)
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={"aemet_api_key": "KEY"},
        subentries_data=[
            location_subentry(URBASA | {CONF_RAIN_ENTITY: "sensor.rain", "aemet_station": "9263D"})
        ],
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.mycomonitor.coordinator.async_fetch_local",
            AsyncMock(
                return_value=measured(yesterday, Variable.PRECIPITATION, 50, DataKind.MEASURED)
            ),
        ),
        patch(
            "custom_components.mycomonitor.coordinator.AemetProvider.async_fetch_daily",
            AsyncMock(return_value=_station_series(yesterday, two_days)),
        ) as station_fetch,
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()

    coordinator = next(iter(entry.runtime_data.coordinators.values()))
    data = coordinator.data
    assert data.measured_days == {"precipitation": 1}
    assert data.station_days == 2
    assert station_fetch.await_args.args[0] == "9263D"
    rain_3d = data.indicators["rain_3d"]
    assert DataKind.MEASURED in rain_3d.kinds
    assert DataKind.STATION in rain_3d.kinds
    model = provider_result.series
    expected = (
        50  # measured beats station (7) for yesterday
        + 30  # station beats the model two days ago
        + model.get(Variable.PRECIPITATION, provider_result.today).value
    )
    assert rain_3d.value == pytest.approx(expected)


def _station_series(yesterday: date, two_days: date) -> DailySeries:
    series = DailySeries()
    source = Source("aemet", DataKind.STATION, model="9263D")
    series.put(Variable.PRECIPITATION, yesterday, Reading(7, source))
    series.put(Variable.PRECIPITATION, two_days, Reading(30, source))
    return series


async def test_failing_sources_do_not_break_update(
    hass: HomeAssistant, mock_fetch: AsyncMock
) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        options={"aemet_api_key": "KEY"},
        subentries_data=[
            location_subentry(URBASA | {CONF_RAIN_ENTITY: "sensor.rain", "aemet_station": "9263D"})
        ],
    )
    entry.add_to_hass(hass)
    with (
        patch(
            "custom_components.mycomonitor.coordinator.async_fetch_local",
            AsyncMock(side_effect=RuntimeError("no recorder")),
        ),
        patch(
            "custom_components.mycomonitor.coordinator.AemetProvider.async_fetch_daily",
            AsyncMock(side_effect=ProviderConnectionError("down")),
        ),
    ):
        assert await hass.config_entries.async_setup(entry.entry_id)
        await hass.async_block_till_done()
    data = next(iter(entry.runtime_data.coordinators.values())).data
    assert any("local sensors" in w for w in data.warnings)
    assert any("AEMET" in w for w in data.warnings)
    assert hass.states.get("sensor.mycomonitor_urbasa_rain_7d").state != "unavailable"


# --- config flow: local sensors and AEMET -----------------------------------------


@pytest.fixture
def no_setup() -> Generator[None]:
    with patch("custom_components.mycomonitor.async_setup_entry", return_value=True):
        yield


FORM = {
    "name": "Estella-Lizarra",
    "location": {"latitude": 42.6713, "longitude": -2.031},
    "habitats": ["oak"],
}


async def test_local_sensor_validation(
    hass: HomeAssistant, config_entry: MockConfigEntry, no_setup: None
) -> None:
    hass.states.async_set("sensor.rain_today", "1.2", {"state_class": "measurement"})
    hass.states.async_set("sensor.rain_total", "120", {"state_class": "total_increasing"})
    hass.states.async_set("sensor.garden_temp", "9", {"state_class": "measurement"})
    result = await hass.config_entries.subentries.async_init(
        (config_entry.entry_id, SUBENTRY_LOCATION), context={"source": SOURCE_USER}
    )
    for local, error in (
        ({"rain_entity": "sensor.rain_today"}, "rain_needs_total"),
        ({"rain_entity": "sensor.nope"}, "entity_not_found"),
        ({"temperature_entity": "sensor.rain_total"}, "needs_measurement"),
    ):
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], FORM | {"local_sensors": local}
        )
        assert result["errors"] == {"base": error}
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        FORM
        | {
            "local_sensors": {
                "rain_entity": "sensor.rain_total",
                "temperature_entity": "sensor.garden_temp",
            }
        },
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    sub = next(s for s in config_entry.subentries.values() if s.title == "Estella-Lizarra")
    assert sub.data["rain_entity"] == "sensor.rain_total"
    assert sub.data["temperature_entity"] == "sensor.garden_temp"
    assert sub.data["aemet_station"] is None


async def test_station_step_with_aemet_key(
    hass: HomeAssistant, config_entry: MockConfigEntry, no_setup: None
) -> None:
    hass.config_entries.async_update_entry(config_entry, options={"aemet_api_key": "KEY"})
    with patch(
        "custom_components.mycomonitor.config_flow.AemetProvider.async_stations",
        AsyncMock(return_value=STATIONS),
    ):
        result = await hass.config_entries.subentries.async_init(
            (config_entry.entry_id, SUBENTRY_LOCATION), context={"source": SOURCE_USER}
        )
        result = await hass.config_entries.subentries.async_configure(result["flow_id"], FORM)
        assert result["step_id"] == "station"
        options = result["data_schema"].schema["aemet_station"].config["options"]
        assert [o["value"] for o in options] == ["none", "9171K", "9263D"]  # nearest first
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], {"aemet_station": "9171K"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    sub = next(s for s in config_entry.subentries.values() if s.title == "Estella-Lizarra")
    assert sub.data["aemet_station"] == "9171K"

    # Reconfigure keeps the station selectable and can clear it.
    with patch(
        "custom_components.mycomonitor.config_flow.AemetProvider.async_stations",
        AsyncMock(side_effect=ProviderConnectionError("down")),
    ):
        result = await config_entry.start_subentry_reconfigure_flow(hass, sub.subentry_id)
        result = await hass.config_entries.subentries.async_configure(result["flow_id"], FORM)
        assert result["step_id"] == "station"
        assert result["errors"] == {"base": "stations_unavailable"}
        result = await hass.config_entries.subentries.async_configure(
            result["flow_id"], {"aemet_station": ""}
        )
    assert result["reason"] == "reconfigure_successful"
    assert config_entry.subentries[sub.subentry_id].data["aemet_station"] is None


async def test_reconfigure_without_key_keeps_station(hass: HomeAssistant, no_setup: None) -> None:
    entry = MockConfigEntry(
        domain=DOMAIN,
        data={},
        subentries_data=[location_subentry(URBASA | {"aemet_station": "9263D"})],
    )
    entry.add_to_hass(hass)
    sub_id = next(iter(entry.subentries))
    result = await entry.start_subentry_reconfigure_flow(hass, sub_id)
    result = await hass.config_entries.subentries.async_configure(
        result["flow_id"],
        {
            "name": "Urbasa",
            "location": {"latitude": 42.84, "longitude": -2.17},
            "habitats": ["beech"],
        },
    )
    assert result["reason"] == "reconfigure_successful"
    assert entry.subentries[sub_id].data["aemet_station"] == "9263D"


async def _settings(hass: HomeAssistant, entry: MockConfigEntry):  # type: ignore[no-untyped-def]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    return await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )


async def test_aemet_key_validation(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_fetch: AsyncMock
) -> None:
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    target = "custom_components.mycomonitor.config_flow.AemetProvider.async_stations"

    with patch(target, AsyncMock(side_effect=AemetAuthError("no"))):
        result = await _settings(hass, config_entry)
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"favorable_threshold": 60, "aemet_api_key": "BAD"}
        )
    assert result["errors"] == {"aemet_api_key": "invalid_api_key"}

    with patch(target, AsyncMock(side_effect=ProviderConnectionError("down"))):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"favorable_threshold": 60, "aemet_api_key": "KEY"}
        )
    assert result["errors"] == {"aemet_api_key": "cannot_connect"}

    with patch(target, AsyncMock(return_value=STATIONS)):
        result = await hass.config_entries.options.async_configure(
            result["flow_id"], {"favorable_threshold": 60, "aemet_api_key": "KEY"}
        )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options["aemet_api_key"] == "KEY"
    await hass.async_block_till_done()

    result = await _settings(hass, config_entry)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"favorable_threshold": 60, "aemet_api_key": ""}
    )
    assert "aemet_api_key" not in config_entry.options
