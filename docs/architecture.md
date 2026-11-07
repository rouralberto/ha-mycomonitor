# Architecture

## Principles

1. **Explainable over clever.** Rule-based models with every threshold
   documented, graded by evidence and configurable. Statistical models only
   once enough local observations exist.
2. **Say what each number is.** Every value carries its provenance:
   measured, station, analysis (modelled past) or forecast, plus the model
   and grid cell. An index is never presented as a probability.
3. **Each location stands alone.** Weather is fetched for each location's
   own coordinates and altitude; nothing is borrowed from another location.
4. **Small and dependency-free.** Only what Home Assistant already ships
   (aiohttp, PyYAML). No numpy or pandas: a location is about 110 days of a
   dozen variables.
5. **Home Assistant-native, but not Home Assistant-bound.** The core has no
   Home Assistant imports, so it can later become a library, a CLI or an
   external collector (e.g. publishing over MQTT).

## Layers

```
custom_components/mycomonitor/
  (0.2+) config_flow · coordinator · sensor · binary_sensor · diagnostics · services
        │  plain dataclasses
  core/ ▼
    models.py        Variable, DataKind, Source, Reading, DailySeries, Location
    providers/       base (interface + errors), open_meteo, (later) ha_statistics, aemet
    indicators.py    pure functions over a DailySeries, for any day
    (0.3) species/   factor engine + YAML species profiles
    (0.4) observations.py
```

### Data model

- `DailySeries` holds daily `Reading`s per `Variable`, keyed by the
  location's local date. Units are fixed per variable (`UNITS`).
- Each `Reading` has a `Source`: provider, `DataKind`, model, and the grid
  cell the model used (latitude, longitude, elevation).
- Merging never overwrites: `fill_gaps_from` adds readings only where none
  exist, so priority is set by merge order. Starting in 0.5 the order is
  measured, then station, then model.

### Providers

A provider implements `async_fetch(location, past_days, forecast_days)` and
returns a `ProviderResult` (series, the location's "today", warnings). It
raises `ProviderConnectionError`, `ProviderRateLimitError` or
`ProviderResponseError`, which the coordinator maps to entity availability.

Open-Meteo makes two calls per fetch: the forecast API (today onwards) and
the archive API (history). Why both is explained in
[data-sources.md](data-sources.md).

### Indicators

Pure functions with explicit windows ending on a given day (inclusive). They
return an `Indicator` with value, unit, window, coverage and the data kinds
used. Missing data is never silently filled in. The same functions serve
three purposes:

- **current conditions:** the window ends today;
- **outlook:** the window ends on a forecast day;
- **observation snapshots and hindcasts:** the window ends on a past day.

## Home Assistant layer (0.2)

- **Config entries:** one hub entry (single instance) holds global settings
  and the optional AEMET key. **Each location is a config sub-entry** and
  becomes one device:
  - name, coordinates and altitude;
  - habitats (beech, pine, oak, mixed, grassland) and substrate;
  - optional station and Home Assistant entity mapping (later versions).
- **Coordinator:** one per location, updating every 3 hours (two Open-Meteo
  calls). A location that fails at startup doesn't block the others and
  retries every 15 minutes. After a failed update, the last data is kept for
  up to 12 hours and marked stale.
- **Entities:** about 20 per location, with the less important ones disabled
  by default:
  - indicator sensors with proper units and state classes;
  - one suitability index sensor per species compatible with the habitats;
  - one "favourable conditions" binary sensor;
  - a diagnostic "last update" sensor.

  Large attributes (factor breakdown, outlook) are excluded from the
  recorder.
- **No `number`/`select` entities:** thresholds live in the options flow, not
  on dashboards.
- **No YAML required:** everything is configured in the UI.

## Species engine (0.3)

See [species/](species/README.md) for the generated per-species pages.


- Profiles are data (`core/species/profiles/*.yaml`). Each factor names:
  - an indicator and an optional time lag (e.g. "rain 10–25 days ago");
  - a response curve (trapezoid or threshold);
  - a weight, an evidence grade (A–D) and references.
- **Index:** the season gate (shifted by altitude), habitat compatibility and
  hard limits (frost, drought) multiply a weighted geometric mean of the soft
  factors. The result is a unitless index from 0 to 100, **not a
  probability**.
- **Output:** the index, a category and the factor breakdown, plus the
  limiting factor, the weakest evidence grade, data quality and a 7-day
  outlook.

## Observations (0.4)

- **Fields:**
  - species, date, location and habitat;
  - outcome (found / **not found**) and a quantity class;
  - optional notes, coordinates and photo path.
- **Recording:** an options-flow step and a service. Stored in Home
  Assistant's `.storage`.
- **Snapshot:** each record saves the indicators for the 60 days before it,
  plus provider and model versions, so later calibration is reproducible.
- **Privacy:** coordinates never appear in attributes, logs or diagnostics.
  Exports leave them out unless explicitly requested.

## Calibration (later)

1. Hindcast the rule-based models on ERA5-Land for past seasons and compare
   them with recorded observations and GBIF phenology.
2. Fit simple statistical models (e.g. logistic regression on
   found/not-found visits) only once there are about 10 events per
   predictor (Peduzzi et al., 1996).
