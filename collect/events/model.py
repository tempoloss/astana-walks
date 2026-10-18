"""Event fact-card schema, Astana time helpers and Russian date parsing shared by every source parser.

One record of `data/events.json` (every fact carries evidence; no descriptions, no images):

    {"id": "sxodim.com:77443", "source": "sxodim.com", "title": str, "category": str | None,
     "kind": "event" | "run" | "sessions" | "standing",
     "start": ISO+05:00 | None, "end": ISO+05:00 | None,            # event: one occurrence
     "date_from": "YYYY-MM-DD" | None, "date_to": "YYYY-MM-DD" | None,  # run: a date range without hours (from == to
                                                                     # for a single date without a time);
                                                                     # sessions: the run of the film / show
     "sessions": [ISO+05:00, ...],                                    # sessions: the times the page lists (one day)
     "hours_raw": str | None, "hours_osm": str | None,               # standing: weekly schedule of a venue / exhibit
     "price_text": str | None, "price_from": int | None,
     "venue": {"name", "hall", "address", "lat", "lon", "coords_source": "page" | "poi" | None,
               "poi_id", "poi_name", "match": "name" | "address" | None},
     "url": str, "fetched_at": ISO, "also_listed": [{"source", "url"}],
     "evidence": [{"field", "url", "snippet", "fetched_at"}]}

Times are Astana local time (UTC+5, a fixed offset: the zone has had no DST since 2024-03).
"""

from __future__ import annotations

import re
from datetime import UTC, date, datetime, timedelta, timezone
from hashlib import sha1

from collect.sites.store import evidence, norm_ws

TZ = timezone(timedelta(hours=5))
KINDS = ("event", "run", "sessions", "standing")
ASTANA_LAT, ASTANA_LON = (50.98, 51.25), (71.25, 71.60)

MONTHS_RU = {
    "января": 1, "февраля": 2, "марта": 3, "апреля": 4, "мая": 5, "июня": 6, "июля": 7, "августа": 8,
    "сентября": 9, "октября": 10, "ноября": 11, "декабря": 12,
}
_M = "|".join(MONTHS_RU)
# "7 ноября в 19:00", "17 октября - 31 октября", "15 - 18 октября", "17 октября", "6 октября, 19:00"
DATE_RE = re.compile(
    rf"(?<![\d.])(?P<d1>\d{{1,2}})(?:\s+(?P<m1>{_M}))?(?:\s*[-–]\s*(?P<d2>\d{{1,2}})\s+(?P<m2>{_M}))?"
    rf"(?(m1)|(?(m2)|(?!)))(?:\s*(?:в|,)\s*(?P<t>\d{{1,2}}:\d{{2}}))?(?!\d)", re.IGNORECASE)
_ZW = re.compile(r"[\u200b\u200c\u200d\ufeff]")


def clean(text: str) -> str:
    """Whitespace-normalised text without zero-width characters."""
    return norm_ws(_ZW.sub("", text or ""))


def now_local() -> datetime:
    return datetime.now(UTC).astimezone(TZ)


def iso(dt: datetime) -> str:
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def local_dt(day: date, hhmm: str | None = None) -> datetime:
    h, m = (int(x) for x in hhmm.split(":")) if hhmm else (0, 0)
    return datetime(day.year, day.month, day.day, h, m, tzinfo=TZ)


def parse_iso(text: str | None) -> datetime | None:
    if not text:
        return None
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return None
    return dt if dt.tzinfo else dt.replace(tzinfo=TZ)


def nearest_year(day: int, month: int, today: date) -> date | None:
    """`day month` with the year (today's, +-1) that lands closest to today; None for an impossible date."""
    best: date | None = None
    for year in (today.year - 1, today.year, today.year + 1):
        try:
            cand = date(year, month, day)
        except ValueError:
            continue
        if best is None or abs((cand - today).days) < abs((best - today).days):
            best = cand
    return best


class WhenText:
    """A parsed Russian date expression: first day, last day (== first for a single date), optional HH:MM."""

    __slots__ = ("first", "last", "time")

    def __init__(self, first: date, last: date, time: str | None):
        self.first, self.last, self.time = first, last, time

    @property
    def is_range(self) -> bool:
        return self.last != self.first


def find_when(text: str, today: date) -> tuple[WhenText, int, int] | None:
    """The first date expression in `text` as (WhenText, start, end offsets); None when there is none.
    The year is not on the page: it is the one that puts the date closest to `today`; a range ends on or after its
    first day (an end earlier than the start rolls into the next year)."""
    for m in DATE_RE.finditer(text):
        m1, m2 = (m["m1"] or "").lower(), (m["m2"] or "").lower()
        month1 = MONTHS_RU[m1 or m2]
        first = nearest_year(int(m["d1"]), month1, today)
        if first is None:
            continue
        last = first
        if m["d2"]:
            last_try = nearest_year(int(m["d2"]), MONTHS_RU[m2], today)
            if last_try is None:
                continue
            last = last_try
            if last < first:
                last = nearest_year_after(int(m["d2"]), MONTHS_RU[m2], first)
                if last is None:
                    continue
        time = m["t"]
        if time and not valid_time(time):
            time = None
        return WhenText(first, last, time), m.start(), m.end()
    return None


def nearest_year_after(day: int, month: int, floor: date) -> date | None:
    for year in (floor.year, floor.year + 1):
        try:
            cand = date(year, month, day)
        except ValueError:
            continue
        if cand >= floor:
            return cand
    return None


def valid_time(hhmm: str) -> bool:
    h, _, m = hhmm.partition(":")
    return h.isdigit() and m.isdigit() and 0 <= int(h) < 24 and 0 <= int(m) < 60


def event_id(source: str, key: str) -> str:
    return f"{source}:{key}"


def short_hash(text: str) -> str:
    return sha1(text.encode("utf-8")).hexdigest()[:10]


def ev(fields: str | tuple[str, ...], url: str, snippet: str, fetched_at: str) -> list[dict]:
    """Evidence entries, one per field, sharing one verbatim snippet."""
    names = (fields,) if isinstance(fields, str) else fields
    return [evidence(f, url, snippet, fetched_at) for f in names]


def venue(name: str, *, address: str | None = None, hall: str | None = None, lat: float | None = None,
          lon: float | None = None) -> dict:
    return {"name": clean(name), "hall": clean(hall) if hall else None, "address": clean(address) if address else None,
            "lat": lat, "lon": lon, "coords_source": "page" if lat is not None else None, "poi_id": None,
            "poi_name": None, "match": None}


def make_event(source: str, key: str, *, title: str, kind: str, url: str, fetched_at: str, venue_: dict,
               evidence_: list[dict], category: str | None = None, start: datetime | None = None,
               end: datetime | None = None, date_from: date | None = None, date_to: date | None = None,
               sessions: list[datetime] | None = None, hours_raw: str | None = None, hours_osm: str | None = None,
               price_text: str | None = None, price_from: int | None = None) -> dict:
    return {
        "id": event_id(source, key), "source": source, "title": clean(title), "category": clean(category) or None
        if category else None,
        "kind": kind, "start": iso(start) if start else None, "end": iso(end) if end else None,
        "date_from": date_from.isoformat() if date_from else None,
        "date_to": date_to.isoformat() if date_to else None,
        "sessions": [iso(s) for s in sorted(sessions or [])], "hours_raw": hours_raw, "hours_osm": hours_osm,
        "price_text": clean(price_text) if price_text else None, "price_from": price_from,
        "venue": venue_, "url": url, "fetched_at": fetched_at, "also_listed": [], "evidence": evidence_,
    }


def in_astana(lat: float | None, lon: float | None) -> bool:
    return lat is not None and lon is not None and ASTANA_LAT[0] <= lat <= ASTANA_LAT[1] \
        and ASTANA_LON[0] <= lon <= ASTANA_LON[1]


_PRICE_NUM = re.compile(r"(?<![\d,.])(\d{1,3}(?: \d{3})+|\d+)\s*(?:тенге|теңге|тг|₸)", re.IGNORECASE)


def min_price(text: str) -> int | None:
    """Smallest amount followed by a tenge word / sign ('от 13 000 тенге' -> 13000; '7000 тенге (взрослый), 3500
    тенге (детский, 5-14 лет)' -> 3500); None when the text names no amount."""
    nums = [int(m[1].replace(" ", "")) for m in _PRICE_NUM.finditer(text)]
    return min(nums) if nums else None


def validate_event(e: dict) -> list[str]:
    errs: list[str] = []
    for key in ("id", "source", "title", "kind", "url", "fetched_at"):
        if not e.get(key):
            errs.append(f"{key} missing")
    kind = e.get("kind")
    if kind not in KINDS:
        errs.append(f"bad kind {kind!r}")
    if kind == "event" and parse_iso(e.get("start")) is None:
        errs.append("event without start")
    if kind == "run" and not (e.get("date_from") and e.get("date_to")):
        errs.append("run without date_from/date_to")
    if kind == "sessions" and not e.get("sessions"):
        errs.append("sessions without times")
    if kind == "standing" and not e.get("hours_osm"):
        errs.append("standing without hours_osm")
    for key in ("start", "end"):
        if e.get(key) and parse_iso(e[key]) is None:
            errs.append(f"bad {key}")
    for s in e.get("sessions") or []:
        if parse_iso(s) is None:
            errs.append(f"bad session {s!r}")
    if e.get("start") and e.get("end") and parse_iso(e["end"]) < parse_iso(e["start"]):
        errs.append("end before start")
    v = e.get("venue") or {}
    if not v.get("name"):
        errs.append("venue name missing")
    if v.get("lat") is not None and not in_astana(v.get("lat"), v.get("lon")):
        errs.append("venue coordinates outside Astana")
    if (v.get("lat") is None) != (v.get("lon") is None):
        errs.append("venue lat/lon half given")
    if v.get("lat") is not None and v.get("coords_source") not in ("page", "poi"):
        errs.append("coordinates without coords_source")
    if not e.get("evidence"):
        errs.append("no evidence")
    return errs
