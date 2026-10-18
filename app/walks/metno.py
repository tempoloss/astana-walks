"""The forecast leg: MET Norway `locationforecast/2.0/compact` for the centre of Astana (collect/weather/README.md).

Terms (api.met.no/doc/TermsOfService, read 2026-10-17): data CC BY 4.0 + NLOD 2.0 (commercial use allowed, credit
«MET Norway»); an identifying User-Agent with a contact; do not repeat a request before the `Expires` time; revalidate
with `If-Modified-Since` = the previous `Last-Modified` (the server answers 304); gzip; coordinates at most 4
decimals; more than 20 requests/s per application needs an agreement; throttled clients get 429 (403 for a client it
has banned) and must stop at once.

The parsed series and the cache state live in this module (one process = one forecast). `forecast()` never raises:
a failed request leaves the last good series in use for as long as it still covers «now», and after a refusal
(403/429) nothing is asked for 15 minutes.
"""

from __future__ import annotations

import gzip
import json
import logging
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from email.utils import parsedate_to_datetime

from . import apparent
from .httpget import USER_AGENT

URL = "https://api.met.no/weatherapi/locationforecast/2.0/compact?lat=51.13&lon=71.43"
DEFAULT_TTL_S = 600  # no (or unreadable) Expires header
MIN_TTL_S = (
    60  # never ask more often than this, whatever Expires says (Streamlit reruns, clock skew)
)
MAX_TTL_S = 6 * 3600
FAILURE_TTL_S = 60  # a network error or a bad body: try again soon
REFUSED_TTL_S = 900  # 403 / 429: the terms say stop at once; the client is throttled or banned
MAX_OFFSET = timedelta(hours=2)  # a series entry farther from «now» is not the current weather
MAX_STALE = timedelta(
    hours=3
)  # a series not confirmed for this long is not served (as for the METAR report)
_KMH_PER_MS = 3.6

log = logging.getLogger(__name__)


@dataclass(frozen=True)
class Forecast:
    """The series entry nearest to «now»: instant values and the precipitation of the next hour."""

    time: datetime  # UTC, the hour the entry stands for
    temperature_c: float
    apparent_c: float
    wind_kmh: float
    precipitation_mm: (
        float  # next_1_hours; 0.0 when the entry has none (far horizon): nothing is announced
    )
    wind_from_deg: int | None = None  # where the wind blows from; None when the series does not say
    cloud_pct: float | None = None  # cloud_area_fraction, 0..100; None when the series does not say


@dataclass(frozen=True)
class Hour:
    """One hour of the series ahead of «now», for the panel's strip."""

    time: datetime  # UTC
    temperature_c: float
    precipitation_mm: float | None  # next_1_hours; None when the entry has none
    symbol: str  # clear / partly / cloud / fog / rain / sleet / snow / thunder, or "" when the series has no symbol


@dataclass(frozen=True)
class _Entry:
    time: datetime
    temperature_c: float
    humidity_pct: float | None
    wind_ms: float | None
    precipitation_mm: float | None
    wind_from_deg: float | None = None
    cloud_pct: float | None = None
    symbol: str | None = None  # symbol_code of next_1_hours («lightsnow», «partlycloudy_night»)


@dataclass
class _State:
    entries: list[_Entry]
    last_modified: str = ""  # of the answer the entries come from, sent back as If-Modified-Since
    fetched_at: datetime | None = (
        None  # UTC of the last answer (200 or 304) the entries are confirmed by
    )
    next_try: float = 0.0  # monotonic time before which nothing is requested


_state = _State(entries=[])


def reset() -> None:
    global _state
    _state = _State(entries=[])


def parse(doc: dict) -> list[_Entry]:
    """The time series of a `compact` answer; ValueError when the document is not one."""
    try:
        series = doc["properties"]["timeseries"]
        out = []
        for item in series:
            details = item["data"]["instant"]["details"]
            one_hour = item["data"].get("next_1_hours")
            symbol = one_hour.get("summary", {}).get("symbol_code") if one_hour else None
            precipitation = one_hour["details"].get("precipitation_amount") if one_hour else None
            humidity = details.get("relative_humidity")
            wind = details.get("wind_speed")
            wind_from = details.get("wind_from_direction")
            cloud = details.get("cloud_area_fraction")
            out.append(
                _Entry(
                    time=datetime.fromisoformat(item["time"]).astimezone(UTC),
                    temperature_c=float(details["air_temperature"]),
                    humidity_pct=None if humidity is None else float(humidity),
                    wind_ms=None if wind is None else float(wind),
                    precipitation_mm=None if precipitation is None else float(precipitation),
                    wind_from_deg=None if wind_from is None else float(wind_from),
                    cloud_pct=None if cloud is None else float(cloud),
                    symbol=symbol,
                )
            )
    except (KeyError, TypeError, AttributeError) as exc:
        raise ValueError(f"not a locationforecast answer: {exc!r}") from exc
    if not out:
        raise ValueError("locationforecast answer without a time series")
    return out


def pick(entries: list[_Entry], utc_now: datetime) -> Forecast | None:
    """The entry nearest to `utc_now` (at most MAX_OFFSET away), None when the series no longer covers «now»."""
    entry = min(entries, key=lambda e: abs(e.time - utc_now))
    if abs(entry.time - utc_now) > MAX_OFFSET:
        return None
    wind = entry.wind_ms or 0.0
    return Forecast(
        time=entry.time,
        temperature_c=entry.temperature_c,
        apparent_c=apparent.apparent_c(entry.temperature_c, wind, humidity_pct=entry.humidity_pct),
        wind_kmh=round(wind * _KMH_PER_MS, 1),
        precipitation_mm=entry.precipitation_mm or 0.0,
        wind_from_deg=(
            None
            if entry.wind_from_deg is None or entry.wind_ms is None
            else round(entry.wind_from_deg) % 360
        ),
        cloud_pct=entry.cloud_pct,
    )


def symbol_kind(code: str | None) -> str:
    """MET Norway's symbol_code reduced to what the panel draws; "" for a code it does not know."""
    if not code:
        return ""
    for needle, kind in (
        ("thunder", "thunder"),
        ("sleet", "sleet"),
        ("snow", "snow"),
        ("rain", "rain"),
        ("fog", "fog"),
        ("clearsky", "clear"),
        ("fair", "clear"),
        ("partlycloudy", "partly"),
        ("cloudy", "cloud"),
    ):
        if needle in code:
            return kind
    return ""


def upcoming(utc_now: datetime, count: int = 6) -> list[Hour]:
    """The next `count` hours of the series in memory (the entries after «now»), nothing when the series is not
    confirmed any more (MAX_STALE). Reads memory only: the refresh thread is what fetches."""
    state = _state
    if state.fetched_at is None or utc_now - state.fetched_at > MAX_STALE:
        return []
    later = sorted(
        (e for e in state.entries if utc_now < e.time <= utc_now + timedelta(hours=count + 1)),
        key=lambda e: e.time,
    )
    return [
        Hour(e.time, e.temperature_c, e.precipitation_mm, symbol_kind(e.symbol))
        for e in later[:count]
    ]


def _ttl(headers, utc_now: datetime) -> float:
    """Seconds until the `Expires` of an answer, bounded; DEFAULT_TTL_S when there is none."""
    raw = headers.get("Expires") if headers is not None else None
    if not raw:
        return DEFAULT_TTL_S
    try:
        expires = parsedate_to_datetime(raw)
    except (TypeError, ValueError):
        return DEFAULT_TTL_S
    if expires.tzinfo is None:
        expires = expires.replace(tzinfo=UTC)
    return min(max((expires - utc_now).total_seconds(), MIN_TTL_S), MAX_TTL_S)


def _request(timeout: float, opener, if_modified_since: str):
    """(headers, body) of one GET; the body is None for a 304 (not an exception, unlike urllib's default)."""
    headers = {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}
    if if_modified_since:
        headers["If-Modified-Since"] = if_modified_since
    req = urllib.request.Request(URL, headers=headers)
    try:
        with opener(req, timeout=timeout) as resp:
            raw = resp.read()
            if resp.headers.get("Content-Encoding", "").lower() == "gzip":
                raw = gzip.decompress(raw)
            if (
                getattr(resp, "status", 200) == 203
            ):  # the terms: a deprecated product version, to be logged
                log.warning("api.met.no answered 203: locationforecast/2.0 is deprecated")
            return resp.headers, json.loads(raw.decode("utf-8"))
    except urllib.error.HTTPError as exc:
        if exc.code == 304:
            return exc.headers, None
        raise


def forecast(
    now: float, utc_now: datetime, timeout: float, opener=urllib.request.urlopen
) -> Forecast | None:
    """The forecast for «now»: from the series in memory until its `Expires`, then revalidated (If-Modified-Since) or
    refetched. `now` is monotonic seconds, `utc_now` the wall clock (the Expires header is a wall-clock time)."""
    state = _state
    if now >= state.next_try:
        try:
            headers, doc = _request(timeout, opener, state.last_modified)
            if doc is not None:  # a 200 (or a 203, the deprecated version); a 304 has no body
                state.entries = parse(doc)
                state.last_modified = headers.get("Last-Modified", "") if headers else ""
            state.fetched_at = utc_now
            state.next_try = now + _ttl(headers, utc_now)
        except urllib.error.HTTPError as exc:
            refused = exc.code in (403, 429)
            state.next_try = now + (REFUSED_TTL_S if refused else FAILURE_TTL_S)
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            state.next_try = now + FAILURE_TTL_S
    if state.fetched_at is None or utc_now - state.fetched_at > MAX_STALE:
        return None
    return pick(state.entries, utc_now)
