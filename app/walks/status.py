"""The status of a place in words («Открыто до 22:00», «Закрыто, откроется в 10:00», «Открыто круглосуточно») is
written here and nowhere else: the state is the record's own at the moment the card describes, and the change time is
the next one of the same schedule from the same moment. A state computed for one moment (the arrival) and a change
time for another (the departure) once gave «Открыто до 10:00» at 03:10 for a place open 10:00–21:00. The model gets
this string ready (walks.facts) and may not write a status of its own (walks.specific)."""

from __future__ import annotations

from datetime import datetime, timedelta

from opening_hours import OpeningHours

from .dialog_strings import s
from .hours import is_24_7, poi_hours, to_local_naive
from .models import POI

UNTIL_NEAR = timedelta(
    hours=20
)  # «до 22:00» only when the change is this near; farther it is plain «открыто»
NEXT_DAY_AFTER = timedelta(
    hours=12
)  # a close after midnight this far ahead is said with its day («до 05:00 следующего дня» at 13:00)
TEXT_KEY = {
    "247": "h_open_247",
    "until": "h_open_until",
    "open": "h_open",
    "opens": "h_closed_opens",
    "closed": "h_closed",
    "unknown": "h_unknown",
}


def next_change(poi: POI, local: datetime) -> datetime | None:
    raw = poi.opening_hours
    if not raw or not raw.strip():
        return None
    try:
        return OpeningHours(raw).next_change(local)
    except (ValueError, OverflowError, TypeError):
        return None


def when_text(moment: datetime, local: datetime, lang: str) -> str:
    """«в 10:00» today, «завтра в 10:00» the next day; '' farther away."""
    day = (moment.date() - local.date()).days
    if day == 0:
        return s("h_at", lang, t=f"{moment:%H:%M}")
    if day == 1:
        return s("h_tomorrow", lang, t=f"{moment:%H:%M}")
    return ""


def hours_facts(poi: POI, state: str, at: datetime, lang: str) -> tuple[str, str]:
    """(what the hours say at `at`, its time phrase): 247 / until «22:00» / open / opens «в 10:00» / closed / unknown.
    `state` only says whether the record's hours are known; the state itself is read again at `at`, so the state and
    the change time always describe the same moment."""
    if state == "unknown":
        return "unknown", ""
    local = to_local_naive(at)
    actual = poi_hours(poi, local).state
    if actual == "unknown":
        return "unknown", ""
    nxt = next_change(poi, local)
    if actual == "open":
        if is_24_7(poi.opening_hours):
            return "247", ""
        if nxt is not None and nxt - local < UNTIL_NEAR:
            until = f"{nxt:%H:%M}"
            if nxt.date() > local.date() and nxt - local > NEXT_DAY_AFTER:
                until = s("h_next_day", lang, t=until)  # an overnight close belongs to the next day
            return "until", until
        return "open", ""
    when = when_text(nxt, local, lang) if nxt is not None else ""
    return ("opens", when) if when else ("closed", "")


def status_text(poi: POI, state: str, at: datetime, lang: str) -> str:
    """The card's status line at `at` («Открыто до 22:00»): the only status wording an answer may carry."""
    kind, when = hours_facts(poi, state, at, lang)
    return s(TEXT_KEY[kind], lang, t=when)
