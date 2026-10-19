"""What the map's weather effects draw (web `/api/conditions`): the wind vector, the observed sky, the precipitation
falling now and the air flag of the last background-refreshed weather, each with its source and observation time, and
the position of the sun computed for «now» (walks.sun). Nothing here touches the network; a value without data is None,
never a guess: unknown weather is not clear sky.

Sources: the airport observation (METAR UACC) for the wind, the sky and the precipitation falling now; MET Norway's
forecast for the wind and the sky when there is no usable observation (never for precipitation); the official НМУ
notice of Kazhydromet (with the link to it) or the smoke / haze of the station report for the air flag.

For the weather card: `temp` (temperature and feels-like), `vis` (the station's visibility), `pm25` (only with the
Open-Meteo demo leg), `hours` (the next hours of MET Norway's series in memory), `sun.rise` / `sun.set`."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta

from . import metar, metno, sun
from . import weather as wx
from .envcfg import fx_fake
from .hours import TZ
from .kazhydromet import classify_notice
from .models import WeatherInfo, WeatherWarning

PRECIP_MAX_AGE = timedelta(
    minutes=65
)  # METAR comes every 30 min: a report that two have missed is not «falling now»
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
    """The sun for «now» and today's computed sunrise and sunset (local, HH:MM)."""
    altitude, morning = override or sun.sun_altitude(now_utc)
    rise, sset, _ = sun.sun_for(now_utc.astimezone(TZ).date())
    return {
        "altitude": round(altitude, 1),
        "morning": morning,
        "phase": phase(altitude, morning),
        "rise": rise.strftime("%H:%M"),
        "set": sset.strftime("%H:%M"),
    }


def _observed(weather: WeatherInfo, now_utc: datetime) -> datetime | None:
    """The time of the airport report the weather was read from; None when the weather is not from one or the report
    has become too old to be «now» (the refresh may have been failing for hours)."""
    if weather.source != "metar" or not weather.observed_at:
        return None
    at = datetime.fromisoformat(weather.observed_at)
    return at if -metar.FUTURE_SLACK <= now_utc - at <= metar.MAX_AGE else None


def _stamp(observed: datetime | None, source: str) -> dict:
    return {"source": source, "at": observed.astimezone(TZ).strftime("%H:%M") if observed else ""}


def _source(weather: WeatherInfo, observed: datetime | None) -> str:
    """Where the current values come from: the airport report, the forecast, or nowhere (a demo weather, no data)."""
    if observed:
        return "metar"
    return "met-no" if weather.source == "met-no" and weather.forecast_used else ""


def _wind(weather: WeatherInfo, stamp: dict) -> dict | None:
    if weather.wind_from_deg is None or not weather.wind_kmh:
        return None
    gust = weather.wind_gust_kmh
    return {
        "from_deg": weather.wind_from_deg % 360,
        "speed_ms": round(weather.wind_kmh / 3.6, 1),
        "gust_ms": None if gust is None else round(gust / 3.6, 1),
        **stamp,
    }


def _air(weather: WeatherInfo, observed: datetime | None, stamp: dict) -> dict | None:
    notice = next((w for w in weather.warnings if w.kind == "nmu" and w.active), None)
    if notice is not None:
        return {
            "kind": "nmu",
            "source": "kazhydromet",
            "at": "",
            "title": notice.title,
            "url": notice.source_url,
        }
    if "smog" in weather.conditions and observed:
        return {"kind": "smog", **stamp}
    return None


def _notice(weather: WeatherInfo) -> dict | None:
    """The active Kazhydromet storm notice: its phenomenon and period as codes (the card writes them in the visitor's
    language), the notice's own Russian text for the disclosure behind the link, the link, and how long it holds. What
    the notice says matters to a person, not that it is formally a «штормовое предупреждение»."""
    w = next((w for w in weather.warnings if w.kind == "storm" and w.active), None)
    if w is None:
        return None
    until = ""
    if w.valid_to:
        end = datetime.fromisoformat(w.valid_to).astimezone(TZ)
        until = end.strftime("%H:%M %d.%m")
    text = _PLACE.sub("", w.text.strip()).rstrip(
        "."
    )  # «г. Астана: » is the page's own place, the card is about Astana
    phenomena, periods = classify_notice(text)
    return {
        "text": text or w.title,
        "phenomena": phenomena,
        "periods": periods,
        "until": until,
        "source": "kazhydromet",
        "at": "",
        "url": w.source_url,
    }


def _hours(utc_now: datetime) -> dict | None:
    items = [
        {
            "at": h.time.astimezone(TZ).strftime("%H:%M"),
            "temp_c": round(h.temperature_c),
            "precip_mm": h.precipitation_mm,
            "sym": h.symbol,
        }
        for h in metno.upcoming(utc_now)
    ]
    return {"source": "met-no", "items": items} if items else None


def _measures(weather: WeatherInfo, now_utc: datetime) -> dict:
    observed = _observed(weather, now_utc)
    source = _source(weather, observed)
    stamp = _stamp(observed, source)
    out: dict = dict.fromkeys(BLOCKS)
    if source and weather.temperature_c is not None:
        out["temp"] = {
            "temp_c": round(weather.temperature_c),
            "feels_c": None if weather.apparent_c is None else round(weather.apparent_c),
            **stamp,
        }
    if source:
        out["wind"] = _wind(weather, stamp)
    if source and weather.cloud_pct is not None:
        out["sky"] = {"cloud_pct": round(weather.cloud_pct), **stamp}
    if observed and weather.visibility_m is not None:
        out["vis"] = {"m": weather.visibility_m, **stamp}
    if (
        observed
        and weather.precip_now
        and weather.precip_level
        and now_utc - observed <= PRECIP_MAX_AGE
    ):
        out["precip"] = {"kind": weather.precip_now, "level": weather.precip_level, **stamp}
    out["air"] = _air(weather, observed, stamp)
    out["notice"] = _notice(weather)
    if weather.pm25 is not None:
        out["pm25"] = {
            "value": round(weather.pm25),
            "source": "open-meteo",
            "at": weather.fetched_at,
        }
    if weather.forecast_used:
        out["hours"] = _hours(now_utc)
    return out


_PLACE = re.compile(r"^г\.\s*Астан[аы]\s*[:,\-–]\s*", re.IGNORECASE)
BLOCKS = ("wind", "sky", "precip", "air", "notice", "temp", "vis", "pm25", "hours")
NMU_URL = "https://www.kazhydromet.kz/ru/ecology/ezhednevnyy-byulleten-sostoyaniya-vozdushnogo-basseyna-nmu"
_FAKE_SYMBOLS = {"snow": "snow", "rain": "rain"}


def _fake_hours(now_utc: datetime, kind: str, temp: int) -> dict:
    """Six made-up hours for a `?fake=` scenario: the precipitation of the scenario falls for the first four."""
    first = (now_utc + timedelta(hours=1)).replace(minute=0, second=0, microsecond=0)
    items = []
    for i in range(6):
        wet = bool(kind) and i < 4
        items.append(
            {
                "at": (first + timedelta(hours=i)).astimezone(TZ).strftime("%H:%M"),
                "temp_c": temp - i // 2,
                "precip_mm": (0.6 + 0.3 * i) if wet else 0.0,
                "sym": _FAKE_SYMBOLS.get(kind, "") if wet else ("cloud" if i < 2 else "partly"),
            }
        )
    return {"source": "met-no", "items": items}


def _fake_weather(
    spec: str, now_utc: datetime
) -> tuple[WeatherInfo, tuple[float, bool] | None, dict | None]:
    """A made-up airport observation for `?fake=`, words joined with «+»: snow, rain, heavy, clear, fog (a Kazhydromet notice), windy (9 m/s), wind<N>
    (N m/s), overcast, haze, none and one of night / dawn / golden / dusk / day for the sun."""
    words = set(re.split(r"[+,\s]+", spec.lower()))
    override = next((_FAKE_SUN[w] for w in words if w in _FAKE_SUN), None)
    if "none" in words:
        return wx.make_weather(), override, None
    falling = next((w for w in ("snow", "rain") if w in words), "")
    speed = next((float(m[1]) for w in words if (m := re.fullmatch(r"wind(\d+)", w))), None)
    if speed is None:
        speed = 9.0 if falling or "windy" in words else 3.0
    cloud = (
        100.0
        if falling or "overcast" in words
        else 0.0
        if "clear" in words
        else 44.0
        if "haze" in words
        else 19.0
    )
    observed = (now_utc - timedelta(minutes=10)).astimezone(TZ).isoformat(timespec="minutes")
    temp, feels = (-3.0, -8.0) if falling == "snow" else (6.0, 3.0) if falling else (12.0, 10.0)
    notice = WeatherWarning(
        kind="nmu",
        title="Неблагоприятные метеоусловия",
        text="Ожидается...",
        source_url=NMU_URL,
        active=True,
    )
    storm = WeatherWarning(
        kind="storm",
        title="Штормовое предупреждение ОЯ № 17",
        text="г. Астана: 18 октября ночью и утром ожидается туман.",
        source_url="https://www.kazhydromet.kz/ru/storm",
        valid_to=(now_utc + timedelta(hours=7)).astimezone(TZ).isoformat(timespec="minutes"),
        active=True,
    )
    weather = wx.make_weather(
        temp,
        feels,
        round(speed * 3.6, 1),
        0.0,
        pm25=62.0 if "haze" in words else None,
        source="metar",
        observed_at=observed,
        precip_adverse=False,
        warnings=((notice,) if "haze" in words else ()) + ((storm,) if "fog" in words else ()),
        wind_from_deg=315,
        wind_gust_kmh=round(speed * 1.4 * 3.6, 1) if speed >= 5 else None,
        cloud_pct=cloud,
        precip_now=falling,
        precip_level=(3 if "heavy" in words else 2) if falling else 0,
        visibility_m=3000 if falling == "snow" else 9999,
        fetched_at=now_utc.astimezone(TZ).strftime("%H:%M"),
        forecast_used=True,
    )
    return weather, override, _fake_hours(now_utc, falling, round(temp))


def current(now_utc: datetime | None = None, fake: str = "") -> dict:
    """The payload of `/api/conditions`. `fake` only counts under WALKS_FX_FAKE=1. «known» is False until the first
    background refresh has finished (the page asks again soon); every block is then None."""
    now = (now_utc or datetime.now(UTC)).astimezone(UTC)
    override = hours = None
    weather = wx.refreshed_weather()
    if fake and fx_fake():
        weather, override, hours = _fake_weather(fake, now)
    blank = dict.fromkeys(BLOCKS)
    measures = blank if weather is None else _measures(weather, now)
    if hours is not None:
        measures["hours"] = hours
    return {
        "known": weather is not None,
        "now": now.astimezone(TZ).isoformat(timespec="seconds"),
        "sun": _sun_block(now, override),
        **measures,
    }
