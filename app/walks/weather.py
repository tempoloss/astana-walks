"""Astana conditions. The forecast is MET Norway locationforecast 2.0 (walks.metno; data CC BY 4.0 + NLOD 2.0, commercial
use allowed): the model's current temperature, wind and the precipitation of the next hour. The current weather is the
airport station report when there is a fresh one (METAR UACC of Kazhydromet, walks.metar), and official Kazhydromet
storm / НМУ notices for Astana are attached (walks.kazhydromet). Sunrise and sunset are computed (walks.sun). PM2.5 has
no keyless source with a licence for a paid product (collect/weather/README.md): the Open-Meteo air-quality API is
asked only under `WALKS_AIR_DEMO=1` (its free API is for non-commercial use), otherwise the smog signals are the
station's smoke / haze and the НМУ notices. Short timeout, every request may fail independently; offline mode makes
none.

Requests carry only the fixed city-centre coordinates below, never the user's location.
"""

from __future__ import annotations

import json
import logging
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Sequence
from concurrent.futures import ThreadPoolExecutor
from datetime import UTC, datetime

from . import kazhydromet, metar, metno
from .envcfg import air_demo, offline
from .hours import TZ, local_now
from .httpget import get_text
from .i18n import t
from .i18n_weather import tw
from .models import WeatherInfo, WeatherWarning

AIR_URL = (
    "https://air-quality-api.open-meteo.com/v1/air-quality?latitude=51.13&longitude=71.43"
    "&current=pm2_5,european_aqi&timezone=Asia%2FAlmaty"
)
CACHE_TTL_S = 600
FAILURE_TTL_S = 60  # do not hammer a dead network on every Streamlit rerun
NOTICE_TTL_S = 900  # Kazhydromet notices change a few times a day
NOTICE_FAILURE_TTL_S = 300
TIMEOUT_S = 4.0

COLD_APPARENT_C = -15.0  # at or below -> adverse
HEAT_APPARENT_C = (
    35.0  # at or above -> adverse (Kazhydromet hazard degree 3 for the maximum is +35...+40 °C)
)
HEAVY_PRECIP_MM = 2.5  # mm in the hour at or above -> adverse (moderate/heavy rain or snow)
BAD_PM25 = 35.0  # ug/m3, strictly above -> prefer indoor (WHO 24h guideline is 15; 35 = US "unhealthy for sensitive")
# Adverse tokens that come from the airport report or a Kazhydromet warning (walks.metar), in the order they are said.
WEATHER_TOKENS = (
    "storm_warning",
    "thunder",
    "freezing_rain",
    "rain",
    "snow",
    "blowing_snow",
    "fog",
    "wind",
)
AIR_TOKENS = ("smog", "nmu")  # smoke / haze at the station, the НМУ of Kazhydromet: the air is bad

# Indoor-friendly vs. outdoor categories, used by retrieval when the weather / air is bad or it is dark.
INDOOR_CATEGORIES = {
    "museum_gallery",
    "mall",
    "cafe",
    "culture_theatre_cinema",
    "coworking_library",
    "entertainment",
}
OUTDOOR_CATEGORIES = {"park_garden", "viewpoint", "kids_playground"}

_Cache = tuple[float, dict | None]
_air_cache: _Cache | None = None
_obs_cache: tuple[float, metar.Observation | None] | None = None
_obs_last: metar.Observation | None = (
    None  # the last good report: shown with its time when a fetch fails
)
_notice_cache: tuple[float, bool] | None = None  # (stamp, the last fetch succeeded)
_notice_last: list[kazhydromet.Notice] = []


def reason_text(
    apparent_c: float | None,
    precipitation_mm: float | None,
    lang: str | None,
    conditions: Sequence[str] = (),
) -> str:
    """Why the weather counts as adverse, in the answer language ('' when it does not)."""
    reasons = []
    if apparent_c is not None and apparent_c <= COLD_APPARENT_C:
        reasons.append(t("wx_feels", lang, deg=f"{apparent_c:.0f}"))
    if apparent_c is not None and apparent_c >= HEAT_APPARENT_C:
        reasons.append(tw("wx_hot", lang, deg=f"{apparent_c:.0f}"))
    if precipitation_mm is not None and precipitation_mm >= HEAVY_PRECIP_MM:
        reasons.append(t("wx_heavy", lang, p=f"{precipitation_mm:.1f}"))
    reasons += [tw(f"wx_c_{c}", lang) for c in WEATHER_TOKENS if c in conditions]
    return ", ".join(reasons)


def assess(
    apparent_c: float | None, precipitation_mm: float | None, conditions: Sequence[str] = ()
) -> tuple[bool, str]:
    reason = reason_text(apparent_c, precipitation_mm, "ru", conditions)
    return bool(reason), reason


def fmt_temp(value: float) -> str:
    """Whole degrees without a '-0' (round(-0.4) is 0)."""
    return str(round(value))


def air_reason_text(pm25: float, lang: str | None) -> str:
    return t("air_reason", lang, pm=f"{pm25:.0f}")


def air_conditions_text(conditions: Sequence[str], lang: str | None) -> str:
    """The smoke / haze of the station report and the НМУ of Kazhydromet, as the cause of bad air ('' for neither)."""
    return ", ".join(tw(f"wx_c_{c}", lang) for c in AIR_TOKENS if c in conditions)


def assess_air(pm25: float | None, conditions: Sequence[str] = ()) -> tuple[bool, str]:
    reasons = []
    if pm25 is not None and pm25 > BAD_PM25:
        reasons.append(air_reason_text(pm25, "ru"))
    if what := air_conditions_text(conditions, "ru"):
        reasons.append(what)
    return bool(reasons), ", ".join(reasons)


def with_user_hint(weather: WeatherInfo | None, hint: str) -> WeatherInfo | None:
    """The user's own words about the conditions («-25, холодно», «ливень», «жара», «смог») count as adverse: the
    shelter rule and the walking cap apply as they do for a measured frost, downpour or smog. The measured value
    stays when it already says the same; `weather=None` (adaptation off) does not silence the user's own words."""
    if hint in ("", "none"):
        return weather
    base = weather if weather is not None else WeatherInfo(source="manual")
    if hint == "smog":
        if base.air_bad:
            return base
        return base.model_copy(
            update={"air_bad": True, "air_reason": t("wx_hint_smog", "ru"), "user_hint": hint}
        )
    if base.adverse:
        return base
    return base.model_copy(
        update={"adverse": True, "reason": t(f"wx_hint_{hint}", "ru"), "user_hint": hint}
    )


def adverse_text(weather: WeatherInfo, lang: str | None) -> str:
    """Why the conditions count as adverse, in the answer language: the measured frost / heat / precipitation, what
    the station or Kazhydromet reports, or the user's own words when those made them so."""
    if weather.user_hint and weather.user_hint != "smog":
        return t(f"wx_hint_{weather.user_hint}", lang)
    precip = None if weather.source == "metar" else weather.precipitation_mm
    return reason_text(weather.apparent_c, precip, lang, weather.conditions)


def air_text(weather: WeatherInfo, lang: str | None) -> str:
    """The clause for bad air: the user's own «smog», the measured PM2.5, or the smoke / haze at the station and the
    НМУ of Kazhydromet when those made the air bad."""
    if weather.user_hint == "smog":
        return t("wx_bad", lang, what=t("wx_hint_smog", lang))
    if weather.pm25 is not None and weather.pm25 > BAD_PM25:
        return t("wx_air", lang, pm=f"{weather.pm25:.0f}")
    if what := air_conditions_text(weather.conditions, lang):
        return t("wx_bad", lang, what=what)
    if weather.pm25 is None:
        return t("wx_bad", lang, what=t("wx_hint_smog", lang))
    return t("wx_air", lang, pm=f"{weather.pm25:.0f}")


def air_driver_text(weather: WeatherInfo, lang: str | None) -> str:
    """What made the air bad, in the answer language and without a verdict: the user's own «smog», the measured PM2.5,
    the smoke / haze at the station, the НМУ notice of Kazhydromet (several of them are all said)."""
    if weather.user_hint == "smog":
        return t("wx_hint_smog", lang)
    parts = []
    if weather.pm25 is not None and weather.pm25 > BAD_PM25:
        parts.append(air_reason_text(weather.pm25, lang))
    if what := air_conditions_text(weather.conditions, lang):
        parts.append(what)
    return ", ".join(parts) or weather.air_reason


def attribution(weather: WeatherInfo, lang: str | None) -> str:
    """«по наблюдению Казгидромета (METAR UACC), 17.10 20:00», or the note that the observation is stale and the
    forecast is used; '' when no station report was found."""
    if not weather.observed_at:
        return ""
    when = datetime.fromisoformat(weather.observed_at).strftime("%d.%m %H:%M")
    return tw("obs_stale" if weather.obs_stale else "obs_attr", lang, time=when)


def source_details(lang: str | None) -> str:
    """Where the station report comes from, for the «sources» panel (the delivery through NOAA/NWS is named here)."""
    return tw("obs_details", lang)


def forecast_credit(lang: str | None) -> str:
    """«прогноз: MET Norway (CC BY 4.0)»: the credit CC BY 4.0 asks for the forecast leg."""
    return tw("fc_attr", lang)


def air_credit(lang: str | None) -> str:
    """The credit of the PM2.5 leg, with the note that its free API is for demo / non-commercial use only."""
    return tw("air_attr", lang)


def credit_lines(weather: WeatherInfo, lang: str | None) -> list[str]:
    """The credits of the remote data this answer's weather is made of (nothing for a manual demo weather)."""
    if weather.source == "manual":
        return []
    out = [forecast_credit(lang)] if weather.forecast_used else []
    if weather.pm25 is not None:
        out.append(air_credit(lang))
    return out


def warning_text(warning: WeatherWarning, lang: str | None) -> str:
    """The notice (title and text as Kazhydromet wrote them) with the mandatory link to its source."""
    head, text = warning.title.rstrip(". "), warning.text.rstrip(". ")
    return f"{head}. {text}. {tw('warn_source', lang, url=warning.source_url)}"


def make_weather(
    temperature_c: float | None = None,
    apparent_c: float | None = None,
    wind_kmh: float | None = None,
    precipitation_mm: float | None = None,
    *,
    pm25: float | None = None,
    aqi: int | None = None,
    force_dark: bool = False,
    source: str = "met-no",
    fetched_at: str = "",
    conditions: Sequence[str] = (),
    warnings: Sequence[WeatherWarning] = (),
    precip_adverse: bool = True,
    observed_at: str = "",
    obs_stale: bool = False,
    obs_raw: str = "",
    forecast_used: bool = False,
    wind_from_deg: int | None = None,
    wind_gust_kmh: float | None = None,
    cloud_pct: float | None = None,
    precip_now: str = "",
    precip_level: int = 0,
    visibility_m: int | None = None,
) -> WeatherInfo:
    """The conditions with their verdict. `conditions` are the adverse tokens read off the airport report; an active
    Kazhydromet storm warning adds «storm_warning», an active НМУ adds «nmu» (the air is then bad). With
    `precip_adverse=False` the amount of precipitation is only shown (the station says what falls, not how much)."""
    tokens = list(conditions)
    for w in warnings:
        if w.active:
            tokens.append("storm_warning" if w.kind == "storm" else "nmu")
    precip = precipitation_mm if precip_adverse else None
    adverse, reason = assess(apparent_c, precip, tokens)
    air_bad, air_reason = assess_air(pm25, tokens)
    return WeatherInfo(
        temperature_c=temperature_c,
        apparent_c=apparent_c,
        wind_kmh=wind_kmh,
        precipitation_mm=precipitation_mm,
        pm25=pm25,
        aqi=aqi,
        force_dark=force_dark,
        source=source,  # type: ignore[arg-type]
        fetched_at=fetched_at,
        observed_at=observed_at,
        obs_stale=obs_stale,
        obs_raw=obs_raw,
        forecast_used=forecast_used,
        wind_from_deg=wind_from_deg,
        wind_gust_kmh=wind_gust_kmh,
        cloud_pct=cloud_pct,
        precip_now=precip_now,  # type: ignore[arg-type]
        precip_level=precip_level,
        visibility_m=visibility_m,
        conditions=tokens,
        warnings=list(warnings),
        adverse=adverse,
        reason=reason,
        air_bad=air_bad,
        air_reason=air_reason,
    )


def manual_weather(
    apparent_c: float,
    precipitation_mm: float = 0.0,
    *,
    pm25: float = 10.0,
    force_dark: bool = False,
) -> WeatherInfo:
    """Demo override (e.g. simulate -30°C, PM2.5 80, or 'already after sunset')."""
    return make_weather(
        apparent_c,
        apparent_c,
        0.0,
        precipitation_mm,
        pm25=pm25,
        force_dark=force_dark,
        source="manual",
        fetched_at=local_now().strftime("%H:%M"),
    )


def _get_json(url: str, timeout: float, opener) -> dict:
    return json.loads(get_text(url, timeout, opener))


def _cached(slot: _Cache | None, now: float) -> tuple[bool, dict | None]:
    if slot is not None:
        stamp, value = slot
        if now - stamp < (CACHE_TTL_S if value is not None else FAILURE_TTL_S):
            return True, value
    return False, None


def _air(now: float, timeout: float, opener) -> dict:
    """PM2.5 and the European AQI of the Open-Meteo air-quality API (demo switch `WALKS_AIR_DEMO`), cached 10 minutes."""
    global _air_cache
    hit, air = _cached(_air_cache, now)
    if not hit:
        try:
            air = _get_json(AIR_URL, timeout, opener)
            float(air["current"]["pm2_5"])
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, TypeError):
            air = None
        _air_cache = (now, air)
    if air is None:
        return {}
    cur = air["current"]
    out: dict = {"pm25": float(cur["pm2_5"])}
    if cur.get("european_aqi") is not None:
        out["aqi"] = int(cur["european_aqi"])
    return out


def fetch_weather(
    timeout: float = TIMEOUT_S,
    *,
    opener=urllib.request.urlopen,
    clock=time.monotonic,
    sleep=time.sleep,
) -> WeatherInfo:
    """Current conditions. Never raises: a failed request leaves its part None (UI shows 'погода неизвестна' /
    'воздух неизвестен' and retrieval does not adapt to it); sunrise/sunset are always computed locally."""
    if offline():  # no request: unknown weather and air, sun times from the local formula
        return make_weather(fetched_at=local_now().strftime("%H:%M"))
    now = clock()
    # Kazhydromet is polite-throttled (about 3 s for its first four requests): fetched beside the other requests
    pool = ThreadPoolExecutor(max_workers=1)
    notices = pool.submit(_notices, now, timeout, opener, sleep)

    kwargs: dict = {}
    if (fc := metno.forecast(now, _utc_now(), timeout, opener)) is not None:
        kwargs.update(
            temperature_c=fc.temperature_c,
            apparent_c=fc.apparent_c,
            wind_kmh=fc.wind_kmh,
            precipitation_mm=fc.precipitation_mm,
            wind_from_deg=fc.wind_from_deg,
            cloud_pct=fc.cloud_pct,
            forecast_used=True,
        )
    if air_demo():
        kwargs.update(_air(now, timeout, opener))
    kwargs.update(_measured(kwargs, now, timeout, opener, notices.result()))
    pool.shutdown()
    return make_weather(**kwargs, fetched_at=local_now().strftime("%H:%M"))


def _utc_now() -> datetime:
    return local_now().replace(tzinfo=TZ).astimezone(UTC)


def _observation(now: float, timeout: float, opener) -> metar.Observation | None:
    """The newest UACC report: from the 10-minute cache, else fetched; the last good report when the fetch fails."""
    global _obs_cache, _obs_last
    if _obs_cache is not None:
        stamp, cached = _obs_cache
        if now - stamp < (CACHE_TTL_S if cached is not None else FAILURE_TTL_S):
            return _obs_last
    fetched = metar.fetch_observation(timeout, opener, now_utc=_utc_now())
    _obs_cache = (now, fetched)
    if fetched is not None:
        _obs_last = fetched
    return _obs_last


def _notices(now: float, timeout: float, opener, sleep) -> list[kazhydromet.Notice]:
    """Kazhydromet notices for Astana: cached for 15 minutes (5 after a failure); the last good set stays in use
    when a fetch fails, as every notice carries its own period of validity."""
    global _notice_cache, _notice_last
    if _notice_cache is not None:
        stamp, ok = _notice_cache
        if now - stamp < (NOTICE_TTL_S if ok else NOTICE_FAILURE_TTL_S):
            return _notice_last
    try:
        _notice_last = kazhydromet.fetch_notices(
            timeout, opener, today=local_now().date(), sleep=sleep
        )
        _notice_cache = (now, True)
    except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, TypeError):
        _notice_cache = (now, False)
    return _notice_last


def _obs_fields(obs: metar.Observation, forecast: dict) -> dict:
    """The weather of a fresh airport report; the forecast only supplies the amount of precipitation."""
    falling = metar.falling_now(obs) or ("", 0)
    return {
        "source": "metar",
        "temperature_c": obs.temperature_c,
        "apparent_c": metar.apparent_c(obs),
        "wind_kmh": round((obs.wind_ms or 0.0) * 3.6, 1),
        "precipitation_mm": forecast.get("precipitation_mm", 0.0),
        "precip_adverse": False,  # the station reports the kind of precipitation, the model its amount
        "conditions": metar.adverse_conditions(obs),
        "wind_from_deg": obs.wind_from_deg,
        "wind_gust_kmh": None if obs.gust_ms is None else round(obs.gust_ms * 3.6, 1),
        "cloud_pct": None if obs.cloud is None else metar.CLOUD_PCT[obs.cloud],
        "precip_now": falling[0],
        "precip_level": falling[1],
        "visibility_m": obs.visibility_m,
    }


def _measured(
    forecast: dict, now: float, timeout: float, opener, notices: list[kazhydromet.Notice]
) -> dict:
    """What the station and Kazhydromet add to the forecast: the observation replaces the forecast's temperature and
    wind when it is at most 3 h old (a stale one is only reported), notices of Astana go into `warnings`."""
    out: dict = {}
    utc_now = _utc_now()
    obs = _observation(now, timeout, opener)
    if obs is not None:
        out["observed_at"] = obs.observed_at.astimezone(TZ).isoformat(timespec="minutes")
        out["obs_raw"] = obs.raw
        if obs.fresh(utc_now) and obs.temperature_c is not None:
            out.update(_obs_fields(obs, forecast))
        else:
            out["obs_stale"] = not obs.fresh(utc_now)
    out["warnings"] = kazhydromet.warnings_at(notices, local_now())
    return out


def clear_cache() -> None:
    global _air_cache, _obs_cache, _obs_last, _notice_cache, _notice_last, _latest
    _air_cache = _obs_cache = _obs_last = _notice_cache = None
    _notice_last = []
    _latest = None
    _first.clear()
    metno.reset()
    kazhydromet.reset()


# ---------------------------------------------------------------- the background refresh
# A request never waits for the network: a thread (started by the server at startup) refreshes the conditions every
# REFRESH_S and a request reads the last value. Without that thread (CLI, tests) `latest_weather` fetches as before.

REFRESH_S = 600.0
RETRY_S = 60.0  # a refresh that found nothing is repeated sooner
FIRST_WAIT_S = (
    3.0  # the very first request after a start waits this long at most for the first value
)
log = logging.getLogger(__name__)
_latest: WeatherInfo | None = None
_first = threading.Event()
_refresher: threading.Thread | None = None


def _has_data(w: WeatherInfo) -> bool:
    return w.temperature_c is not None or w.pm25 is not None


def _refresh_loop() -> None:
    global _latest
    while True:
        delay = REFRESH_S
        try:
            w = fetch_weather()
            if _has_data(w) or _latest is None:
                _latest = w
            if not _has_data(w):
                delay = RETRY_S
        except Exception:
            log.exception("weather refresh failed")
            delay = RETRY_S
        _first.set()
        time.sleep(delay)


def start_refresher() -> None:
    """Start the refresh thread (once); the first fetch runs at once, in the background."""
    global _refresher
    if _refresher is not None and _refresher.is_alive():
        return
    _refresher = threading.Thread(target=_refresh_loop, name="weather-refresh", daemon=True)
    _refresher.start()


def latest_weather() -> WeatherInfo:
    """The conditions a request uses: the last value of the refresh thread, never a network call of its own (only the
    first request after a start waits, up to FIRST_WAIT_S, for the first value). Without the thread: `fetch_weather`."""
    if _refresher is None or not _refresher.is_alive():
        return fetch_weather()
    if _latest is None:
        _first.wait(FIRST_WAIT_S)
    return _latest or make_weather(fetched_at=local_now().strftime("%H:%M"))


def refreshed_weather() -> WeatherInfo | None:
    """The last value of the refresh thread and nothing else: no wait, no network. None before the first refresh
    finished (and without the thread, as in the CLI and in tests)."""
    return _latest
