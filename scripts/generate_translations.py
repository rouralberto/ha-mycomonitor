"""Generate strings.json, translations/{en,es}.json and icons.json from one source.

    python scripts/generate_translations.py          # write the files
    python scripts/generate_translations.py --check  # exit 1 if they are out of date

Species names come from the species profiles, so a new profile only needs its
`names` there (plus its icon below).
"""

from __future__ import annotations

import json
from pathlib import Path
import sys
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_components.mycomonitor.core.species.loader import load_profiles  # noqa: E402

INTEGRATION = ROOT / "custom_components" / "mycomonitor"
LANGS = ("en", "es")


def t(en: str, es: str) -> dict[str, str]:
    return {"en": en, "es": es}


LOCATION_DATA = {
    "name": t("Name", "Nombre"),
    "location": t("Location", "Ubicación"),
    "altitude": t("Altitude", "Altitud"),
    "habitats": t("Habitats", "Hábitats"),
}
LOCATION_DESC = {
    "name": t(
        "How the location appears in Home Assistant, e.g. Urbasa.",
        "Cómo aparece la ubicación en Home Assistant, p. ej. Urbasa.",
    ),
    "location": t(
        "The point to monitor. Weather data is fetched for these exact coordinates.",
        "El punto a vigilar. Los datos meteorológicos se piden para estas coordenadas exactas.",
    ),
    "altitude": t(
        "Optional. Leave empty to use the terrain height (90 m model). "
        "Temperatures are adjusted to this altitude.",
        "Opcional. Déjalo vacío para usar la altura del terreno (modelo de 90 m). "
        "Las temperaturas se ajustan a esta altitud.",
    ),
    "habitats": t(
        "Vegetation at the location. Only species compatible with these habitats get a sensor.",
        "Vegetación de la ubicación. Solo las especies compatibles con estos hábitats "
        "tienen sensor.",
    ),
}
LOCATION_ERRORS = {
    "invalid_location": t(
        "Invalid name, coordinates or altitude.", "Nombre, coordenadas o altitud no válidos."
    ),
    "no_habitat": t("Choose at least one habitat.", "Elige al menos un hábitat."),
}

HABITATS = {
    "beech": t("Beech forest", "Hayedo"),
    "pine": t("Pine forest", "Pinar"),
    "oak": t("Oak forest", "Robledal o encinar"),
    "mixed": t("Mixed forest", "Bosque mixto"),
    "grassland": t("Grassland and meadows", "Pastos y prados"),
}

CATEGORIES = {
    "out_of_season": t("Out of season", "Fuera de temporada"),
    "unfavorable": t("Unfavourable", "Desfavorable"),
    "low": t("Low", "Baja"),
    "moderate": t("Moderate", "Moderada"),
    "favorable": t("Favourable", "Favorable"),
    "very_favorable": t("Very favourable", "Muy favorable"),
}

FACTORS = {
    "rain": t("Rain", "Lluvia"),
    "water_balance": t("Water balance", "Balance hídrico"),
    "temperature": t("Temperature", "Temperatura"),
    "frost": t("Frost (gate)", "Heladas (limitante)"),
    "heat": t("Heat", "Calor"),
    "wet_days": t("Rainy days", "Días de lluvia"),
    "soil_warming": t("Soil warming", "Calentamiento del suelo"),
}

INDICATORS: dict[str, dict[str, str]] = {
    "rain_3d": t("Rainfall 3 days", "Lluvia 3 días"),
    "rain_7d": t("Rainfall 7 days", "Lluvia 7 días"),
    "rain_14d": t("Rainfall 14 days", "Lluvia 14 días"),
    "rain_21d": t("Rainfall 21 days", "Lluvia 21 días"),
    "rain_30d": t("Rainfall 30 days", "Lluvia 30 días"),
    "api_30d": t("Antecedent precipitation index", "Índice de precipitación antecedente"),
    "water_balance_14d": t("Water balance 14 days", "Balance hídrico 14 días"),
    "water_balance_30d": t("Water balance 30 days", "Balance hídrico 30 días"),
    "wet_days_14d": t("Rainy days (14 days)", "Días de lluvia (14 días)"),
    "dry_spell": t("Dry spell", "Racha seca"),
    "wet_streak": t("Wet streak", "Racha húmeda"),
    "temperature_mean_7d": t("Mean temperature 7 days", "Temperatura media 7 días"),
    "temperature_mean_14d": t("Mean temperature 14 days", "Temperatura media 14 días"),
    "temperature_mean_21d": t("Mean temperature 21 days", "Temperatura media 21 días"),
    "temperature_min_7d": t("Minimum temperature 7 days", "Temperatura mínima 7 días"),
    "temperature_max_7d": t("Maximum temperature 7 days", "Temperatura máxima 7 días"),
    "frost_days_7d": t("Frost days (7 days)", "Días de helada (7 días)"),
    "frost_days_14d": t("Frost days (14 days)", "Días de helada (14 días)"),
    "humidity_mean_7d": t("Mean humidity 7 days", "Humedad media 7 días"),
    "soil_moisture": t("Soil moisture", "Humedad del suelo"),
    "soil_moisture_deep": t("Soil moisture 7–28 cm", "Humedad del suelo 7–28 cm"),
    "soil_moisture_trend_7d": t("Soil moisture trend", "Tendencia de la humedad del suelo"),
    "soil_temperature": t("Soil temperature", "Temperatura del suelo"),
    "soil_temperature_trend_7d": t(
        "Soil temperature trend", "Tendencia de la temperatura del suelo"
    ),
    "last_update": t("Data updated", "Datos actualizados"),
}

ICONS = {
    **dict.fromkeys(
        ("rain_3d", "rain_7d", "rain_14d", "rain_21d", "rain_30d"), "mdi:weather-rainy"
    ),
    "api_30d": "mdi:water-plus",
    "water_balance_14d": "mdi:scale-balance",
    "water_balance_30d": "mdi:scale-balance",
    "wet_days_14d": "mdi:weather-pouring",
    "dry_spell": "mdi:weather-sunny",
    "wet_streak": "mdi:umbrella",
    "frost_days_7d": "mdi:snowflake-thermometer",
    "frost_days_14d": "mdi:snowflake-thermometer",
    "soil_moisture": "mdi:water-percent",
    "soil_moisture_deep": "mdi:water-percent",
    "soil_moisture_trend_7d": "mdi:chart-line-variant",
    "soil_temperature": "mdi:thermometer-lines",
    "soil_temperature_trend_7d": "mdi:chart-line-variant",
}


def pick(tree: Any, lang: str) -> Any:
    """Resolve every {"en": …, "es": …} leaf to one language."""
    if isinstance(tree, dict):
        if set(tree) == set(LANGS):
            return tree[lang]
        return {k: pick(v, lang) for k, v in tree.items()}
    return tree


def location_step(title: dict[str, str], description: dict[str, str] | None = None) -> dict:
    step: dict[str, Any] = {"title": title}
    if description:
        step["description"] = description
    step["data"] = LOCATION_DATA
    step["data_description"] = LOCATION_DESC
    return step


def source() -> dict[str, Any]:
    profiles = load_profiles()
    species_names = {pid: dict(p.names) for pid, p in profiles.items()}
    category_attr = {"category": {"state": CATEGORIES}}
    return {
        "config": {
            "abort": {
                "single_instance_allowed": t(
                    "MycoMonitor is already set up. Add locations from its integration page.",
                    "MycoMonitor ya está configurado. Añade ubicaciones desde su página "
                    "de integración.",
                )
            },
            "error": LOCATION_ERRORS,
            "step": {
                "user": location_step(
                    t("Add a monitoring location", "Añadir una ubicación"),
                    t(
                        "MycoMonitor estimates how favourable conditions are for mushrooms to "
                        "fruit. Its scores are explainable indices, not probabilities. Start "
                        "with your first location; you can add more later.",
                        "MycoMonitor estima lo favorables que son las condiciones para que "
                        "fructifiquen las setas. Sus puntuaciones son índices explicables, no "
                        "probabilidades. Empieza por tu primera ubicación; puedes añadir más "
                        "después.",
                    ),
                )
            },
        },
        "config_subentries": {
            "location": {
                "abort": {
                    "already_configured": t(
                        "A location at these coordinates already exists.",
                        "Ya existe una ubicación en estas coordenadas.",
                    ),
                    "reconfigure_successful": t(
                        "The location was updated.", "Se ha actualizado la ubicación."
                    ),
                },
                "entry_type": t("Location", "Ubicación"),
                "error": LOCATION_ERRORS,
                "initiate_flow": {"user": t("Add location", "Añadir ubicación")},
                "step": {
                    "user": location_step(t("Add a monitoring location", "Añadir una ubicación")),
                    "reconfigure": location_step(
                        t("Edit monitoring location", "Editar la ubicación")
                    ),
                },
            }
        },
        "options": {
            "error": {
                "invalid_override": t("Invalid value: {error}", "Valor no válido: {error}"),
            },
            "step": {
                "init": {
                    "title": t("MycoMonitor options", "Opciones de MycoMonitor"),
                    "menu_options": {
                        "settings": t("Settings", "Ajustes"),
                        "species": t("Species thresholds", "Umbrales de especies"),
                    },
                },
                "settings": {
                    "title": t("Settings", "Ajustes"),
                    "data": {
                        "favorable_threshold": t(
                            "Favourable conditions threshold", "Umbral de condiciones favorables"
                        )
                    },
                    "data_description": {
                        "favorable_threshold": t(
                            "A location's favourable-conditions sensor turns on when any "
                            "species' index reaches this value (0-100).",
                            "El sensor de condiciones favorables de una ubicación se activa "
                            "cuando el índice de alguna especie alcanza este valor (0-100).",
                        )
                    },
                },
                "species": {
                    "title": t("Species thresholds", "Umbrales de especies"),
                    "description": t(
                        "Choose a species to adjust its season and response curves.",
                        "Elige una especie para ajustar su temporada y sus curvas de respuesta.",
                    ),
                    "data": {"species": t("Species", "Especie")},
                },
                "species_edit": {
                    "title": t("{species}", "{species}"),
                    "description": t(
                        "Season dates are MM-DD. Each curve is a list of indicator:score "
                        "points (score 0-1), e.g. 10:0.05, 40:0.5, 80:1; values in between "
                        "are interpolated. Factors:\n{factors}\n\nSee docs/species for the "
                        "evidence behind each default.",
                        "Las fechas de temporada son MM-DD. Cada curva es una lista de puntos "
                        "indicador:puntuación (puntuación 0-1), p. ej. 10:0.05, 40:0.5, 80:1; "
                        "los valores intermedios se interpolan. Factores:\n{factors}\n\n"
                        "Consulta docs/species para ver la evidencia de cada valor por defecto.",
                    ),
                    "data": {
                        "season_start": t("Season start", "Inicio de temporada"),
                        "season_peak_start": t("Peak start", "Inicio del pico"),
                        "season_peak_end": t("Peak end", "Fin del pico"),
                        "season_end": t("Season end", "Fin de temporada"),
                        **{f"curve_{k}": v for k, v in FACTORS.items()},
                        "reset": t("Reset to defaults", "Restablecer valores por defecto"),
                    },
                },
            },
        },
        "entity": {
            "binary_sensor": {
                "favorable_conditions": {
                    "name": t("Favourable conditions", "Condiciones favorables")
                }
            },
            "sensor": {
                **{k: {"name": v} for k, v in INDICATORS.items()},
                **{
                    pid: {"name": names, "state_attributes": category_attr}
                    for pid, names in species_names.items()
                },
            },
        },
        "exceptions": {
            "update_failed": {
                "message": t(
                    "Could not update {location}: {error}",
                    "No se pudo actualizar {location}: {error}",
                )
            },
            "no_data": {
                "message": t(
                    "Could not fetch weather data for any location.",
                    "No se pudieron obtener datos meteorológicos de ninguna ubicación.",
                )
            },
        },
        "selector": {
            "habitat": {"options": HABITATS},
            "species": {"options": species_names},
        },
    }


def icons() -> dict[str, Any]:
    profiles = load_profiles()
    return {
        "entity": {
            "binary_sensor": {
                "favorable_conditions": {
                    "default": "mdi:mushroom-off-outline",
                    "state": {"on": "mdi:mushroom"},
                }
            },
            "sensor": {
                **{k: {"default": v} for k, v in ICONS.items()},
                **{pid: {"default": "mdi:mushroom-outline"} for pid in profiles},
            },
        }
    }


def outputs() -> dict[Path, str]:
    tree = source()

    def dump(obj: Any) -> str:
        return json.dumps(obj, ensure_ascii=False, indent=2) + "\n"

    return {
        INTEGRATION / "strings.json": dump(pick(tree, "en")),
        INTEGRATION / "translations" / "en.json": dump(pick(tree, "en")),
        INTEGRATION / "translations" / "es.json": dump(pick(tree, "es")),
        INTEGRATION / "icons.json": dump(icons()),
    }


def main() -> int:
    check = "--check" in sys.argv
    stale = []
    for path, text in outputs().items():
        current = path.read_text(encoding="utf-8") if path.exists() else None
        if current != text:
            stale.append(path.relative_to(ROOT))
            if not check:
                path.write_text(text, encoding="utf-8")
    if check and stale:
        print("Out of date:", *stale, sep="\n  ")
        return 1
    print("Written:" if stale else "Up to date.", *stale, sep="\n  ")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
