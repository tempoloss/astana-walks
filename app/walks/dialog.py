"""The dialogue as one pure function: `take_turn(state, message, env) -> Outcome(turn, state, result)`.

A turn is one of: places (at most three, one primary, short plain text, buttons that change the request); a clarifying
question (a message with nothing to search for); thanks / goodbye; an answer about places already shown or named
(from data, or an honest «в данных этого нет»); a refusal. The state is JSON (`DialogState`), holds no request text
and is never mutated. Rules work offline; the model, when there is one, may only narrow what the rules read.

Models: walks.dialog_types. Contract: docs/dialog.md. Reading a message: walks.dialog_nlu; cards and answers:
walks.dialog_place; buttons: walks.dialog_chips; sentences: walks.dialog_strings.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Literal, NamedTuple

from . import demo_pin, gov_hours
from .bookmarks import Ref, find_ref
from .dialog_asks import Ask, airport_answer, events_answer, mentions_travel, read_ask
from .dialog_chips import MAX_BUDGET_MIN, chip, refine_chips, reset_chip, start_chips
from .dialog_extras import airport_notice, decorate, events_block, lighting_line, weather_notice
from .dialog_lead import follow_up_lead, lead, taken_into_account
from .dialog_named import find_named, spells_a_place, unknown_name
from .dialog_nlu import (
    PlaceQuestion,
    detect,
    mentioned,
    out_of_data,
    place_question,
    reset_request,
    restore,
    small_talk,
    strip_fillers,
    tidy,
)
from .dialog_place import (
    answer,
    place_from_poi,
    place_from_rec,
    short_reply,
    shown_of,
)
from .dialog_strings import s
from .dialog_types import (
    Chip,
    DialogState,
    Meta,
    Notice,
    Place,
    PlaceAnswer,
    Route,
    ShownPlace,
    Turn,
    TurnKind,
    Walk,
)
from .feedback import FeedbackIndex, load_feedback
from .followup import FollowUp, conversation_after, parse_follow_up, refine_with_llm
from .generate import MAX_RECS
from .gov_hours import is_state_request, request_when
from .hours import local_now, to_local_naive
from .i18n import category_name, public_text, t
from .intent import named_categories, parse_intent, parse_rules
from .lexicon import is_info_question
from .llm import Deadline, ai_off_reason
from .models import (
    POI,
    Bookmark,
    IntentResult,
    LLMStep,
    Recommendation,
    Result,
    StartHints,
    WeatherInfo,
)
from .outing import default_outing, is_outing
from .pipeline import get_pois, recommend, round_location
from .profile import Profile, personal_view
from .stay import min_stay
from .walking import WalkingRouter, default_router

MAX_PLACES = MAX_RECS
LLM_FOLLOW_UP_MAX_WORDS = (
    6  # a vaguer message is not worth a model call (see followup.refine_with_llm)
)


@dataclass
class TurnEnv:
    """What a turn runs under (a Python object, not JSON); every field is optional."""

    when: datetime | None = None
    weather: WeatherInfo | Callable[[], WeatherInfo] | None = (
        None  # a callable is asked only by an unpinned search
    )
    use_llm: bool = True
    router: WalkingRouter | None = None
    profile: Profile | None = None
    feedback: FeedbackIndex | None = None
    pois: list[POI] | None = None
    language: str | None = None  # the user fixed the language: answer in it whatever they write
    budget_min: int | None = None  # tapped next to the input box (30 / 60 / 120): a NEW search only
    company: Literal["solo", "pair", "kids"] | None = None  # tapped: with whom, a NEW search only
    bookmarks: list[Bookmark] = field(
        default_factory=list
    )  # the user's own named places, this request only
    on_stage: Callable[[str], None] | None = None  # called with parse / search / write / route


class Outcome(NamedTuple):
    turn: Turn
    state: DialogState
    result: Result | None = None  # Python only: the pipeline's full result of a search turn


def new_state(lat: float, lon: float, lang: str = "ru") -> DialogState:
    lat, lon = round_location(lat, lon)
    return DialogState(lang=lang if lang in ("ru", "kk", "en") else "ru", lat=lat, lon=lon)  # type: ignore[arg-type]


def with_location(state: DialogState, lat: float, lon: float) -> DialogState:
    """The user moved the point: the old shown places and constraints are about another place, so they go."""
    return new_state(lat, lon, state.lang)


# ------------------------------------------------------------------ small turns


def _turn(
    kind: TurnKind, reply: str, lang: str, state: DialogState, chips: list[Chip] | None = None
) -> Turn:
    return Turn(
        kind=kind,
        lang=lang,  # type: ignore[arg-type]
        reply=reply,
        chips=chips or [],
        origin=(state.lat, state.lon),
    )


def _after(state: DialogState, lang: str, **changes: object) -> DialogState:
    return state.model_copy(update={"lang": lang, "turns": state.turns + 1, **changes})


def _refine(state: DialogState, lang: str) -> list[Chip]:
    conv = state.conversation
    if conv is None:
        return start_chips(lang)
    return refine_chips(conv.intent, conv.constraints, state.shown, lang)


def _clarify(state: DialogState, lang: str, key: str) -> Outcome:
    """One short question; the starter buttons (nothing searched yet) or the refinements (a search exists)."""
    chips = start_chips(lang) if state.conversation is None else _refine(state, lang)
    return Outcome(_turn("clarify", s(key, lang), lang, state, chips), _after(state, lang))


def _small_talk(act: str, state: DialogState, lang: str) -> Outcome:
    if act == "greeting":
        return _clarify(
            state, lang, "clarify_hello" if state.conversation is None else "clarify_change"
        )
    key, kind = {
        "thanks": ("thanks", "thanks"),
        "bye": ("bye", "bye"),
        "decline": ("decline", "bye"),
    }[act]
    chips = [reset_chip(lang)] if state.conversation is not None else []
    return Outcome(_turn(kind, s(key, lang), lang, state, chips), _after(state, lang))  # type: ignore[arg-type]


def _ask_turn(state: DialogState, env: TurnEnv, lang: str, text: str, ask: Ask) -> Outcome | None:
    """The afisha or the airport bus: answered from that layer's data, or honestly «данных нет»; no search, and the
    shown places and the request stay as they were. None for a question about the cinema when the afisha lists no
    session near: the cinemas themselves are then searched for as usual."""
    when = _question_when(state, env, text)
    if ask.kind == "events":
        reply, block = events_answer(text, state.lat, state.lon, when, lang, cinema=ask.cinema)
        if block is None and ask.cinema:
            return None
        turn = _turn("place_answer", reply, lang, state, _refine(state, lang))
        turn.events = block
    else:
        reply, notices = airport_answer(when, lang, ask)
        turn = _turn("place_answer", reply, lang, state, _refine(state, lang))
        turn.notices = notices
    return Outcome(turn, _after(state, lang))


# ------------------------------------------------------------------ questions about places


def _mode(state: DialogState) -> str:
    return state.conversation.intent.mode if state.conversation else "walk"


def _targets(state: DialogState, pq: PlaceQuestion, text: str) -> list[ShownPlace]:
    """The place(s) a question is about: by ordinal («второе»), by name, plural («они»), the place the last
    question was about, else the main one."""
    shown = state.shown
    if pq.ordinal is not None:
        return shown[pq.ordinal : pq.ordinal + 1]
    named = mentioned(text, [p.name for p in shown])
    if named is not None:
        return [shown[named]]
    if pq.plural and shown:
        return list(shown)
    if state.asked is not None and (state.focus_id == state.asked.id or not shown):
        return [state.asked]
    focus = next((p for p in shown if p.id == state.focus_id), None)
    return [focus or shown[0]] if shown else []


def _question_when(state: DialogState, env: TurnEnv, text: str) -> datetime:
    if demo_pin.pins(text, state.demo_base):
        return demo_pin.when_for(text, state.demo_base)
    return env.when or local_now()


def _answer_turn(
    state: DialogState,
    env: TurnEnv,
    lang: str,
    pq: PlaceQuestion,
    targets: list[tuple[ShownPlace | None, POI]],
    when: datetime,
) -> Outcome:
    origin = (state.lat, state.lon)
    mode = _mode(state)
    places: list[Place] = []
    answers: list[PlaceAnswer] = []
    for i, (sp, poi) in enumerate(targets):
        place = place_from_poi(
            poi, origin=origin, mode=mode, when=when, lang=lang, what=sp.what if sp else ""
        )
        if sp is not None:
            place.walk = Walk(
                minutes=sp.minutes,
                distance_m=sp.distance_m,
                method="estimate",
                mode=sp.mode,
                text=s(f"walk_{sp.mode}", lang, n=sp.minutes),
            )
        place.primary = i == 0
        decorate(place, poi, lang, when)
        places.append(place)
        arrival = to_local_naive(when) + timedelta(minutes=place.walk.minutes)
        answers.append(answer(pq.topic, place, poi, lang, arrival))
    first = places[0]
    asked = shown_of(first) if len(places) == 1 and not state.shown_has(first.id) else state.asked
    turn = _turn("place_answer", short_reply(answers), lang, state, _refine(state, lang))
    turn.places, turn.answers = places, answers
    focus = first.id if len(places) == 1 else None
    new = _after(state, lang, focus_id=focus, asked=asked if focus else None)
    return Outcome(turn, new)


def _place_question_turn(
    state: DialogState, env: TurnEnv, lang: str, text: str, pq: PlaceQuestion
) -> Outcome:
    pois = env.pois if env.pois is not None else get_pois()
    by_id = {p.id: p for p in pois}
    when = _question_when(state, env, text)
    targets = [(sp, by_id[sp.id]) for sp in _targets(state, pq, text) if sp.id in by_id]
    if not targets:
        return _clarify(state, lang, "clarify_no_place") if not state.shown else _which(state, lang)
    return _answer_turn(state, env, lang, pq, targets, when)


def _which(state: DialogState, lang: str) -> Outcome:
    turn = _turn("clarify", s("a_which", lang), lang, state, _refine(state, lang))
    return Outcome(turn, _after(state, lang))


# ------------------------------------------------------------------ search


def _read_follow_up(
    state: DialogState, text: str, env: TurnEnv, signal: bool
) -> tuple[FollowUp, LLMStep | None] | None:
    """The message as a change of the previous request: the rules first; for a short vague message the model may
    give a second opinion (only when the rules found nothing to search for either)."""
    conv = state.conversation
    if conv is None:
        return None
    fu = parse_follow_up(strip_fillers(text), conv.intent)
    if fu is not None:
        return fu, None
    if signal or ai_off_reason(env.use_llm) or len(text.split()) > LLM_FOLLOW_UP_MAX_WORDS:
        return None
    fu, step = refine_with_llm(text, conv.intent, use_llm=env.use_llm)
    return (fu, step) if fu is not None else None


def _change_label(fu: FollowUp, lang: str) -> str:
    parts = [
        *([s("ch_closer", lang)] if fu.closer else []),
        *([s("ch_more", lang)] if fu.more else []),
        *([s("ch_no_alcohol", lang)] if fu.no_alcohol else []),
        *({"low": [s("ch_cheaper", lang)], "high": [s("ch_pricier", lang)]}.get(fu.budget, [])),
        *([s(f"ch_kids_{fu.with_kids}", lang)] if fu.with_kids != "keep" else []),
        *([s("ch_quiet", lang)] if fu.quiet == "yes" else []),
        *([s("ch_wifi", lang)] if fu.wifi_socket == "yes" else []),
        *([s("ch_longer" if fu.extra_min > 0 else "ch_shorter", lang)] if fu.extra_min else []),
        *([s("ch_mode", lang)] if fu.mode != "keep" else []),
    ]
    text = ", ".join(parts)
    return text[:1].upper() + text[1:]


def _route(res: Result, ids: set[str]) -> Route | None:
    rt = res.route
    if rt is None or not set(rt.stops) <= ids:
        return None
    return Route(
        stops=rt.stops,
        legs_min=rt.legs_min,
        legs_m=rt.legs_m,
        stay_min=rt.stay_min,
        walk_min_total=rt.walk_min_total,
        return_min=rt.return_min,
        total_min=rt.total_min,
        budget_min=rt.budget_min,
        fits=rt.fits,
        method=rt.method,
        kind="plan" if len(rt.stops) > 1 and res.intent.intent.plan_order else "nearest",
    )


def _meta(res: Result, change: str) -> Meta:
    cached = bool(res.generation_step and res.generation_step.cached) or bool(
        res.intent.llm_step and res.intent.llm_step.cached
    )
    return Meta(
        parser=res.intent.parser,
        generation=res.generation,
        model=public_text(res.model) or None,
        cached=cached,
        generation_retry=res.generation_retry,
        ms=res.timings_ms.get("total", 0),
        continued=res.continued,
        change=change,
        intent=res.intent.intent.model_dump(mode="json"),
        note=public_text(res.intent.note),
        radius_m=res.retrieval.filters.radius_effective_m,
    )


def _hints(env: TurnEnv) -> StartHints | None:
    if env.budget_min is None and env.company is None:
        return None
    return StartHints(budget_min=env.budget_min, company=env.company)


def _one_voice(
    recs: list[Recommendation], generation: str, fu: FollowUp | None
) -> list[Recommendation]:
    """After «ещё / другое» an answer written by the AI never carries a back-filled card written from a template
    (another voice, another badge): the template cards are left out. A first answer keeps its cards, each one
    says by `text_source` whose words it has."""
    if fu is None or not fu.more or generation != "llm":
        return recs
    voiced = [r for r in recs if r.text_source == "llm"]
    return voiced or recs


def _decorate(res: Result, recs: list[Recommendation], places: list[Place], lang: str) -> Result:
    """The cards get their extra lines (an open OpenStreetMap note, the nearest stop). A place with such a note is
    never a high-confidence pick, so the result carries it as at most medium."""
    noted = {
        r.poi.id for r, p in zip(recs, places, strict=True) if decorate(p, r.poi, lang, res.when)
    }
    if not noted:
        return res
    capped = [
        r.model_copy(update={"confidence": "medium"})
        if r.poi.id in noted and r.confidence == "high"
        else r
        for r in res.recs
    ]
    return res.model_copy(update={"recs": capped})


def _notices(res: Result, text: str, lang: str) -> list[Notice]:
    """A warning or the station's adverse weather; the last airport bus when the request is about a trip."""
    found = [weather_notice(res.weather, lang)]
    if mentions_travel(text):
        found.append(airport_notice(to_local_naive(res.when), lang))
    return [n for n in found if n is not None]


def _lighting(turn: Turn, res: Result, env: TurnEnv, lang: str, pinned: bool) -> str:
    router = demo_pin.router() if pinned else env.router or default_router()
    by_id = {p.id: p for p in turn.places}
    stops = [(by_id[i].lat, by_id[i].lon) for i in turn.route.stops] if turn.route else []
    return lighting_line((res.lat, res.lon), stops, router, res.when, res.weather, lang)


def _time_notice(res: Result, places: list[Place], lang: str, asked: list[str]) -> str:
    """A kind of place the user NAMED that the time-fit rule dropped («на бар этого времени мало») is said so; a kind
    the weather or a default added to the request is not the user's wish, so it is never mentioned."""
    shown = {p.category for p in places}
    kinds = [
        k
        for k in res.retrieval.filters.excluded_stay_kinds
        if k in res.intent.intent.categories and k in asked and k not in shown
    ]
    if not kinds:
        return ""
    return s("notice_time", lang, kind=category_name(kinds[0], lang), lo=min_stay(kinds[0]))


def _state_reply(
    turn: Turn, recs: list[Recommendation], when: datetime, day: str | int, lang: str
) -> None:
    """A state-service request (ЦОН): the reply is one sentence with the nearest branch's interval of the asked day and
    its source (or that no branch works then, by the data); the branches are not a walk, so no route joins them."""
    first = recs[0].poi if recs else None
    if first is not None and not first.is_state_service():
        return
    name = turn.places[0].name if turn.places else ""
    text = gov_hours.reply_text(first.model_dump() if first else None, name, when, day, lang)
    if text:
        turn.reply = text
    turn.route = None


def _bookmark_of(
    state: DialogState, env: TurnEnv, ref: Ref | None, fu: tuple[FollowUp, LLMStep | None] | None
) -> tuple[Bookmark | None, Literal["", "near", "along"]]:
    """The bookmark this search is built around: the one the message names, or (a follow-up) the one the dialogue
    was already searching around; it must still be among the bookmarks sent with this request."""
    if ref is not None:
        return ref.bookmark, "along" if ref.along else "near"
    if fu is not None and state.bookmark_mode:
        kept = next((b for b in env.bookmarks if b.name == state.bookmark), None)
        if kept is not None:
            return kept, state.bookmark_mode
    return None, ""


def _way_of(res: Result, env: TurnEnv) -> tuple[str, str] | None:
    """(kind, name) of the bookmark the first place lies toward, as the pipeline found it."""
    found = (
        next((b for b in env.bookmarks if b.name == res.on_the_way), None)
        if res.on_the_way
        else None
    )
    return (found.kind, found.name) if found is not None else None


def _search(
    state: DialogState,
    env: TurnEnv,
    lang: str,
    text: str,
    fu: tuple[FollowUp, LLMStep | None] | None,
    model: tuple[IntentResult, Deadline] | None = None,
    ref: Ref | None = None,
) -> Outcome:
    conv = state.conversation
    base = (
        state.demo_base if fu is not None else None
    )  # a follow-up keeps the conditions of its dialogue
    pinned = demo_pin.pins(text, base)
    gov_when = (  # «ЦОН в субботу»: the day the answer is about (None: not a state-service request)
        request_when(text, env.when or local_now())
        if fu is None and not pinned and is_state_request(text)
        else None
    )
    bookmark, bmode = _bookmark_of(state, env, ref, fu)
    origin = (
        (bookmark.lat, bookmark.lon)
        if bookmark is not None and bmode == "near"
        else (state.lat, state.lon)
    )
    if pinned:
        res = demo_pin.recommend_pinned(
            text,
            state.lat,
            state.lon,
            base_text=base,
            use_llm=env.use_llm,
            conversation=conv,
            profile=env.profile,
            language=lang,
            follow_up=fu,
            hints=_hints(env),
            on_stage=env.on_stage,
        )
    else:
        res = recommend(
            text,
            *origin,
            gov_when[0] if gov_when else env.when,
            use_llm=env.use_llm,
            pois=env.pois,
            weather=env.weather() if callable(env.weather) else env.weather,
            router=env.router,
            conversation=conv,
            profile=env.profile,
            feedback=env.feedback if env.feedback is not None else load_feedback(),
            language=lang,
            follow_up=fu,
            hints=_hints(env),
            understood=model[0] if model else None,
            deadline=model[1] if model else None,
            bookmarks=env.bookmarks,
            along=bookmark if bmode == "along" else None,
            anchored=bmode == "near",
            on_stage=env.on_stage,
        )
    change = _change_label(fu[0], lang) if fu and res.continued else ""
    mode = res.intent.intent.mode
    recs = _one_voice(res.recs[:MAX_PLACES], res.generation, fu[0] if fu else None)
    new_conv = conversation_after(conv, res.model_copy(update={"recs": recs}))
    places = [
        place_from_rec(r, primary=i == 0, lang=lang, when=res.when, mode=mode)
        for i, r in enumerate(recs)
    ]
    res = _decorate(res, recs, places, lang)
    shown = [shown_of(p) for p in places]
    next_base = (base or text) if pinned else None
    new = _after(
        state,
        lang,
        conversation=new_conv,
        shown=shown,
        focus_id=None,
        asked=None,
        demo_base=next_base,
        bookmark=bookmark.name if bookmark is not None else "",
        bookmark_mode=bmode,
    )
    if (
        res.refusal != "none"
    ):  # never reached for a refusal the rules read; kept for a model-only one
        return Outcome(
            _turn("refusal", t("refusal", lang), lang, state, start_chips(lang)), state, res
        )
    if not places:
        toilet = (
            "public_toilet" in new_conv.intent.wished
        )  # said as the data's absence, never as the street's
        key = "none_new" if res.continued and new_conv.constraints.exclude_ids else "none_found"
        longer = new_conv.intent.time_budget_min < MAX_BUDGET_MIN and not toilet
        chips = (
            [chip("longer", lang)] if longer and "other" not in new_conv.intent.categories else []
        )
        reply = s("none_toilet" if toilet else key, lang)
        turn = _turn("none_found", reply, lang, state, [*chips, reset_chip(lang)])
    else:
        anchor = bookmark.name if bookmark is not None and bmode == "near" else ""
        way = _way_of(res, env)
        if res.continued:
            reply = follow_up_lead(places, change, lang, anchor=anchor, way=way)
        else:
            show_temp = env.when is None and not pinned and gov_when is None
            taken = taken_into_account(res, env.profile, lang)
            reply = lead(
                res, places, lang, show_temp=show_temp, anchor=anchor, way=way, taken=taken
            )
        turn = _turn(
            "places",
            reply,
            lang,
            state,
            refine_chips(new_conv.intent, new_conv.constraints, shown, lang),
        )
        turn.places = places
        turn.route = _route(res, {p.id for p in places})
        if turn.route is not None:
            turn.route.lighting = _lighting(turn, res, env, lang, pinned)
    turn.origin = origin
    turn.notice = _time_notice(res, places, lang, named_categories(text))
    turn.notices = _notices(res, text, lang)
    turn.events = events_block(res.lat, res.lon, res.when, lang)
    turn.meta = _meta(res, change)
    if gov_when is not None and "other" in res.intent.intent.categories:
        _state_reply(turn, recs, res.when, gov_when[1], lang)
    return Outcome(turn, new, res)


def _model_reading(env: TurnEnv, text: str) -> tuple[IntentResult, Deadline] | None:
    """A message the rules found nothing in, read by the model's intent step: slang («где побухать»), typos, a bare
    «куда сходить». Returns the reading with the request's time budget when the model found something to search for
    (a kind of place, a wish, an accessibility need, or a refusal); None when no model is available or it found nothing."""
    if ai_off_reason(env.use_llm):
        return None
    deadline = Deadline()
    about = personal_view(env.profile).about if env.profile is not None else ""
    res = parse_intent(
        text, use_llm=True, deadline=deadline, when=env.when or local_now(), about=about
    )
    it = res.intent
    found = it.categories or it.free_text_keywords or it.accessibility or it.refusal != "none"
    return (res, deadline) if res.parser == "rules+llm" and found else None


# ------------------------------------------------------------------ the turn


def _named_question(state: DialogState, env: TurnEnv, lang: str, text: str) -> Outcome | None:
    """«какие часы у Хан Шатыра», «далеко идти до Дерева жизни?»: an explicitly named place is answered directly,
    wherever it is, with its distance, hours and source, or «в данных нет». A name that is not in the data is
    said so; a name of a shown place is a question about that place."""
    if is_state_request(text) or is_outing(text):
        return None  # a state service point or «куда сходить» is searched for, not looked up by the words of a name
    pq = place_question(text, allow_kind=True)
    if pq is None and not is_info_question(text):
        return None
    if (
        pq is not None
        and pq.topic == "toilet"
        and "public_toilet" in parse_rules(text).intent.wished
    ):
        return None  # «где туалет», «public toilet»: a search for a toilet, not a question about a named place
    if pq is not None and pq.ordinal is not None:
        return None
    if state.shown and mentioned(text, [p.name for p in state.shown]) is not None:
        return None
    pois = env.pois if env.pois is not None else get_pois()
    poi = find_named(text, pois, (state.lat, state.lon))
    if poi is None:
        nothing_in_view = not state.shown and state.asked is None
        if pq is not None and (unknown_name(text) or (nothing_in_view and spells_a_place(text))):
            key = "a_unknown_place" if state.shown else "a_unknown_place_bare"
            turn = _turn("place_answer", s(key, lang), lang, state, _refine(state, lang))
            return Outcome(turn, _after(state, lang))
        return None
    shown = next((p for p in state.shown if p.id == poi.id), None)
    return _answer_turn(
        state,
        env,
        lang,
        pq or PlaceQuestion(topic="about"),
        [(shown, poi)],
        _question_when(state, env, text),
    )


def _signal(text: str) -> tuple[bool, bool, bool]:
    """(refusal, a kind of place or a named place, anything to search for) as the rules read the text."""
    intent = parse_rules(text).intent
    strong = bool(intent.categories or intent.landmark_refs or intent.info_about)
    wish = (
        bool(intent.free_text_keywords) or intent.accessibility
    )  # «на коляске» is a request without a kind
    return intent.refusal != "none", strong, strong or wish


def take_turn(state: DialogState, message: str, env: TurnEnv | None = None) -> Outcome:
    env = env or TurnEnv()
    text = restore(tidy(message))
    saved = env.profile.language if env.profile is not None else None
    # «☕», «?», «👍»: no word to read the language from, so the saved answer language («Язык ответа») speaks
    lang = env.language or detect(
        text, saved if saved and not any(ch.isalpha() for ch in text) else state.lang
    )
    if not any(ch.isalnum() for ch in text):
        key = "clarify_start" if state.conversation is None else "clarify_change"
        return _clarify(state, lang, key)
    is_reset, rest = reset_request(text)
    if is_reset:
        state = new_state(state.lat, state.lon, lang)
        if not _signal(rest)[2]:
            return _clarify(state, lang, "clarify_new")
        text = rest
    ref = find_ref(
        text, env.bookmarks
    )  # «рядом с домом», «по пути домой»: the words are not a wish for a place
    if ref is not None:
        if not ref.rest:
            return _clarify(state, lang, "clarify_start")
        text = ref.rest
    refusal, strong, has_signal = _signal(text)
    if refusal:
        refused = _turn("refusal", t("refusal", lang), lang, state, start_chips(lang))
        return Outcome(refused, _after(state, lang))
    if (act := small_talk(text)) is not None:
        return _small_talk(act, state, lang)
    if (ask := read_ask(text)) is not None and (asked := _ask_turn(state, env, lang, text, ask)):
        return asked
    if (missing := out_of_data(text)) is not None and not strong:
        reply = s("not_in_data", lang, what=s(f"ood_{missing}", lang))
        chips = start_chips(lang) if state.conversation is None else _refine(state, lang)
        return Outcome(_turn("none_found", reply, lang, state, chips), _after(state, lang))
    if (named := _named_question(state, env, lang, text)) is not None:
        return named
    pq = (
        None if is_outing(text) else place_question(text)
    )  # «where should I go» asks for places, not about one
    if pq is None and (state.shown or state.asked):
        priced = place_question(
            text, allow_kind=True
        )  # «сколько стоит капучино там»: a price asked of a shown place
        pq = priced if priced is not None and priced.topic == "price" else None
    if pq is not None and (pq.marked or not strong or pq.topic == "price"):
        if state.shown or state.asked:
            return _place_question_turn(state, env, lang, text, pq)
        if not has_signal or pq.marked:
            return _clarify(state, lang, "clarify_no_place")
    fu = _read_follow_up(state, text, env, has_signal)
    model = None
    if fu is None and not has_signal:
        # slang, typos, a phrase with no word the rules know: the model reads it before anything is asked back
        model = _model_reading(env, text)
        if model is None:
            outing = default_outing(
                text, env.when
            )  # «куда сходить» and no model: a default answer, not a question
            if outing is None:
                key = "clarify_unclear" if state.conversation is None else "clarify_change"
                return _clarify(state, lang, key)
            model = (outing, Deadline())
    return _search(state, env, lang, text, fu, model, ref)
