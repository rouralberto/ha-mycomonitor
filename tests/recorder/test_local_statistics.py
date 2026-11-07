"""Local sensors read through the real recorder's long-term statistics."""

from __future__ import annotations

from datetime import datetime, timedelta

from homeassistant.components.recorder.models import (
    StatisticData,
    StatisticMeanType,
    StatisticMetaData,
)
from homeassistant.components.recorder.statistics import async_import_statistics
from homeassistant.core import HomeAssistant
from homeassistant.util import dt as dt_util
import pytest
from pytest_homeassistant_custom_component.components.recorder.common import (
    async_wait_recording_done,
)

from custom_components.mycomonitor.core.models import Variable
from custom_components.mycomonitor.local_sensors import (
    CONF_RAIN_ENTITY,
    CONF_TEMPERATURE_ENTITY,
    async_fetch_local,
)


def _meta(statistic_id: str, unit: str, unit_class: str, *, has_sum: bool) -> StatisticMetaData:
    return StatisticMetaData(
        source="recorder",
        statistic_id=statistic_id,
        name=None,
        unit_of_measurement=unit,
        unit_class=unit_class,
        mean_type=StatisticMeanType.NONE if has_sum else StatisticMeanType.ARITHMETIC,
        has_sum=has_sum,
    )


async def test_local_sensors_read_long_term_statistics(hass: HomeAssistant) -> None:
    today = dt_util.now().date()
    tz = dt_util.get_default_time_zone()
    temperature, rain = [], []
    total = 0.0
    for offset in (3, 2, 1):
        day = today - timedelta(days=offset)
        for hour in range(24):
            start = dt_util.as_utc(
                datetime.combine(day, datetime.min.time(), tz) + timedelta(hours=hour)
            )
            temperature.append(StatisticData(start=start, mean=10.0 + offset, min=2.0, max=18.0))
            total += offset / 24  # 3, 2 and 1 mm on the three days
            rain.append(StatisticData(start=start, state=total, sum=total))
    async_import_statistics(
        hass, _meta("sensor.garden_temperature", "°C", "temperature", has_sum=False), temperature
    )
    async_import_statistics(hass, _meta("sensor.garden_rain", "mm", "distance", has_sum=True), rain)
    await async_wait_recording_done(hass)

    series = await async_fetch_local(
        hass,
        {
            CONF_TEMPERATURE_ENTITY: "sensor.garden_temperature",
            CONF_RAIN_ENTITY: "sensor.garden_rain",
        },
        today,
        10,
    )
    yesterday = today - timedelta(days=1)
    assert series.get(Variable.TEMPERATURE_MEAN, yesterday).value == pytest.approx(11.0)
    assert series.get(Variable.TEMPERATURE_MIN, yesterday).value == pytest.approx(2.0)
    assert len(series.dates(Variable.TEMPERATURE_MEAN)) == 3
    assert series.get(Variable.PRECIPITATION, yesterday).value == pytest.approx(1.0)
    assert series.get(Variable.PRECIPITATION, today - timedelta(days=2)).value == pytest.approx(2.0)


async def test_no_mapping_reads_nothing(hass: HomeAssistant) -> None:
    series = await async_fetch_local(hass, {}, dt_util.now().date(), 10)
    assert len(series) == 0
