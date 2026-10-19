"""Opening-hours state of a place (an OSM-syntax `opening_hours` string, in Astana local time)."""

from __future__ import annotations

import re
from datetime import datetime
from typing import NamedTuple
from zoneinfo import ZoneInfo

from opening_hours import OpeningHours, ParserError, State

from .holidays import holiday_name
from .models import POI, HoursIssue, HoursState

TZ = ZoneInfo("Asia/Almaty")  # Astana has used this zone since March 2024 (UTC+5)

# Constructs whose result we cannot compute without extra data (location, free-text rules).
_UNTRUSTED = ("||", "sunrise", "sunset", "dawn", "dusk", "easter", "week ", "unknown")
# «Mo-Su 09:00-09:00» (Почта №17): opens and closes at the same minute, a slip of the record, not a day and a night;
# «00:00-00:00» stays the whole day, the way mappers write it
_SAME_MINUTE = re.compile(r"\b(?!00:00)(\d\d:\d\d)-\1\b")


def local_now() -> datetime:
    return datetime.now(TZ).replace(tzinfo=None)


def to_local_naive(when: datetime) -> datetime:
    """Naive datetime expressed in Astana local time (what opening_hours expects)."""
    if when.tzinfo is None:
        return when
    return when.astimezone(TZ).replace(tzinfo=None)


def _plain_state(raw: str | None, local: datetime) -> HoursState:
    """open / closed / unknown for the string at the local time, holidays not considered."""
    if not raw or not raw.strip():
        return "unknown"
    low = raw.lower()
    if any(m in low for m in _UNTRUSTED) or _SAME_MINUTE.search(low):
        return "unknown"
    try:
        state, _comment = OpeningHours(raw).state(local)
    except (ParserError, ValueError, OverflowError):
        return "unknown"
    return {State.CLOSED: "closed", State.OPEN: "open"}.get(state, "unknown")


_ALL_DAY = re.compile(r"(?:mo-su\s+)?00:00-24:00", re.IGNORECASE)


def is_24_7(raw: str | None) -> bool:
    """«24/7», and «Mo-Su 00:00-24:00» (every day, the whole day), the two ways a record says «round the clock»."""
    text = (raw or "").strip()
    return text == "24/7" or bool(_ALL_DAY.fullmatch(text))


def _with_holiday(raw: str, state: HoursState, local: datetime) -> tuple[HoursState, str]:
    """`open` on a public holiday becomes `unknown` with the note «праздник: <name>» (the string describes ordinary
    days); the exact string «24/7» stays `open`, with the same note."""
    if state != "open":
        return state, ""
    holiday = holiday_name(local.date())
    if not holiday:
        return "open", ""
    return ("open" if is_24_7(raw) else "unknown"), f"праздник: {holiday}"


def hours_check(raw: str | None, when: datetime) -> tuple[HoursState, str]:
    """(state, note). state is open / closed / unknown; missing or unparsable data is always `unknown`, never
    `open`. On a public holiday an `open` state is downgraded to `unknown` with note "праздник: <name>" because
    OSM hours describe ordinary days; `closed` stays `closed`. The exact string «24/7» is the one exception: it
    stays `open` (the note «праздник: …» still says the hours may differ that day)."""
    local = to_local_naive(when)
    return _with_holiday(raw or "", _plain_state(raw, local), local)


class PoiHours(NamedTuple):
    state: HoursState
    note: str  # «праздник: <name>» or ""
    issue: HoursIssue  # why the card has to say more than the state (see models.HoursIssue)


def poi_hours(poi: POI, when: datetime) -> PoiHours:
    """The hours verdict of a place from everything its record says (`opening_hours` of OSM or of the business's
    own website, and the website's other statements):

    * the hours the record carries decide, as in `hours_check`;
    * both OSM and the website name hours and the weekly schedules differ (`hours_conflict`): the card keeps the OSM
      verdict and says the sources differ (issue `conflict`); when at this moment one says open and the other
      closed, the state is `unknown` (issue `split`), never `open`;
    * no hours but the website names some without days (`hours_unqualified`): `unknown`, issue `unqualified`."""
    local = to_local_naive(when)
    raw = poi.opening_hours
    if not raw or not raw.strip():
        return PoiHours("unknown", "", "unqualified" if poi.hours_unqualified else "")
    plain = _plain_state(raw, local)
    state, note = _with_holiday(raw, plain, local)
    if not (poi.hours_conflict and poi.opening_hours_official):
        return PoiHours(state, note, "")
    site = _plain_state(poi.opening_hours_official, local)
    if {plain, site} == {"open", "closed"}:
        return PoiHours("unknown", "", "split")
    return PoiHours(state, note, "conflict")


def hours_state(raw: str | None, when: datetime) -> HoursState:
    return hours_check(raw, when)[0]
