# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.2.0] - 2026-11-07

### Added

- Home Assistant integration: a hub config entry with one sub-entry per
  monitoring location (name, coordinates, optional altitude, habitats),
  added and edited from the UI.
- One device per location with indicator sensors (units, device and state
  classes; less common ones disabled by default), plus a diagnostic
  "Data updated" sensor.
- Language-independent entity IDs (`sensor.mycomonitor_<location>_<indicator>`).
- Updates every 3 hours. A failing location doesn't block the others and
  retries every 15 minutes. After a failed update, the last data is kept for
  up to 12 hours.
- Diagnostics with redacted coordinates and model grid distances.
- English and Spanish translations.
- hassfest and HACS validation in CI.

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
