"""Generate a Lovelace dashboard (YAML) for your MycoMonitor locations.

    python scripts/generate_dashboard.py \\
        --location "Urbasa=beech,grassland" \\
        --location "Montejurra=pine,oak,mixed" \\
        --title "MycoMonitor - Tierra Estella" --style core > dashboard.yaml

Location names must match the names in Home Assistant (entity IDs are built
from them) and habitats must match the location's habitats (they decide which
species have sensors).

Styles:
  core      built-in cards only (works everywhere)
  mushroom  Mushroom cards + ApexCharts (install both from HACS first)
"""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
from typing import Any
import unicodedata

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_components.mycomonitor.core.species.loader import (  # noqa: E402
    HABITATS,
    load_profiles,
)

CATEGORIES = {
    "es": {
        "out_of_season": "fuera de temporada",
        "unfavorable": "desfavorable",
        "low": "baja",
        "moderate": "moderada",
        "favorable": "favorable",
        "very_favorable": "muy favorable",
    },
    "en": {
        "out_of_season": "out of season",
        "unfavorable": "unfavourable",
        "low": "low",
        "moderate": "moderate",
        "favorable": "favourable",
        "very_favorable": "very favourable",
    },
}
FACTORS = {
    "es": {
        "rain": "Lluvia",
        "water_balance": "Balance hídrico",
        "temperature": "Temperatura",
        "frost": "Heladas",
        "heat": "Calor",
        "wet_days": "Días de lluvia",
        "soil_warming": "Calentamiento del suelo",
    },
    "en": {
        "rain": "Rain",
        "water_balance": "Water balance",
        "temperature": "Temperature",
        "frost": "Frost",
        "heat": "Heat",
        "wet_days": "Rainy days",
        "soil_warming": "Soil warming",
    },
}
TEXT = {
    "es": {
        "summary": "Resumen",
        "species": "Especies",
        "weather": "Clima",
        "observations": "Observaciones",
        "favorable": "Condiciones favorables",
        "best": "Mejor especie",
        "limiting": "factor limitante",
        "outlook": "Previsión 7 días",
        "disclaimer": (
            "Los índices (0-100) estiman lo favorables que son las condiciones para la "
            "fructificación. **No son probabilidades** ni garantizan que haya setas. Datos "
            "meteorológicos de modelos (Open-Meteo), salvo sensores propios."
        ),
        "rain": "Lluvia",
        "soil": "Suelo",
        "temperature": "Temperatura",
        "index": "Índice",
        "value": "Valor",
        "score": "Puntuación",
        "evidence": "evidencia",
        "factor": "Factor",
        "record_help": (
            "Registra cada salida, **también las que no encuentras nada**: Ajustes → "
            "Dispositivos y servicios → MycoMonitor → Configurar → Registrar una salida."
        ),
        "rain_7d": "Lluvia 7 días",
        "rain_30d": "Lluvia 30 días",
        "water_balance_30d": "Balance hídrico 30 días",
        "temperature_mean_14d": "Temperatura media 14 días",
        "temperature_min_7d": "Mínima 7 días",
        "frost_days_14d": "Heladas 14 días",
        "soil_moisture": "Humedad del suelo",
        "soil_temperature": "Temperatura del suelo",
        "dry_spell": "Racha seca",
    },
    "en": {
        "summary": "Summary",
        "species": "Species",
        "weather": "Weather",
        "observations": "Observations",
        "favorable": "Favourable conditions",
        "best": "Best species",
        "limiting": "limiting factor",
        "outlook": "7-day outlook",
        "disclaimer": (
            "The indices (0-100) estimate how favourable conditions are for fruiting. "
            "**They are not probabilities** and don't guarantee mushrooms. Weather data comes "
            "from models (Open-Meteo) unless you mapped your own sensors."
        ),
        "rain": "Rain",
        "soil": "Soil",
        "temperature": "Temperature",
        "index": "Index",
        "value": "Value",
        "score": "Score",
        "evidence": "evidence",
        "factor": "Factor",
        "record_help": (
            "Record every visit, **including the ones where you find nothing**: Settings → "
            "Devices & services → MycoMonitor → Configure → Record a visit."
        ),
        "rain_7d": "Rain 7 days",
        "rain_30d": "Rain 30 days",
        "water_balance_30d": "Water balance 30 days",
        "temperature_mean_14d": "Mean temperature 14 days",
        "temperature_min_7d": "Minimum 7 days",
        "frost_days_14d": "Frost days 14 days",
        "soil_moisture": "Soil moisture",
        "soil_temperature": "Soil temperature",
        "dry_spell": "Dry spell",
    },
}
KEY_INDICATORS = (
    "rain_7d",
    "rain_30d",
    "water_balance_30d",
    "dry_spell",
    "temperature_mean_14d",
    "temperature_min_7d",
    "frost_days_14d",
    "soil_moisture",
)
SEVERITY = {"green": 60, "yellow": 40, "red": 0}


class Literal(str):
    """Rendered as a YAML block scalar."""


class Dumper(yaml.SafeDumper):
    """No anchors/aliases: Home Assistant's loader warns about them in dashboards."""

    def ignore_aliases(self, data: Any) -> bool:
        return True


def _literal(dumper: yaml.SafeDumper, value: Literal) -> yaml.Node:
    return dumper.represent_scalar("tag:yaml.org,2002:str", value, style="|")


Dumper.add_representer(Literal, _literal)


def slugify(text: str) -> str:
    """Like Home Assistant's entity-id slugs: "Estella-Lizarra" -> "estella_lizarra"."""
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    return re.sub(r"[^a-z0-9]+", "_", ascii_text.lower()).strip("_")


class Dashboard:
    def __init__(self, title: str, locations: list[tuple[str, list[str]]], lang: str) -> None:
        self.title = title
        self.lang = lang
        self.t = TEXT[lang]
        self.profiles = load_profiles()
        self.locations = [
            (name, slugify(name), [p for p in self.profiles.values() if p.compatible_with(h)])
            for name, h in locations
        ]

    def name(self, pid: str) -> str:
        return self.profiles[pid].name(self.lang)

    def species_entity(self, slug: str, pid: str) -> str:
        return f"sensor.mycomonitor_{slug}_{pid}"

    def all_species(self) -> list[str]:
        seen: list[str] = []
        for _, _, profiles in self.locations:
            seen += [p.id for p in profiles if p.id not in seen]
        return seen

    # --- templates ---------------------------------------------------------

    def names_dict(self) -> str:
        pairs = ", ".join(f"'{pid}': '{self.name(pid)}'" for pid in self.profiles)
        return "{" + pairs + "}"

    def summary_markdown(self) -> Literal:
        t = self.t
        lines = [
            f"{{% set names = {self.names_dict()} %}}",
            f"{{% set factors = {FACTORS[self.lang]!r} %}}",
        ]
        for name, slug, _ in self.locations:
            b = f"binary_sensor.mycomonitor_{slug}_favorable_conditions"
            lines += [
                f"{{% set best = state_attr('{b}', 'best_species') %}}",
                f"**{name}**: "
                f"{{% if best %}}{t['best']}: {{{{ names.get(best, best) }}}} "
                f"({{{{ state_attr('{b}', 'best_index') | round(0) }}}})"
                f"{{% set lim = state_attr('sensor.mycomonitor_{slug}_' ~ best, "
                f"'limiting_factor') %}}"
                f"{{% if lim %}} · {t['limiting']}: {{{{ factors.get(lim, lim) }}}}{{% endif %}}"
                "{% else %}—{% endif %}",
                "",
            ]
        lines.append(f"<sub>{t['disclaimer']}</sub>")
        return Literal("\n".join(lines) + "\n")

    def factors_markdown(self, slug: str, pid: str) -> Literal:
        t = self.t
        e = self.species_entity(slug, pid)
        return Literal(
            f"{{% set e = '{e}' %}}\n"
            f"{{% set cat = {CATEGORIES[self.lang]!r} %}}\n"
            f"{{% set names = {FACTORS[self.lang]!r} %}}\n"
            f"**{{{{ states(e) | float(0) | round(0) }}}}** · "
            f"{{{{ cat.get(state_attr(e, 'category'), '—') }}}} · "
            f"{t['evidence']} {{{{ state_attr(e, 'evidence') or '—' }}}}\n\n"
            f"| {t['factor']} | {t['value']} | {t['score']} |\n|---|---|---|\n"
            "{% for f in state_attr(e, 'factors') or [] %}"
            "| {{ names.get(f.id, f.id) }}{% if f.lag_days %} (−{{ f.lag_days }} d){% endif %} "
            "| {{ f.value if f.value is not none else '—' }} {{ f.unit or '' }} "
            "| {{ f.score if f.score is not none else '—' }} |\n"
            "{% endfor %}"
        )

    # --- views -------------------------------------------------------------

    def build(self, style: str) -> dict[str, Any]:
        return {
            "title": self.title,
            "views": [
                self.summary_view(style),
                self.species_view(style),
                self.weather_view(style),
                self.observations_view(),
            ],
        }

    def summary_view(self, style: str) -> dict[str, Any]:
        t = self.t
        sections: list[dict[str, Any]] = [
            {
                "type": "grid",
                "cards": [
                    {"type": "heading", "heading": t["favorable"], "icon": "mdi:mushroom"},
                    {"type": "markdown", "content": self.summary_markdown()},
                ],
            }
        ]
        for name, slug, profiles in self.locations:
            cards: list[dict[str, Any]] = [
                {"type": "heading", "heading": name, "icon": "mdi:map-marker"},
                {
                    "type": "tile",
                    "entity": f"binary_sensor.mycomonitor_{slug}_favorable_conditions",
                    "name": t["favorable"],
                },
            ]
            for profile in profiles:
                cards.append(self.species_card(style, slug, profile.id))
            if style == "mushroom":
                cards.append(self.outlook_chart(slug, profiles))
            for key in KEY_INDICATORS:
                cards.append(
                    {
                        "type": "tile",
                        "entity": f"sensor.mycomonitor_{slug}_{key}",
                        "name": t[key],
                        "grid_options": {"columns": 6},
                    }
                )
            sections.append({"type": "grid", "cards": cards})
        return {
            "title": t["summary"],
            "path": "resumen" if self.lang == "es" else "summary",
            "icon": "mdi:mushroom",
            "type": "sections",
            "max_columns": max(2, min(4, len(self.locations) + 1)),
            "sections": sections,
        }

    def species_card(self, style: str, slug: str, pid: str) -> dict[str, Any]:
        entity = self.species_entity(slug, pid)
        if style == "mushroom":
            return {
                "type": "custom:mushroom-template-card",
                "entity": entity,
                "primary": self.name(pid),
                "secondary": "{{ states(entity) | float(0) | round(0) }} · "
                "{{ state_attr(entity, 'category') }}",
                "icon": "mdi:mushroom",
                "icon_color": "{% set v = states(entity) | float(0) %}"
                "{{ 'green' if v >= 60 else 'amber' if v >= 40 else 'orange' if v >= 20 "
                "else 'grey' }}",
                "tap_action": {"action": "more-info"},
                "grid_options": {"columns": 6},
            }
        return {
            "type": "gauge",
            "entity": entity,
            "name": self.name(pid),
            "min": 0,
            "max": 100,
            "needle": True,
            "severity": SEVERITY,
            "grid_options": {"columns": 6},
        }

    def outlook_chart(self, slug: str, profiles: list[Any]) -> dict[str, Any]:
        return {
            "type": "custom:apexcharts-card",
            "header": {"show": True, "title": self.t["outlook"]},
            "graph_span": "8d",
            "span": {"start": "day"},
            "yaxis": [{"min": 0, "max": 100, "decimals": 0}],
            "series": [
                {
                    "entity": self.species_entity(slug, p.id),
                    "name": self.name(p.id),
                    "data_generator": Literal(
                        "const today = [new Date().setHours(12, 0, 0, 0), "
                        "Number(entity.state)];\n"
                        "return [today, ...(entity.attributes.outlook || []).map(p => "
                        "[new Date(p.date + 'T12:00:00').getTime(), p.index])];\n"
                    ),
                }
                for p in profiles
            ],
        }

    def species_view(self, style: str) -> dict[str, Any]:
        sections = []
        for pid in self.all_species():
            located = [(n, s) for n, s, ps in self.locations if any(p.id == pid for p in ps)]
            cards: list[dict[str, Any]] = [
                {
                    "type": "heading",
                    "heading": self.name(pid),
                    "icon": "mdi:mushroom-outline",
                },
                {
                    "type": "history-graph",
                    "hours_to_show": 720,
                    "entities": [
                        {"entity": self.species_entity(s, pid), "name": n} for n, s in located
                    ],
                },
            ]
            for name, slug in located:
                cards.append(
                    {"type": "markdown", "title": name, "content": self.factors_markdown(slug, pid)}
                )
            sections.append({"type": "grid", "cards": cards})
        return {
            "title": self.t["species"],
            "path": "especies" if self.lang == "es" else "species",
            "icon": "mdi:mushroom-outline",
            "type": "sections",
            "max_columns": 3,
            "sections": sections,
        }

    def weather_view(self, style: str) -> dict[str, Any]:
        t = self.t

        def graph(key: str, hours: int = 1440) -> dict[str, Any]:
            entities = [
                {"entity": f"sensor.mycomonitor_{s}_{key}", "name": n} for n, s, _ in self.locations
            ]
            if style == "mushroom":
                return {
                    "type": "custom:apexcharts-card",
                    "header": {"show": True, "title": t[key]},
                    "graph_span": f"{hours // 24}d",
                    "series": [{"entity": e["entity"], "name": e["name"]} for e in entities],
                }
            return {
                "type": "history-graph",
                "title": t[key],
                "hours_to_show": hours,
                "entities": entities,
            }

        groups = (
            (t["rain"], "mdi:weather-rainy", ("rain_7d", "rain_30d", "water_balance_30d")),
            (t["temperature"], "mdi:thermometer", ("temperature_mean_14d", "temperature_min_7d")),
            (t["soil"], "mdi:water-percent", ("soil_moisture", "soil_temperature")),
        )
        sections = [
            {
                "type": "grid",
                "cards": [{"type": "heading", "heading": title, "icon": icon}]
                + [graph(k) for k in keys],
            }
            for title, icon, keys in groups
        ]
        return {
            "title": t["weather"],
            "path": "clima" if self.lang == "es" else "weather",
            "icon": "mdi:weather-partly-rainy",
            "type": "sections",
            "max_columns": 3,
            "sections": sections,
        }

    def observations_view(self) -> dict[str, Any]:
        t = self.t
        cards: list[dict[str, Any]] = [
            {"type": "heading", "heading": t["observations"], "icon": "mdi:notebook-outline"},
            {"type": "markdown", "content": t["record_help"]},
        ]
        cards += [
            {"type": "tile", "entity": f"sensor.mycomonitor_{s}_observations", "name": n}
            for n, s, _ in self.locations
        ]
        return {
            "title": t["observations"],
            "path": "observaciones" if self.lang == "es" else "observations",
            "icon": "mdi:notebook-outline",
            "type": "sections",
            "sections": [{"type": "grid", "cards": cards}],
        }


def parse_location(text: str) -> tuple[str, list[str]]:
    name, _, habitats = text.partition("=")
    chosen = [h.strip() for h in habitats.split(",") if h.strip()]
    if not name.strip() or not chosen or not set(chosen) <= HABITATS:
        raise argparse.ArgumentTypeError(
            f"use NAME=habitat,habitat with habitats from {sorted(HABITATS)}: {text!r}"
        )
    return name.strip(), chosen


def render(title: str, locations: list[tuple[str, list[str]]], style: str, lang: str) -> str:
    header = (
        f"# {title}: generated by MycoMonitor's scripts/generate_dashboard.py "
        f"(style: {style}).\n"
        + (
            "# Needs the Mushroom and ApexCharts cards from HACS.\n"
            if style == "mushroom"
            else "# Built-in cards only.\n"
        )
    )
    body = yaml.dump(
        Dashboard(title, locations, lang).build(style),
        Dumper=Dumper,
        sort_keys=False,
        allow_unicode=True,
        width=100,
    )
    return header + body


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--location", action="append", type=parse_location, required=True)
    parser.add_argument("--title", default="MycoMonitor")
    parser.add_argument("--style", choices=["core", "mushroom"], default="core")
    parser.add_argument("--lang", choices=["es", "en"], default="es")
    args = parser.parse_args()
    sys.stdout.write(render(args.title, args.location, args.style, args.lang))


if __name__ == "__main__":
    main()
