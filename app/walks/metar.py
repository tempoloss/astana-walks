"""The Astana airport observation: METAR / SPECI of UACC (Kazhydromet, issued through the WMO exchange) read from
aviationweather.gov, with IEM ASOS (mesonet.agron.iastate.edu) as the fallback. Both are NOAA/NWS public-domain
feeds of the same station (collect/SOURCES.md §14.1).

`parse_metar` turns one report into an `Observation`; `adverse_conditions` maps its present-weather codes, visibility
and wind onto the adverse tokens of walks.weather: rain, snow, blowing_snow, freezing_rain, thunder, fog, wind, smog
(FU smoke / HZ haze). Temperature-based categories (cold, heat) are decided from the numbers by walks.weather.
"""

from __future__ import annotations

import contextlib
import re
import urllib.error
import urllib.request
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta

from . import apparent
from .httpget import get_text

STATION = "UACC"
AVIATION_URL = f"https://aviationweather.gov/api/data/metar?ids={STATION}&format=raw&hours=6"
IEM_URL = (
    f"https://mesonet.agron.iastate.edu/cgi-bin/request/asos.py?station={STATION}&data=metar&hours=6"
    "&format=onlycomma&latlon=no&tz=UTC&missing=empty&trace=T&report_type=3&report_type=4"
)
MAX_AGE = timedelta(hours=3)  # an older report is not «now»: the forecast is used instead
FUTURE_SLACK = timedelta(hours=1)  # clock skew tolerated before a report counts as from the future

WIND_ADVERSE_MS = (
    12.0  # Kazhydromet hazard degree 1 for wind is 12-14 m/s (kazhydromet.kz/ru/meteoalert)
)
MIST_ADVERSE_M = 2000  # mist (BR) only counts as fog when it limits the visibility this much
DRIFT_ADVERSE_M = 2000  # drifting snow (DRSN) only counts when the visibility is this poor
_KT_MS = 0.514444
_MPS_KMH = 3.6

_STATION = re.compile(r"^[A-Z]{4}$")
_TIME = re.compile(r"^(\d{2})(\d{2})(\d{2})Z$")
_WIND = re.compile(r"^(\d{3}|VRB)(\d{2,3})(?:G(\d{2,3}))?(MPS|KT|KMH)$")
_VIS_M = re.compile(r"^\d{4}$")
_VIS_SM = re.compile(r"^(\d{1,2})SM$")
_TEMP = re.compile(r"^([M-]?\d{2})/([M-]?\d{2})?$")
_WX = re.compile(
    r"^(?P<i>[-+]|VC)?(?P<d>MI|PR|BC|DR|BL|SH|TS|FZ)?"
    r"(?P<p>(?:DZ|RA|SN|SG|IC|PL|GR|GS|UP|BR|FG|FU|VA|DU|SA|HZ|PY|PO|SQ|FC|SS|DS)*)$"
)
_CLOUD = re.compile(r"^(?:(FEW|SCT|BKN|OVC)(?:\d{3}|///)(?:CB|TCU|///)?|(VV)(?:\d{3}|///))$")
_CLEAR_SKY = {"SKC", "CLR", "NSC", "NCD"}
CLOUD_ORDER = (
    "CLR",
    "FEW",
    "SCT",
    "BKN",
    "OVC",
    "VV",
)  # the sky cover of a report, from clear to obscured
CLOUD_PCT = {
    "CLR": 0.0,
    "FEW": 19.0,
    "SCT": 44.0,
    "BKN": 75.0,
    "OVC": 100.0,
    "VV": 100.0,
}  # mid-oktas
# present-weather phenomena that fall: snow family and rain family (IC, UP and drifting / blowing snow do not count)
_SNOWFALL = {"SN", "SG", "GS", "IC"}
_RAINFALL = {"DZ", "RA", "PL", "GR"}
_TRENDS = {
    "NOSIG",
    "BECMG",
    "TEMPO",
    "RMK",
}  # what follows describes the forecast, not the present weather


@dataclass(frozen=True)
class Observation:
    raw: str
    station: str
    observed_at: datetime  # aware, UTC
    temperature_c: float | None
    dew_point_c: float | None
    wind_ms: float | None
    gust_ms: float | None
    visibility_m: int | None
    weather: tuple[str, ...]  # present-weather groups as reported: ("-SN", "BLSN")
    source_url: str = ""
    wind_from_deg: int | None = None  # None: calm or variable (VRB), or no wind group
    cloud: str | None = (
        None  # the largest cover of CLOUD_ORDER; None when the report says nothing about the sky
    )

    def age(self, now_utc: datetime) -> timedelta:
        return now_utc - self.observed_at

    def fresh(self, now_utc: datetime) -> bool:
        return -FUTURE_SLACK <= self.age(now_utc) <= MAX_AGE


def _temp(token: str) -> float:
    return -float(token[1:]) if token[0] in "M-" else float(token)


def _resolve_time(day: int, hour: int, minute: int, now_utc: datetime) -> datetime | None:
    """The latest instant with this day-of-month and time that is not in the future (a report carries no month)."""
    candidates = []
    year, month = now_utc.year, now_utc.month
    for _ in range(2):  # this month, then the previous one
        with contextlib.suppress(ValueError):  # a day the month does not have
            candidates.append(datetime(year, month, day, hour, minute, tzinfo=UTC))
        year, month = (year - 1, 12) if month == 1 else (year, month - 1)
    past = [c for c in candidates if c <= now_utc + FUTURE_SLACK]
    return max(past) if past else None


def _sky(so_far: str | None, token: str) -> str:
    """The larger cover of the sky so far and one sky token (clear tokens and CAVOK are «CLR»)."""
    m = _CLOUD.match(token)
    cover = (m[1] or m[2]) if m else "CLR"
    return max(so_far or "CLR", cover, key=CLOUD_ORDER.index)


def parse_metar(raw: str, now_utc: datetime) -> Observation | None:
    """One METAR / SPECI (or the bare report of IEM) -> Observation; None when it is not a readable report."""
    tokens = raw.strip().rstrip("=").split()
    i = 1 if tokens and tokens[0] in ("METAR", "SPECI") else 0
    if i < len(tokens) and tokens[i] == "COR":
        i += 1
    if (
        len(tokens) < i + 2
        or not _STATION.match(tokens[i])
        or not (tm := _TIME.match(tokens[i + 1]))
    ):
        return None
    observed = _resolve_time(int(tm[1]), int(tm[2]), int(tm[3]), now_utc)
    if observed is None:
        return None
    wind = gust = vis = temp = dew = wind_dir = cloud = None
    seen_temp = False
    weather: list[str] = []
    for tok in tokens[i + 2 :]:
        if tok in _TRENDS:
            break
        if tok == "CAVOK":
            vis = 9999 if vis is None else vis
            cloud = _sky(cloud, tok)
        elif wind is None and (m := _WIND.match(tok)):
            unit = {"MPS": 1.0, "KT": _KT_MS, "KMH": 1 / _MPS_KMH}[m[4]]
            wind = int(m[2]) * unit
            gust = int(m[3]) * unit if m[3] else None
            wind_dir = int(m[1]) % 360 if m[1] != "VRB" and int(m[2]) > 0 else None
        elif vis is None and _VIS_M.match(tok):
            vis = int(tok)
        elif vis is None and (m := _VIS_SM.match(tok)):
            vis = round(int(m[1]) * 1609.344)
        elif not seen_temp and (tok == "CAVOK" or tok in _CLEAR_SKY or _CLOUD.match(tok)):
            cloud = _sky(cloud, tok)
        elif not seen_temp and (m := _TEMP.match(tok)):
            temp, dew, seen_temp = _temp(m[1]), (_temp(m[2]) if m[2] else None), True
        elif not seen_temp and tok and (m := _WX.match(tok)) and (m["p"] or m["d"] == "TS"):
            weather.append(tok)
    return Observation(
        raw=raw.strip().rstrip("="),
        station=tokens[i],
        observed_at=observed,
        temperature_c=temp,
        dew_point_c=dew,
        wind_ms=wind,
        gust_ms=gust,
        visibility_m=vis,
        weather=tuple(weather),
        wind_from_deg=wind_dir,
        cloud=cloud,
    )


def parse_feed(text: str, now_utc: datetime) -> list[Observation]:
    """Reports of an aviationweather.gov raw listing (one per line) or of an IEM `onlycomma` CSV, newest first."""
    out = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith(f"{STATION},"):  # IEM: station,valid,metar
            line = line.split(",", 2)[-1]
        if (obs := parse_metar(line, now_utc)) is not None and obs.station == STATION:
            out.append(obs)
    return sorted(out, key=lambda o: o.observed_at, reverse=True)


def fetch_observation(
    timeout: float, opener=urllib.request.urlopen, *, now_utc: datetime | None = None
) -> Observation | None:
    """The newest report of UACC: aviationweather.gov first, IEM when that is down or has nothing; None when both fail.
    The caller decides whether the report is fresh enough (`Observation.fresh`)."""
    now_utc = now_utc or datetime.now(UTC)
    for url in (AVIATION_URL, IEM_URL):
        try:
            reports = parse_feed(get_text(url, timeout, opener), now_utc)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            continue
        if reports:
            return replace(reports[0], source_url=url)
    return None


def apparent_c(obs: Observation) -> float | None:
    """Apparent temperature of the report (walks.apparent: Steadman without radiation), the vapour pressure from the
    dew point. Without a wind or a dew point that term is left out."""
    if obs.temperature_c is None:
        return None
    return apparent.apparent_c(obs.temperature_c, obs.wind_ms, dew_point_c=obs.dew_point_c)


def _groups(obs: Observation) -> list[tuple[str, str, list[str]]]:
    """(intensity, descriptor, phenomena) of every present-weather group at the station (vicinity groups dropped)."""
    out = []
    for tok in obs.weather:
        m = _WX.match(tok)
        if m is None or m["i"] == "VC":
            continue
        out.append((m["i"] or "", m["d"] or "", re.findall(r"..", m["p"])))
    return out


def _token(
    intensity: str, descriptor: str, phenomenon: str, visibility_m: int | None
) -> str | None:
    """The adverse token of one phenomenon of a present-weather group, None when it is not adverse."""
    light = intensity == "-"
    if descriptor == "FZ" and phenomenon in ("RA", "DZ"):
        return "freezing_rain"
    if phenomenon in ("GR", "PL") or (phenomenon in ("GS", "RA") and not light):
        return "rain"
    if phenomenon == "DZ" and intensity == "+":
        return "rain"
    if phenomenon == "SN" and descriptor in ("BL", "DR"):
        # blowing snow is lifted to eye level; low drifting snow is not, it counts when the visibility is poor anyway
        limited = visibility_m is not None and visibility_m <= DRIFT_ADVERSE_M
        return "blowing_snow" if descriptor == "BL" or limited else None
    if phenomenon in ("SN", "SG") and not light:
        return "snow"
    if phenomenon == "FG" and descriptor not in ("MI", "BC", "PR"):
        return "fog"
    if phenomenon == "BR" and visibility_m is not None and visibility_m <= MIST_ADVERSE_M:
        return "fog"
    if phenomenon in ("FU", "HZ"):
        return "smog"
    return None


def adverse_conditions(obs: Observation) -> tuple[str, ...]:
    """Adverse tokens of the report, in a fixed order. Light rain / snow / drizzle, mist, shallow or patchy fog are
    reported but not adverse; thunder, hail, freezing rain, blowing snow, fog, thick mist, smoke, haze and a strong
    wind are."""
    found: set[str] = set()
    for intensity, descriptor, phenomena in _groups(obs):
        if descriptor == "TS":
            found.add("thunder")
        found.update(
            tok
            for p in phenomena
            if (tok := _token(intensity, descriptor, p, obs.visibility_m)) is not None
        )
    if max(obs.wind_ms or 0.0, obs.gust_ms or 0.0) >= WIND_ADVERSE_MS:
        found.add("wind")
    order = ("thunder", "freezing_rain", "rain", "snow", "blowing_snow", "fog", "wind", "smog")
    return tuple(c for c in order if c in found)


_LEVEL = {"-": 1, "": 2, "+": 3}  # light / moderate / heavy


def falling_now(obs: Observation) -> tuple[str, int] | None:
    """What falls at the station now: ("snow" | "rain", 1 light / 2 moderate / 3 heavy) from the present-weather groups,
    None when nothing does. Blowing and drifting snow is lifted from the ground, not falling; a mix counts as snow;
    the level is the strongest of the groups of that kind."""
    best: dict[str, int] = {}
    for intensity, descriptor, phenomena in _groups(obs):
        if descriptor in ("BL", "DR"):
            continue
        for p in phenomena:
            kind = "snow" if p in _SNOWFALL else "rain" if p in _RAINFALL else None
            if kind is not None:
                best[kind] = max(best.get(kind, 0), _LEVEL[intensity])
    kind = "snow" if "snow" in best else "rain" if "rain" in best else None
    return None if kind is None else (kind, best[kind])
