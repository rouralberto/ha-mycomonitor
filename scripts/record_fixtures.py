"""Record Open-Meteo responses used as test fixtures.

Only public reference points are recorded (never a home location):

    python scripts/record_fixtures.py
"""

from __future__ import annotations

from datetime import date, timedelta
import json
from pathlib import Path
import sys
import urllib.parse
import urllib.request

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from custom_components.mycomonitor.core.models import Location  # noqa: E402
from custom_components.mycomonitor.core.providers import open_meteo  # noqa: E402

URBASA = Location("Urbasa", 42.84, -2.17)  # Raso de Urbasa, public reference point
OUT = ROOT / "tests" / "fixtures" / "open_meteo"
PAST_DAYS = 35
FORECAST_DAYS = 16


def fetch(url: str, params: dict[str, object]) -> dict[str, object]:
    query = urllib.parse.urlencode(params)
    with urllib.request.urlopen(f"{url}?{query}", timeout=30) as response:
        return json.load(response)


def main() -> None:
    common = open_meteo._common_params(URBASA)
    forecast = fetch(
        open_meteo.FORECAST_URL,
        {
            **common,
            "models": open_meteo.DEFAULT_MODEL,
            "past_days": open_meteo.FORECAST_FALLBACK_PAST_DAYS,
            "forecast_days": FORECAST_DAYS,
        },
    )
    today = date.fromisoformat(forecast["daily"]["time"][open_meteo.FORECAST_FALLBACK_PAST_DAYS])
    archive = fetch(
        open_meteo.ARCHIVE_URL,
        {
            **common,
            "start_date": (today - timedelta(days=PAST_DAYS)).isoformat(),
            "end_date": (today - timedelta(days=1)).isoformat(),
        },
    )
    for name, payload in (("urbasa_forecast", forecast), ("urbasa_archive", archive)):
        payload.pop("generationtime_ms", None)
        (OUT / f"{name}.json").write_text(json.dumps(payload, ensure_ascii=False) + "\n")
    print(f"recorded fixtures for today = {today}")


if __name__ == "__main__":
    main()
