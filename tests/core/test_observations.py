"""Tests for observations, snapshots and exports."""

from __future__ import annotations

import csv
from datetime import UTC, date, datetime, timedelta
import io

import pytest

from custom_components.mycomonitor.core.indicators import compute_indicators
from custom_components.mycomonitor.core.models import Location, Variable
from custom_components.mycomonitor.core.observations import (
    EXPORT_INDICATORS,
    SNAPSHOT_DAYS,
    ExportOptions,
    Observation,
    Outcome,
    Quantity,
    Snapshot,
    export_csv,
    export_geojson,
    make_snapshot,
)
from custom_components.mycomonitor.core.providers import open_meteo
from custom_components.mycomonitor.core.species.loader import load_profiles

from ..fake_open_meteo import fixture_result, load, session_with

URBASA = Location("Urbasa", 42.84, -2.17)


def obs(**changes: object) -> Observation:
    base: dict[str, object] = {
        "id": "abc",
        "species": "hydnum_repandum",
        "day": date(2026, 11, 5),
        "location_id": "sub1",
        "location_name": "Urbasa",
        "outcome": Outcome.FOUND,
        "quantity": Quantity.SOME,
        "created_at": "2026-11-05T18:00:00+00:00",
        "habitat": "beech",
        "notes": "near the path",
        "latitude": 42.8412345,
        "longitude": -2.1698765,
    }
    return Observation(**(base | changes))  # type: ignore[arg-type]


@pytest.mark.parametrize(
    ("changes", "message"),
    [
        ({"latitude": None}, "both"),
        ({"latitude": 99.0}, "latitude"),
        ({"longitude": 200.0}, "longitude"),
        ({"outcome": Outcome.NOT_FOUND}, "none"),
        ({"quantity": Quantity.NONE}, "quantity"),
    ],
)
def test_observation_validation(changes: dict[str, object], message: str) -> None:
    with pytest.raises(ValueError, match=message):
        obs(**changes)


def test_not_found_visit_is_valid() -> None:
    visit = obs(outcome=Outcome.NOT_FOUND, quantity=Quantity.NONE, latitude=None, longitude=None)
    assert not visit.has_coordinates


async def test_snapshot_and_roundtrip() -> None:
    result = await fixture_result()
    day = result.today - timedelta(days=1)
    profile = load_profiles()["hydnum_repandum"]
    snapshot = make_snapshot(result.series, day, URBASA, profile, datetime(2026, 11, 7, tzinfo=UTC))
    assert snapshot.start == day - timedelta(days=SNAPSHOT_DAYS - 1)
    assert set(snapshot.daily) == {v.value for v in Variable}
    assert all(len(values) == SNAPSHOT_DAYS for values in snapshot.daily.values())
    rain = snapshot.daily["precipitation"]
    assert rain[-1] == pytest.approx(result.series.get(Variable.PRECIPITATION, day).value)
    assert rain[0] is None  # the fixture has 35 days, the snapshot window is 92
    expected = compute_indicators(result.series, day)
    assert snapshot.indicators["rain_7d"] == pytest.approx(expected["rain_7d"].value, abs=1e-3)
    assert snapshot.species_evidence == "C"
    assert all("grid_distance_km" in s for s in snapshot.sources)

    full = obs(snapshot=snapshot)
    again = Observation.from_dict(full.to_dict())
    assert again == full
    assert Snapshot.from_dict(snapshot.to_dict()) == snapshot


def test_summary_has_no_private_fields() -> None:
    summary = obs().summary()
    assert "latitude" not in summary
    assert "notes" not in summary
    assert summary["has_snapshot"] is False


def test_csv_without_coordinates_by_default() -> None:
    text = export_csv([obs()], ExportOptions())
    rows = list(csv.DictReader(io.StringIO(text)))
    assert "latitude" not in rows[0]
    assert "42.84" not in text
    assert rows[0]["species"] == "hydnum_repandum"
    assert set(EXPORT_INDICATORS) <= set(rows[0])


def test_csv_with_rounded_coordinates() -> None:
    text = export_csv([obs()], ExportOptions(include_coordinates=True, decimals=2))
    row = next(csv.DictReader(io.StringIO(text)))
    assert row["latitude"] == "42.84"
    assert row["longitude"] == "-2.17"


def test_geojson_needs_coordinates_and_skips_unlocated() -> None:
    with pytest.raises(ValueError, match="include_coordinates"):
        export_geojson([obs()], ExportOptions())
    located = obs()
    unlocated = obs(id="def", latitude=None, longitude=None)
    doc = export_geojson([located, unlocated], ExportOptions(include_coordinates=True, decimals=3))
    assert len(doc["features"]) == 1
    assert doc["features"][0]["geometry"]["coordinates"] == [-2.17, 42.841]


def test_export_options_validation() -> None:
    with pytest.raises(ValueError, match="decimals"):
        ExportOptions(decimals=9)


async def test_fetch_history_uses_archive_only() -> None:
    session = session_with()
    provider = open_meteo.OpenMeteoProvider(session)  # type: ignore[arg-type]
    series = await provider.async_fetch_history(URBASA, end=date(2026, 11, 6), days=35)
    ((url, params),) = session.calls
    assert url == open_meteo.ARCHIVE_URL
    assert params["start_date"] == "2026-10-03"
    assert params["end_date"] == "2026-11-06"
    archive_days = load("urbasa_archive")["daily"]["time"]
    assert [d.isoformat() for d in series.dates(Variable.PRECIPITATION)] == archive_days
    with pytest.raises(ValueError, match="days"):
        await provider.async_fetch_history(URBASA, end=date(2026, 11, 6), days=0)
