"""What the map's weather effects draw (web `/api/conditions`): the wind vector, the observed sky, the precipitation
falling now and the air flag of the last background-refreshed weather, each with its source and observation time, and
the position of the sun computed for «now» (walks.sun). Nothing here touches the network; a value without data is None,
never a guess: unknown weather is not clear sky.

Sources: the airport observation (METAR UACC) for the wind, the sky and the precipitation falling now; MET Norway's
forecast for the wind and the sky when there is no usable observation (never for precipitation); the official НМУ
notice of Kazhydromet or the smoke / haze of the station report for the air flag."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from . import metar, sun
from . import weather as wx
from .envcfg import fx_fake
from .hours import TZ
from .models import WeatherInfo

PRECIP_MAX_AGE = timedelta(
    minutes=90
)  # METAR comes every 30 min: a report older than two is not «falling now»
# (altitude of the sun in degrees, before noon) of the scenarios `?fake=` can name
_FAKE_SUN = {
    "night": (-25.0, False),
    "dawn": (-4.0, True),
    "golden": (3.0, False),
    "dusk": (-4.0, False),
    "day": (35.0, True),
}


def phase(altitude: float, morning: bool) -> str:
    """night / dawn / golden / day / dusk of the sun's altitude (golden hour is the sun below ~10 degrees)."""
    if altitude < -10.0:
        return "night"
    if altitude < -0.83:
        return "dawn" if morning else "dusk"
    return "golden" if altitude < 10.0 else "day"


def _sun_block(now_utc: datetime, override: tuple[float, bool] | None = None) -> dict:
    altitude, morning = override or sun.sun_altitude(now_utc)
    return {"altitude": round(altitude, 1), "morning": morning, "phase": phase(altitude, morning)}


def _observed(weather: WeatherInfo, now_utc: datetime) -> datetime | None:
    """The time of the airport report the weather was read from; None when the weather is not from one or the report
    has become too old to be «now» (the refresh may have been failing for hours)."""
    if weather.source != "metar" or not weather.observed_at:
        return None
    at = datetime.fromisoformat(weather.observed_at)
    return at if -metar.FUTURE_SLACK <= now_utc - at <= metar.MAX_AGE else None


def _stamp(observed: datetime | None, source: str) -> dict:
    return {"source": source, "at": observed.astimezone(TZ).strftime("%H:%M") if observed else ""}


def _measures(weather: WeatherInfo, now_utc: datetime) -> dict:
    observed = _observed(weather, now_utc)
    source = (
        "metar"
        if observed
        else "met-no"
        if weather.source == "met-no" and weather.forecast_used
        else ""
    )
    stamp = _stamp(observed, source)
    out: dict = {"wind": None, "sky": None, "precip": None, "air": None}
    if source and weather.wind_from_deg is not None and weather.wind_kmh:
        gust = weather.wind_gust_kmh
        out["wind"] = {
            "from_deg": weather.wind_from_deg % 360,
            "speed_ms": round(weather.wind_kmh / 3.6, 1),
            "gust_ms": None if gust is None else round(gust / 3.6, 1),
            **stamp,
        }
    if source and weather.cloud_pct is not None:
        out["sky"] = {"cloud_pct": round(weather.cloud_pct), **stamp}
    if (
        observed
        and weather.precip_now
        and weather.precip_level
        and now_utc - observed <= PRECIP_MAX_AGE
    ):
        out["precip"] = {"kind": weather.precip_now, "level": weather.precip_level, **stamp}
    if "nmu" in weather.conditions:
        out["air"] = {"kind": "nmu", "source": "kazhydromet", "at": ""}
    elif "smog" in weather.conditions and observed:
        out["air"] = {"kind": "smog", **stamp}
    return out


def _fake_weather(spec: str, now_utc: datetime) -> tuple[WeatherInfo, tuple[float, bool] | None]:
    """A made-up airport observation for `?fake=`: words joined with «+»: snow, rain, heavy, windy, overcast, haze, none and
    one of night / dawn / golden / dusk / day for the sun."""
    words = set(re.split(r"[+,\s]+", spec.lower()))
    override = next((_FAKE_SUN[w] for w in words if w in _FAKE_SUN), None)
    if "none" in words:
        return wx.make_weather(), override
    falling = next((w for w in ("snow", "rain") if w in words), "")
    windy = bool(falling) or "windy" in words
    cloud = 100.0 if falling or "overcast" in words else 44.0 if "haze" in words else 19.0
    observed = (now_utc - timedelta(minutes=10)).astimezone(TZ).isoformat(timespec="minutes")
    return wx.make_weather(
        0.0,
        0.0,
        32.4 if windy else 10.8,
        0.0,
        source="metar",
        observed_at=observed,
        precip_adverse=False,
        conditions=("nmu",) if "haze" in words else (),
        wind_from_deg=315 if windy else 270,
        wind_gust_kmh=45.0 if windy else None,
        cloud_pct=cloud,
        precip_now=falling,
        precip_level=(3 if "heavy" in words else 2) if falling else 0,
    ), override


def current(now_utc: datetime | None = None, fake: str = "") -> dict:
    """The payload of `/api/conditions`. `fake` only counts under WALKS_FX_FAKE=1. «known» is False until the first
    background refresh has finished (the page asks again soon); every effect block is then None."""
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    override = None
    weather = wx.refreshed_weather()
    if fake and fx_fake():
        weather, override = _fake_weather(fake, now)
    blank = {"wind": None, "sky": None, "precip": None, "air": None}
    return {
        "known": weather is not None,
        "now": now.astimezone(TZ).isoformat(timespec="seconds"),
        "sun": _sun_block(now, override),
        **(blank if weather is None else _measures(weather, now)),
    }
