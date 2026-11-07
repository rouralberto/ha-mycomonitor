# Observations

Recording what you find, **and where you looked and found nothing**, is what
will eventually turn the rule-based indices into locally calibrated models.

## Recording

- **UI:** Settings → Devices & services → MycoMonitor → **Configure** →
  **Record a visit**.
- **Service:** `mycomonitor.record_observation`, handy from the mobile app or a
  script:

```yaml
action: mycomonitor.record_observation
data:
  location: Urbasa          # location name or sub-entry id
  species: hydnum_repandum  # or "other"
  outcome: found            # or not_found
  quantity: some            # few (1-5), some (6-20), many (>20); none for not_found
  date: "2026-11-05"        # optional, defaults to today
  habitat: beech            # optional
  notes: ""                 # optional; avoid exact places
  # latitude / longitude    # optional; stored privately
```

Each location has an **Observations** sensor (count, finds, empty visits and
the latest entries, with no coordinates).

## What is stored

| Field | Notes |
|---|---|
| species, date, location, outcome, quantity, habitat, notes | Always |
| latitude, longitude | Only if given (UI: only if *Save exact coordinates* is ticked) |
| photo | A media-library reference, not the image |
| snapshot | Daily weather for the 92 days up to the date (raw values for every variable), the indicators on that day, the observed species' index and evidence grade, and the data sources with their grid distances |

The snapshot always comes from the Open-Meteo archive, so finds recorded
days later get the same kind of data as those recorded on the spot. If the
fetch fails, the observation is saved anyway and the snapshot is added on a
later update.

Raw daily values are stored, not only today's features, so future models can
compute whatever they need without re-downloading.

## Privacy

- Stored in `.storage/mycomonitor.observations` with file mode 0600, and
  included in Home Assistant backups like the rest of `.storage`.
- Coordinates and notes never appear in entity attributes, logs or
  diagnostics. Diagnostics only report counts.
- Exports (`mycomonitor.export_observations`) **leave coordinates out by
  default**. With `include_coordinates: true` you can round them (`decimals:
  3` is about 100 m, `2` about 1 km). GeoJSON is only available with
  coordinates.
- Notes are exported as written: don't put exact places in them.

## Exports

```yaml
action: mycomonitor.export_observations
data:
  format: csv                 # or geojson
  include_coordinates: false
```

Files go to `<config>/mycomonitor/exports/`. Each CSV row has the observation,
the observed species' index on that day and the main indicators (rain over
7/14/30 days, water balance, dry spell, temperatures, frost days, soil
moisture and temperature). That is enough for a first look at which
conditions preceded finds and empty visits.

## Towards calibrated models

Plan, in order, once enough observations exist:

1. **Hindcast** the rule-based indices against your records: did finds happen
   at higher indices than empty visits?
2. **Adjust thresholds** (Configure → Species thresholds) where the records
   clearly disagree, and note why.
3. **Simple statistical models**, e.g. logistic regression of found / not
   found on a few indicators, only with roughly 10 events per predictor
   (Peduzzi et al., 1996), validated on seasons they weren't fitted on.

No machine learning is used until then.
