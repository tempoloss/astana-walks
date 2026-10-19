"""The person's vibe over the cards of an answer (walks.pipeline). The model picks and writes the cards and may lead with
any of them (Starbucks for an introvert and an extrovert alike); with a vibe set, the place of the wished kind that
answers the vibe best among those at most NEAR_EXTRA_MIN farther on foot than the nearest of them leads, when it
answers the vibe better than the model's first card. The model's own text of every other card stays; a place the model
left out comes as the template's card, in the place of the last card the request does not require
(walks.generate.required_cards), the way a required card does. The pick carries every mark of the wish the first card
has (halal, a diet, Wi-Fi), breaks no weather / time rule and is no coffee shop for a meal.

An errand (the nearest that works leads), a plan in stages (its own order), a request with no named kind, a place asked
about (it leads) and an answer with no vibe set stay exactly as they were."""

from __future__ import annotations

from collections.abc import Callable, Mapping

from .attributes import coffee_shop
from .chains import distinct
from .generate import MAX_RECS, _breaks_rules, required_cards
from .models import Candidate, Intent, Recommendation
from .radius import INFO_ABOUT
from .vibe import vibe_match
from .wish_rank import _marks
from .wishes import errand

NEAR_EXTRA_MIN = 3  # the vibe may lead with a place this many minutes farther on foot than the nearest of its kind


def vibe_pick(
    cands: list[Candidate],
    intent: Intent,
    suits: Callable[[Candidate], float],
    marks: set[str],
) -> Candidate | None:
    """The candidate of the wished kind that answers the vibe best (`suits`) among those at most NEAR_EXTRA_MIN farther
    on foot than the nearest of them (the rank order breaks a tie): one with every wish mark of `marks`, no broken
    rule, no coffee shop for a meal."""
    mine = [
        c
        for c in cands
        if c.poi.category in intent.wished
        and marks <= _marks(c)
        and not _breaks_rules(c)
        and not (intent.eat and coffee_shop(c.poi))
    ]
    if not mine:
        return None
    reach = min(c.walk_min for c in mine) + NEAR_EXTRA_MIN
    return max((c for c in mine if c.walk_min <= reach), key=suits)


def vibe_first(
    recs: list[Recommendation],
    cands: list[Candidate],
    intent: Intent,
    weights: Mapping[str, float],
    make: Callable[[Candidate], Recommendation],
    *,
    day: bool,
) -> list[Recommendation]:
    """The cards with the vibe's pick (`vibe_pick`) first when it answers the vibe better than the first card does and
    has evidence to show (a match above 0 is a facet its line names): a place the data say nothing of is never moved.
    `make` writes the card of a place the model left out; `day`: before the night (walks.vibe.evidence_of). `recs`
    themselves when nothing moves."""
    if not weights or not recs or not intent.wished or intent.plan_order or errand(intent.wished):
        return recs
    need = required_cards(cands, intent)
    if any(INFO_ABOUT in c.reasons for c in need):
        return recs

    def suits(x: Candidate | Recommendation) -> float:
        return vibe_match(x.poi, x.people, weights, day=day, kids=intent.with_kids)[0]

    lead = next((c for c in cands if c.poi.id == recs[0].poi.id), None)
    pick = vibe_pick(cands, intent, suits, _marks(lead) if lead is not None else set())
    if pick is None or suits(pick) <= max(suits(recs[0]), 0.0):
        return recs
    first = next((r for r in recs if r.poi.id == pick.poi.id), None) or make(pick)
    out = distinct([first, *recs])
    if len(out) > MAX_RECS:
        kept = {c.poi.id for c in need}
        spare = next((i for i in range(len(out) - 1, 0, -1) if out[i].poi.id not in kept), None)
        if spare is None:
            return recs
        del out[spare]
    return out
