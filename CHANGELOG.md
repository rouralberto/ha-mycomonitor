# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.1.0] - 2026-11-07

### Added

- Core data model: daily series with per-value provenance (measured,
  station, analysis, forecast; model and grid cell).
- Open-Meteo provider: history from the archive API and forecast from the
  forecast API, joined at today, with fallback for archive gaps.
- Indicator engine: rainfall sums, antecedent precipitation index, climatic
  water balance, wet days, dry spell, wet streak, air temperatures, frost
  days, humidity, soil moisture and soil temperature with trends.
- Documentation of the architecture, data sources, indicators and
  scientific basis.
- CI: ruff, mypy (strict on the core) and pytest.
