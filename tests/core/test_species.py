"""Tests for the species engine and the bundled profiles."""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest
import yaml

from custom_components.mycomonitor.core.indicators import Indicator
from custom_components.mycomonitor.core.models import DataKind, Variable
from custom_components.mycomonitor.core.species import engine as eng
from custom_components.mycomonitor.core.species.loader import (
    INDICATOR_KEYS,
    load_profiles,
    load_references,
    profile_from_dict,
)

from .helpers import series_of

DAY = date(2026, 10, 20)


# --- curves ----------------------------------------------------------------


def test_curve_interpolates_and_clamps() -> None:
    curve = eng.validate_curve([[0, 0], [10, 1], [20, 0.5]])
    assert eng.evaluate_curve(curve, -5) == 0
    assert eng.evaluate_curve(curve, 5) == pytest.approx(0.5)
    assert eng.evaluate_curve(curve, 15) == pytest.approx(0.75)
    assert eng.evaluate_curve(curve, 99) == 0.5


@pytest.mark.parametrize(
    ("points", "message"),
    [
        ([[0, 0]], "at least two"),
        ([[0, 0], [0, 1]], "strictly increasing"),
        ([[0, 0], [1, 1.5]], "between 0 and 1"),
        ([[0], [1, 1]], "pairs"),
    ],
)
def test_curve_validation(points: list[list[float]], message: str) -> None:
    with pytest.raises(eng.ProfileError, match=message):
        eng.validate_curve(points)


# --- season ----------------------------------------------------------------


def test_season_ramps_and_peak() -> None:
    season = eng.Season("09-01", "10-01", "10-31", "11-30")
    assert season.score(date(2026, 8, 31)) == 0
    assert season.score(date(2026, 9, 16)) == pytest.approx(0.5)
    assert season.score(date(2026, 10, 15)) == 1
    assert season.score(date(2026, 11, 15)) == pytest.approx(0.5)
    assert season.score(date(2026, 12, 1)) == 0


def test_season_wraps_over_new_year() -> None:
    season = eng.Season("10-01", "11-01", "12-31", "02-15")
    assert season.score(date(2026, 12, 20)) == 1
    assert 0 < season.score(date(2027, 1, 20)) < 1
    assert season.score(date(2027, 3, 1)) == 0
    assert season.score(date(2026, 7, 1)) == 0


def test_season_handles_leap_day() -> None:
    season = eng.Season("01-15", "02-01", "03-15", "04-01")
    assert season.score(date(2028, 2, 29)) == 1


@pytest.mark.parametrize(
    "dates",
    [("10-01", "09-01", "10-31", "11-30"), ("13-01", "10-01", "10-31", "11-30"), ("02-29",) * 4],
)
def test_season_validation(dates: tuple[str, ...]) -> None:
    with pytest.raises(eng.ProfileError):
        eng.Season(*dates)


# --- scoring ---------------------------------------------------------------


def make_profile(**changes: object) -> eng.SpeciesProfile:
    base = eng.SpeciesProfile(
        id="test",
        scientific_name="Testus testus",
        names={"en": "Test", "es": "Prueba"},
        habitats=frozenset({"pine"}),
        season=eng.Season("09-01", "10-01", "10-31", "11-30"),
        season_grade="C",
        factors=(
            eng.Factor("rain", "rain_7d", eng.validate_curve([[0, 0], [20, 1]]), weight=3),
            eng.Factor("temp", "temperature_mean_7d", eng.validate_curve([[0, 0], [10, 1]])),
            eng.Factor(
                "frost",
                "frost_days_7d",
                eng.validate_curve([[0, 1], [2, 0]]),
                role=eng.Role.GATE,
                grade="B",
            ),
        ),
    )
    return eng.SpeciesProfile(**{**{f: getattr(base, f) for f in base.__slots__}, **changes})  # type: ignore[arg-type]


def lookup_from(values: dict[str, float | None], kind: DataKind = DataKind.ANALYSIS):  # type: ignore[no-untyped-def]
    def lookup(day: date) -> dict[str, Indicator]:
        return {
            key: Indicator(key, value, "x", day, day, 1.0, frozenset({kind}))
            for key, value in values.items()
        }

    return lookup


def test_score_combines_season_gates_and_weighted_geometric_mean() -> None:
    profile = make_profile()
    lookup = lookup_from({"rain_7d": 10, "temperature_mean_7d": 10, "frost_days_7d": 1})
    result = eng.score_species(profile, lookup, DAY)
    # season 1, gate 0.5, soft: rain 0.5 (w3), temp 1.0 (w1) -> 0.5^(3/4)
    assert result.index == pytest.approx(round(100 * 0.5 * 0.5**0.75, 1))
    assert result.category is eng.Category.LOW  # 29.7
    assert result.limiting_factor in {"rain", "frost"}
    assert result.evidence == "D"  # factors default to D
    assert result.weight_coverage == 1
    assert result.kinds == {DataKind.ANALYSIS}


def test_out_of_season_is_zero() -> None:
    lookup = lookup_from({"rain_7d": 50, "temperature_mean_7d": 15, "frost_days_7d": 0})
    result = eng.score_species(make_profile(), lookup, date(2026, 6, 1))
    assert result.index == 0
    assert result.category is eng.Category.OUT_OF_SEASON


def test_zero_soft_factor_zeroes_index() -> None:
    lookup = lookup_from({"rain_7d": 0, "temperature_mean_7d": 15, "frost_days_7d": 0})
    result = eng.score_species(make_profile(), lookup, DAY)
    assert result.index == 0
    assert result.category is eng.Category.UNFAVORABLE
    assert result.limiting_factor == "rain"


def test_missing_minor_factor_still_scores() -> None:
    lookup = lookup_from({"rain_7d": 20, "temperature_mean_7d": None, "frost_days_7d": 0})
    result = eng.score_species(make_profile(), lookup, DAY)
    assert result.index == 100
    assert result.weight_coverage == pytest.approx(0.75)
    assert not next(f for f in result.factors if f.id == "temp").available


def test_missing_major_factor_gives_no_index() -> None:
    lookup = lookup_from({"rain_7d": None, "temperature_mean_7d": 10, "frost_days_7d": 0})
    result = eng.score_species(make_profile(), lookup, DAY)
    assert result.index is None
    assert result.category is None


def test_lag_reads_an_earlier_day() -> None:
    seen: list[date] = []

    def lookup(day: date) -> dict[str, Indicator]:
        seen.append(day)
        return {}

    profile = make_profile(
        factors=(eng.Factor("rain", "rain_7d", eng.validate_curve([[0, 0], [1, 1]]), lag=5),)
    )
    eng.score_species(profile, lookup, DAY)
    assert seen == [DAY - timedelta(days=5)]


def test_outlook_covers_next_days() -> None:
    lookup = lookup_from({"rain_7d": 20, "temperature_mean_7d": 10, "frost_days_7d": 0})
    result = eng.score_with_outlook(make_profile(), lookup, DAY, days=3)
    assert [d for d, _ in result.outlook] == [DAY + timedelta(days=n) for n in (1, 2, 3)]
    assert all(index == 100 for _, index in result.outlook)


def test_indicator_lookup_caches_per_day() -> None:
    series = series_of({Variable.PRECIPITATION: [1.0] * 10})
    lookup = eng.indicator_lookup(series)
    end = date(2026, 10, 10)
    assert lookup(end) is lookup(end)
    assert lookup(end)["rain_7d"].value == 7


# --- overrides -------------------------------------------------------------


def test_overrides_replace_season_and_curves() -> None:
    profile = make_profile().with_overrides(
        {"season": {"end": "12-31"}, "curves": {"rain": [[0, 0], [40, 1]]}}
    )
    assert profile.season.end == "12-31"
    assert profile.season.start == "09-01"
    rain = next(f for f in profile.factors if f.id == "rain")
    assert rain.curve == ((0, 0), (40, 1))
    assert make_profile().with_overrides(None) == make_profile()


@pytest.mark.parametrize(
    "overrides",
    [
        {"curves": {"nope": [[0, 0], [1, 1]]}},
        {"curves": {"rain": [[0, 0]]}},
        {"season": {"start": "12-01"}},
    ],
)
def test_invalid_overrides(overrides: dict[str, object]) -> None:
    with pytest.raises(eng.ProfileError):
        make_profile().with_overrides(overrides)


def test_names_and_habitats() -> None:
    profile = make_profile()
    assert profile.name("es") == "Prueba"
    assert profile.name("fr") == "Test"
    assert profile.compatible_with(["oak", "pine"])
    assert not profile.compatible_with(["grassland"])


# --- bundled profiles ------------------------------------------------------

EXPECTED_SPECIES = {
    "boletus_edulis",
    "lactarius_deliciosus",
    "craterellus_cornucopioides",
    "hydnum_repandum",
    "lepista_nuda",
    "cantharellus_cibarius",
    "calocybe_gambosa",
}


def test_bundled_profiles_load() -> None:
    profiles = load_profiles()
    assert set(profiles) == EXPECTED_SPECIES
    references = load_references()
    for profile in profiles.values():
        assert {"es", "en"} <= set(profile.names), profile.id
        assert profile.season_source, profile.id
        assert profile.notes, profile.id
        for factor in profile.factors:
            assert factor.indicator in INDICATOR_KEYS
            assert factor.rationale, f"{profile.id}.{factor.id}"
            assert all(r in references for r in factor.references)


def test_factor_ids_have_translations() -> None:
    """The options form labels factors by id, so ids must come from a known set."""
    known = {"rain", "water_balance", "temperature", "frost", "heat", "wet_days", "soil_warming"}
    for profile in load_profiles().values():
        assert {f.id for f in profile.factors} <= known, profile.id


def test_profile_loader_rejects_bad_data() -> None:
    raw = yaml.safe_load(
        (
            Path(__file__).parents[2]
            / "custom_components/mycomonitor/core/species/profiles/lepista_nuda.yaml"
        ).read_text()
    )
    refs = load_references()
    bad_indicator = {**raw, "factors": [{**raw["factors"][0], "indicator": "nope"}]}
    with pytest.raises(eng.ProfileError, match="unknown indicator"):
        profile_from_dict(bad_indicator, refs)
    bad_habitat = {**raw, "habitats": ["desert"]}
    with pytest.raises(eng.ProfileError, match="habitats"):
        profile_from_dict(bad_habitat, refs)
    bad_ref = {**raw, "references": ["nobody2020"]}
    with pytest.raises(eng.ProfileError, match="references"):
        profile_from_dict(bad_ref, refs)
    only_gates = {**raw, "factors": [raw["factors"][-1]]}
    with pytest.raises(eng.ProfileError, match="soft factor"):
        profile_from_dict(only_gates, refs)
    missing = {k: v for k, v in raw.items() if k != "season_grade"}
    with pytest.raises(eng.ProfileError, match="season_grade"):
        profile_from_dict(missing, refs)


def test_seasons_match_local_records() -> None:
    """Sanity check: each profile's peak covers the month with most local GBIF records."""
    peak_month = {
        "boletus_edulis": 10,
        "lactarius_deliciosus": 11,
        "craterellus_cornucopioides": 10,
        "hydnum_repandum": 10,
        "lepista_nuda": 12,
        "cantharellus_cibarius": 7,
        "calocybe_gambosa": 5,
    }
    for pid, month in peak_month.items():
        assert load_profiles()[pid].season.score(date(2026, month, 15)) == 1, pid


def test_scenarios_on_real_profiles() -> None:
    """Wet, mild October favours níscalo; a dry one does not; frost suppresses it."""
    niscalo = load_profiles()["lactarius_deliciosus"]
    day = date(2026, 11, 5)
    wet = {
        "rain_30d": 120,
        "water_balance_30d": 30,
        "temperature_mean_14d": 11,
        "frost_days_7d": 0,
    }
    good = eng.score_species(niscalo, lookup_from(wet), day)
    dry = eng.score_species(
        niscalo, lookup_from(wet | {"rain_30d": 10, "water_balance_30d": -70}), day
    )
    frosty = eng.score_species(niscalo, lookup_from(wet | {"frost_days_7d": 6}), day)
    assert good.index is not None
    assert dry.index is not None
    assert frosty.index is not None
    assert good.index >= 80
    assert dry.index < 15
    assert frosty.index <= good.index * 0.25
    assert good.evidence == "C"
