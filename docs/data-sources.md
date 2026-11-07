# Data sources and their limits

Checked against the live APIs in November 2026.

## Open-Meteo (implemented)

Free for non-commercial use (personal home automation is explicitly
allowed). It needs no API key; the limits are 600 calls/min, 5,000/hour and
10,000/day per IP. Data is CC BY 4.0, so attribution is required. MycoMonitor
makes two calls per location per update.

### What we request

| Variable | API name | Daily value |
|---|---|---|
| Precipitation | `precipitation_sum` | daily sum, mm |
| Air temperature | `temperature_2m_mean`, `_min`, `_max` | °C |
| Relative humidity | `relative_humidity_2m_mean` | % |
| Reference evapotranspiration | `et0_fao_evapotranspiration` | FAO-56 ET₀, mm |
| Soil moisture | `soil_moisture_0_to_7cm`, `soil_moisture_7_to_28cm` (hourly) | daily mean, m³/m³ |
| Soil temperature | `soil_temperature_0_to_7cm`, `soil_temperature_7_to_28cm` (hourly) | daily mean, °C |

Hourly values are averaged per local day when at least 18 of the 24 hours
have data.

### Why two endpoints

- The **forecast API**'s `past_days` (up to 92) is not a reliable history.
  With `best_match`, values only reach back about two months; earlier days
  are null, because the underlying models change.
- The **archive API** (`/v1/archive`, default `best_match`) is gap-free up to
  today. It uses ECMWF IFS at 9 km for recent dates and ERA5/ERA5-Land
  further back. `era5_land` alone has no precipitation.
- **Both APIs serve the IFS soil layers** (0–7 and 7–28 cm), and on
  overlapping days their values match. The forecast API also offers 0–1,
  1–3, 3–9, 9–27 and 27–81 cm from other models, but using those would mean
  splicing different depth bands.

So: archive for the `past_days` before today, forecast from today. The
forecast call also asks for 7 past days, used only to fill any days the
archive lacks. Values before today are `analysis` and values from today are
`forecast`. **Both are modelled**: past precipitation is a model estimate,
not a rain-gauge reading.

### Spatial resolution

| Source | Grid | Notes |
|---|---|---|
| AROME France HD (forecast, short range) | 1.5 km | Covers Navarra; temperature and precipitation only, no soil variables; about 1.5 days ahead |
| ECMWF IFS (archive + forecast) | 9 km | Soil moisture and soil temperature come from here |
| ICON-EU | 7 km | Open-Meteo lists it as discontinued on 2026-11-30, so we never hardcode model names |
| ERA5-Land / ERA5 | 11 km / 25 km | Older history |
| Terrain model for `elevation` | 90 m | Adjusts temperatures to the point's altitude; cannot correct precipitation or soil moisture |

What this means in practice:

- **Shared grid cells.** Two nearby locations can share a cell. In ICON-EU, a
  village at the foot of Montejurra and the mountain itself fall in the same
  7 km cell, so they get identical soil moisture.
- **Cell selection can move far.** With `cell_selection=land` (our default),
  Open-Meteo picks a nearby land cell whose elevation is similar to the
  point's. In a test with Montejurra at 966 m, the archive used a cell about
  10 km away. That suits temperature but may not suit precipitation. The
  grid cell used is recorded in every reading's `Source` and will be shown in
  diagnostics.
- **Things models don't see.** Karst plateaus such as Urbasa drain fast, and
  mountain fog adds moisture that never shows up as precipitation. Treat
  modelled soil moisture there with caution and prefer a local sensor when
  you have one.

## AEMET OpenData (planned)

- **Key:** free, requested at <https://opendata.aemet.es/centrodedescargas/inicio>
  and sent in the `api_key` header.
- **Two-step responses:** each call returns URLs for `datos` and `metadatos`,
  which must then be fetched.
- **Endpoints we need:**
  - `/api/valores/climatologicos/diarios/datos/fechaini/{ini}/fechafin/{fin}/estacion/{idema}`
    returns daily `tmed`, `tmin`, `tmax`, `prec`, `hrmedia`… **about 4 days
    behind**. Each request covers at most about 6 months, per third-party
    libraries.
  - `/api/observacion/convencional/datos/estacion/{idema}` returns hourly
    observations, last 12 hours.
  - `/api/valores/climatologicos/inventarioestaciones/todasestaciones` returns
    the station list (used to pick the nearest stations by distance and
    altitude).
- **Quirks:**
  - `prec` can be `"Ip"` (under 0.1 mm) or `"Acum"`, and the rain day runs
    07:00 to 07:00.
  - Rate limits answer with HTTP 429, and the service has intermittent
    outages.
- **Licence:** reuse is allowed, citing AEMET as the author ("© AEMET").
- **Role:** bias checks and history, not the live path.

## Home Assistant sensors (planned, 0.5)

Your entities (rain gauge, temperature, humidity, soil moisture, soil
temperature) are read through Home Assistant's long-term statistics. They
need a `state_class`, and they survive the recorder purge. When present,
they take priority over model data and are tagged `measured`.

## Other sources considered

- **Regional networks** (e.g. Gobierno de Navarra): often closer to the
  sites, but no documented public API was found. These are candidates for
  future providers.
- **GBIF occurrences:** useful for checking species seasons against our
  models. Records near Tierra Estella match the expected seasons, but there
  are only 40–150 per species, all finds only, with collection bias, so they
  can't calibrate a model.
