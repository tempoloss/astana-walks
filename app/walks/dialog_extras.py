"""The extra lines of an answer, each from a layer outside the dialogue's own data and each silent when the layer has
nothing to say: the «Сегодня рядом» block of the afisha, a Kazhydromet warning or the station's adverse weather, the
last airport bus, an open OpenStreetMap note about a place, the nearest bus stop, the street lights along a route.

Pure post-processing of a finished search: nothing here reaches the model's prompt or its payload, so the recorded
answers of the demo are untouched. A missing file or an empty radius is «no line», never a statement about the world.
"""

from __future__ import annotations

import re
from datetime import datetime
from itertools import pairwise

from . import gov_hours, mobility
from .city_layers import MEANINGFUL_SHARE, lit_share, signals_for_poi
from .dialog_types import EventItem, EventsBlock, Notice, Place, Signal, Source, Stop
from .events import DEFAULT_RADIUS_M, DEFAULT_WINDOW_MIN, load_snapshot, nearby_events
from .hours import to_local_naive
from .i18n_afisha import ta
from .i18n_events import (
    SOURCE_LABELS,
    event_text,
    price_part,
    source_label,
    stale_note,
    venue_part,
    when_part,
)
from .i18n_events import heading as events_heading
from .i18n_gov import gt
from .i18n_notices import MONTHS_OF, tn
from .i18n_signals import ts
from .models import POI, WeatherInfo, WeatherWarning
from .sun import is_dark
from .walking import WalkingRouter

EVENTS_SHOWN = 2  # the block under a search
SCAN = 50  # events looked at before a kind is picked out of them
MAX_WARNING_CHARS = 160
NOTE_KINDS = ("closure", "hours")
MAX_STOP_M = 500  # a stop farther than this is not «the nearest stop» worth a line
STOPS_RANKED = 8  # stops looked at before the two directions of one stop are merged
GTFS_URL = "https://zenodo.org/records/15769359"
LAST_BUS_LEAD_MIN = 240  # the last airport bus is worth a line from this long before it leaves
MOSTLY_LIT = 0.5  # share of the way along lit streets for «большая часть пути»
TO_AIRPORT = "города в аэропорт"


# ------------------------------------------------------------------ afisha


def afisha_sources(lang: str) -> str:
    """The sources behind the afisha file, by name: «Sxodim, InAstana, YouTicket»."""
    seen = {e.get("source") for e in load_snapshot().events}
    named = [source_label(s) for s in SOURCE_LABELS if s in seen]
    named += [source_label(s) for s in sorted(seen - set(SOURCE_LABELS)) if s]
    return ", ".join(named or SOURCE_LABELS.values())


def events_block(
    lat: float,
    lon: float,
    when: datetime,
    lang: str,
    *,
    limit: int = EVENTS_SHOWN,
    radius_m: int = DEFAULT_RADIUS_M,
    window_min: int = DEFAULT_WINDOW_MIN,
    coverage: bool = False,
    only_kind: str | None = None,
) -> EventsBlock | None:
    """«Сегодня рядом»: the events near the point on now or starting inside the window, each with its source link;
    None when there are none (the caller stays silent). `coverage` adds the note that the afisha is only a few sources;
    `only_kind` keeps one kind of listing («sessions» = the cinema)."""
    local = to_local_naive(when)
    near = nearby_events(
        lat, lon, local, radius_m, limit if only_kind is None else SCAN, window_min
    )
    hits = (
        [h for h in near.hits if only_kind is None or h.kind == only_kind][:limit] if near else []
    )
    if near is None or not hits:
        return None
    items = [
        EventItem(
            title=h.title,
            when=when_part(h, lang, local),
            venue=venue_part(h),
            distance_m=h.distance_m,
            price=price_part(h, lang),
            text=event_text(h, lang, local),
            source=Source(label=source_label(h.source), url=h.url),
        )
        for h in hits
    ]
    notes = [ta("coverage", lang, sources=afisha_sources(lang))] if coverage else []
    if near.stale and near.fetched_at:
        notes.append(stale_note(near.fetched_at, lang))
    return EventsBlock(heading=events_heading(lang), items=items, note=" ".join(notes))


# ------------------------------------------------------------------ weather


def _short(text: str) -> str:
    text = " ".join(text.split()).rstrip(" .")
    if len(text) <= MAX_WARNING_CHARS:
        return text
    return text[:MAX_WARNING_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"


_ASTANA = re.compile(r"Астан|Нур-Султан", re.IGNORECASE)
_SENTENCE = re.compile(r"(?<=[.;!?])\s+")
_CITY_PREFIX = re.compile(
    r"^(?:г\.\s*|город\s+)?(?:Астана|Астане|Нур-Султан)\s*[:,—-]\s*", re.IGNORECASE
)


def _storm_text(w: WeatherWarning) -> str:
    """The storm warning shortened to what it says about Astana: the sentences that name the city, else its title."""
    own = [s for s in _SENTENCE.split(" ".join(w.text.split())) if _ASTANA.search(s)]
    # «Астана: 19 октября ночью и утром ожидается туман»: the city is already in the heading, say it once
    text = _CITY_PREFIX.sub("", " ".join(own) or w.title)
    return _short(text)


def _day_of(w: WeatherWarning, lang: str) -> str:
    """«18 октября»: the day the notice is valid from (the bulletin's own day)."""
    start = datetime.fromisoformat(w.valid_from)
    return f"{start.day} {MONTHS_OF.get(lang, MONTHS_OF['ru'])[start.month - 1]}"


def weather_notice(weather: WeatherInfo | None, lang: str) -> Notice | None:
    """An active official Kazhydromet notice about Astana, short, with the link to its page. What the weather is now
    is part of the answer's lead sentence, not a notice; a notice that is not about Astana is never shown (the НМУ
    bulletin names several cities: only Astana's day is kept)."""
    if weather is None:
        return None
    active = [w for w in weather.warnings if w.active]
    if not active:
        return None
    w = active[0]
    if w.kind == "storm":
        text = tn("wx_warn_storm", lang, text=_storm_text(w))
    elif _ASTANA.search(f"{w.title} {w.text}"):
        text = tn("wx_warn_nmu", lang, day=_day_of(w, lang))
    else:
        return None
    return Notice(
        kind="weather",
        text=text,
        source=Source(label=tn("wx_src", lang), url=w.source_url),
        detail=w.title,
    )


# ------------------------------------------------------------------ the airport bus


def _minutes(hhmm: str) -> int:
    hour, minute = hhmm.split(":")
    return int(hour) * 60 + int(minute)


def _hhmm(hhmm: str) -> str:
    return f"{_minutes(hhmm) // 60:02d}:{_minutes(hhmm) % 60:02d}"


def airport_routes(info: mobility.AirportBusInfo) -> list[dict]:
    return [r for r in info.routes if r.get("direction") == TO_AIRPORT]


def airport_notice(when: datetime, lang: str, *, asked: bool = False) -> Notice | None:
    """The last bus to the airport (nn-airport.kz) when it is worth saying at this time: the evening before it leaves
    («последний № 10 в аэропорт — 21:23»), once it has left, or before the first one runs. `asked`: the user wants
    exactly this, so it is said at any hour."""
    info = mobility.airport_bus(when)
    routes = airport_routes(info) if info else []
    if info is None or not routes:
        return None
    last = max(routes, key=lambda r: _minutes(r["last_departure"]))
    first = min(routes, key=lambda r: _minutes(r["first_departure"]))
    now = when.hour * 60 + when.minute
    stamp = {"route": last["route"], "time": _hhmm(last["last_departure"])}
    if now > _minutes(last["last_departure"]):
        text = tn("ap_gone", lang, **stamp)
    elif asked or now >= _minutes(last["last_departure"]) - LAST_BUS_LEAD_MIN:
        text = tn("ap_last", lang, **stamp)
    elif now < _minutes(first["first_departure"]):
        text = tn("ap_first", lang, route=first["route"], time=_hhmm(first["first_departure"]))
    else:
        return None
    return Notice(
        kind="airport",
        text=text,
        source=Source(label="nn-airport.kz", url=info.source_url),
        detail=tn("ap_detail", lang, date=info.fetched_at) if info.fetched_at else "",
    )


# ------------------------------------------------------------------ a card


def _day(iso: str | None) -> str:
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}" if iso and len(iso) >= 10 else ""


def note_signal(poi: POI, lang: str) -> Signal | None:
    """The open OpenStreetMap note about this place that says it may have closed (or changed its hours): the line and
    the link to the note. A closure outranks an hours note; the nearest note of that kind wins."""
    notes = [n for n in signals_for_poi(poi) if n.classification in NOTE_KINDS]
    if not notes:
        return None
    note = min(notes, key=lambda n: (n.classification != "closure", n.distance_m))
    key = "note_closure" if note.classification == "closure" else "note_hours"
    date = _day(note.date_created)
    text = ts(key, lang, date=date).replace(" ()", "")
    return Signal(
        kind="osm_note",
        text=text,
        source=Source(label=ts("note_source", lang), url=note.url),
        date=note.date_created,
    )


def near_stop(lat: float, lon: float, lang: str) -> Stop | None:
    """The nearest bus stop with its walking minutes. The two directions of a stop are two records of one name: one
    stop. None when the data is missing or no stop is within `MAX_STOP_M`."""
    seen: set[str] = set()
    stops = []
    for s in sorted(mobility.nearest_stops(lat, lon, STOPS_RANKED), key=lambda s: s.distance_m):
        if s.name and s.name not in seen:
            seen.add(s.name)
            stops.append(s)
    if not stops or stops[0].distance_m > MAX_STOP_M:
        return None
    s = stops[0]
    return Stop(
        name=s.name or "",
        minutes=s.walk_min,
        distance_m=s.distance_m,
        text=ts("stop_line", lang, name=s.name, n=s.walk_min),
        source=Source(label=ts("stop_source", lang), url=GTFS_URL),
    )


def gov_signal(poi: POI, when: datetime, lang: str) -> Signal | None:
    """The one schedule line of a ЦОН card for the day `when` falls on («сб: 09:00-13:00; по данным gov4c.kz»), with the
    operator's page as its source; None for any other place (a sports object's administration hours are never a card
    line: they answer only a question about its hours)."""
    if not poi.is_state_service():
        return None
    g = gov_hours.gov_hours(poi.model_dump(), when, lang)
    return Signal(
        kind="state_registry",
        text=g.line,
        source=Source(label=gt("src_gov", lang), url=g.url),
        date=g.snapshot_date,
    )


def decorate(place: Place, poi: POI, lang: str, when: datetime | None = None) -> bool:
    """Adds the card's one signal line (an open OpenStreetMap note, else the schedule of a ЦОН for the day of `when`) and
    the nearest stop; True when the note is there."""
    place.signal = note_signal(poi, lang) or (gov_signal(poi, when, lang) if when else None)
    place.stop = near_stop(place.lat, place.lon, lang)
    return place.signal is not None and place.signal.kind == "osm_note"


# ------------------------------------------------------------------ a route


def lighting_line(
    origin: tuple[float, float],
    stops: list[tuple[float, float]],
    router: WalkingRouter,
    when: datetime,
    weather: WeatherInfo | None,
    lang: str,
) -> str:
    """After dark: «большая часть пути по освещённым улицам — по данным OpenStreetMap», only when the street lines of
    every leg are known and most of the way runs along ways tagged lit. Streets with no tag are unknown, never dark,
    so there is no line about unlit streets."""
    if not stops or not is_dark(weather or WeatherInfo(), to_local_naive(when)):
        return ""
    points = [origin, *stops]
    way: list[tuple[float, float]] = []
    for a, b in pairwise(points):
        leg = router.shape(a, b)
        if not leg:
            return ""
        way += leg
    share = lit_share(way)
    if share is None or share.known_share < MEANINGFUL_SHARE or share.lit_yes < MOSTLY_LIT:
        return ""
    return ts("lit_most", lang)
