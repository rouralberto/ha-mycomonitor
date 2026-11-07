"""Generated files must match their sources."""

from __future__ import annotations

import importlib.util
from pathlib import Path

ROOT = Path(__file__).parents[1]


def _load(name: str):  # type: ignore[no-untyped-def]
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_translations_are_up_to_date() -> None:
    for path, text in _load("generate_translations").outputs().items():
        assert path.read_text(encoding="utf-8") == text, (
            f"{path.name} is stale: run python scripts/generate_translations.py"
        )


def test_species_docs_are_up_to_date() -> None:
    for path, text in _load("generate_species_docs").outputs().items():
        assert path.exists(), f"{path.name} missing: run python scripts/generate_species_docs.py"
        assert path.read_text(encoding="utf-8") == text, (
            f"{path.name} is stale: run python scripts/generate_species_docs.py"
        )


EXAMPLE_LOCATIONS = [
    ("Urbasa", ["beech", "grassland"]),
    ("Montejurra", ["pine", "oak", "mixed"]),
    ("Estella-Lizarra", ["oak", "grassland"]),
]


def test_example_dashboards_are_up_to_date() -> None:
    generator = _load("generate_dashboard")
    for style, name in (("core", "tierra_estella"), ("mushroom", "tierra_estella_mushroom")):
        path = ROOT / "examples" / "dashboards" / f"{name}.yaml"
        expected = generator.render("MycoMonitor - Tierra Estella", EXAMPLE_LOCATIONS, style, "es")
        assert path.read_text(encoding="utf-8") == expected, f"{path.name} is stale"
        assert "&id" not in expected  # no YAML anchors


def test_dashboard_entities_match_integration() -> None:
    """Every MycoMonitor entity in the example exists for those locations' habitats."""
    import re

    from custom_components.mycomonitor.core.species.loader import load_profiles
    from custom_components.mycomonitor.sensor import INDICATOR_SENSORS

    text = (ROOT / "examples/dashboards/tierra_estella.yaml").read_text(encoding="utf-8")
    profiles = load_profiles()
    valid = set()
    for name, habitats in EXAMPLE_LOCATIONS:
        slug = _load("generate_dashboard").slugify(name)
        valid |= {f"sensor.mycomonitor_{slug}_{d.key}" for d in INDICATOR_SENSORS}
        valid |= {
            f"sensor.mycomonitor_{slug}_{pid}"
            for pid, p in profiles.items()
            if p.compatible_with(habitats)
        }
        valid |= {
            f"sensor.mycomonitor_{slug}_observations",
            f"binary_sensor.mycomonitor_{slug}_favorable_conditions",
        }
    used = set(re.findall(r"(?:binary_)?sensor\.mycomonitor_[a-z0-9_]+", text))
    used = {u for u in used if not u.endswith("_")}  # template prefixes like ..._' ~ best
    assert used <= valid, sorted(used - valid)
