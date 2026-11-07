# Indicators

All windows end on a given day **inclusive**: `rain_7d` on 7 November covers
1–7 November. When the window ends today it includes today's partly forecast
value, and `kinds` lists `forecast`. For the outlook, the window ends on a
forecast day.

| Key | Definition | Unit | Missing data |
|---|---|---|---|
| `rain_3d` … `rain_30d` | Sum of daily precipitation over 3, 7, 14, 21, 30 days | mm | Needs every day |
| `api_30d` | Antecedent precipitation index: Σ P(t−i)·0.9ⁱ, i = 0…29 (Kohler & Linsley, 1951). Recent rain counts more. | mm | Needs every day |
| `water_balance_14d`, `_30d` | Σ (precipitation − ET₀). Negative means the atmosphere demanded more water than fell. | mm | Needs every day of both |
| `wet_days_14d` | Days with ≥ 1 mm (ETCCDI wet-day threshold) | d | Needs every day |
| `dry_spell` | Consecutive days < 1 mm up to and including the day (capped at 60) | d | Stops at a gap |
| `wet_streak` | Consecutive days ≥ 1 mm up to and including the day (capped at 60) | d | Stops at a gap |
| `temperature_mean_7d`, `_14d`, `_21d` | Mean of daily mean air temperature | °C | ≥ 80 % of days |
| `temperature_min_7d` | Lowest daily minimum | °C | ≥ 80 % |
| `temperature_max_7d` | Highest daily maximum | °C | ≥ 80 % |
| `frost_days_7d`, `_14d` | Days with minimum < 0 °C (ETCCDI frost day) | d | Needs every day |
| `humidity_mean_7d` | Mean relative humidity | % | ≥ 80 % |
| `soil_moisture` | Daily mean volumetric water content, 0–7 cm | m³/m³ | That day |
| `soil_moisture_deep` | Same, 7–28 cm | m³/m³ | That day |
| `soil_moisture_trend_7d` | Least-squares slope of 0–7 cm moisture, as change per 7 days | m³/m³ | ≥ 80 % |
| `soil_temperature` | Daily mean, 0–7 cm | °C | That day |
| `soil_temperature_trend_7d` | Least-squares slope, as change per 7 days | °C | ≥ 80 % |

## Why these

- **Rain alone is not enough.** Water-balance models (rain minus evaporative
  demand) explained fungal yields better than rainfall models, and diverged
  from them under warming (Ágreda et al., 2015).
- **Response delays.** Yield tracked same-month soil moisture and weather,
  with precipitation acting about a month later (Karavani et al., 2018).
  Species models (0.3) will apply such lags per factor, using windows that
  end before the current day.
- **Frost and cooling** end the season for many autumn species and shift
  fruiting timing (Kauserud et al., 2008; Boddy et al., 2014).

## References

- Kohler, M. A. & Linsley, R. K. (1951). *Predicting the runoff from storm
  rainfall.* US Weather Bureau Research Paper 34.
- ETCCDI climate change indices: <https://etccdi.pacificclimate.org/list_27_indices.shtml>
- Allen, R. G. et al. (1998). *Crop evapotranspiration (FAO Irrigation and
  Drainage Paper 56).* FAO.
- Ágreda, T. et al. (2015). *Global Change Biology* 21(9): 3499–3510.
- Karavani, A. et al. (2018). *Agricultural and Forest Meteorology* 248: 432–440.
- Kauserud, H. et al. (2008). *PNAS* 105(10): 3811–3814.
- Boddy, L. et al. (2014). *Fungal Ecology* 10: 20–33.
