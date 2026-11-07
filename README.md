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

**0.1.0, alpha: the environmental core only.** No Home Assistant entities
yet. What works today:

- Open-Meteo provider: about 3 months of history plus a 16-day forecast for
  any coordinates, with every value tagged as *analysis* (modelled past) or
  *forecast*.
- Indicator engine: rainfall over 3–30 days, antecedent precipitation index,
  climatic water balance, temperatures, frost days, dry spells, soil
  moisture and soil temperature with trends. They work for today, for past
  days and for forecast days.

| Version | Adds |
|---|---|
| 0.2 | Home Assistant integration: hub + one sub-entry per location, indicator sensors, diagnostics, Spanish and English |
| 0.3 | Species engine and seven species profiles, suitability index sensors, "favourable conditions" binary sensor |
| 0.4 | Recording findings (and empty visits) with the conditions that preceded them; privacy-safe export |
| 0.5 | Local sensor mapping (rain gauge, soil moisture…), example dashboard *MycoMonitor – Tierra Estella*, HACS release |
| later | AEMET OpenData, more regional networks, hindcasts, locally calibrated models |

The design is in [docs/architecture.md](docs/architecture.md).

## Species planned for 0.3

*Boletus edulis* group, *Lactarius deliciosus*, *Craterellus cornucopioides*,
*Hydnum repandum*, *Lepista nuda*, *Cantharellus cibarius* and *Calocybe
gambosa*. Each gets its own model, with every threshold graded by the
strength of its evidence and configurable by the user.

## Documentation

- [Architecture](docs/architecture.md)
- [Data sources and their limits](docs/data-sources.md)
- [Indicators](docs/indicators.md)
- [Scientific basis](docs/science.md)

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
