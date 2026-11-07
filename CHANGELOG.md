# Changelog

All notable changes to this project are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), and the project uses
[Semantic Versioning](https://semver.org/).

## [Unreleased]

## [0.4.0] - 2026-11-07

### Added

- Observation log: record finds **and empty visits** from the options flow
  (*Record a visit*) or the `mycomonitor.record_observation` service.
  Coordinates are optional and only saved when explicitly requested; photos
  are media-library references.
- Each observation stores a snapshot: 92 days of raw daily weather from the
  archive, the indicators and the observed species' index on that day. Failed
  snapshots are retried automatically.
- Exports (`mycomonitor.export_observations`): CSV with the preceding
  conditions, or GeoJSON. Coordinates are left out unless requested, and can
  be rounded.
- Deleting observations (options flow or `mycomonitor.delete_observation`).
- An **Observations** sensor per location (counts and latest entries, no
  coordinates).
- Diagnostics report observation counts only.

## [0.3.0] - 2026-11-07

### Added

- Species engine: season window (wrapping over New Year), gates and soft factors
  with piecewise-linear response curves and per-factor lags, combined as
  `100 × season × Π gates × weighted geometric mean`. Every factor carries an
  evidence grade (A-D) and references; results report the weakest grade, the
  limiting factor, the data used and a 7-day outlook.
- Seven species profiles (YAML data): *Boletus edulis* group, *Lactarius
  deliciosus*, *Craterellus cornucopioides*, *Hydnum repandum*, *Lepista nuda*,
  *Cantharellus cibarius*, *Calocybe gambosa*. Seasons are checked against
  local GBIF records.
- A suitability index sensor per species compatible with each location's
  habitats, and a "Favourable conditions" binary sensor per location.
- Options: favourable-conditions threshold, and per-species season and curve
  overrides edited in the UI (validated; reset to defaults).
- Species documentation generated from the profiles (`docs/species/`), and
  translations generated from one source (`scripts/generate_translations.py`).
- Integration icon (light and dark) in `custom_components/mycomonitor/brand/`,
  rendered from the SVG sources in `assets/`: an original mark, a porcini-style
  mushroom inside a dry-to-favourable gauge.

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
