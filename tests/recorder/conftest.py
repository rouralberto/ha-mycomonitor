"""Recorder-backed tests: the recorder must be set up before Home Assistant."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(recorder_mock: None, enable_custom_integrations: None) -> None:
    """Recorder first, then custom integrations."""
