"""A turn of the dialogue with the person's vibe (walks.vibe) around it: what the web page calls instead of
walks.dialog.take_turn.

* «под мой вайб», «под моё настроение», «менің вайбыма», «my vibe», or words that state the vibe and name no kind
  («куда сходить интроверту»): a search across kinds, ranked by vibe match, distance and open status (walks.retrieve),
  whose lead names the facets the places shown have evidence for. With no vibe stored or stated: one sentence of where
  to set it, nothing searched.
* every other message: the usual turn; with a vibe set, its places are re-ranked within the asked kind and the best
  match about as near leads whatever card the model put first (an introvert asking «кофе» gets the calmer café first,
  walks.vibe_order); every card and every row «Ещё N мест рядом» carries the line of its evidence.
* with no vibe set and none stated, the turn is exactly walks.dialog.take_turn's.

The model never decides a facet: it reads the request as before (it may only narrow) and writes the text; the facets,
their evidence and the order are code's."""

from __future__ import annotations

from dataclasses import replace
from datetime import datetime

# `_search`: the dialogue's own search, run here for the reading of «под мой вайб» (walks.dialog has no other entry)
from .dialog import Outcome, TurnEnv, _search, take_turn
from .dialog_chips import refine_chips, start_chips
from .dialog_nlu import detect, restore, tidy
from .dialog_types import DialogState, Turn
from .intent import parse_rules
from .llm import Deadline
from .models import IntentResult
from .profile import Profile
from .retrieve import is_night
from .vibe import (
    asks_vibe,
    focused,
    lead_sentence,
    ranked_facets,
    stated_vibe,
    unset_sentence,
    vibe_line,
    vibe_match,
    with_stated,
)

# «под мой вайб» looks across these kinds: everything one goes out to, nothing one runs an errand to (no pharmacy, no
# bank, no shop), no children's playground (the profile's «с детьми» brings the children's places in as usual)
VIBE_KINDS = (
    "park_garden",
    "viewpoint",
    "attraction_landmark",
    "museum_gallery",
    "culture_theatre_cinema",
    "coworking_library",
    "cafe",
    "restaurant",
    "bar_nightlife",
    "entertainment",
    "sport",
    "mall",
)


def vibe_reading(text: str, when: datetime | None) -> IntentResult:
    """The reading of «под мой вайб»: the rules' own reading of the time and the company, every kind of VIBE_KINDS, no
    kind wished (the vibe orders them; the lead names no kind)."""
    rules = parse_rules(text, when)
    intent = rules.intent.model_copy(update={"categories": list(VIBE_KINDS)})
    note = "; ".join(filter(None, [rules.note, "вайб → места всех видов, порядок по вайбу"]))
    return IntentResult(intent=intent, parser="rules", note=note)


def _unset(state: DialogState, lang: str) -> Outcome:
    """No vibe is stored or stated: where to set it, in one sentence; nothing is searched, the request stays."""
    conv = state.conversation
    chips = (
        start_chips(lang)
        if conv is None
        else refine_chips(conv.intent, conv.constraints, state.shown, lang)
    )
    turn = Turn(
        kind="clarify",
        lang=lang,  # type: ignore[arg-type]
        reply=unset_sentence(lang),
        chips=chips,
        origin=(state.lat, state.lon),
    )
    return Outcome(turn, state.model_copy(update={"lang": lang, "turns": state.turns + 1}))


def _lined(out: Outcome, weights: dict[str, float], *, lead: bool = False) -> Outcome:
    """Every card and every row («Ещё N мест рядом») of a search with the line of its evidence; `lead`: the reply opens
    with the facets the cards have."""
    res = out.result
    if res is None or out.turn.kind != "places":
        return out
    lang = out.turn.lang
    intent = res.intent.intent
    day, kids = not is_night(intent, res.when), intent.with_kids
    recs = {r.poi.id: r for r in res.recs}
    have: set[str] = set()
    for place in out.turn.places:
        if (rec := recs.get(place.id)) is not None:
            place.vibe = vibe_line(rec.poi, rec.people, weights, lang, day=day, kids=kids)
            have |= set(vibe_match(rec.poi, rec.people, weights, day=day, kids=kids)[1])
    cands = {c.poi.id: c for c in res.retrieval.candidates}
    for row in out.turn.more:
        if (c := cands.get(row.id)) is not None:
            row.vibe = vibe_line(c.poi, c.people, weights, lang, day=day, kids=kids)
    if lead:
        facets = [f for f in ranked_facets(weights) if f in have]
        out.turn.reply = f"{lead_sentence(facets, lang)} {out.turn.reply}"
    return out


def take_vibe_turn(state: DialogState, message: str, env: TurnEnv | None = None) -> Outcome:
    """walks.dialog.take_turn with the person's vibe: the profile's, with the axis the words state («интроверту») put
    over it for this message only (never stored)."""
    env = env or TurnEnv()
    text = restore(tidy(message))
    stated = stated_vibe(text)
    if stated:
        base = env.profile or Profile()
        env = replace(env, profile=base.model_copy(update={"vibe": with_stated(base.vibe, stated)}))
    weights = dict(env.profile.vibe) if env.profile is not None else {}
    if (stated or asks_vibe(text)) and not parse_rules(text, env.when).intent.categories:
        lang = env.language or detect(text, state.lang)
        if not weights or env.profile is None:
            return _unset(state, lang)
        searched = replace(env, profile=env.profile.model_copy(update={"vibe": focused(weights)}))
        reading = (vibe_reading(text, env.when), Deadline())
        return _lined(_search(state, searched, lang, text, None, reading), weights, lead=True)
    out = take_turn(state, message, env)
    return _lined(out, weights) if weights else out
