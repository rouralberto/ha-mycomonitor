# Scientific basis

MycoMonitor estimates **environmental suitability**: how closely recent and
forecast conditions match those associated with fruiting. That is not the
same as **expected fruiting** (which also depends on the site, the fungus's
own state, host trees and past years), and neither is **actual presence**.
No index in this project is a probability, and none is validated until it
has been checked against observations.

## Evidence grades

Every threshold in a species profile carries a grade:

| Grade | Meaning |
|---|---|
| A | Peer-reviewed, quantitative, relevant region or habitat |
| B | Peer-reviewed but qualitative, another region or habitat, or a preprint |
| C | Expert consensus: field guides, regional mycological bulletins, observation phenology |
| D | Placeholder chosen by us, to be replaced as soon as better evidence exists |

A species index shows its weakest grade.

## What the literature supports

Most quantitative work concerns **total mushroom yield** in Spanish and
Mediterranean pine stands, not when individual species appear:

| Finding | Source | Grade |
|---|---|---|
| Water balance (rain − ET₀) predicts yield better than rain alone; under warming, rain-based models predict stable yields while water-balance models predict decline | Ágreda et al. 2015, *Glob. Change Biol.* 21: 3499–3510 | A |
| Yield follows same-month soil moisture and weather; precipitation acts with about a one-month delay | Karavani et al. 2018, *Agric. For. Meteorol.* 248: 432–440 | A |
| Regional yield models for pine forests in the pre-Pyrenees, with climate and stand predictors | Martínez de Aragón et al. 2007, *For. Ecol. Manage.* 252: 239–256 | A (pine) |
| Yield models for *B. edulis* and *L. deliciosus* in *Pinus sylvestris* forests | Martínez-Peña et al. 2012, *For. Ecol. Manage.* | A (pine) |
| *B. edulis* in beech forests: peak fruiting at about 13 °C mean over the previous 20 days, rising linearly with rain over 26 days | bioRxiv preprint (2025), not peer-reviewed | B |
| *B. edulis* responds to extreme rain and heat events within about 21 days; sudden heat inhibits it | Salerni et al. 2023, *Ital. J. Mycol.* | B |
| Fruiting seasons shift with climate | Kauserud et al. 2008, *PNAS*; Büntgen et al. 2012, *Fungal Ecol.*; Boddy et al. 2014, *Fungal Ecol.* | A (qualitative) |
| *Calocybe gambosa* responds to spring rain and mild temperatures | No peer-reviewed study found; regional bulletins and field guides | C |

**Consequences for the design:**

- Pine-stand yield models do not carry over to beech forests or grasslands.
- Most per-species thresholds will start at grade C or D.
- Thresholds are configurable, and the documentation says where they came
  from.

## Weather-data limitations

Model data is not measurement, and resolution limits what a location can
represent. See [data-sources.md](data-sources.md).

## Observations and bias

Records of finds alone tell you where people looked and succeeded, not
where conditions were poor. MycoMonitor records **visits with outcome "not
found"** too, so local calibration has true negatives. GBIF records are
useful only to sanity-check seasons.

## Species notes

Detailed per-species documents arrive with the species engine (0.3), in
`docs/species/`.
