"""Sunrise / sunset for Astana by a local astronomical calculation (NOAA 'sunrise equation', accurate to ~2 min; the
tests compare it with Open-Meteo's daily values), so darkness is known with or without a network and no forecast API
has to supply it."""

from __future__ import annotations

import math
from datetime import UTC, date, datetime, time, timedelta

from .models import WeatherInfo

ASTANA_LAT, ASTANA_LON = 51.13, 71.43
UTC_OFFSET_H = 5  # Asia/Almaty since 2024-03-01 (same as Astana)


def computed_sun_times(
    d: date, lat: float = ASTANA_LAT, lon: float = ASTANA_LON
) -> tuple[time, time]:
    """(sunrise, sunset) as naive local (UTC+5) times for the date, by the NOAA sunrise equation."""
    jd_noon = d.toordinal() + 1721424.5 + 0.5  # Julian date of 12:00 UT on `d`
    n = round(jd_noon - 2451545.0 + 0.0008)
    j_star = n - lon / 360.0
    m = math.radians((357.5291 + 0.98560028 * j_star) % 360)
    c = 1.9148 * math.sin(m) + 0.0200 * math.sin(2 * m) + 0.0003 * math.sin(3 * m)
    lam = math.radians((math.degrees(m) + c + 180 + 102.9372) % 360)
    j_transit = 2451545.0 + j_star + 0.0053 * math.sin(m) - 0.0069 * math.sin(2 * lam)
    sin_dec = math.sin(lam) * math.sin(math.radians(23.4397))
    dec = math.asin(sin_dec)
    phi = math.radians(lat)
    cos_w = (math.sin(math.radians(-0.833)) - math.sin(phi) * sin_dec) / (
        math.cos(phi) * math.cos(dec)
    )
    cos_w = max(-1.0, min(1.0, cos_w))
    w = math.degrees(math.acos(cos_w))
    j_rise, j_set = j_transit - w / 360.0, j_transit + w / 360.0

    def to_local(jd: float) -> time:
        utc = datetime(2000, 1, 1, 12, tzinfo=UTC) + timedelta(days=jd - 2451545.0)
        local = utc + timedelta(hours=UTC_OFFSET_H)
        return (local + timedelta(seconds=30)).replace(second=0, microsecond=0).time()

    return to_local(j_rise), to_local(j_set)


def sun_for(d: date) -> tuple[time, time, str]:
    """(sunrise, sunset, source) for date `d`; the source label is always 'расчёт' (calculation)."""
    rise_t, set_t = computed_sun_times(d)
    return rise_t, set_t, "расчёт"


def is_dark(weather: WeatherInfo | None, when: datetime) -> bool:
    """True when `when` (naive Astana local) is after sunset or before sunrise. Always False without conditions
    (weather is None = the user switched adaptation off); `force_dark` is the manual demo override."""
    if weather is None:
        return False
    if weather.force_dark:
        return True
    rise, sset, _ = sun_for(when.date())
    t = when.time()
    return t >= sset or t < rise


def sun_altitude(
    when_utc: datetime, lat: float = ASTANA_LAT, lon: float = ASTANA_LON
) -> tuple[float, bool]:
    """(altitude of the sun's centre above the horizon in degrees, True before solar noon) at an aware instant: the
    NOAA solar position (equation of time and declination), no refraction. At the computed sunrise it is about
    -0.83 degrees, as `computed_sun_times` assumes."""
    jd = when_utc.timestamp() / 86400.0 + 2440587.5
    t = (jd - 2451545.0) / 36525.0
    l0 = math.radians((280.46646 + t * (36000.76983 + 0.0003032 * t)) % 360)
    m = math.radians((357.52911 + t * (35999.05029 - 0.0001537 * t)) % 360)
    c = (
        (1.914602 - t * (0.004817 + 0.000014 * t)) * math.sin(m)
        + (0.019993 - 0.000101 * t) * math.sin(2 * m)
        + 0.000289 * math.sin(3 * m)
    )
    omega = math.radians(125.04 - 1934.136 * t)
    lam = math.radians(math.degrees(l0) + c - 0.00569 - 0.00478 * math.sin(omega))
    eps = math.radians(
        23.439291 - 0.013004 * t + 0.00256 * math.cos(omega)
    )  # mean obliquity + nutation
    dec = math.asin(math.sin(eps) * math.sin(lam))
    y = math.tan(eps / 2) ** 2
    e = 0.016708634 - t * (0.000042037 + 0.0000001267 * t)
    eq_min = 4 * math.degrees(
        y * math.sin(2 * l0)
        - 2 * e * math.sin(m)
        + 4 * e * y * math.sin(m) * math.cos(2 * l0)
        - 0.5 * y * y * math.sin(4 * l0)
        - 1.25 * e * e * math.sin(2 * m)
    )
    utc_min = when_utc.hour * 60 + when_utc.minute + when_utc.second / 60.0
    hour_angle = (utc_min + eq_min + 4 * lon) / 4.0 - 180.0
    hour_angle = (hour_angle + 180.0) % 360.0 - 180.0
    phi = math.radians(lat)
    sin_alt = math.sin(phi) * math.sin(dec) + math.cos(phi) * math.cos(dec) * math.cos(
        math.radians(hour_angle)
    )
    return math.degrees(math.asin(max(-1.0, min(1.0, sin_alt)))), hour_angle < 0
