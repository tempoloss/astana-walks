"""«Что происходит рядом сегодня / сейчас»: events of `data/events.json` near a point inside the user's time window.

The file is built by `collect/events` (fact-cards from sxodim.com, inastana.kz, qazaqconcert.kz, youticket.kz,
alem.ai and a public Telegram channel; every fact has a source link). This module is pure: it reads the file and
answers `events_near(lat, lon, when, ...)`; it never calls the network and does not touch the dialogue or the UI.

Rules (the display contract of the future block):

* Only events that are **on now or start within the window** `[when, when + window_min]` are returned. An event past
  its end is never returned: a timed event without an end is taken to last `DEFAULT_DURATION`; a cinema session counts
  until `LATE_ENTRY` after its start; a venue with weekly hours counts only while `hours_osm` says open (a public
  holiday downgrades it to unknown, so it is left out); a run of dates without hours («17–31 октября») counts between
  `RUN_HOURS` of each of its days.
* Order: timed events (an event, a cinema session, a venue opening within the window) by start (events already on
  count as starting at `when`), then by distance; untimed runs after them by distance.
* The block exists only when there is at least one such event: `nearby_events` returns None otherwise and the caller
  stays silent — three or four sources are not a complete afisha, so «событий нет» is never said.
* Events without coordinates cannot be placed near anyone and are not returned.
* The snapshot's `fetched_at` (the oldest source page behind the file) is reported; older than `STALE_AFTER_H` hours
  the block says so.
"""

from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path

from .hours import TZ, hours_check
from .i18n_events import event_line, heading, stale_note
from .radius import haversine_m

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "events.json"
_SUFFIX = re.compile(
    r",?\s*(?:кинотеатр\s+)?в\s+городе\s+\S+\s*$", re.IGNORECASE
)  # «…, кинотеатр в городе Астана»
STALE_AFTER_H = 36
DEFAULT_DURATION = timedelta(hours=2)  # an event whose page names no end
LATE_ENTRY = timedelta(
    minutes=20
)  # a cinema session can still be joined this long after it started
RUN_HOURS = (9, 22)  # when a run of dates without hours is taken to be on
OPEN_STEP = timedelta(
    minutes=15
)  # how finely the opening hours of a venue are scanned inside the window
DEFAULT_RADIUS_M = 1500
DEFAULT_WINDOW_MIN = 180
TIMED = ("event", "sessions", "standing")


@dataclass(frozen=True)
class EventHit:
    """One event near the user; JSON-serializable (`to_dict`). Times are ISO-8601 in Astana time (UTC+5)."""

    id: str
    title: str
    kind: str  # event | sessions | run | standing
    category: str | None
    source: str
    url: str
    venue: str
    hall: str | None
    address: str | None
    lat: float
    lon: float
    poi_id: str | None
    distance_m: int
    start: (
        str | None
    )  # the start (event), the first session in the window, the next opening (standing)
    end: str | None
    ongoing: bool
    sessions: tuple[str, ...]  # the sessions inside the window (cinema)
    until: str | None  # last day of a run (YYYY-MM-DD)
    hours_raw: str | None
    price_text: str | None
    price_from: int | None
    fetched_at: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass(frozen=True)
class Snapshot:
    events: tuple[dict, ...]
    fetched_at: str | None  # the oldest source page behind the file (UTC ISO), None when unknown
    schema: int = 1

    def age_hours(self, now: datetime) -> float | None:
        if not self.fetched_at:
            return None
        return (_aware(now) - datetime.fromisoformat(self.fetched_at)).total_seconds() / 3600

    def is_stale(self, now: datetime) -> bool:
        age = self.age_hours(now)
        return age is None or age > STALE_AFTER_H


@dataclass(frozen=True)
class NearbyEvents:
    hits: tuple[EventHit, ...]  # never empty
    fetched_at: str | None
    stale: bool

    def to_dict(self) -> dict:
        return {
            "hits": [h.to_dict() for h in self.hits],
            "fetched_at": self.fetched_at,
            "stale": self.stale,
        }


def _aware(when: datetime) -> datetime:
    return when.replace(tzinfo=TZ) if when.tzinfo is None else when.astimezone(TZ)


@lru_cache(maxsize=4)
def _load(path: str, mtime_ns: int, size: int) -> Snapshot:
    doc = json.loads(Path(path).read_text(encoding="utf-8"))
    return Snapshot(tuple(doc.get("events", [])), doc.get("fetched_at"), int(doc.get("schema", 1)))


def load_snapshot(path: str | Path | None = None) -> Snapshot:
    """The events file (an empty snapshot when it does not exist); re-read when the file changes."""
    p = Path(path) if path else DEFAULT_PATH
    try:
        st = p.stat()
        return _load(str(p), st.st_mtime_ns, st.st_size)
    except (OSError, ValueError):
        return Snapshot((), None)


def _iso(dt: datetime) -> str:
    return dt.astimezone(TZ).isoformat(timespec="seconds")


def _dt(text: str) -> datetime:
    return _aware(datetime.fromisoformat(text))


def _day_window(day: date, hours: tuple[int, int]) -> tuple[datetime, datetime]:
    return (
        datetime(day.year, day.month, day.day, hours[0], tzinfo=TZ),
        datetime(day.year, day.month, day.day, hours[1], tzinfo=TZ),
    )


def _occurrence(e: dict, when: datetime, until: datetime) -> dict | None:
    """What of event `e` is on in [when, until]: {start, end, ongoing, sessions, until_day} or None (past / later)."""
    kind = e["kind"]
    if kind == "event":
        start = _dt(e["start"])
        end = _dt(e["end"]) if e.get("end") else start + DEFAULT_DURATION
        if end <= when or start > until:
            return None
        return {"start": start, "end": end, "ongoing": start <= when}
    if kind == "sessions":
        inside = sorted(s for s in map(_dt, e["sessions"]) if s + LATE_ENTRY > when and s <= until)
        if not inside:
            return None
        return {
            "start": inside[0],
            "end": None,
            "ongoing": inside[0] <= when,
            "sessions": tuple(map(_iso, inside)),
        }
    if kind == "run":
        first, last = date.fromisoformat(e["date_from"]), date.fromisoformat(e["date_to"])
        day = max(first, when.date())
        while day <= min(last, until.date()):
            lo, hi = _day_window(day, RUN_HOURS)
            if hi > when and lo <= until:
                return {"start": None, "end": None, "ongoing": True, "until_day": e["date_to"]}
            day += timedelta(days=1)
        return None
    t = when
    while t <= until:
        if hours_check(e.get("hours_osm"), t)[0] == "open":
            return {"start": t, "end": None, "ongoing": t == when}
        t += OPEN_STEP
    return None


def events_near(
    lat: float,
    lon: float,
    when: datetime,
    radius_m: int = DEFAULT_RADIUS_M,
    limit: int = 5,
    window_min: int = DEFAULT_WINDOW_MIN,
    snapshot: Snapshot | None = None,
) -> list[EventHit]:
    """Events within `radius_m` that are on at `when` or start within `window_min` minutes after it (see the module
    docstring for the order). `when` without a zone is Astana local time."""
    snap = snapshot if snapshot is not None else load_snapshot()
    when = _aware(when)
    until = when + timedelta(minutes=window_min)
    found: list[tuple[tuple, EventHit]] = []
    for e in snap.events:
        v = e["venue"]
        if v.get("lat") is None:
            continue
        dist = round(haversine_m(lat, lon, v["lat"], v["lon"]))
        if dist > radius_m:
            continue
        occ = _occurrence(e, when, until)
        if occ is None:
            continue
        start = occ["start"]
        hit = EventHit(
            id=e["id"],
            title=e["title"],
            kind=e["kind"],
            category=e.get("category"),
            source=e["source"],
            url=e["url"],
            venue=_SUFFIX.sub("", v["name"]).strip(),
            hall=v.get("hall"),
            address=v.get("address"),
            lat=v["lat"],
            lon=v["lon"],
            poi_id=v.get("poi_id"),
            distance_m=dist,
            start=_iso(start) if start else None,
            end=_iso(occ["end"]) if occ.get("end") else None,
            ongoing=occ["ongoing"],
            sessions=occ.get("sessions", ()),
            until=occ.get("until_day"),
            hours_raw=e.get("hours_raw"),
            price_text=e.get("price_text"),
            price_from=e.get("price_from"),
            fetched_at=e["fetched_at"],
        )
        key = (
            (0, max(start, when), dist, e["id"])
            if e["kind"] in TIMED and start
            else (1, when, dist, e["id"])
        )
        found.append((key, hit))
    found.sort(key=lambda kv: kv[0])
    return [h for _, h in found[:limit]]


def nearby_events(
    lat: float,
    lon: float,
    when: datetime,
    radius_m: int = DEFAULT_RADIUS_M,
    limit: int = 5,
    window_min: int = DEFAULT_WINDOW_MIN,
    snapshot: Snapshot | None = None,
) -> NearbyEvents | None:
    """The «сегодня рядом» block, or None — then the caller shows nothing (never «событий нет»)."""
    snap = snapshot if snapshot is not None else load_snapshot()
    hits = events_near(lat, lon, when, radius_m, limit, window_min, snap)
    if not hits:
        return None
    return NearbyEvents(tuple(hits), snap.fetched_at, snap.is_stale(when))


def format_block(near: NearbyEvents, lang: str, when: datetime) -> list[str]:
    """Lines of the block: the heading, one line per event, the stale note when the snapshot is old."""
    local = _aware(when)
    lines = [heading(lang) + ":"] + [f"  • {event_line(h, lang, local)}" for h in near.hits]
    if near.stale and near.fetched_at:
        lines.append("  " + stale_note(near.fetched_at, lang))
    return lines
