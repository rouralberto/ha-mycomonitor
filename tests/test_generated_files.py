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
