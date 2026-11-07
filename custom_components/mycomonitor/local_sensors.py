"""Daily values from the user's own sensors, via the recorder's long-term statistics.

Long-term statistics survive the recorder's purge, so months of history are
available. Only complete days before today are used; today comes from the
forecast like everywhere else.
"""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from homeassistant.components.recorder.statistics import statistics_during_period
from homeassistant.const import UnitOfPrecipitationDepth, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.recorder import get_instance
from homeassistant.util import dt as dt_util

from .core.models import DailySeries, DataKind, Reading, Source, Variable

StatType = Literal["mean", "min", "max", "change"]

CONF_RAIN_ENTITY = "rain_entity"
CONF_TEMPERATURE_ENTITY = "temperature_entity"
CONF_HUMIDITY_ENTITY = "humidity_entity"
CONF_SOIL_MOISTURE_ENTITY = "soil_moisture_entity"
CONF_SOIL_TEMPERATURE_ENTITY = "soil_temperature_entity"


@dataclass(frozen=True, slots=True)
class LocalSensor:
    """How one mapped entity feeds the daily series."""

    device_class: str
    state_classes: tuple[str, ...]
    outputs: tuple[tuple[StatType, Variable, float], ...]  # (statistic, variable, scale)


LOCAL_SENSORS: dict[str, LocalSensor] = {
    CONF_RAIN_ENTITY: LocalSensor(
        "precipitation", ("total", "total_increasing"), (("change", Variable.PRECIPITATION, 1),)
    ),
    CONF_TEMPERATURE_ENTITY: LocalSensor(
        "temperature",
        ("measurement",),
        (
            ("mean", Variable.TEMPERATURE_MEAN, 1),
            ("min", Variable.TEMPERATURE_MIN, 1),
            ("max", Variable.TEMPERATURE_MAX, 1),
        ),
    ),
    CONF_HUMIDITY_ENTITY: LocalSensor(
        "humidity", ("measurement",), (("mean", Variable.HUMIDITY_MEAN, 1),)
    ),
    # % volumetric water content -> m³/m³. Cheap capacitive sensors are often not
    # calibrated; their trend is more meaningful than their level.
    CONF_SOIL_MOISTURE_ENTITY: LocalSensor(
        "moisture", ("measurement",), (("mean", Variable.SOIL_MOISTURE_0_7CM, 0.01),)
    ),
    CONF_SOIL_TEMPERATURE_ENTITY: LocalSensor(
        "temperature", ("measurement",), (("mean", Variable.SOIL_TEMPERATURE_0_7CM, 1),)
    ),
}

UNITS = {"temperature": UnitOfTemperature.CELSIUS, "distance": UnitOfPrecipitationDepth.MILLIMETERS}
SOURCE = Source(provider="home_assistant", kind=DataKind.MEASURED)


def rows_to_series(
    rows: Mapping[str, Sequence[Mapping[str, Any]]],
    mapping: Mapping[str, str],
    today: date,
) -> DailySeries:
    """Statistics rows per entity -> daily series for complete days before `today`."""
    series = DailySeries()
    for key, entity_id in mapping.items():
        sensor = LOCAL_SENSORS[key]
        for row in rows.get(entity_id, []):
            start = row["start"]
            moment = datetime.fromtimestamp(start, UTC) if isinstance(start, int | float) else start
            day = dt_util.as_local(moment).date()
            if day >= today:
                continue
            for stat, variable, scale in sensor.outputs:
                value = row.get(stat)
                if value is not None:
                    series.put(variable, day, Reading(float(value) * scale, SOURCE))
    return series


async def async_fetch_local(
    hass: HomeAssistant, mapping: Mapping[str, str], today: date, past_days: int
) -> DailySeries:
    """Read daily statistics for the mapped entities."""
    if not mapping:
        return DailySeries()
    start_local = datetime.combine(
        today - timedelta(days=past_days), datetime.min.time(), dt_util.get_default_time_zone()
    )
    end_local = datetime.combine(today, datetime.min.time(), dt_util.get_default_time_zone())
    rows = await get_instance(hass).async_add_executor_job(
        statistics_during_period,
        hass,
        dt_util.as_utc(start_local),
        dt_util.as_utc(end_local),
        set(mapping.values()),
        "day",
        UNITS,
        {"mean", "min", "max", "change"},
    )
    return rows_to_series(rows, mapping, today)


def validate_entity(hass: HomeAssistant, key: str, entity_id: str) -> str | None:
    """An error key if the entity can't feed long-term statistics as needed."""
    state = hass.states.get(entity_id)
    if state is None:
        return "entity_not_found"
    if state.attributes.get("state_class") not in LOCAL_SENSORS[key].state_classes:
        return "rain_needs_total" if key == CONF_RAIN_ENTITY else "needs_measurement"
    return None
