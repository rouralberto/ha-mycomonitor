"""Species sensors, the favourable-conditions binary sensor and the options flow."""

from __future__ import annotations

from unittest.mock import AsyncMock

from homeassistant.const import STATE_OFF, STATE_ON
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.mycomonitor.const import CONF_SPECIES_OVERRIDES
from custom_components.mycomonitor.core.providers.base import ProviderResult
from custom_components.mycomonitor.core.species.engine import indicator_lookup, score_species
from custom_components.mycomonitor.core.species.loader import load_profiles


async def setup(hass: HomeAssistant, entry: MockConfigEntry) -> None:
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()


async def test_species_sensors_follow_habitats(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_fetch: AsyncMock
) -> None:
    await setup(hass, config_entry)
    # Urbasa: beech + grassland -> no pine-only níscalo, but perretxiko.
    assert hass.states.get("sensor.mycomonitor_urbasa_lactarius_deliciosus") is None
    assert hass.states.get("sensor.mycomonitor_urbasa_calocybe_gambosa") is not None
    # Montejurra: pine, oak, mixed -> níscalo, but no grassland perretxiko.
    assert hass.states.get("sensor.mycomonitor_montejurra_lactarius_deliciosus") is not None
    assert hass.states.get("sensor.mycomonitor_montejurra_calocybe_gambosa") is None


async def test_species_sensor_state_and_attributes(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    provider_result: ProviderResult,
) -> None:
    await setup(hass, config_entry)
    profile = load_profiles()["lactarius_deliciosus"]
    expected = score_species(
        profile, indicator_lookup(provider_result.series), provider_result.today
    )

    state = hass.states.get("sensor.mycomonitor_montejurra_lactarius_deliciosus")
    assert state is not None
    assert float(state.state) == pytest.approx(expected.index)
    assert state.attributes["friendly_name"] == "Montejurra Saffron milk cap"
    assert "unit_of_measurement" not in state.attributes  # an index, not a percentage
    assert state.attributes["category"] == expected.category
    assert state.attributes["evidence"] == "C"
    assert state.attributes["in_season"] is True
    assert {f["id"] for f in state.attributes["factors"]} == {
        "rain",
        "water_balance",
        "temperature",
        "frost",
    }
    assert len(state.attributes["outlook"]) == 7

    perretxiko = hass.states.get("sensor.mycomonitor_urbasa_calocybe_gambosa")
    assert perretxiko is not None
    assert float(perretxiko.state) == 0
    assert perretxiko.attributes["category"] == "out_of_season"
    assert perretxiko.attributes["in_season"] is False


async def test_favorable_conditions(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_fetch: AsyncMock,
    provider_result: ProviderResult,
) -> None:
    await setup(hass, config_entry)
    lookup = indicator_lookup(provider_result.series)
    indices = {
        pid: score_species(p, lookup, provider_result.today).index
        for pid, p in load_profiles().items()
        if p.compatible_with(["pine", "oak", "mixed"])
    }
    best = max(indices, key=lambda k: indices[k] or 0)

    state = hass.states.get("binary_sensor.mycomonitor_montejurra_favorable_conditions")
    assert state is not None
    assert state.attributes["threshold"] == 60
    assert state.attributes["best_species"] == best
    assert state.state == (STATE_ON if (indices[best] or 0) >= 60 else STATE_OFF)
    assert state.attributes["friendly_name"] == "Montejurra Favourable conditions"


async def test_options_threshold(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_fetch: AsyncMock
) -> None:
    await setup(hass, config_entry)
    result = await hass.config_entries.options.async_init(config_entry.entry_id)
    assert result["type"] is FlowResultType.MENU
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "settings"}
    )
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"favorable_threshold": 1}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()  # reload
    state = hass.states.get("binary_sensor.mycomonitor_montejurra_favorable_conditions")
    assert state.attributes["threshold"] == 1
    assert state.state == STATE_ON


async def _open_species_form(hass: HomeAssistant, entry: MockConfigEntry, species: str):  # type: ignore[no-untyped-def]
    result = await hass.config_entries.options.async_init(entry.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"next_step_id": "species"}
    )
    assert result["step_id"] == "species"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {"species": species}
    )
    assert result["step_id"] == "species_edit"
    return result


def _form_defaults(result) -> dict[str, object]:  # type: ignore[no-untyped-def]
    return {
        str(key): key.default() for key in result["data_schema"].schema if key.default is not None
    }


async def test_options_species_override_applies(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_fetch: AsyncMock
) -> None:
    await setup(hass, config_entry)
    result = await _open_species_form(hass, config_entry, "lactarius_deliciosus")
    form = _form_defaults(result)
    assert form["curve_rain"] == "15:0.05, 50:0.5, 100:0.9, 150:1"
    assert form["season_start"] == "09-20"

    # Make any water balance fully satisfy that factor. (The rain factor needs 37 days of
    # history; the fixture has 35, so it is unavailable here; in use there are 92.)
    form |= {"curve_water_balance": "-500:1, 500:1", "season_end": "02-15"}
    result = await hass.config_entries.options.async_configure(result["flow_id"], form)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_SPECIES_OVERRIDES] == {
        "lactarius_deliciosus": {
            "season": {"end": "02-15"},
            "curves": {"water_balance": [[-500.0, 1.0], [500.0, 1.0]]},
        }
    }
    await hass.async_block_till_done()
    state = hass.states.get("sensor.mycomonitor_montejurra_lactarius_deliciosus")
    balance = next(f for f in state.attributes["factors"] if f["id"] == "water_balance")
    assert balance["score"] == 1
    rain = next(f for f in state.attributes["factors"] if f["id"] == "rain")
    assert rain["score"] is None  # not enough history in the fixture


async def test_options_species_invalid_and_reset(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_fetch: AsyncMock
) -> None:
    await setup(hass, config_entry)
    result = await _open_species_form(hass, config_entry, "boletus_edulis")
    form = _form_defaults(result)

    for bad in ({"curve_rain": "abc"}, {"curve_rain": "10:2, 20:1"}, {"season_start": "13-40"}):
        result = await hass.config_entries.options.async_configure(result["flow_id"], form | bad)
        assert result["type"] is FlowResultType.FORM
        assert result["errors"] == {"base": "invalid_override"}
        assert result["description_placeholders"]["error"]

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], form | {"curve_rain": "0:1, 1:1"}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    await hass.async_block_till_done()
    assert "boletus_edulis" in config_entry.options[CONF_SPECIES_OVERRIDES]

    result = await _open_species_form(hass, config_entry, "boletus_edulis")
    assert _form_defaults(result)["curve_rain"] == "0:1, 1:1"
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _form_defaults(result) | {"reset": True}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert config_entry.options[CONF_SPECIES_OVERRIDES] == {}


async def test_unchanged_form_stores_nothing(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_fetch: AsyncMock
) -> None:
    await setup(hass, config_entry)
    result = await _open_species_form(hass, config_entry, "hydnum_repandum")
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], _form_defaults(result)
    )
    assert config_entry.options[CONF_SPECIES_OVERRIDES] == {}


async def test_invalid_stored_override_falls_back(
    hass: HomeAssistant, config_entry: MockConfigEntry, mock_fetch: AsyncMock
) -> None:
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            CONF_SPECIES_OVERRIDES: {"hydnum_repandum": {"curves": {"nope": [[0, 0], [1, 1]]}}}
        },
    )
    await setup(hass, config_entry)
    assert hass.states.get("sensor.mycomonitor_urbasa_hydnum_repandum") is not None
