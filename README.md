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

## Features

- **Several locations**, each with its own coordinates, altitude and
  habitats (beech, pine, oak, mixed, grassland). Weather is fetched for each
  point, never borrowed from another. Everything is set up in the UI; no YAML.
- **Environmental indicators** per location: rain over 3–30 days, antecedent
  precipitation index, climatic water balance, rainy days, dry spell, wet
  streak, air temperatures, frost days, humidity, soil moisture and soil
  temperature with trends.
- **Species suitability:** an index from 0 to 100 per species and location,
  only for species that suit the location's habitats. Attributes give the
  category, every factor's value and score, the limiting factor, the weakest
  evidence grade and a 7-day outlook. Seasons and thresholds can be edited in
  the UI.
- **Favourable conditions:** a binary sensor per location (threshold
  configurable).
- **Observation log:** record finds **and empty visits**. Each one keeps the
  92 days of weather that preceded it, ready for calibrating models later.
  Coordinates are private by default and exports leave them out.
- **Data sources,** in priority order for each day:
  1. your own sensors, via long-term statistics;
  2. an AEMET station's rain gauge (experimental);
  3. Open-Meteo history and forecast.
- **Dashboards:** example *MycoMonitor – Tierra Estella* dashboards, plus a
  generator for your own locations.
- **Light:** no dependencies beyond Home Assistant; English and Spanish.

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
with every threshold's evidence grade and references. Most thresholds are
grade C (expert consensus) and are labelled as our own choices.

## Installation

Requires Home Assistant 2026.10 or newer.

- **HACS:** add `https://github.com/rouralberto/ha-mycomonitor` as a custom
  repository (category *Integration*), install *MycoMonitor*, then restart
  Home Assistant.
- **Manual:** copy `custom_components/mycomonitor` into your configuration's
  `custom_components/`, then restart.

## Configuration

1. **Settings → Devices & services → Add integration → MycoMonitor.** Enter
   your first location: a name, the point on the map, optionally its
   altitude, its habitats and (optionally) local sensors.
2. **Add location** on the MycoMonitor page for more. Edit one with its ⋮
   menu → **Reconfigure**.
3. **Configure** on the MycoMonitor page:
   - *Record a visit* and *Manage observations*;
   - *Settings*: the favourable threshold and the optional AEMET API key;
   - *Species thresholds*: seasons and response curves per species.

Entity IDs don't depend on the UI language, e.g.
`sensor.mycomonitor_urbasa_rain_7d`, `sensor.mycomonitor_urbasa_hydnum_repandum`,
`binary_sensor.mycomonitor_urbasa_favorable_conditions`.

### Services

| Service | Purpose |
|---|---|
| `mycomonitor.record_observation` | Record a find or an empty visit |
| `mycomonitor.export_observations` | CSV or GeoJSON, with the conditions that preceded each observation; no coordinates unless requested |
| `mycomonitor.delete_observation` | Delete one observation |

## Documentation

- [Architecture](docs/architecture.md)
- [Data sources and their limits](docs/data-sources.md) (Open-Meteo, AEMET, your sensors)
- [Indicators](docs/indicators.md)
- [Scientific basis](docs/science.md)
- [Species models](docs/species/README.md)
- [Observations and privacy](docs/observations.md)
- [Dashboards](docs/dashboards.md)

## Roadmap

- Hindcast tool: score past seasons from ERA5-Land and compare with your
  observations.
- More regional station networks (e.g. Gobierno de Navarra), if they offer
  usable data.
- Locally calibrated models, once enough observations exist (see
  [docs/observations.md](docs/observations.md)).
- More species, contributed with evidence via the *Species data* issue
  template.

## Development

```sh
python3.14 -m venv .venv && .venv/bin/pip install -r tests/requirements.txt
.venv/bin/pytest
.venv/bin/ruff check . && .venv/bin/ruff format --check . && .venv/bin/mypy
```

`custom_components/mycomonitor/core/` must not import Home Assistant (a test
enforces this). Translations, species docs and example dashboards are
generated; see [CONTRIBUTING.md](CONTRIBUTING.md).

## Data attribution

- Weather data by [Open-Meteo.com](https://open-meteo.com/) (CC BY 4.0),
  including Copernicus Climate Change Service information (ERA5, ERA5-Land)
  and ECMWF IFS data. Open-Meteo's free API is for non-commercial use.
- Station data, when enabled: © AEMET.

## License

[MIT](LICENSE)
