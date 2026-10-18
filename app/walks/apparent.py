"""Apparent («feels like») temperature, the Steadman formula without radiation (the family Open-Meteo's
`apparent_temperature` belongs to): AT = T + 0.33 e - 0.70 v - 4.0, e the water-vapour pressure in hPa, v the wind in
m/s. One formula for every source: the airport report (walks.metar, e from the dew point) and the MET Norway forecast
(walks.metno, e from the relative humidity)."""

from __future__ import annotations

import math


def saturation_hpa(temp_c: float) -> float:
    """Saturation vapour pressure at `temp_c` (Magnus form used with the Steadman formula)."""
    return 6.105 * math.exp(17.27 * temp_c / (237.7 + temp_c))


def apparent_c(
    temp_c: float,
    wind_ms: float | None,
    *,
    dew_point_c: float | None = None,
    humidity_pct: float | None = None,
) -> float:
    """Apparent temperature in °C. The vapour pressure is taken from the dew point, else from the relative humidity;
    with neither (or without a wind) that term is left out, as the report did not carry it."""
    if dew_point_c is not None:
        e = saturation_hpa(dew_point_c)
    elif humidity_pct is not None:
        e = humidity_pct / 100.0 * saturation_hpa(temp_c)
    else:
        e = 0.0
    return temp_c + 0.33 * e - 0.70 * (wind_ms or 0.0) - 4.0
