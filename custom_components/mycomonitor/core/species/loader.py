"""Load and validate the bundled species profiles (blocking file I/O: run in an executor)."""

from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from functools import cache
from pathlib import Path
from typing import Any

import yaml

from ..indicators import compute_indicators
from ..models import DailySeries
from .engine import Factor, ProfileError, Role, Season, SpeciesProfile, validate_curve

PROFILE_DIR = Path(__file__).parent / "profiles"
REFERENCES_FILE = Path(__file__).parent / "references.yaml"
HABITATS = frozenset({"beech", "pine", "oak", "mixed", "grassland"})
INDICATOR_KEYS = frozenset(compute_indicators(DailySeries(), date(2000, 1, 1)))


def _require(data: Mapping[str, Any], key: str, where: str) -> Any:
    if key not in data:
        raise ProfileError(f"{where}: missing '{key}'")
    return data[key]


def profile_from_dict(data: Mapping[str, Any], references: Mapping[str, str]) -> SpeciesProfile:
    """Build a profile from parsed YAML, checking every field."""
    pid = str(_require(data, "id", "profile"))
    habitats = frozenset(_require(data, "habitats", pid))
    if not habitats or not habitats <= HABITATS:
        raise ProfileError(f"{pid}: habitats must be a non-empty subset of {sorted(HABITATS)}")
    season = Season(**{k: str(v) for k, v in _require(data, "season", pid).items()})

    factors = []
    for raw in _require(data, "factors", pid):
        fid = f"{pid}.{raw.get('id')}"
        indicator = str(_require(raw, "indicator", fid))
        if indicator not in INDICATOR_KEYS:
            raise ProfileError(f"{fid}: unknown indicator '{indicator}'")
        refs = tuple(raw.get("references", ()))
        if missing := [r for r in refs if r not in references]:
            raise ProfileError(f"{fid}: unknown references {missing}")
        factors.append(
            Factor(
                id=str(_require(raw, "id", fid)),
                indicator=indicator,
                curve=validate_curve(_require(raw, "curve", fid)),
                role=Role(raw.get("role", "soft")),
                weight=float(raw.get("weight", 1.0)),
                lag=int(raw.get("lag", 0)),
                grade=str(_require(raw, "grade", fid)),
                rationale=str(raw.get("rationale", "")).strip(),
                references=refs,
            )
        )
    if len({f.id for f in factors}) != len(factors):
        raise ProfileError(f"{pid}: duplicate factor ids")
    if not any(f.role is Role.SOFT for f in factors):
        raise ProfileError(f"{pid}: needs at least one soft factor")

    refs = tuple(data.get("references", ()))
    if missing := [r for r in refs if r not in references]:
        raise ProfileError(f"{pid}: unknown references {missing}")
    grade = str(_require(data, "season_grade", pid))
    if grade not in "ABCD" or len(grade) != 1:
        raise ProfileError(f"{pid}: season_grade must be A-D")
    names = {str(k): str(v) for k, v in _require(data, "names", pid).items()}
    return SpeciesProfile(
        id=pid,
        scientific_name=str(_require(data, "scientific_name", pid)),
        names=names,
        habitats=habitats,
        season=season,
        season_grade=grade,
        factors=tuple(factors),
        notes=str(data.get("notes", "")).strip(),
        season_source=str(data.get("season_source", "")).strip(),
        references=refs,
    )


@cache
def load_references(path: Path = REFERENCES_FILE) -> dict[str, str]:
    """Reference key -> citation."""
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    return {str(k): " ".join(str(v).split()) for k, v in data.items()}


@cache
def load_profiles(directory: Path = PROFILE_DIR) -> dict[str, SpeciesProfile]:
    """All bundled profiles, keyed by id, in a stable order."""
    references = load_references()
    profiles = {}
    for path in sorted(directory.glob("*.yaml")):
        profile = profile_from_dict(yaml.safe_load(path.read_text(encoding="utf-8")), references)
        if profile.id != path.stem:
            raise ProfileError(f"{path.name}: id '{profile.id}' must match the file name")
        profiles[profile.id] = profile
    return profiles
