"""Questions the dialogue answers from a layer instead of searching for places: the afisha («что сегодня интересного»,
«концерт вечером», «кино сегодня», «афиша») and the airport bus («как добраться до аэропорта», «последний
автобус»), in Kazakh, Russian and English; and the words that make the airport bus worth a line under a search
(аэропорт, вылет, рейс, вокзал, поезд). Rules only: every sentence comes from the data or is «данных нет»."""

from __future__ import annotations

import re
from datetime import datetime, timedelta
from typing import Literal, NamedTuple

from . import mobility
from .dialog_extras import afisha_sources, airport_notice, airport_routes, events_block
from .dialog_types import EventsBlock, Notice
from .events import load_snapshot
from .i18n_afisha import ta
from .i18n_notices import tn

AskKind = Literal["events", "airport"]
MIN_WINDOW_MIN = 180
MAX_WINDOW_MIN = 960
AFISHA_RADIUS_M = 3000
AFISHA_SHOWN = 3
EVENING_FROM = 18

_EVENTS = re.compile(
    r"афиш|концерт|спектакл|мероприят|событи|іс-шара"
    r"|\bafisha\b|\bconcerts?\b|\bgigs?\b|\bevents?\b|what'?s on\b|what is on\b",
    re.IGNORECASE,
)
_WHAT_ON = re.compile(  # a vague «what is interesting» is about the afisha only with a time in it
    r"что (?:сегодня |сейчас )?(?:интересн|происход|идёт|идет)|что интересного"
    r"|не қызық|қызықты не бар"
    r"|what'?s (?:happening|going on)|something interesting",
    re.IGNORECASE,
)
_CINEMA = re.compile(r"кино(?!театр)|фильм|сеанс|\bmovies?\b|\bfilms?\b|\bcinema\b", re.IGNORECASE)
_TODAY = re.compile(
    r"сегодня|вечер|сейчас|ночью|\btoday\b|\btonight\b|\bevening\b|\bnow\b|бүгін|кеш|қазір|түнде",
    re.IGNORECASE,
)
_EVENING = re.compile(r"вечер|\btonight\b|\bevening\b|кеш", re.IGNORECASE)
_NOT_TODAY = re.compile(r"завтра|послезавтра|\btomorrow\b|ертең", re.IGNORECASE)
_AIRPORT = re.compile(r"аэропорт|әуежай|\bairport\b", re.IGNORECASE)
_HOW = re.compile(
    r"добра|доехат|проехат|попасть|ехать|доеду|автобус"
    r"|\bhow (?:do i |can i |to )?(?:get|reach|go)\b|\bbus\b"
    r"|қалай (?:жет|бар)|жету|баруға",
    re.IGNORECASE,
)
_LAST_BUS = re.compile(r"последн\w* автобус|\blast bus\b|соңғы автобус", re.IGNORECASE)
_TRAVEL = re.compile(
    r"аэропорт|вылет|рейс|вокзал|поезд(?!к)|әуежай|ұшу|ұшақ|пойыз"
    r"|\bairport\b|\bflights?\b|\btrains?\b|(?<!gas )(?<!petrol )\bstation\b",
    re.IGNORECASE,
)


class Ask(NamedTuple):
    kind: AskKind
    cinema: bool = False  # the afisha question is about films: only cinema sessions answer it
    generic_bus: bool = (
        False  # «последний автобус» with no airport in it: said to be about the airport buses
    )


def read_ask(text: str) -> Ask | None:
    """The message as a question for the afisha or for the airport bus, or None (then it is read as usual)."""
    if _AIRPORT.search(text) and _HOW.search(text):
        return Ask("airport")
    if _LAST_BUS.search(text):
        return Ask("airport", generic_bus=True)
    if _NOT_TODAY.search(text):
        return None
    today = _TODAY.search(text) is not None
    if _EVENTS.search(text) or (today and (_CINEMA.search(text) or _WHAT_ON.search(text))):
        return Ask(
            "events", cinema=_CINEMA.search(text) is not None and _EVENTS.search(text) is None
        )
    return None


def mentions_travel(text: str) -> bool:
    """The request is about an airport, a flight, a train or a station: the airport bus may be worth a line."""
    return _TRAVEL.search(text) is not None


def _window(text: str, when: datetime) -> tuple[datetime, int]:
    """From `when` (from 18:00 for «вечером») to the end of the day: at least three hours, at most sixteen."""
    if _EVENING.search(text) and when.hour < EVENING_FROM:
        when = when.replace(hour=EVENING_FROM, minute=0, second=0, microsecond=0)
    midnight = datetime.combine(when.date() + timedelta(days=1), datetime.min.time())
    minutes = int((midnight - when).total_seconds() // 60)
    return when, min(max(minutes, MIN_WINDOW_MIN), MAX_WINDOW_MIN)


def events_answer(
    text: str, lat: float, lon: float, when: datetime, lang: str, *, cinema: bool = False
) -> tuple[str, EventsBlock | None]:
    """(the reply, the block of up to three events): the afisha near the point from `when` to the end of the day. An
    empty answer says the afisha reaches only a few sources, never that nothing is on."""
    if not load_snapshot().events:
        return ta("no_data", lang), None
    start, window = _window(text, when)
    block = events_block(
        lat,
        lon,
        start,
        lang,
        limit=AFISHA_SHOWN,
        radius_m=AFISHA_RADIUS_M,
        window_min=window,
        coverage=True,
        only_kind="sessions" if cinema else None,
    )
    if block is None:
        return ta("none", lang, sources=afisha_sources(lang)), None
    return ta("reply", lang), block


def airport_answer(when: datetime, lang: str, ask: Ask) -> tuple[str, list[Notice]]:
    """(the reply, the notice with the last bus and its source link): the airport buses of nn-airport.kz."""
    info = mobility.airport_bus(when)
    routes = airport_routes(info) if info else []
    if info is None or not routes:
        return tn("ap_none", lang), []
    listed = "; ".join(
        tn(
            "ap_route",
            lang,
            route=r["route"],
            first=r["first_departure"],
            last=r["last_departure"],
            headway=str(r["headway_min"]).replace("-", "–"),
        )
        for r in routes
    )
    if info.fare_card_kzt and info.fare_cash_kzt:
        body = tn(
            "ap_answer", lang, routes=listed, card=info.fare_card_kzt, cash=info.fare_cash_kzt
        )
    else:
        body = tn("ap_answer_nofare", lang, routes=listed)
    prefix = tn("ap_only_airport", lang) if ask.generic_bus else ""
    notice = airport_notice(when, lang, asked=True)
    return prefix + body, [notice] if notice else []
