"""Recommendation text: an LLM over candidate facts only, validated by code, with a no-AI template fallback.

Facts that must be trustworthy (distance, walking time, opening-hours state, coordinates) never come from the
LLM: they are copied from the retrieval Candidate after validation.
"""

from __future__ import annotations

import contextlib
import hashlib
import json
import re
from datetime import datetime
from typing import Literal

from .attributes import requested_diets
from .card_notes import data_notes
from .chains import distinct, lead_order
from .claims import note_keys, strip_unbacked
from .colocated import SHARED_COORD
from .envcfg import cache_pin, replay_only
from .facts import allowed_numbers, card_status, checked_opening, sheet, vague_ids
from .hours import to_local_naive
from .i18n import LLM_LANGUAGE, norm, t
from .kids import allowed_unnamed, is_near_named
from .llm import (
    GENERATION_TIMEOUT_S,
    Deadline,
    LLMCall,
    LLMUnavailable,
    ReplayMiss,
    ai_off_reason,
    generate_json,
    generation_models,
)
from .llm_output import LLMOutput, LLMRec
from .models import (
    Candidate,
    Confidence,
    Intent,
    LLMStep,
    Recommendation,
    WeatherInfo,
)
from .names import same_chain
from .prompt_gen import SYSTEM
from .radius import INFO_ABOUT, plan_slot
from .reasons import (
    Trip,
    budget_phrase,
    compose_why,
    honest_hours_text,
    people_phrase,
    template_what,
)
from .retrieve import NEAR_WEIGHT, distance_weight, is_deep_night
from .shelter import AIR_OUTDOOR_KEPT, OUTDOOR_OFF_KIND, OUTDOOR_REQUESTS, WEATHER_OUTDOOR_KEPT
from .specific import keep_status, numbers_ok, without_interest
from .stay import MIN_STAY_OVER_BUDGET, STAY_RANGE_MIN
from .sun import is_dark
from .want import names_the_wish
from .wish_rank import evening_sight

MAX_RECS = 3
_WORD_FIELDS = frozenset({"wished", "refused", "local_food", "time_stated", "eat"})
_CONF_RANK = {"low": 0, "medium": 1, "high": 2}
OUTDOOR_STAY_CAP_MIN = 20
NEARER_MIN_M = 300  # a «nearer twin» is at least this much closer ...
NEARER_RATIO = 0.65  # ... and at most this share of the model's pick's distance
NEARER_SCORE_SLACK = 2.0  # ... and not ranked lower by more than this
DIVERSITY_MARGIN = (
    1.5  # pick_diverse may skip the best remaining candidate only for one within this score gap
)
# Reason codes of a candidate that breaks a weather / budget rule: it is shown only when nothing else is left. An
# outdoor request kept outdoors (the *_KEPT codes) is not one; a place of another kind than it asked for is.
_RULE_VIOLATIONS = frozenset(
    {"weather_outdoor", "air_outdoor", OUTDOOR_OFF_KIND, MIN_STAY_OVER_BUDGET}
)
_KEPT_OUTDOORS = frozenset({WEATHER_OUTDOOR_KEPT, AIR_OUTDOOR_KEPT})
_STRONG_REASONS = {"category", "kids", "wifi", "socket", "keywords", "wheelchair", "quiet"}
MAX_WHY_SENTENCES = 2  # the card shows «почему» in at most two sentences


_NUMERIC_CLAIM = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:м|км|метр\w*|мин\w*|час\w*|ч|сағат\w*|сағ|шақырым\w*|m|km|meters?|metres?|min\w*|hours?|h)(?![\w])"
    r"|\d{1,2}:\d{2}",
    re.I,
)
_OPEN_NOW = re.compile(
    r"(?:сейчас|now|қазір).{0,20}(?:открыт|работает|open|ашық)|(?:открыт\w*|работает|open|ашық).{0,20}(?:сейчас|now|қазір)",
    re.I,
)


# ---------------------------------------------------------------- shared helpers


def strip_unverified_claims(
    text: str, allowed: frozenset[str] = frozenset(), open_now: bool = False
) -> str:
    """Drop sentences that state distances / times / hours the record does not hold (`allowed`: the walking minutes and
    the times written in its hours) or «open now» of a place that is not open by its hours."""
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    keep = [
        p
        for p in parts
        if p
        and not (_NUMERIC_CLAIM.search(p) and not numbers_ok(p, set(allowed)))
        and not (_OPEN_NOW.search(p) and not open_now)
    ]
    return " ".join(keep).strip()


def _data_confidence(c: Candidate) -> Confidence:
    people_disagree = (
        c.people is not None and c.people.hours in ("closed", "mixed") and c.hours_state == "open"
    )
    if SHARED_COORD in c.reasons:
        return "low"  # the position is a placeholder shared with other records
    if c.hours_state == "open" and c.hours_note.startswith("праздник"):
        return "medium"  # 24/7 on a holiday: still open by the data, but the day is unusual
    if c.hours_state == "open" and not c.poi.name_generated and not people_disagree:
        # OSM and the website name different schedules: even when both say open now, not a high confidence
        return "medium" if c.hours_issue == "conflict" else "high"
    if c.hours_state == "unknown" and c.poi.name_generated:
        return "low"
    return "medium"


def _min_conf(a: str, b: str) -> Confidence:
    return a if _CONF_RANK[a] <= _CONF_RANK[b] else b  # type: ignore[return-value]


def category_stay(minutes: int, category: str) -> int:
    """Clamp the LLM's time on site into the typical range of the place's category (decided by code)."""
    lo, hi = STAY_RANGE_MIN.get(category, STAY_RANGE_MIN["other"])
    return max(lo, min(minutes, hi))


def typical_stay(category: str) -> int:
    lo, hi = STAY_RANGE_MIN.get(category, STAY_RANGE_MIN["other"])
    return (lo + hi) // 2


def clamp_stay(minutes: int, c: Candidate, intent: Intent) -> int:
    """The route budget is the last word: travel there and back and the stay must fit."""
    ceiling = max(10, intent.time_budget_min - 2 * c.travel_min)
    return int(max(5, min(minutes, ceiling)))


def _trip(c: Candidate, intent: Intent, stay: int) -> Trip:
    """One visit's time for the reason sentences: the candidate's own estimate of the way, until routing replaces it."""
    return Trip(c.walk_min if intent.mode == "walk" else c.travel_min, stay)


def _to_recommendation(
    c: Candidate,
    intent: Intent,
    *,
    why: str,
    stay: int,
    what: str,
    confidence: str,
    generated: bool,
    notes: str,
    source: str,
    claims: list[str] | None = None,
) -> Recommendation:
    stay = category_stay(stay, c.poi.category)
    if (
        not _KEPT_OUTDOORS.isdisjoint(c.reasons)
        or "weather_outdoor" in c.reasons
        or "air_outdoor" in c.reasons
    ):
        stay = min(stay, OUTDOOR_STAY_CAP_MIN)  # bad weather / air: keep time outside short
    return Recommendation(
        poi=c.poi,
        why=why,
        time_on_site_min=clamp_stay(stay, c, intent),
        what_to_do=what,
        confidence=_min_conf(confidence, _data_confidence(c)),
        generated_idea=generated,
        notes=notes,
        distance_m=c.distance_m,
        walk_min=c.walk_min,
        travel_min=c.travel_min,
        hours_state=c.hours_state,
        hours_raw=c.poi.opening_hours,
        hours_note=c.hours_note,
        hours_issue=c.hours_issue,
        walk_method="estimate",  # replaced by walks.walking for mode=walk
        people=c.people,
        text_source=source,  # type: ignore[arg-type]
        unbacked_claims=list(claims or []),
    )


# ---------------------------------------------------------------- LLM path


def _candidate_item(c: Candidate, lang: str, when: datetime) -> dict:
    """One candidate as the model needs it: its fact sheet (walks.facts), nothing it is told not to write."""
    return sheet(c, lang, when)


def build_payload(
    intent: Intent,
    candidates: list[Candidate],
    when: datetime,
    weather: WeatherInfo | None = None,
    preferences: dict | None = None,
    notes: str = "",
) -> dict:
    """Exactly what the LLM receives: the intent without its defaults, the conditions (for a walk the person asked for
    only: a café is not chosen «в условиях плохого воздуха и холода»), the candidates' usable fields; no user coordinate."""
    local = to_local_naive(when)
    walk = bool(set(intent.wished) & OUTDOOR_REQUESTS)
    return {
        "intent": intent.model_dump(exclude_defaults=True),
        "answer_language": LLM_LANGUAGE[norm(intent.language)],
        "local_time": local.strftime("%Y-%m-%d %H:%M (%A), Asia/Almaty"),
        "weather": None
        if weather is None or not walk
        else {
            "temperature_c": weather.temperature_c,
            "apparent_c": weather.apparent_c,
            "precipitation_mm": weather.precipitation_mm,
            "adverse": weather.adverse,
            "pm25": weather.pm25,
            "air_bad": weather.air_bad,
            "after_sunset": is_dark(weather, local),
        },
        "candidates": [_candidate_item(c, norm(intent.language), when) for c in candidates],
        **({"user_preferences": preferences} if preferences else {}),
        **({"user_notes": notes} if notes else {}),
    }


def fit_why(model_text: str, clause: str, budget: str) -> tuple[str, str]:
    """The `why` of an LLM card in at most MAX_WHY_SENTENCES sentences, by priority: the model's first sentence,
    the code-made clause (weather, marks of people), the budget note, the model's second sentence. Returns
    (why, overflow): the budget note that did not fit is moved to the card's notes."""
    sentences = [  # each sentence ends with its own stop: a code clause is never glued onto the model's text
        s if s[-1] in ".!?…" else s + "."
        for s in re.split(r"(?<=[.!?])\s+", model_text.strip())
        if s
    ]
    ranked = [("model", s) for s in sentences[:1]]
    ranked += [("clause", clause), ("budget", budget)] + [("model", s) for s in sentences[1:2]]
    ranked = [(kind, s) for kind, s in ranked if s]
    kept, dropped = ranked[:MAX_WHY_SENTENCES], ranked[MAX_WHY_SENTENCES:]
    reading = {"model": 0, "clause": 1, "budget": 2}
    why = " ".join(s for _, s in sorted(kept, key=lambda k: reading[k[0]]))
    return why, " ".join(s for kind, s in dropped if kind == "budget")


def _better_twin(
    c: Candidate,
    candidates: list[Candidate],
    taken: set[str],
    intent: Intent,
    deep_night: bool,
) -> Candidate | None:
    """A candidate of the same category that the model should have taken: at 23:00-06:00 one whose hours the data
    confirm instead of one with unknown hours; for a budget / short-time request one clearly nearer at a similar rank.
    `candidates` come in rank order."""
    twins = [
        x
        for x in candidates
        if x.poi.category == c.poi.category
        and x.poi.id != c.poi.id
        and x.poi.id not in taken
        and not _breaks_rules(x)
        and (c.poi.name_generated or not x.poi.name_generated)
    ]
    if deep_night and c.hours_state != "open":
        opened = next((x for x in twins if x.hours_state == "open"), None)
        if opened is not None:
            return opened
    if distance_weight(intent) > NEAR_WEIGHT:
        nearer = [
            x
            for x in twins
            if x.distance_m + NEARER_MIN_M <= c.distance_m
            and x.distance_m <= c.distance_m * NEARER_RATIO
            and x.score >= c.score - NEARER_SCORE_SLACK
            and (x.hours_state == "open" or x.hours_state == c.hours_state)
        ]
        if nearer:
            return min(nearer, key=lambda x: (x.distance_m, x.poi.id))
    return None


def _clean(text: str, c: Candidate, lang: str, removed: list[str], status: str = "") -> str:
    """A sentence block of the model for card `c`: no distances / times / «open now», no status or hour in other words
    than the card's own line (`status`, walks.status), and no attribute claim that no field backs (their kinds are
    appended to `removed`)."""
    allowed = allowed_numbers(c)
    text = honest_hours_text(
        strip_unverified_claims(text, allowed, c.hours_state == "open"), c, lang
    )
    text = without_interest(keep_status(text, status))
    text, kinds = strip_unbacked(text, c)
    removed.extend(kinds)
    return text


_LATIN = re.compile(r"[A-Za-z]")
_CYRILLIC = re.compile(r"[А-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ]")


def _in_language(r: LLMRec, lang: str) -> bool:
    """Is the model's text of this card in the script of the answer language (Latin for en, Cyrillic for ru / kk)? A
    recording made for another language, or a model that ignored `answer_language`, is not shown as the card's own."""
    text = f"{r.why} {r.what_to_do} {r.notes}"
    latin, cyrillic = len(_LATIN.findall(text)), len(_CYRILLIC.findall(text))
    return cyrillic <= latin if lang == "en" else latin <= cyrillic


def _from_llm(
    out: LLMOutput,
    candidates: list[Candidate],
    intent: Intent,
    weather: WeatherInfo | None = None,
    when: datetime | None = None,
) -> tuple[list[Recommendation], list[str]]:
    by_id = {c.poi.id: c for c in candidates}
    has_clean = any(not _breaks_rules(c) for c in candidates)
    cap = allowed_unnamed(sum(1 for c in candidates if is_near_named(c)), MAX_RECS)
    deep_night = when is not None and is_deep_night(when)
    lang = intent.language
    recs: list[Recommendation] = []
    picked: list[Candidate] = []
    seen: set[str] = set()
    for r in out.recommendations:
        c = by_id.get(r.poi_id)
        if c is None or r.poi_id in seen:
            continue  # hallucinated or duplicated id
        if has_clean and _breaks_rules(c):
            continue  # the model must not bring back what the weather / budget rule took out
        twin = _better_twin(c, candidates, seen, intent, deep_night)
        own_text = twin is None and _in_language(
            r, lang
        )  # the model's sentences describe ITS pick, in this language
        c = twin or c
        if c.poi.id in seen:
            continue
        if c.poi.name_generated and sum(1 for x in recs if x.poi.name_generated) >= cap:
            continue  # named places first: the model may not fill the card with anonymous records
        if _anonymous_twin(c, picked) or any(same_chain(c.poi, x.poi) for x in picked):
            continue  # two indistinguishable anonymous records / two branches of one chain are not two choices
        seen.add(c.poi.id)
        picked.append(c)
        removed: list[str] = []  # kinds of the claims no field of the record backs

        status = card_status(c, when, lang)
        why = _clean(r.why, c, lang, removed, status) if own_text else ""
        what = _clean(r.what_to_do, c, lang, removed, status) if own_text else ""
        if not what:
            what = template_what(c, intent)
        stay = r.time_on_site_min if own_text else typical_stay(c.poi.category)
        extra_note = ""
        if why:
            pp = people_phrase(
                c, intent
            )  # the conditions are said once, in the lead: never on every card
            clause = pp
            clause = f"{clause[0].upper()}{clause[1:]}." if clause else ""
            why, extra_note = fit_why(why, clause, budget_phrase(c, intent))
        else:  # nothing the record backs is left of the model's sentences: the fact-based reason of the template
            why = compose_why(
                c, intent, weather, candidates, _trip(c, intent, clamp_stay(stay, c, intent))
            )
        data = data_notes(c, intent, weather)
        notes = [_clean(r.notes, c, lang, removed, status) if own_text else "", extra_note, *data]
        notes += [n for n in (t(key, lang) for key in note_keys(removed)) if n not in data]
        recs.append(
            _to_recommendation(
                c,
                intent,
                why=why,
                stay=stay,
                what=what,
                confidence=r.confidence if own_text else "medium",
                generated=r.generated_idea
                if own_text
                else False,  # only the free-text advice; the source is code's
                notes=" ".join(n for n in notes if n),
                source="llm" if own_text else "template",
                claims=removed,
            )
        )
        if len(recs) == MAX_RECS:
            break
    order = [i for i in out.route_order if i in seen]
    return recs, order


MAX_WANT_CHARS = 90
MIN_WANT_CHARS = 6
MIN_NAME_ECHO = 6  # a place name this long inside the clause is a recommendation, not a wish
_WANT_BANNED = re.compile(r"\d|https?:|@|[«»“”\"<>{}\[\]]|\n")
_NOTES_ECHO_CHARS = (
    12  # a run of this many characters of the user's notes inside the clause is an echo of them
)


def _plain(text: str) -> str:
    return " ".join(re.sub(r"[^\w]+", " ", text.lower()).split())


def _clean_want(text: str, candidates: list[Candidate], intent: Intent, notes: str) -> str:
    """The model's «what you want» clause when it is safe to put in front of the user, else '': one short sentence in
    the answer language, with no digits (those are code's), no hours claim, no place name, nothing quoted from the
    user's own notes. Anything else is dropped and the template composes the clause."""
    text = " ".join(text.split()).rstrip(" .!;:,")
    if not (MIN_WANT_CHARS <= len(text) <= MAX_WANT_CHARS) or _WANT_BANNED.search(text):
        return ""
    if _OPEN_NOW.search(text) or re.search(r"[.!?]\s+\S", text) or not names_the_wish(text, intent):
        return ""
    latin, cyrillic = len(_LATIN.findall(text)), len(_CYRILLIC.findall(text))
    if (cyrillic > latin) if intent.language == "en" else (latin > cyrillic):
        return ""
    plain = _plain(text)
    if any(len(n := _plain(c.poi.name)) >= MIN_NAME_ECHO and n in plain for c in candidates):
        return ""
    own = _plain(notes)
    if own and any(
        plain[i : i + _NOTES_ECHO_CHARS] in own for i in range(len(plain) - _NOTES_ECHO_CHARS + 1)
    ):
        return ""
    return text


# ---------------------------------------------------------------- template (no-AI) path


def _breaks_rules(c: Candidate) -> bool:
    return not _RULE_VIOLATIONS.isdisjoint(c.reasons)


def _anonymous_twin(c: Candidate, picked: list[Candidate]) -> bool:
    """An anonymous OSM record of a kind that `picked` already has one anonymous record of."""
    return c.poi.name_generated and any(
        x.poi.name_generated and x.poi.category == c.poi.category for x in picked
    )


def pick_diverse(
    candidates: list[Candidate], n: int = MAX_RECS, margin: float = DIVERSITY_MARGIN
) -> list[Candidate]:
    """Best-scoring first, preferring distinct categories, but only among candidates within `margin` points of the
    best one left: variety never beats the ranking by more than that. A candidate that breaks a weather / budget
    rule is taken only when no other is left. `candidates` come sorted by rank."""
    pool = [c for c in candidates if not _breaks_rules(c)] or list(candidates)
    cap = allowed_unnamed(sum(1 for c in pool if is_near_named(c)), n)
    picked: list[Candidate] = []
    cats: set[str] = set()
    while pool and len(picked) < n:
        unnamed = sum(1 for c in picked if c.poi.name_generated)
        if unnamed >= cap:  # named places first: anonymous OSM records do not fill every slot
            pool = [c for c in pool if is_near_named(c)] or pool
        # two anonymous records of one kind cannot be told apart: never both; a second branch of a chain only when
        # nothing else is left
        pool = [c for c in pool if not _anonymous_twin(c, picked)]
        pool = [c for c in pool if not any(same_chain(c.poi, x.poi) for x in picked)] or pool
        if not pool:
            break
        floor = pool[0].score - margin
        pos = next(
            (i for i, c in enumerate(pool) if c.poi.category not in cats and c.score >= floor), 0
        )
        choice = pool.pop(pos)
        picked.append(choice)
        cats.add(choice.poi.category)
    return picked


def template_rec(
    c: Candidate, intent: Intent, weather: WeatherInfo | None, peers: list[Candidate]
) -> Recommendation:
    """One no-AI card: every sentence backed by a field of the record (walks.reasons)."""
    rec = _to_recommendation(
        c,
        intent,
        why="",
        stay=typical_stay(c.poi.category),
        what=template_what(c, intent),
        confidence="high"
        if any(r.split(":")[0] in _STRONG_REASONS for r in c.reasons)
        else "medium",
        generated=False,
        notes=" ".join(data_notes(c, intent, weather)),
        source="template",
    )
    rec.why = compose_why(c, intent, weather, peers, _trip(c, intent, rec.time_on_site_min))
    return rec


def cover_plan(
    recs: list[Recommendation],
    candidates: list[Candidate],
    intent: Intent,
    weather: WeatherInfo | None,
) -> list[Recommendation]:
    """A plan in stages («сначала поесть, потом музей», `Intent.plan_order`) needs one stop for every stage: a stage no
    card fills gets the best candidate of its kind, in the place of a card that fills no stage (else the last one)."""
    plan = list(getattr(intent, "plan_order", []) or [])
    if not plan:
        return recs
    out = list(recs)
    for stage in range(len(plan)):
        if any(plan_slot(r.poi.category, plan) == stage for r in out):
            continue
        pick = next(
            (
                c
                for c in candidates
                if plan_slot(c.poi.category, plan) == stage
                and c.poi.id not in {r.poi.id for r in out}
                and not _breaks_rules(c)
            ),
            None,
        )
        if pick is None:
            continue
        new = template_rec(pick, intent, weather, candidates)
        spare = next(
            (
                i
                for i in range(len(out) - 1, -1, -1)
                if plan_slot(out[i].poi.category, plan) >= len(plan)
            ),
            None,
        )
        if spare is not None:
            out[spare] = new
        elif len(out) < MAX_RECS:
            out.append(new)
        else:
            dup = next(
                (
                    i
                    for i in range(len(out) - 1, -1, -1)
                    if sum(
                        plan_slot(r.poi.category, plan) == plan_slot(out[i].poi.category, plan)
                        for r in out
                    )
                    > 1
                ),
                None,
            )
            if dup is not None:
                out[dup] = new
    return out


def required_cards(candidates: list[Candidate], intent: Intent) -> list[Candidate]:
    """The candidates the answer must show whatever the model preferred: the place the user asks ABOUT, and the best
    place the data themselves mark for each diet (or halal) the request names. `candidates` come in rank order."""
    out: list[Candidate] = [c for c in candidates if INFO_ABOUT in c.reasons][:1]
    marks = [f"diet:{d}" for d in requested_diets(intent)] + (["halal"] if intent.halal else [])
    for mark in marks:
        if pick := next(
            (c for c in candidates if mark in c.reasons and not _breaks_rules(c)), None
        ):
            out.append(pick)
    out += [
        c for c in (evening_sight(candidates, intent),) if c is not None
    ]  # Байтерек lit until 21:00
    seen: set[str] = set()
    return [c for c in out if not (c.poi.id in seen or seen.add(c.poi.id))]


def keep_required(
    recs: list[Recommendation],
    candidates: list[Candidate],
    intent: Intent,
    weather: WeatherInfo | None,
) -> list[Recommendation]:
    """Every required card (see `required_cards`) is in the answer: a missing one takes the last free slot or the place
    of the last card that is not required itself; the place asked about goes first."""
    need = required_cards(candidates, intent)
    out = list(recs)
    protected = {c.poi.id for c in need}
    for c in need:
        if any(r.poi.id == c.poi.id for r in out):
            continue
        new = template_rec(c, intent, weather, candidates)
        if len(out) < MAX_RECS:
            out.append(new)
        elif (
            slot := next(
                (i for i in range(len(out) - 1, -1, -1) if out[i].poi.id not in protected), None
            )
        ) is not None:
            out[slot] = new
    asked = {c.poi.id for c in need if INFO_ABOUT in c.reasons}
    return sorted(out, key=lambda r: r.poi.id not in asked)


def template_recs(
    candidates: list[Candidate], intent: Intent, weather: WeatherInfo | None = None
) -> list[Recommendation]:
    picked = [template_rec(c, intent, weather, candidates) for c in pick_diverse(candidates)]
    recs = cover_plan(
        keep_required(picked, candidates, intent, weather), candidates, intent, weather
    )
    return distinct(recs)


# ---------------------------------------------------------------- entry point


class Generation:
    def __init__(
        self,
        recs: list[Recommendation],
        route_order: list[str],
        mode: str,
        note: str,
        payload: dict | None,
        model: str | None,
        step: LLMStep | None = None,
        retry: Literal["", "live", "failed"] = "",
        want: str = "",
    ):
        self.recs, self.route_order, self.mode, self.note, self.payload, self.model, self.step = (
            recs,
            route_order,
            mode,
            note,
            payload,
            model,
            step,
        )
        self.retry = retry  # "live" / "failed": a recorded answer had no card with model text (see `generate`)
        self.want = (
            want  # the model's «what you want» clause, checked by `_clean_want` ('' = none usable)
        )
        self.opening = ""  # the model's own opening of the reply, checked by `facts.checked_opening` ('' = none)


def cache_material(
    intent: Intent,
    lat: float,
    lon: float,
    candidates: list[Candidate],
    when: datetime,
    preferences: dict | None = None,
    notes: str = "",
) -> str:
    """What makes two generation requests interchangeable: rounded cell, intent, 30-minute time bucket, the exact
    candidate list, the people's marks on it and the saved preferences (the model is added by walks.llm). Hashed
    there; never stored in clear. With WALKS_CACHE_PIN (demo replay) only the scenario cell, the intent hash and the
    candidate ids: the same scenario is answered from the recording at any time of day."""
    # `wished` / `refused` / `local_food` / `time_stated` follow from the words, and what they change is the candidate
    # ids and the card's own lines: out, the recorded keys stay
    intent_hash = hashlib.sha256(
        intent.model_dump_json(exclude=_WORD_FIELDS).encode("utf-8")
    ).hexdigest()[:16]
    ids = ",".join(c.poi.id for c in candidates)
    if cache_pin():
        return f"generation|{lat:.3f},{lon:.3f}|{intent_hash}|{ids}"
    local = to_local_naive(when)
    bucket = f"{local:%Y-%m-%d}/{(local.hour * 60 + local.minute) // 30}"
    key = f"generation|{lat:.3f},{lon:.3f}|{intent_hash}|{bucket}|{ids}"
    extra = [[c.poi.id, c.people.model_dump()] for c in candidates if c.people] + [
        preferences,
        notes,
    ]
    if any(extra):
        key += "|" + hashlib.sha256(json.dumps(extra, sort_keys=True).encode()).hexdigest()[:16]
    return key


def _ask(payload: dict, cache_key: str | None, deadline: Deadline | None) -> LLMCall[LLMOutput]:
    """One call of the generation chain; `cache_key=None` asks the models whatever the cache holds."""
    return generate_json(
        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
        LLMOutput,
        system=SYSTEM,
        models=generation_models(),
        timeout_s=GENERATION_TIMEOUT_S,
        cache_key=cache_key,
        deadline=deadline,
    )


def generate(
    intent: Intent,
    lat: float,
    lon: float,
    candidates: list[Candidate],
    when: datetime,
    *,
    use_llm: bool = True,
    weather: WeatherInfo | None = None,
    deadline: Deadline | None = None,
    preferences: dict | None = None,
    notes: str = "",
) -> Generation:
    """1-3 recommendations in ONE LLM call (provider chain, response cache); the template path when the AI is
    off, offline, out of the request's time budget (`deadline`) or every link failed."""
    if not candidates:
        return Generation([], [], "template", "нет кандидатов в радиусе", None, None)
    if why := ai_off_reason(use_llm):
        return Generation(
            template_recs(candidates, intent, weather), [], "template", why, None, None
        )

    payload = build_payload(intent, candidates, when, weather, preferences, notes)
    key = cache_material(intent, lat, lon, candidates, when, preferences, notes)
    try:
        call = _ask(payload, key, deadline)
    except LLMUnavailable as exc:
        return Generation(
            template_recs(candidates, intent, weather),
            [],
            "template",
            str(exc) if isinstance(exc, ReplayMiss) else f"ошибка ИИ: {exc}",
            payload,
            None,
            exc.step,
        )
    recs, order = _from_llm(call.value, candidates, intent, weather, when)
    final = _finish(recs, candidates, intent, weather)
    retry = ""
    if call.step.cached and not replay_only() and all(r.text_source != "llm" for r in final):
        # a recorded / cached answer that leaves no card with the model's own text (no id of today's candidates, another
        # answer language, claims no field backs, nearer twins, places a required one displaced) is no answer on a
        # stand with live models: ask the chain once more, uncached
        retry = "failed"
        with contextlib.suppress(LLMUnavailable):
            again = _ask(payload, None, deadline)
            fresh, fresh_order = _from_llm(again.value, candidates, intent, weather, when)
            if fresh:
                call, recs, order, retry = again, fresh, fresh_order, "live"
                final = _finish(fresh, candidates, intent, weather)
    recorded = (
        replay_only() or cache_pin()
    )  # a recorded demo answer is the director's: never re-asked or rewritten
    if recs and not recorded and (vague := vague_ids(final, candidates, norm(intent.language))):
        # a reason that names no fact of its place («удобно расположено», «отлично подходит»): asked once more, then the
        # card that is still vague is the template's own, fact-based one
        with contextlib.suppress(LLMUnavailable):
            again = _ask({**payload, "rewrite": vague}, None, deadline)
            fresh, fresh_order = _from_llm(again.value, candidates, intent, weather, when)
            if fresh:
                call, recs, order = again, fresh, fresh_order
                final = _finish(fresh, candidates, intent, weather)
        still = set(vague_ids(final, candidates, norm(intent.language)))
        by_id = {c.poi.id: c for c in candidates}
        final = [
            template_rec(by_id[r.poi.id], intent, weather, candidates) if r.poi.id in still else r
            for r in final
        ]
    if not recs:
        return Generation(
            template_recs(candidates, intent, weather),
            [],
            "template",
            "ответ ИИ не прошёл проверку (нет валидных poi_id)",
            payload,
            call.step.model,
            call.step,
            retry,
        )
    gen = Generation(
        final,
        order,
        "llm",
        "",
        payload,
        call.step.model,
        call.step,
        retry,
        _clean_want(call.value.you_want, candidates, intent, notes),
    )
    gen.opening = checked_opening(
        call.value.opening, final, candidates, weather, norm(intent.language), when
    )
    return gen


def _finish(
    recs: list[Recommendation],
    candidates: list[Candidate],
    intent: Intent,
    weather: WeatherInfo | None,
) -> list[Recommendation]:
    """The model's cards after code's rules: the places the request requires, a plan's stops covered, one card per
    place, in the order of the wish (walks.shelter.lead_order)."""
    if not recs:
        return []
    out = cover_plan(keep_required(recs, candidates, intent, weather), candidates, intent, weather)
    return lead_order(distinct(out), intent, weather)
