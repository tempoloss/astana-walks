"""The assistant's endpoints: GET /api/config (the stand's mode, the places and the starter requests) and POST /api/turn
(one message through walks.dialog). The dialogue, its texts and its chips are the core's; around a turn this module
adds only what the page shows beside it: the conditions that changed the answer and, with the opt-in profile on, the
«Запомнить: …?» chips; the `explain` block (web.explain) stays in the answer for API readers, the page does not render it. The taps beside the input (time
budget, company, another time or weather) go to the core as they are (`TurnEnv`), never as words of the message."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, time
from itertools import pairwise
from time import perf_counter
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from i18n import tr
from walks import demo_pin
from walks.dialog import Outcome, TurnEnv, new_state, with_location
from walks.dialog_types import DialogState, Turn
from walks.envcfg import offline, replay_only
from walks.feedback import feedback_path, load_feedback
from walks.hours import local_now, to_local_naive
from walks.i18n import LANGS
from walks.intent import detect_language
from walks.llm import llm_available
from walks.models import Bookmark as CoreBookmark
from walks.pipeline import round_location
from walks.presets import DEMO_REQUESTS, PRESETS, SCENARIOS, preset_name
from walks.profile import Profile, load_profile, suggest_chips, valid_id
from walks.reqlog import held, write_held
from walks.vibe_turn import take_vibe_turn
from walks.walking import WalkingRouter, default_router
from walks.weather import (
    latest_weather as fetch_weather,  # the last value of the background refresh; never waits
)
from walks.weather import manual_weather
from web import geocode
from web.explain import explain

START_PRESET = "EXPO"
MAX_TEXT = 600
# «Другое время / погода»: the manual conditions a user may try; the answer says the time or weather is manual
WEATHER = {
    "frost": lambda: manual_weather(-25.0),
    "rain": lambda: manual_weather(8.0, 6.0),
    "smog": lambda: manual_weather(10.0, pm25=80.0),
}


class Bookmark(BaseModel):
    """A place the user saved in their own browser («Дом», «Учёба»): used for this request only, never stored."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=40)
    kind: Literal["home", "work", "study", "other"] = "other"
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)


class TurnRequest(BaseModel):
    """One message of the user. `state` is the DialogState the previous turn returned (None: a new dialogue)."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1, max_length=MAX_TEXT)
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)
    lang: Literal["kk", "ru", "en"] = "ru"
    lang_fixed: bool = False  # the user chose the language: answers stay in it
    at: str | None = Field(
        default=None, pattern=r"^\d{2}:\d{2}$"
    )  # a scenario's or the user's own time
    weather: Literal["now", "frost", "rain", "smog"] = "now"
    budget_min: Literal[30, 60, 120] | None = None
    company: Literal["solo", "pair", "kids"] | None = None
    state: DialogState | None = None
    bookmarks: list[Bookmark] = Field(default_factory=list, max_length=10)
    profile_on: bool = False
    profile_id: str | None = None


def mode() -> dict:
    """The stand's mode as the API reports it (the page uses only `offline`): no network, recorded answers only, no AI, pinned demo time."""
    return {
        "offline": offline(),
        "replay_only": replay_only(),
        "ai": llm_available() and not offline(),
        "demo_pin": demo_pin.pinned(),
    }


def _starters() -> dict[str, list[dict]]:
    """The starter chips per interface language: the five scenarios of the brief in that language, then the demo's
    other requests written in it. Each sends its text exactly, from its own place, so the recorded answers replay."""
    out: dict[str, list[dict]] = {}
    for lang in LANGS:
        rows = [
            {
                "id": f"s{i}",
                "label": tr(f"starter_s{i}", lang),
                "text": s.text_in(lang),
                "preset": s.preset,
                "at": f"{s.at:%H:%M}" if s.at else None,
            }
            for i, s in enumerate(SCENARIOS)
        ]
        rows += [
            {
                "id": f"r{i}",
                "label": tr(f"starter_r{i}", lang),
                "text": text,
                "preset": preset,
                "at": None,
            }
            for i, (text, preset) in enumerate(DEMO_REQUESTS)
            if detect_language(text) == lang
        ]
        out[lang] = rows
    return out


def _now() -> str:
    """The stand's «now» for the time row: the real local time (YYYY-MM-DDTHH:MM, no zone). A pinned demo answer carries
    its own moment (`at` of the answer), never the row."""
    return f"{to_local_naive(local_now()):%Y-%m-%dT%H:%M}"


def config() -> dict:
    return {
        "mode": mode(),
        "now": _now(),
        "presets": [
            {"id": key, "lat": lat, "lon": lon, "names": {lg: preset_name(key, lg) for lg in LANGS}}
            for key, (lat, lon) in PRESETS.items()
        ],
        "start": START_PRESET,
        "starters": _starters(),
        "marks": feedback_path()
        is not None,  # False: residents' marks are not saved here, so no report buttons
    }


def _profile(req: TurnRequest) -> Profile | None:
    """None while «запоминать» is off: nothing is read from the disk then."""
    if not req.profile_on:
        return None
    stored = load_profile(req.profile_id) if valid_id(req.profile_id) else None
    return stored or Profile()


def _when(at: str | None) -> datetime | None:
    if at is None:
        return None
    hour, minute = (int(x) for x in at.split(":"))
    return datetime.combine(local_now().date(), time(hour % 24, minute % 60))


def route_shape(turn: Turn, router: WalkingRouter) -> list[list[list[float]] | None] | None:
    """The street line of every leg of the route, in walking order: origin -> first stop -> ..., each as
    [[lat, lon], ...] or None when the router has no street line for it (the map then draws a faint straight line)."""
    if turn.route is None:
        return None
    by_id = {p.id: p for p in turn.places}
    stops = [by_id[i] for i in turn.route.stops if i in by_id]
    points = [turn.origin, *((p.lat, p.lon) for p in stops)]
    legs = [router.shape(a, b) for a, b in pairwise(points)]
    return [[[round(la, 5), round(lo, 5)] for la, lo in leg] if leg else None for leg in legs]


def place_legs(turn: Turn, router: WalkingRouter) -> list[dict]:
    """For every place of the answer the way from the origin to it, in the order of `turn.places` then `turn.more`: the
    minutes and metres the card says, how they were obtained and the street line [[lat, lon], ...] (None: the router
    has none, the map draws a faint straight line). The line of a place comes from the router's cache, or from a
    router of one's own; the shared public server is never asked here. The longer list («Ещё N мест рядом») takes
    the cached line only: seven more lookups would slow every answer."""
    legs: list[dict] = []
    for i, p in enumerate([*turn.places, *turn.more]):
        if p.walk.mode != "walk":
            line = None
        elif i < len(turn.places):
            line = router.line(turn.origin, (p.lat, p.lon))
        else:
            line = router.shape(turn.origin, (p.lat, p.lon))
        legs.append(
            {
                "minutes": p.walk.minutes,
                "meters": p.walk.distance_m,
                "method": p.walk.method,
                "shape": [[round(la, 5), round(lo, 5)] for la, lo in line] if line else None,
            }
        )
    return legs


def answer_time(out: Outcome, text: str, manual: datetime | None) -> dict:
    """The moment the answer is about (what the day strip of a card marks as «сейчас»): the search's own time, or the
    one a question about a place was answered at; `day` is how many days ahead of today it is (0 today, 1 tomorrow), so
    the card says «завтра» for tomorrow. A pinned demo answer is the stage's «now»: day 0."""
    pinned = out.state.demo_base is not None or demo_pin.pins(text, out.state.demo_base)
    if out.result is not None:
        when = out.result.when
    elif pinned:
        when = demo_pin.when_for(text, out.state.demo_base)
    else:
        when = manual or local_now()
    local = to_local_naive(when)
    days = 0 if pinned else max((local.date() - to_local_naive(local_now()).date()).days, 0)
    return {"time": f"{local:%H:%M}", "date": f"{local:%Y-%m-%d}", "day": days}


def _target(query: str, lang: str) -> tuple[float, float, str] | None:
    """«в сторону Мангилик Ел»: the first point of the local address search (nothing leaves the server, nothing is logged)."""
    found = geocode.search(query, lang)
    return (found[0]["lat"], found[0]["lon"], found[0]["label"]) if found else None


def answer(req: TurnRequest, on_stage: Callable[[str], None] | None = None) -> dict:
    """One turn for the page. The anonymous request log gets the time of the whole turn, from the message to the ready
    answer (walks.reqlog.held), not only the pipeline's own part of it."""
    t0 = perf_counter()
    with held() as records:
        body = _answer(req, on_stage)
    write_held(records, round((perf_counter() - t0) * 1000))
    return body


def _answer(req: TurnRequest, on_stage: Callable[[str], None] | None) -> dict:
    lat, lon = round_location(req.lat, req.lon)
    state = req.state
    if state is None:
        state = new_state(lat, lon, lang=req.lang)
    elif (state.lat, state.lon) != (lat, lon):
        state = with_location(state, lat, lon)
    profile = _profile(req)
    router = default_router()
    env = TurnEnv(
        when=_when(req.at),
        weather=WEATHER.get(
            req.weather, fetch_weather
        ),  # asked only by a search that is not pinned
        router=router,
        profile=profile,
        feedback=load_feedback(),
        language=req.lang if req.lang_fixed else None,
        budget_min=req.budget_min,
        company=req.company,
        on_stage=on_stage,
        bookmarks=[CoreBookmark.model_validate(b.model_dump()) for b in req.bookmarks],
        geocode=lambda q: _target(q, req.lang),
    )
    out = take_vibe_turn(
        state, req.text, env=env
    )  # walks.dialog's turn, with the person's vibe when one is set
    pinned = (
        out.state.demo_base is not None
    )  # the core pinned this turn: a recorded request or a follow-up of one
    shape_router = demo_pin.router() if pinned else router
    manual_time = pinned or req.at is not None
    res, lang = out.result, out.turn.lang
    remember = (
        suggest_chips(res.intent.intent, res.constraints, profile, res.query, lang)
        if res is not None and profile is not None
        else []
    )
    return {
        "turn": out.turn.model_dump(mode="json"),
        "state": out.state.model_dump(mode="json"),
        "route_shape": route_shape(out.turn, shape_router),
        "place_legs": place_legs(out.turn, shape_router),
        "at": answer_time(out, req.text, env.when),
        "pinned": pinned,
        "explain": explain(res, lang, manual_time=manual_time) if res is not None else None,
        "remember": [{"key": c.key, "label": c.label} for c in remember],
    }
