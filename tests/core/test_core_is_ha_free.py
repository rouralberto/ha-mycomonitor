"""The core must stay usable without Home Assistant."""

from __future__ import annotations

import ast
from pathlib import Path

CORE = Path(__file__).parents[2] / "custom_components" / "mycomonitor" / "core"


def test_core_does_not_import_homeassistant() -> None:
    offenders = []
    for path in CORE.rglob("*.py"):
        for node in ast.walk(ast.parse(path.read_text(), filename=str(path))):
            names: list[str] = []
            if isinstance(node, ast.Import):
                names = [alias.name for alias in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
                names = [node.module]
            offenders += [
                f"{path.relative_to(CORE)}: {name}"
                for name in names
                if name.split(".")[0] == "homeassistant"
            ]
    assert not offenders
