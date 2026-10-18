"""Hours of state objects for citizens (ЦОН branches, register № 730 sports objects): a pure, JSON-serialisable API over
the records of `data/poi.enriched.json` that `collect/gov` wrote (`source: state_registry`).

It works on the raw JSON dicts, not on `models.POI`: the POI model ignores `admin_hours` / `state_registry_match`.

Scope is the point of the layer. `venue` hours (a ЦОН window) say whether the place is open on a day. `administration`
hours (register № 730 `rrr`) are the office week of the managing body: they never answer «открыто ли», the line says so.
Missing hours are «данных нет», never «закрыто».

    objs = lookup(load_dataset(), when, kind="cson", near=(51.09, 71.42))   # [GovHours] -> asdict() -> JSON
    card_line(poi_dict, when, "ru")    # at most one short line for a card, None when the layer has nothing to say
"""

from __future__ import annotations

import json
import math
import re
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from pathlib import Path

from opening_hours import OpeningHours, ParserError, State

from .hours import hours_check, local_now, to_local_naive
from .i18n_gov import (
    KIND_STEMS,
    SOURCES,
    TODAY_STEMS,
    TOMORROW_STEMS,
    WEEKDAY_STEMS,
    gt,
    weekday_label,
    weekday_on,
)
from .lexicon import match, normalize

DATASET_PATH = Path(__file__).resolve().parents[2] / "data" / "poi.enriched.json"
SOURCE = "state_registry"
DEFAULT_HOUR = 10  # the time of day a «ЦОН в субботу» question is evaluated at


@dataclass(frozen=True)
class GovHours:
    poi_id: str
    name: str
    kind: str  # cson | sport_facility
    address: str | None
    lat: float
    lon: float
    scope: str | None  # venue | administration | None (no hours in the record)
    state: str  # open | closed | unknown, at `when`; always unknown for scope administration
    hours: str | None  # OSM string (venue) or the printed administration schedule
    day: str  # the asked day, e.g. «сб»
    day_open: bool | None  # open at some time that day (venue hours only)
    day_text: str | None  # «09:00-13:00»
    note: str | None  # second schedule (e.g. «Выдача: ...»), holiday hint
    source: str | None
    url: str | None
    snapshot_date: str | None
    distance_m: int | None
    line: str


def load_dataset(path: Path | None = None) -> list[dict]:
    return json.loads((path or DATASET_PATH).read_text(encoding="utf-8"))


def kind_of(p: dict) -> str | None:
    match = p.get("state_registry_match")
    return match.get("kind") if match and SOURCE in (p.get("sources") or []) else None


def state_objects(pois: list[dict], kind: str | None = None) -> list[dict]:
    return [p for p in pois if (k := kind_of(p)) and (kind is None or k == kind)]


def day_intervals(raw: str | None, day: date) -> list[tuple[str, str]]:
    """The open intervals of `day` under the OSM string, as ('09:00', '13:00') pairs; [] = closed that day or no data."""
    if not raw:
        return []
    try:
        oh = OpeningHours(raw)
        start = datetime(day.year, day.month, day.day)
        spans = oh.intervals(start, start + timedelta(days=1))
    except (ParserError, ValueError):
        return []
    out = []
    for a, b, state, _ in spans:
        if state == State.OPEN:
            end = "24:00" if b >= start + timedelta(days=1) else b.strftime("%H:%M")
            out.append((a.strftime("%H:%M"), end))
    return out


def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    a = (
        math.sin((p2 - p1) / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(math.radians(lon2 - lon1) / 2) ** 2
    )
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


def _source(p: dict, field: str) -> dict:
    s = (p.get("field_sources") or {}).get(field) or {}
    return s if s.get("source") == SOURCE else {}


def gov_hours(
    p: dict, when: datetime, lang: str | None = "ru", near: tuple[float, float] | None = None
) -> GovHours:
    """The hours verdict of one state object at `when` (Astana local time) with the one-line wording."""
    local = to_local_naive(when)
    kind = kind_of(p) or "cson"
    match = p.get("state_registry_match") or {}
    day = weekday_label(local.weekday(), lang)
    admin = p.get("admin_hours")
    raw = p.get("opening_hours") if _source(p, "opening_hours") else None
    state, scope, hours, day_open, day_text, note = "unknown", None, None, None, None, None
    if raw:
        scope, hours = "venue", raw
        state, holiday = hours_check(raw, local)
        spans = day_intervals(raw, local.date())
        day_open = bool(spans)
        day_text = ", ".join(f"{a}-{b}" for a, b in spans) or None
        note = gt("gov_holiday", lang) if holiday else None
    elif admin:
        scope, hours = "administration", admin.get("raw")
    elif p.get("hours_unqualified") and _source(p, "hours_unqualified"):
        hours = p["hours_unqualified"]
    src = _source(p, "opening_hours") or _source(p, "admin_hours") or _source(p, "name")
    if scope == "venue":
        line = (
            gt("gov_day_open", lang, day=day, hours=day_text)
            if day_open
            else gt("gov_day_closed", lang, day=day)
        )
    elif scope == "administration":
        line = gt("gov_admin", lang, hours=hours)
    elif hours:
        line = gt("gov_unqualified", lang, hours=hours)
    else:
        line = gt("gov_unknown", lang)
    snap = src.get("snapshot_date")
    line += "; " + gt(
        "gov_source", lang, source=SOURCES.get(match.get("source") or "", match.get("source") or "")
    )
    dist = round(_haversine_m(near[0], near[1], p["lat"], p["lon"])) if near else None
    return GovHours(
        p["id"],
        p["name"],
        kind,
        p.get("address"),
        p["lat"],
        p["lon"],
        scope,
        state,
        hours,
        day,
        day_open,
        day_text,
        note,
        match.get("source"),
        src.get("url") or match.get("url"),
        snap,
        dist,
        line,
    )


def lookup(
    pois: list[dict],
    when: datetime,
    *,
    kind: str | None = "cson",
    near: tuple[float, float] | None = None,
    limit: int = 5,
    lang: str | None = "ru",
    open_that_day: bool = False,
) -> list[GovHours]:
    """State objects of `kind` with their hours verdict at `when`: open that day first, then the nearest (or by name).
    `open_that_day` keeps only the venues whose schedule opens that day."""
    rows = [gov_hours(p, when, lang, near) for p in state_objects(pois, kind)]
    if open_that_day:
        rows = [r for r in rows if r.day_open]
    rows.sort(
        key=lambda r: (not r.day_open, r.distance_m if r.distance_m is not None else 0, r.name)
    )
    return rows[:limit]


def card_line(p: dict, when: datetime, lang: str | None = "ru") -> str | None:
    """The one short line a card of a state object adds; None for any other POI."""
    return gov_hours(p, when, lang).line if kind_of(p) else None


# ---- the question: «ЦОН в субботу» ---------------------------------------------------------------------------


def _has(text: str, stem: str) -> bool:
    stem = normalize(stem)
    return re.search(rf"\b{re.escape(stem)}" + (r"\b" if len(stem) <= 3 else ""), text) is not None


def parse_query(q: str) -> tuple[str | None, int | None]:
    """(kind, weekday index 0..6 or None; -1 today, -2 tomorrow are resolved by `target_date`) of a short question.
    Kazakh letters are read as their Russian look-alikes on both sides («жұма» = «жума»)."""
    low = normalize(q)
    kind = next(
        (k for k, stems in KIND_STEMS.items() if any(normalize(s) in low for s in stems)), None
    )
    for i, stems in enumerate(WEEKDAY_STEMS):
        if any(_has(low, s) for s in stems):
            return kind, i
    if any(_has(low, s) for s in TOMORROW_STEMS):
        return kind, -2
    return kind, -1 if any(_has(low, s) for s in TODAY_STEMS) else None


def target_date(weekday: int | None, now: datetime) -> datetime:
    """The next day with this weekday (today counts) at DEFAULT_HOUR; no weekday: `now` itself."""
    if weekday is None or weekday == -1:
        return now
    if weekday == -2:
        return (now + timedelta(days=1)).replace(
            hour=DEFAULT_HOUR, minute=0, second=0, microsecond=0
        )
    ahead = (weekday - now.weekday()) % 7
    return (now + timedelta(days=ahead)).replace(
        hour=DEFAULT_HOUR, minute=0, second=0, microsecond=0
    )


# ---- the dialogue: «ЦОН в субботу работает?» ---------------------------------------------------------------

NOW = "now"
TOMORROW = "tomorrow"


def is_state_request(text: str) -> bool:
    """The message explicitly asks for a state service point («ЦОН», «госуслуги», «справку получить», kk / en alike):
    the only request the ЦОН records answer."""
    return match(text).has("state_service")


def request_when(text: str, now: datetime) -> tuple[datetime, str | int]:
    """(the moment to look at, how the answer names it): a weekday ahead is that day at DEFAULT_HOUR («сб»); the
    weekday of today, «сегодня» and no day at all are `now` (NOW); «завтра» is tomorrow at DEFAULT_HOUR."""
    weekday = parse_query(text)[1]
    if weekday is None or weekday == -1 or weekday == now.weekday():
        return now, NOW
    return target_date(weekday, now), (TOMORROW if weekday == -2 else weekday)


def day_phrase(day: str | int, lang: str | None) -> str:
    """«сейчас» / «завтра» / «в субботу»."""
    if day == NOW:
        return gt("gov_now", lang)
    return gt("gov_tomorrow", lang) if day == TOMORROW else weekday_on(int(day), lang)


def reply_text(
    row: dict | None, name: str, when: datetime, day: str | int, lang: str | None
) -> str:
    """The one sentence of the answer to a state-service request: the nearest branch's interval of that day and its
    source, or that no branch works then (by the data); '' when the branch has no day-qualified schedule."""
    if row is None:
        return gt("gov_reply_none", lang, day=day_phrase(day, lang))
    g = gov_hours(row, when, lang)
    if not g.day_text:
        return ""
    iv = g.day_text.replace("-", "–")
    return gt(
        "gov_reply_open", lang, name=name, day=day_phrase(day, lang), iv=iv, src=gt("src_gov", lang)
    )


def unmapped_count(kind: str, path: Path | None = None) -> int | None:
    """How many ЦОН records have no coordinates (kept in data/gov, absent from the dataset); None for other kinds (sport
    records only attach to existing POIs) and when the build stats are not next to the dataset."""
    stats = (path or DATASET_PATH).parent / "poi_enriched_stats.json"
    if kind != "cson" or not stats.exists():
        return None
    reg = json.loads(stats.read_text(encoding="utf-8")).get("state_registry")
    return sum(1 for r in reg["unmapped_records"] if r["kind"] == kind) if reg else None


def run_cli(
    kind_arg: str,
    q: str | None,
    lat: float | None,
    lon: float | None,
    when: datetime | None,
    path: Path | None = None,
    lang: str = "ru",
) -> list[str]:
    """Lines printed by `walks.cli --gov-hours`: the question's kind / weekday decide, the flag's kind is the default."""
    pois = load_dataset(path)
    q_kind, weekday = parse_query(q or "")
    kind = q_kind or ("sport_facility" if kind_arg == "sport" else "cson")
    at = when if when is not None and weekday is None else target_date(weekday, when or local_now())
    near = (lat, lon) if lat is not None and lon is not None else None
    rows = lookup(pois, at, kind=kind, near=near, limit=50, lang=lang)
    total_kind = len(state_objects(pois, kind))
    out = [f"{gt('gov_kind_' + kind, lang)}: {len(rows)} в данных, на {at:%Y-%m-%d %H:%M} (Астана)"]
    for r in rows:
        dist = f", {r.distance_m} м" if r.distance_m is not None else ""
        out.append(
            f"- {r.name} [{r.poi_id}] {r.address or ''}{dist}\n    {r.line}"
            + (f"; {r.note}" if r.note else "")
        )
    if not rows:
        out.append(gt("gov_none", lang))
    out.append(f"Всего в наборе объектов этого вида: {total_kind}")
    if (unmapped := unmapped_count(kind, path)) is not None:
        out.append(gt("gov_unmapped", lang, n=unmapped))
    return out


def to_json(rows: list[GovHours]) -> list[dict]:
    return [asdict(r) for r in rows]
