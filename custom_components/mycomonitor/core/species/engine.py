"""Rule-based species suitability engine.

A species profile (YAML, see profiles/) defines:

- a season window (month-day dates, may wrap over New Year),
- the habitats it can occur in,
- factors: each reads one indicator (optionally lagged by some days),
  maps it through a piecewise-linear response curve to a score in [0, 1],
  and is either a *gate* (multiplies the result) or *soft* (combined as a
  weighted geometric mean).

    index = 100 × season × Π gates × Π soft^(w / Σw)

The index is a transparent suitability score, NOT a probability. Every
factor carries an evidence grade (A-D, see docs/science.md); the result
reports the weakest one.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field, replace
from datetime import date, timedelta
from enum import StrEnum
import itertools
import math
from typing import Any

from ..indicators import Indicator, compute_indicators
from ..models import DailySeries, DataKind

GRADES = ("A", "B", "C", "D")
MIN_WEIGHT_COVERAGE = 0.5  # below this share of soft weight with data, no index
OUTLOOK_DAYS = 7
MAX_SEASON_DAYS = 330  # catches start/end typos that would wrap into a near-year-round season


class Role(StrEnum):
    """How a factor enters the index."""

    GATE = "gate"
    SOFT = "soft"


class Category(StrEnum):
    """Plain-language band for an index. The cut-offs are conventions, not science."""

    OUT_OF_SEASON = "out_of_season"
    UNFAVORABLE = "unfavorable"
    LOW = "low"
    MODERATE = "moderate"
    FAVORABLE = "favorable"
    VERY_FAVORABLE = "very_favorable"


CATEGORY_BANDS: tuple[tuple[float, Category], ...] = (
    (80, Category.VERY_FAVORABLE),
    (60, Category.FAVORABLE),
    (40, Category.MODERATE),
    (20, Category.LOW),
    (0, Category.UNFAVORABLE),
)


class ProfileError(ValueError):
    """A species profile (or a user override) is invalid."""


Curve = tuple[tuple[float, float], ...]


def validate_curve(points: Sequence[Sequence[float]]) -> Curve:
    """Check a response curve: >= 2 points, x strictly increasing, 0 <= y <= 1."""
    try:
        curve = tuple((float(x), float(y)) for x, y in points)
    except (TypeError, ValueError) as err:
        raise ProfileError(f"curve points must be [x, y] pairs: {points!r}") from err
    if len(curve) < 2:
        raise ProfileError("a curve needs at least two points")
    if any(b[0] <= a[0] for a, b in itertools.pairwise(curve)):
        raise ProfileError("curve x values must be strictly increasing")
    if any(not 0 <= y <= 1 for _, y in curve):
        raise ProfileError("curve y values must be between 0 and 1")
    return curve


def evaluate_curve(curve: Curve, x: float) -> float:
    """Piecewise-linear interpolation, flat beyond the first and last points."""
    if x <= curve[0][0]:
        return curve[0][1]
    if x >= curve[-1][0]:
        return curve[-1][1]
    for (x0, y0), (x1, y1) in itertools.pairwise(curve):
        if x0 <= x <= x1:
            return y0 + (y1 - y0) * (x - x0) / (x1 - x0)
    raise AssertionError("unreachable")  # pragma: no cover


def _parse_month_day(value: str) -> tuple[int, int]:
    try:
        month, day = (int(part) for part in str(value).split("-"))
        date(2001, month, day)  # validates (no 29 February)
    except ValueError as err:
        raise ProfileError(f"season dates are MM-DD (not 02-29): {value!r}") from err
    return month, day


@dataclass(frozen=True, slots=True)
class Season:
    """Fruiting season: ramps up from `start` to `peak_start`, down from `peak_end` to `end`."""

    start: str
    peak_start: str
    peak_end: str
    end: str

    def __post_init__(self) -> None:
        points = [self._offset(v) for v in (self.start, self.peak_start, self.peak_end, self.end)]
        if any(b < a for a, b in itertools.pairwise(points)):
            raise ProfileError("season dates must run start <= peak_start <= peak_end <= end")
        if points[-1] > MAX_SEASON_DAYS:
            raise ProfileError(f"a season can last at most {MAX_SEASON_DAYS} days")

    def _offset(self, value: str) -> int:
        """Days from `start`, wrapping over New Year."""
        start = date(2001, *_parse_month_day(self.start))
        day = date(2001, *_parse_month_day(value))
        return (day - start).days % 365

    def score(self, day: date) -> float:
        """1 in the peak, 0 outside the season, linear in between."""
        mmdd = (day.month, day.day) if (day.month, day.day) != (2, 29) else (2, 28)
        x = (date(2001, *mmdd) - date(2001, *_parse_month_day(self.start))).days % 365
        a, b, c, d = (
            self._offset(v) for v in (self.start, self.peak_start, self.peak_end, self.end)
        )
        if x > d:
            return 0.0
        if x < b:
            return (x - a) / (b - a) if b > a else 1.0
        if x <= c:
            return 1.0
        return (d - x) / (d - c) if d > c else 1.0


@dataclass(frozen=True, slots=True)
class Factor:
    """One environmental condition in a species model."""

    id: str
    indicator: str
    curve: Curve
    role: Role = Role.SOFT
    weight: float = 1.0
    lag: int = 0
    grade: str = "D"
    rationale: str = ""
    references: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        if self.grade not in GRADES:
            raise ProfileError(f"{self.id}: grade must be one of {GRADES}")
        if self.weight <= 0:
            raise ProfileError(f"{self.id}: weight must be positive")
        if not 0 <= self.lag <= 60:
            raise ProfileError(f"{self.id}: lag must be 0..60 days")


@dataclass(frozen=True, slots=True)
class SpeciesProfile:
    """Everything the engine needs to score one species."""

    id: str
    scientific_name: str
    names: Mapping[str, str]
    habitats: frozenset[str]
    season: Season
    season_grade: str
    factors: tuple[Factor, ...]
    notes: str = ""
    season_source: str = ""
    references: tuple[str, ...] = ()

    def name(self, language: str) -> str:
        """Common name in `language` (falls back to English, then the scientific name)."""
        return self.names.get(language) or self.names.get("en") or self.scientific_name

    def compatible_with(self, habitats: Sequence[str]) -> bool:
        """Whether any of a location's habitats suits the species."""
        return bool(self.habitats.intersection(habitats))

    def with_overrides(self, overrides: Mapping[str, Any] | None) -> SpeciesProfile:
        """A copy with user-configured season and curves applied (validated)."""
        if not overrides:
            return self
        season = self.season
        if "season" in overrides:
            season = Season(**{**_season_dict(self.season), **overrides["season"]})
        curves: Mapping[str, Any] = overrides.get("curves", {})
        unknown = set(curves) - {f.id for f in self.factors}
        if unknown:
            raise ProfileError(f"{self.id}: unknown factors {sorted(unknown)}")
        factors = tuple(
            replace(f, curve=validate_curve(curves[f.id])) if f.id in curves else f
            for f in self.factors
        )
        return replace(self, season=season, factors=factors)


def _season_dict(season: Season) -> dict[str, str]:
    return {
        "start": season.start,
        "peak_start": season.peak_start,
        "peak_end": season.peak_end,
        "end": season.end,
    }


@dataclass(frozen=True, slots=True)
class FactorResult:
    """How one factor scored."""

    id: str
    indicator: str
    lag: int
    role: Role
    weight: float
    grade: str
    value: float | None
    unit: str | None
    score: float | None
    kinds: frozenset[DataKind] = frozenset()

    @property
    def available(self) -> bool:
        """Whether there was data for this factor."""
        return self.score is not None


@dataclass(frozen=True, slots=True)
class SpeciesResult:
    """The suitability of one species on one day."""

    species: str
    day: date
    index: float | None
    category: Category | None
    season_score: float
    factors: tuple[FactorResult, ...]
    evidence: str
    limiting_factor: str | None
    weight_coverage: float
    kinds: frozenset[DataKind]
    outlook: tuple[tuple[date, float | None], ...] = field(default=())


def _category(index: float, season_score: float) -> Category:
    if season_score == 0:
        return Category.OUT_OF_SEASON
    for threshold, category in CATEGORY_BANDS:
        if index >= threshold:
            return category
    return Category.UNFAVORABLE  # pragma: no cover


IndicatorLookup = Callable[[date], Mapping[str, Indicator]]


def indicator_lookup(series: DailySeries) -> IndicatorLookup:
    """Indicators per end date, computed once per date."""
    cache: dict[date, Mapping[str, Indicator]] = {}

    def lookup(day: date) -> Mapping[str, Indicator]:
        if day not in cache:
            cache[day] = compute_indicators(series, day)
        return cache[day]

    return lookup


def score_species(profile: SpeciesProfile, lookup: IndicatorLookup, day: date) -> SpeciesResult:
    """Score `profile` for `day` (today, a past day or a forecast day)."""
    season_score = profile.season.score(day)
    results: list[FactorResult] = []
    for factor in profile.factors:
        indicator = lookup(day - timedelta(days=factor.lag)).get(factor.indicator)
        value = indicator.value if indicator is not None else None
        results.append(
            FactorResult(
                id=factor.id,
                indicator=factor.indicator,
                lag=factor.lag,
                role=factor.role,
                weight=factor.weight,
                grade=factor.grade,
                value=value,
                unit=indicator.unit if indicator is not None else None,
                score=evaluate_curve(factor.curve, value) if value is not None else None,
                kinds=indicator.kinds if indicator is not None else frozenset(),
            )
        )

    gate_scores = [r.score for r in results if r.role is Role.GATE and r.score is not None]
    soft = [r for r in results if r.role is Role.SOFT]
    soft_scored = [(r.weight, r.score) for r in soft if r.score is not None]
    total_weight = sum(r.weight for r in soft) or 1.0
    coverage = sum(w for w, _ in soft_scored) / total_weight

    index: float | None = None
    if coverage >= MIN_WEIGHT_COVERAGE:
        index = round(
            100 * season_score * math.prod(gate_scores) * _weighted_geometric_mean(soft_scored), 1
        )

    scored = [(r.score, -r.weight, r.id) for r in results if r.score is not None]
    limiting = min(scored)[2] if scored else None
    grades = [profile.season_grade, *(f.grade for f in profile.factors)]
    return SpeciesResult(
        species=profile.id,
        day=day,
        index=index,
        category=_category(index, season_score) if index is not None else None,
        season_score=season_score,
        factors=tuple(results),
        evidence=max(grades),  # "D" is the weakest
        limiting_factor=limiting,
        weight_coverage=round(coverage, 2),
        kinds=frozenset(k for r in results for k in r.kinds),
    )


def _weighted_geometric_mean(pairs: Sequence[tuple[float, float]]) -> float:
    """Π score^(w/Σw); 0 if any score is 0, 1 if there are none."""
    if not pairs:
        return 1.0
    if any(score <= 0 for _, score in pairs):
        return 0.0
    total = sum(weight for weight, _ in pairs)
    return math.exp(sum(weight * math.log(score) for weight, score in pairs) / total)


def score_with_outlook(
    profile: SpeciesProfile,
    lookup: IndicatorLookup,
    today: date,
    days: int = OUTLOOK_DAYS,
) -> SpeciesResult:
    """Today's result, plus the index for each of the next `days` (forecast-based)."""
    result = score_species(profile, lookup, today)
    outlook = tuple(
        (day, score_species(profile, lookup, day).index)
        for day in (today + timedelta(days=n) for n in range(1, days + 1))
    )
    return replace(result, outlook=outlook)
