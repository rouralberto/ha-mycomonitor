# Dashboards

Two example dashboards for three locations in Tierra Estella, in Spanish:

| File | Cards | Needs |
|---|---|---|
| [examples/dashboards/tierra_estella.yaml](../examples/dashboards/tierra_estella.yaml) | Built-in only: gauges, tiles, history graphs, markdown | Nothing |
| [examples/dashboards/tierra_estella_mushroom.yaml](../examples/dashboards/tierra_estella_mushroom.yaml) | [Mushroom](https://github.com/piitaya/lovelace-mushroom) template cards and [ApexCharts](https://github.com/RomRider/apexcharts-card), with a 7-day outlook chart per location | Both cards, from HACS |

Each has four views:

- **Resumen:** the best species per location and its limiting factor, a
  gauge (or Mushroom card) per species, and the key indicators.
- **Especies:** each species' index over the last 30 days at every location,
  plus a table of its factors (value and score) per location. This is how a
  score is explained.
- **Clima:** rain, water balance, temperatures, soil moisture and soil
  temperature for all locations.
- **Observaciones:** how to record visits, and the observation counts.

## Make one for your locations

Entity IDs come from your location names, and which species exist depends on
each location's habitats. Generate a dashboard that matches your setup:

```sh
python scripts/generate_dashboard.py \
  --location "Urbasa=beech,grassland" \
  --location "Montejurra=pine,oak,mixed" \
  --title "MycoMonitor - Tierra Estella" \
  --style core \
  --lang es > mycomonitor.yaml
```

- `--style mushroom` uses the custom cards.
- `--lang en` writes English text.

Then add it in Settings → Dashboards → Add dashboard → *New dashboard from
scratch* → ⋮ → Raw configuration editor (paste), or as a YAML-mode
dashboard:

```yaml
lovelace:
  dashboards:
    dashboard-setas:
      mode: yaml
      filename: dashboards/mycomonitor.yaml
      title: Setas
      icon: mdi:mushroom
      show_in_sidebar: true
```

## Reading the cards

- **Gauge colours:** green from 60 (the default *favourable* threshold),
  yellow from 40, red below.
- **Category:** fuera de temporada, desfavorable, baja, moderada, favorable,
  muy favorable. The bands are conventions, not science.
- **Factor table:** each factor's indicator value and its score (0-1). A lag
  such as "(−7 d)" means the value is read a week earlier.
- **Evidence:** the weakest grade (A-D) among the species' thresholds. See
  [science.md](science.md).
