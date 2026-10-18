"""End-to-end pipeline: text + location -> intent -> candidates -> recommendations -> walking times -> route."""

from __future__ import annotations

import contextlib
import re
import time
from collections import Counter
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from pathlib import Path

from .bookmarks import late_home, prefer_toward, toward
from .envcfg import cache_pin, replay_only
from .feedback import FeedbackIndex
from .followup import FollowUp, apply_follow_up, describe, parse_follow_up, refine_with_llm
from .generate import MAX_RECS, Generation, generate
from .hours import local_now, to_local_naive
from .i18n import t
from .intent import parse_intent, parse_rules, parse_time_budget
from .lexicon import normalize
from .llm import Deadline, ai_off_reason
from .models import (
    POI,
    Bookmark,
    Candidate,
    Constraints,
    Conversation,
    Intent,
    IntentResult,
    LLMStep,
    Result,
    RetrievalResult,
    StartHints,
    WeatherInfo,
    load_pois,
    poi_path,
)
from .presets import PRESETS
from .profile import (
    Profile,
    adapt_weather,
    avoided_kinds,
    constraints_for,
    merge_into_intent,
    personal_view,
    preferences_payload,
)
from .realfit import apply_leg, replace_unreachable, sync_stays
from .reasons import refresh_why
from .reqlog import log_request
from .retrieve import retrieve
from .route import build_route
from .transit import attach_lrt_hints
from .visit_hours import visit_note
from .walking import WalkingRouter, default_router
from .weather import with_user_hint

COORD_DECIMALS = 3  # ~100 m; the only precision that is ever used, stored or sent anywhere
PAIR_SIZE = 2  # «вдвоём» next to the input box: two people, nothing more is read into it


def round_location(lat: float, lon: float) -> tuple[float, float]:
    return round(lat, COORD_DECIMALS), round(lon, COORD_DECIMALS)


# Demo presets are public places: legs starting there may go to the on-disk walking cache. A user-chosen point
# never does (see walks.walking).
PUBLIC_ORIGINS = {round_location(*p) for p in PRESETS.values()}


@lru_cache(maxsize=2)
def _cached_pois(path: str) -> tuple[POI, ...]:
    return tuple(load_pois(path))


def get_pois(path: str | Path | None = None) -> list[POI]:
    return list(_cached_pois(str(path or poi_path())))


def _unseen(candidates: list[Candidate]) -> list[Candidate]:
    """Places the profile marks visited were already ranked down; when enough others remain they are not offered
    (nor sent to the LLM) at all, so that a visited place's id never leaves retrieval."""
    fresh = [c for c in candidates if "visited" not in c.reasons]
    return fresh if len(fresh) >= MAX_RECS else candidates


class _Request:
    """How one request was understood: the intent, what the dialogue / profile narrow, and why."""

    def __init__(self, parsed: IntentResult, constraints: Constraints) -> None:
        self.parsed = parsed
        self.constraints = constraints
        self.continued = False
        self.note = ""
        self.applied: list[str] = []


def _stage(on_stage: Callable[[str], None] | None, name: str) -> None:
    if on_stage is not None:
        on_stage(name)


def _with_hints(intent: Intent, hints: StartHints | None, text: str) -> Intent:
    """What the person tapped next to the input box (a budget, a company) on top of what the words say: a time
    the words state wins; «with kids» is OR-ed; two people are a group of two, nothing romantic."""
    if hints is None:
        return intent
    update: dict = {}
    if hints.budget_min and parse_time_budget(text) is None:
        update["time_budget_min"] = hints.budget_min
    if hints.company == "kids":
        update["with_kids"] = True
    elif hints.company == "pair":
        update["group_size"] = intent.group_size or PAIR_SIZE
    elif hints.company == "solo":
        update["group_size"] = intent.group_size or 1
    return intent.model_copy(update=update) if update else intent


def _understand(
    text: str,
    use_llm: bool,
    deadline: Deadline,
    conversation: Conversation | None,
    profile: Profile | None,
    when: datetime,
    language: str | None = None,
    pois: list[POI] | None = None,
    decided: tuple[FollowUp, LLMStep | None] | None = None,
    hints: StartHints | None = None,
    understood: IntentResult | None = None,
    about: str = "",
) -> _Request:
    """A follow-up of the previous request when the message reads as one (rules first, then the optional LLM
    second opinion), otherwise a new request: the parsed intent with the profile's flags merged under it.
    `language` (the user's choice in the UI) replaces the language read from the text. `decided`: the dialogue
    layer already read the message as this follow-up (and the model step behind it, if any)."""
    if (
        conversation is not None
        and understood is None
        and parse_rules(text, when).intent.refusal == "none"
    ):
        if decided is not None:
            fu, step = decided
        else:
            fu, step = parse_follow_up(text, conversation.intent), None
            if (
                fu is None and not parse_rules(text, when).intent.wished
            ):  # a named wish is a new request
                fu, step = refine_with_llm(
                    text, conversation.intent, use_llm=use_llm, deadline=deadline
                )
        if fu is not None:
            intent, constraints = apply_follow_up(conversation, fu, pois)
            if profile is not None:  # a kind named once lifts «не показывать» for that message only
                constraints = constraints.model_copy(update={"avoid": list(profile.avoid)})
            if language:
                intent = intent.model_copy(update={"language": language})
            note = describe(fu, intent, constraints, intent.language)
            parsed = IntentResult(
                intent=intent,
                parser="rules+llm" if step is not None else "rules",
                note=note,
                llm_step=step,
            )
            req = _Request(parsed, constraints)
            req.continued, req.note = True, note
            return req
    parsed = understood or parse_intent(
        text, use_llm=use_llm, deadline=deadline, when=when, about=about
    )
    parsed, constraints, applied = _prepare(parsed, profile, hints, language, text)
    req = _Request(parsed, constraints)
    req.applied = applied
    return req


def _prepare(
    parsed: IntentResult,
    profile: Profile | None,
    hints: StartHints | None,
    language: str | None,
    text: str,
) -> tuple[IntentResult, Constraints, list[str]]:
    """A new request's parsed intent with what is not the words' own put under or over it: the profile's flags, the taps
    next to the input box, the language the user fixed."""
    constraints, applied = Constraints(), []
    if profile is not None and parsed.intent.refusal == "none":
        intent, applied = merge_into_intent(parsed.intent, profile, text)
        constraints, extra = constraints_for(profile)
        applied += extra
        if avoided := avoided_kinds(intent, profile, text):
            constraints = constraints.model_copy(update={"avoid": avoided})
            applied.append("avoid")
        parsed = parsed.model_copy(update={"intent": intent})
    if hints is not None and parsed.intent.refusal == "none":
        parsed = parsed.model_copy(update={"intent": _with_hints(parsed.intent, hints, text)})
    if language:
        intent = parsed.intent.model_copy(update={"language": language})
        parsed = parsed.model_copy(update={"intent": intent})
    return parsed, constraints, applied


def _actionable(intent: Intent) -> bool:
    return bool(
        intent.categories or intent.landmark_refs or intent.info_about or intent.free_text_keywords
    )


def _may_speculate() -> bool:
    """Only with live models: a recording, an offline stand or a missing key has nothing to wait for."""
    return not (ai_off_reason(True) or cache_pin() or replay_only())


def _stem4(word: str) -> str:
    return normalize(word)[:4]


def _restates(keyword: str, text: str) -> bool:
    """Does every word of the model's keyword only repeat a word of the user's own message («кофе» for «хочу кофе»)?"""
    said = {_stem4(w) for w in re.findall(r"\w+", text)}
    return all(_stem4(w) in said for w in re.findall(r"\w+", keyword))


def _same_reading(rules: Intent, final: Intent, text: str) -> bool:
    """The model's reading adds nothing the rules' reading did not have, apart from keywords that restate the user's
    own words: the answer prepared for the rules' intent is then the answer."""
    skip = {"free_text_keywords"}
    if rules.model_dump(exclude=skip) != final.model_dump(exclude=skip):
        return False
    added = [k for k in final.free_text_keywords if k not in rules.free_text_keywords]
    return all(_restates(k, text) for k in added)


@dataclass
class _Plan:
    """What follows from an intent: the conditions, the candidates, the written answer, and how long it took."""

    intent: Intent
    weather: WeatherInfo | None
    retrieval: RetrievalResult
    cands: list[Candidate]
    way: Bookmark | None
    gen: Generation
    retrieve_ms: int
    generation_ms: int


def _refused(
    text: str,
    lat: float,
    lon: float,
    when: datetime,
    req: _Request,
    t0: float,
    private: bool,
) -> Result:
    """The request asks for drugs, sex services or weapons: no place is searched or offered, the answer is the
    refusal note (`Result.refusal`, i18n key `refusal`). Never logged."""
    parsed = req.parsed
    intent = parsed.intent
    retrieval = retrieve([], lat, lon, intent, when, constraints=req.constraints)
    ms = round((time.perf_counter() - t0) * 1000)
    return Result(
        lat=lat,
        lon=lon,
        when=when,
        query=text,
        intent=parsed,
        retrieval=retrieval,
        recs=[],
        route=None,
        generation="template",
        generation_note=t("refusal", intent.language),
        timings_ms={"intent": ms, "retrieve": 0, "generation": 0, "route": 0, "total": ms},
        constraints=req.constraints,
        private=private,
        refusal=intent.refusal,
    )


def recommend(
    text: str,
    lat: float,
    lon: float,
    when: datetime | None = None,
    *,
    use_llm: bool = True,
    pois: list[POI] | None = None,
    weather: WeatherInfo | None = None,
    router: WalkingRouter | None = None,
    conversation: Conversation | None = None,
    profile: Profile | None = None,
    feedback: FeedbackIndex | None = None,
    language: str | None = None,
    follow_up: tuple[FollowUp, LLMStep | None] | None = None,
    hints: StartHints | None = None,
    understood: IntentResult | None = None,
    deadline: Deadline | None = None,
    bookmarks: list[Bookmark] | None = None,
    along: Bookmark | None = None,
    anchored: bool = False,
    on_stage: Callable[[str], None] | None = None,
) -> Result:
    """Run the whole pipeline. Coordinates are rounded to 3 decimals on entry and only the rounded values are
    used for distances, prompts, routing requests and the returned Result. The only things persisted are the
    anonymised aggregate record of walks.reqlog (grid cell, intent flags, counts; no free text, no coordinates)
    and walking legs between public points (walks.walking).

    Optional memory, all off unless passed: `conversation` (session only: the message may refine the previous
    request), `profile` (opt-in personal flags; a request that used it is not logged) and `feedback` (anonymous
    marks of people from data/city_feedback.json; they never change `hours_state`)."""
    lat, lon = round_location(lat, lon)
    when = when or local_now()
    pois = pois if pois is not None else get_pois()
    router = router or default_router()

    clock = time.perf_counter
    t0 = clock()
    deadline = (
        deadline or Deadline()
    )  # one time budget for every LLM link of this request (intent + generation)
    _stage(on_stage, "parse")
    personal = personal_view(profile) if profile is not None else None
    about = personal.about if personal is not None else ""
    private = (
        profile is not None
        or anchored
        or along is not None
        or bool(bookmarks)
        or (conversation is not None and conversation.private)
    )

    def plan(intent: Intent, cold_applied: list[str] | None = None) -> _Plan:
        """Conditions, retrieval and the written text for one intent: what is needed after the intent is known."""
        wx, cold = (weather, False) if profile is None else adapt_weather(weather, profile)
        if cold and cold_applied is not None:
            cold_applied.append("cold_tolerance")
        if intent.mode != "walk" and not intent.mode_explicit:
            # the mode is the user's to change: a model's guess (car, 15 km) never replaces walking + the LRT hint
            intent = intent.model_copy(update={"mode": "walk"})
        wx = with_user_hint(wx, intent.weather_hint)  # «-25, холодно» counts as the weather
        t_start = clock()
        retrieval = retrieve(
            pois,
            lat,
            lon,
            intent,
            when,
            weather=wx,
            constraints=constraints,
            feedback=feedback,
            personal=personal,
        )
        cands = _unseen(retrieval.candidates) if profile is not None else retrieval.candidates
        way = along or late_home(intent, to_local_naive(when).hour, (lat, lon), bookmarks or [])
        if way is not None:
            cands = prefer_toward(
                cands, (lat, lon), way, along=along is not None, kinds=frozenset(intent.wished)
            )
        t_found = clock()
        gen = generate(
            intent,
            lat,
            lon,
            cands,
            when,
            use_llm=use_llm,
            weather=wx,
            deadline=deadline,
            preferences=preferences_payload(profile) if profile is not None else None,
            notes=about,
        )
        return _Plan(
            intent,
            wx,
            retrieval,
            cands,
            way,
            gen,
            round((t_found - t_start) * 1000),
            round((clock() - t_found) * 1000),
        )

    constraints = Constraints()
    speculation = None
    if (
        conversation is None
        and follow_up is None
        and understood is None
        and use_llm
        and _may_speculate()
    ):
        rules = parse_rules(text, when)
        if rules.intent.refusal == "none" and _actionable(rules.intent):
            # the rules read the request: the written answer for THEIR intent is prepared while the model reads it
            # too; it is used when the model changes nothing (the usual case), else made again
            spec_parsed, constraints, _ = _prepare(rules, profile, hints, language, text)
            spec_intent = spec_parsed.intent
            pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="speculative")
            speculation = (spec_intent, pool.submit(plan, spec_intent))
            pool.shutdown(wait=False)
    req = _understand(
        text,
        use_llm,
        deadline,
        conversation,
        profile,
        when,
        language,
        pois,
        follow_up,
        hints,
        understood,
        about,
    )
    parsed = req.parsed
    t_intent = clock()
    intent = parsed.intent
    constraints = req.constraints
    if intent.refusal != "none":
        return _refused(text, lat, lon, when, req, t0, private)
    _stage(on_stage, "search")
    _stage(on_stage, "write")
    chosen = None
    if speculation is not None and _same_reading(speculation[0], intent, text):
        with contextlib.suppress(Exception):
            chosen = speculation[1].result()
    prepared = chosen or plan(intent, req.applied)
    if chosen is not None and profile is not None and adapt_weather(weather, profile)[1]:
        req.applied.append("cold_tolerance")
    intent, weather, retrieval, cands, way, gen = (
        prepared.intent,
        prepared.weather,
        prepared.retrieval,
        prepared.cands,
        prepared.way,
        prepared.gen,
    )
    parsed = parsed.model_copy(update={"intent": intent})
    t_retrieve = t_intent + prepared.retrieve_ms / 1000
    t_gen = t_retrieve + prepared.generation_ms / 1000
    recs = gen.recs
    padding_by_id = {c.poi.id: c.padding for c in retrieval.candidates}
    for r in recs:
        r.padding = padding_by_id.get(r.poi.id, "none")

    user = (lat, lon)
    user_public = user in PUBLIC_ORIGINS
    stats: Counter[str] = Counter()
    seen: set[frozenset] = set()

    def walk_leg(a, b):  # walking leg through the router, counted once per distinct pair
        persist = (a != user or user_public) and (b != user or user_public)
        leg = router.leg(a, b, persist=persist)
        pair = frozenset((a, b))
        if pair not in seen:
            seen.add(pair)
            stats["cache" if leg.from_cache else leg.method] += 1
        return leg.distance_m, leg.minutes, leg.method

    leg_fn = walk_leg if intent.mode == "walk" else None  # None: modelled estimate (car / transit)
    if leg_fn is not None:
        for r in recs:  # real distance / time to each final recommendation
            apply_leg(r, leg_fn(user, (r.poi.lat, r.poi.lon)))
        replace_unreachable(
            recs, cands, intent, weather, leg_fn, user
        )  # a real route that does not fit
    else:
        stats["estimate"] += len(recs)

    _stage(on_stage, "route")
    route = build_route(
        lat,
        lon,
        recs,
        intent.mode,
        intent.time_budget_min,
        gen.route_order,
        leg_fn,
        list(intent.plan_order),
    )
    sync_stays(recs, route)  # the card's time on site is the stay the route allots
    for r in recs:  # the hours of this visit: opens before you arrive / closes while you are there
        stay = r.time_on_site_min
        if note := visit_note(r.poi, when, r.travel_min, stay, r.hours_state, intent.language):
            r.notes = f"{r.notes} {note}".strip()
    refresh_why(recs, cands, intent, weather)  # the reasons name the final walking times and stays
    lrt_note = attach_lrt_hints(pois, lat, lon, recs, intent.mode, intent.language)
    on_the_way = (
        way.name
        if way is not None
        and recs
        and toward((lat, lon), way, recs[0].poi.lat, recs[0].poi.lon, along=along is not None)
        else ""
    )
    t_end = clock()
    result = Result(
        lat=lat,
        lon=lon,
        when=when,
        query=text,
        intent=parsed,
        retrieval=retrieval,
        recs=recs,
        route=route,
        generation=gen.mode,
        generation_note=gen.note,
        llm_payload=gen.payload,
        model=gen.model,  # type: ignore[arg-type]
        generation_step=gen.step,
        generation_retry=gen.retry,
        timings_ms={
            "intent": round((t_intent - t0) * 1000),
            "retrieve": round((t_retrieve - t_intent) * 1000),
            "generation": round((t_gen - t_retrieve) * 1000),
            "route": round((t_end - t_gen) * 1000),
            "total": round((t_end - t0) * 1000),
        },
        weather=weather,
        walk_stats=dict(stats),
        lrt_note=lrt_note,
        constraints=req.constraints,
        continued=req.continued,
        follow_up_note=req.note,
        profile_applied=req.applied,
        private=private,
        lead_want=gen.want,
        on_the_way=on_the_way,
        unbacked_claims_removed=sum(len(r.unbacked_claims) for r in recs),
    )
    log_request(result)
    return result
