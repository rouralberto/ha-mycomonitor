"""Constants for MycoMonitor."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "mycomonitor"

SUBENTRY_LOCATION: Final = "location"

CONF_LOCATION: Final = "location"  # location selector: {"latitude", "longitude"}
CONF_ALTITUDE: Final = "altitude"
CONF_HABITATS: Final = "habitats"

HABITATS: Final = ["beech", "pine", "oak", "mixed", "grassland"]

UPDATE_INTERVAL: Final = timedelta(hours=3)
RETRY_INTERVAL: Final = timedelta(minutes=15)
# After a failed update, keep showing the last data for this long. Daily
# indicators change slowly, so a short outage shouldn't blank every sensor.
STALE_DATA_GRACE: Final = timedelta(hours=12)

PAST_DAYS: Final = 92
FORECAST_DAYS: Final = 16

# Hub options
CONF_FAVORABLE_THRESHOLD: Final = "favorable_threshold"
DEFAULT_FAVORABLE_THRESHOLD: Final = 60
CONF_SPECIES_OVERRIDES: Final = "species"  # {species_id: {"season": {...}, "curves": {...}}}
