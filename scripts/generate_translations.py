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
    "entity_not_found": t("A selected sensor doesn't exist.", "Un sensor elegido no existe."),
    "rain_needs_total": t(
        "The rain gauge needs state class total or total_increasing.",
        "El pluviómetro necesita la clase de estado total o total_increasing.",
    ),
    "needs_measurement": t(
        "Temperature, humidity and soil sensors need state class measurement.",
        "Los sensores de temperatura, humedad y suelo necesitan la clase de estado measurement.",
    ),
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
    "observations": t("Observations", "Observaciones"),
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
    "observations": "mdi:notebook-outline",
}


OBSERVATION_ERRORS = {
    "future_date": t("The date is in the future.", "La fecha es futura."),
    "invalid_date": t("The date is too old.", "La fecha es demasiado antigua."),
    "unknown_species": t("Unknown species.", "Especie desconocida."),
    "invalid_observation": t("Invalid observation: {error}", "Observación no válida: {error}"),
}
OBSERVATION_ABORTS = {
    "no_locations": t("Add a location first.", "Añade primero una ubicación."),
    "observation_recorded": t(
        "Observation recorded, with the conditions that preceded it.",
        "Observación registrada, con las condiciones que la precedieron.",
    ),
    "observation_recorded_no_snapshot": t(
        "Observation recorded. The weather data couldn't be fetched now; it will be added "
        "automatically later.",
        "Observación registrada. No se pudieron obtener los datos meteorológicos; se añadirán "
        "automáticamente más tarde.",
    ),
    "no_observations": t("No observations yet.", "Todavía no hay observaciones."),
    "observations_deleted": t("{count} observations deleted.", "{count} observaciones borradas."),
}
RECORD_STEP = {
    "title": t("Record a visit", "Registrar una salida"),
    "description": t(
        "Record finds and also visits where you found nothing: both are needed to calibrate "
        "the models later. Exact coordinates are only saved if you tick the box, and are "
        "never shown in entities, logs or diagnostics.",
        "Registra los hallazgos y también las salidas sin éxito: ambos hacen falta para "
        "calibrar los modelos más adelante. Las coordenadas exactas solo se guardan si marcas "
        "la casilla, y nunca aparecen en entidades, registros ni diagnósticos.",
    ),
    "data": {
        "site": t("Location", "Ubicación"),
        "species": t("Species", "Especie"),
        "date": t("Date", "Fecha"),
        "outcome": t("Outcome", "Resultado"),
        "quantity": t("Quantity (if found)", "Cantidad (si se encontró)"),
        "habitat": t("Habitat", "Hábitat"),
        "notes": t("Notes", "Notas"),
        "save_coordinates": t("Save exact coordinates", "Guardar coordenadas exactas"),
        "location": t("Exact spot", "Punto exacto"),
        "photo": t("Photo", "Foto"),
    },
    "data_description": {
        "notes": t(
            "Exported together with the observation: avoid writing exact places here.",
            "Se exportan junto con la observación: evita escribir lugares exactos aquí.",
        ),
        "location": t(
            "Only used if 'Save exact coordinates' is ticked.",
            "Solo se usa si marcas «Guardar coordenadas exactas».",
        ),
        "photo": t("Optional, from your media library.", "Opcional, de tu biblioteca multimedia."),
    },
}
SERVICE_EXCEPTIONS = {
    "not_loaded": {
        "message": t("MycoMonitor is not set up or not loaded.", "MycoMonitor no está cargado.")
    },
    "unknown_location": {
        "message": t("Unknown location: {location}", "Ubicación desconocida: {location}")
    },
    "unknown_species": {
        "message": t("Unknown species: {species}", "Especie desconocida: {species}")
    },
    "invalid_observation": {
        "message": t("Invalid observation: {error}", "Observación no válida: {error}")
    },
    "geojson_needs_coordinates": {
        "message": t(
            "A GeoJSON export needs include_coordinates.",
            "Una exportación GeoJSON necesita include_coordinates.",
        )
    },
    "unknown_observation": {
        "message": t("No observation with id {id}.", "No hay ninguna observación con id {id}.")
    },
}


def field(name: dict[str, str], description: dict[str, str]) -> dict[str, Any]:
    return {"name": name, "description": description}


SERVICES = {
    "record_observation": {
        "name": t("Record observation", "Registrar observación"),
        "description": t(
            "Records a find or an empty visit, with the conditions that preceded it.",
            "Registra un hallazgo o una salida sin éxito, con las condiciones que lo precedieron.",
        ),
        "fields": {
            "location": field(
                t("Location", "Ubicación"),
                t("Location name or sub-entry id.", "Nombre de la ubicación o id de subentrada."),
            ),
            "species": field(t("Species", "Especie"), t("Species id.", "Id de la especie.")),
            "date": field(t("Date", "Fecha"), t("Defaults to today.", "Por defecto, hoy.")),
            "outcome": field(
                t("Outcome", "Resultado"), t("Found or not found.", "Encontrada o no.")
            ),
            "quantity": field(
                t("Quantity", "Cantidad"),
                t("Approximate amount if found.", "Cantidad aproximada si se encontró."),
            ),
            "habitat": field(t("Habitat", "Hábitat"), t("Where it was.", "Dónde estaba.")),
            "notes": field(
                t("Notes", "Notas"),
                t("Free text; avoid exact places.", "Texto libre; evita lugares exactos."),
            ),
            "latitude": field(
                t("Latitude", "Latitud"),
                t("Optional; stored privately.", "Opcional; se guarda en privado."),
            ),
            "longitude": field(
                t("Longitude", "Longitud"),
                t("Optional; stored privately.", "Opcional; se guarda en privado."),
            ),
            "photo": field(
                t("Photo", "Foto"), t("Media content id or path.", "Id o ruta del archivo.")
            ),
        },
    },
    "export_observations": {
        "name": t("Export observations", "Exportar observaciones"),
        "description": t(
            "Writes the observations, with their preceding conditions, to the "
            "mycomonitor/exports folder in the configuration directory.",
            "Guarda las observaciones, con sus condiciones previas, en la carpeta "
            "mycomonitor/exports del directorio de configuración.",
        ),
        "fields": {
            "format": field(t("Format", "Formato"), t("CSV or GeoJSON.", "CSV o GeoJSON.")),
            "include_coordinates": field(
                t("Include coordinates", "Incluir coordenadas"),
                t(
                    "Off by default. Never share an export with coordinates publicly.",
                    "Desactivado por defecto. Nunca compartas en público una exportación "
                    "con coordenadas.",
                ),
            ),
            "decimals": field(
                t("Coordinate decimals", "Decimales de las coordenadas"),
                t(
                    "Rounding: 3 decimals is about 100 m, 2 about 1 km.",
                    "Redondeo: 3 decimales son unos 100 m; 2, aproximadamente 1 km.",
                ),
            ),
            "location": field(
                t("Location", "Ubicación"),
                t("Only this location (optional).", "Solo esta ubicación (opcional)."),
            ),
        },
    },
    "delete_observation": {
        "name": t("Delete observation", "Borrar observación"),
        "description": t("Deletes one observation.", "Borra una observación."),
        "fields": {"id": field(t("ID", "ID"), t("Observation id.", "Id de la observación."))},
    },
}


def pick(tree: Any, lang: str) -> Any:
    """Resolve every {"en": …, "es": …} leaf to one language."""
    if isinstance(tree, dict):
        if set(tree) == set(LANGS):
            return tree[lang]
        return {k: pick(v, lang) for k, v in tree.items()}
    return tree


LOCAL_SECTION = {
    "name": t("Local sensors (optional)", "Sensores locales (opcional)"),
    "description": t(
        "Your own sensors at this location. Their daily values replace the model's for "
        "past days. They need long-term statistics: rain gauges with state class total or "
        "total_increasing, the others with measurement.",
        "Tus propios sensores en esta ubicación. Sus valores diarios sustituyen a los del "
        "modelo en los días pasados. Necesitan estadísticas a largo plazo: pluviómetros con "
        "clase de estado total o total_increasing, el resto con measurement.",
    ),
    "data": {
        "rain_entity": t("Rain gauge", "Pluviómetro"),
        "temperature_entity": t("Air temperature", "Temperatura del aire"),
        "humidity_entity": t("Humidity", "Humedad"),
        "soil_moisture_entity": t("Soil moisture", "Humedad del suelo"),
        "soil_temperature_entity": t("Soil temperature", "Temperatura del suelo"),
    },
    "data_description": {
        "soil_moisture_entity": t(
            "Read as volumetric water content (%). Uncalibrated sensors are better for "
            "trends than levels.",
            "Se interpreta como contenido volumétrico de agua (%). Los sensores sin calibrar "
            "sirven más para tendencias que para niveles.",
        ),
    },
}
STATION_STEP = {
    "title": t("AEMET station (experimental)", "Estación de AEMET (experimental)"),
    "description": t(
        "Optionally use the rain gauge of a nearby AEMET station for past days (about 4 "
        "days behind). The nearest stations are listed with their distance and altitude. "
        "Only precipitation is used.",
        "Opcionalmente, usa el pluviómetro de una estación de AEMET cercana para los días "
        "pasados (con unos 4 días de retraso). Se listan las estaciones más cercanas con su "
        "distancia y altitud. Solo se usa la precipitación.",
    ),
    "data": {"aemet_station": t("Station", "Estación")},
}


def location_step(title: dict[str, str], description: dict[str, str] | None = None) -> dict:
    step: dict[str, Any] = {"title": title}
    if description:
        step["description"] = description
    step["data"] = LOCATION_DATA
    step["data_description"] = LOCATION_DESC
    step["sections"] = {"local_sensors": LOCAL_SECTION}
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
                "error": LOCATION_ERRORS
                | {
                    "stations_unavailable": t(
                        "Couldn't load AEMET's station list: type a station ID (e.g. 9263D) "
                        "or leave it empty.",
                        "No se pudo cargar la lista de estaciones de AEMET: escribe un "
                        "indicativo (p. ej. 9263D) o déjalo vacío.",
                    )
                },
                "initiate_flow": {"user": t("Add location", "Añadir ubicación")},
                "step": {
                    "user": location_step(t("Add a monitoring location", "Añadir una ubicación")),
                    "reconfigure": location_step(
                        t("Edit monitoring location", "Editar la ubicación")
                    ),
                    "station": STATION_STEP,
                },
            }
        },
        "options": {
            "error": {
                "invalid_api_key": t(
                    "AEMET rejected this API key.", "AEMET ha rechazado esta clave."
                ),
                "cannot_connect": t(
                    "Couldn't reach AEMET to check the key.",
                    "No se pudo contactar con AEMET para comprobar la clave.",
                ),
                "invalid_override": t("Invalid value: {error}", "Valor no válido: {error}"),
            },
            "step": {
                "init": {
                    "title": t("MycoMonitor options", "Opciones de MycoMonitor"),
                    "menu_options": {
                        "record_observation": t("Record a visit", "Registrar una salida"),
                        "manage_observations": t("Manage observations", "Gestionar observaciones"),
                        "settings": t("Settings", "Ajustes"),
                        "species": t("Species thresholds", "Umbrales de especies"),
                    },
                },
                "record_observation": RECORD_STEP,
                "manage_observations": {
                    "title": t("Manage observations", "Gestionar observaciones"),
                    "description": t(
                        "{count} observations recorded. Select the ones to delete (newest first).",
                        "{count} observaciones registradas. Selecciona las que quieras borrar "
                        "(las más recientes primero).",
                    ),
                    "data": {"delete": t("Delete", "Borrar")},
                },
                "settings": {
                    "title": t("Settings", "Ajustes"),
                    "data": {
                        "favorable_threshold": t(
                            "Favourable conditions threshold", "Umbral de condiciones favorables"
                        ),
                        "aemet_api_key": t(
                            "AEMET OpenData API key (optional)",
                            "Clave de AEMET OpenData (opcional)",
                        ),
                    },
                    "data_description": {
                        "aemet_api_key": t(
                            "Free from opendata.aemet.es. With a key, each location can use a "
                            "nearby AEMET rain gauge (experimental). Leave empty to disable.",
                            "Gratuita en opendata.aemet.es. Con una clave, cada ubicación puede "
                            "usar un pluviómetro cercano de AEMET (experimental). Déjala vacía "
                            "para desactivarlo.",
                        ),
                        "favorable_threshold": t(
                            "A location's favourable-conditions sensor turns on when any "
                            "species' index reaches this value (0-100).",
                            "El sensor de condiciones favorables de una ubicación se activa "
                            "cuando el índice de alguna especie alcanza este valor (0-100).",
                        ),
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
            **SERVICE_EXCEPTIONS,
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
            "species": {"options": species_names | {"other": t("Other", "Otra")}},
            "outcome": {
                "options": {
                    "found": t("Found", "Encontrada"),
                    "not_found": t("Searched, not found", "Buscada, no encontrada"),
                }
            },
            "quantity": {
                "options": {
                    "none": t("None", "Ninguna"),
                    "few": t("A few (1-5)", "Pocas (1-5)"),
                    "some": t("Some (6-20)", "Bastantes (6-20)"),
                    "many": t("Many (more than 20)", "Muchas (más de 20)"),
                }
            },
            "export_format": {
                "options": {"csv": t("CSV", "CSV"), "geojson": t("GeoJSON", "GeoJSON")}
            },
        },
        "services": SERVICES,
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
