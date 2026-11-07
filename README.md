# MycoMonitor

**Favourable mushroom-fruiting conditions for Home Assistant.**

MycoMonitor estimates how favourable recent and forecast environmental
conditions are for wild mushrooms to fruit, per location and per species. It
combines weather-model data, official station data and your own Home
Assistant sensors, and explains every number it shows.

> **What it does not do.** It does not tell you whether mushrooms are there,
> it does not identify species, and it says nothing about edibility or about
> whether collecting is allowed where you are. Its scores are transparent
> rule-based indices, **not probabilities**, and are not scientifically
> validated (see [docs/science.md](docs/science.md)).

## Status

**0.4.0, alpha.** What works today:

- **Locations in the UI.** Add MycoMonitor, then as many monitoring
  locations as you like, each with its own coordinates, optional altitude and
  habitats. No YAML.
- **Indicator sensors per location** (one device each): rainfall over 3–30
  days, antecedent precipitation index, climatic water balance, rainy days,
  dry spell, wet streak, air temperatures, frost days, humidity, soil moisture
  and soil temperature with trends. The less common ones are disabled by
  default. Attributes show the window, data coverage and whether the value
  includes forecast data.
- **Data:** Open-Meteo history (about 3 months) plus a 16-day forecast,
  updated every 3 hours. If an update fails, the last data is kept for up to
  12 hours.
- **Species suitability:** an index from 0 to 100 per species and location
  (only for species that match the location's habitats). Attributes include
  the category, every factor's value and score, the limiting factor, the
  weakest evidence grade and a 7-day outlook. Per location there is also a
  **Favourable conditions** binary sensor. Seasons and thresholds can be
  edited in the UI. See [docs/species](docs/species/README.md).
- **Observation log:** record finds and empty visits (UI or service). Each
  keeps the 92 days of weather that preceded it, ready for calibrating models
  later. Coordinates are private by default and exports leave them out. See
  [docs/observations.md](docs/observations.md).
- **Diagnostics** with location coordinates redacted, including how far
  each model grid cell is from the point.
- English and Spanish.

| Version | Adds |
|---|---|
| 0.5 | Local sensor mapping (rain gauge, soil moisture…), example dashboard *MycoMonitor – Tierra Estella*, HACS release |
| later | AEMET OpenData, more regional networks, hindcasts, locally calibrated models |

The design is in [docs/architecture.md](docs/architecture.md).

## Installation

Until the HACS release, add this repository to HACS as a custom repository
(category *Integration*), or copy `custom_components/mycomonitor` into your
Home Assistant `config/custom_components/`. Then restart Home Assistant.
Requires Home Assistant 2026.10 or newer.

## Configuration

1. **Settings → Devices & services → Add integration → MycoMonitor.** Enter
   your first location: a name, the point on the map, optionally its altitude,
   and its habitats.
2. Add more locations from the MycoMonitor page (**Add location**). Edit one
   with its ⋮ menu → **Reconfigure**.

Entity IDs don't depend on the UI language, e.g.
`sensor.mycomonitor_urbasa_rain_7d`.

## Species

| Species | Spanish | Habitats |
|---|---|---|
| *Boletus edulis* group | Boletus | beech, oak, pine, mixed |
| *Lactarius deliciosus* | Níscalo | pine |
| *Craterellus cornucopioides* | Trompeta de los muertos | beech, oak, mixed |
| *Hydnum repandum* | Lengua de vaca | beech, oak, pine, mixed |
| *Lepista nuda* | Pie azul | all, including grassland |
| *Cantharellus cibarius* | Rebozuelo | beech, oak, pine, mixed |
| *Calocybe gambosa* | Perretxiko | grassland |

Each has its own model, documented in [docs/species](docs/species/README.md)
with every threshold's evidence grade and references.

## Documentation

- [Architecture](docs/architecture.md)
- [Data sources and their limits](docs/data-sources.md)
- [Indicators](docs/indicators.md)
- [Scientific basis](docs/science.md)
- [Species models](docs/species/README.md)
- [Observations and privacy](docs/observations.md)

## Development

```sh
python3.14 -m venv .venv && .venv/bin/pip install -r tests/requirements.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy
```

`custom_components/mycomonitor/core/` must not import Home Assistant (a
test enforces this). See [CONTRIBUTING.md](CONTRIBUTING.md).

## Data attribution

Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0),
including Copernicus Climate Change Service information (ERA5, ERA5-Land)
and ECMWF IFS data. Open-Meteo's free API is for non-commercial use.

## License

[MIT](LICENSE)
