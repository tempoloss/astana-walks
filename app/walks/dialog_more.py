"""«Ещё N мест рядом»: under the three cards of a search answer, the further candidates of the same wish, the nearest
first. Code only: nothing here asks a model, so the payload of the generation step and the three
cards stay exactly as they were. Each row is checked like a card (the state of its hours at the arrival time, minutes
and metres from the retrieval)."""

from __future__ import annotations

from .dialog_extras import decorate
from .dialog_place import place_from_candidate
from .dialog_types import Place
from .models import Candidate, Result
from .radius import ERRAND_KINDS

MORE_MAX = 7
HOURS_RANK = {
    "open": 0,
    "unknown": 1,
    "closed": 2,
}  # an errand's list: confirmed open, then unknown hours, then closed
# a candidate retrieval padded in (a kind the person did not name, a substitute for the weather) is never a row of
# «ещё»: the list is more of the same wish
PADDED = frozenset({"backfill", "substituted"})
BY_DISTANCE, OPEN_FIRST = (
    "distance",
    "open_first",
)  # `Turn.more_order`: what the label under the button says


def order_key(c: Candidate, errand: bool) -> tuple:
    """The nearest first by the walking minutes shown, then metres; an errand: confirmed open, then unknown hours, then
    closed, the nearest within each group."""
    return (HOURS_RANK[c.hours_state] if errand else 0, c.travel_min, c.distance_m, c.poi.id)


def more_places(res: Result, shown: list[Place], lang: str) -> tuple[list[Place], str]:
    """Up to `MORE_MAX` places of the request that the answer did not show, the nearest first by the walking minutes
    the row says (then metres): the three cards are the ranking's pick, this list is read by distance, and it says so.
    An errand (a pharmacy, a cash machine, a shop, a bed for the night) lists only its own kinds and keeps its
    open-first order: confirmed open, then unknown hours, then closed, the nearest within each group. A route the
    person spelled out stop by stop has no «more». Returns the rows and the order they are in ('' with no rows)."""
    intent = res.intent.intent
    if intent.plan_order:
        return [], ""
    wished = set(intent.wished)
    errand = bool(wished & ERRAND_KINDS)
    taken = {p.id for p in shown}
    pool = [
        c
        for c in res.retrieval.candidates
        if c.poi.id not in taken
        and c.padding not in PADDED
        and (not errand or c.poi.category in wished)
    ]
    pool.sort(key=lambda c: order_key(c, errand))
    out: list[Place] = []
    for c in pool[:MORE_MAX]:
        place = place_from_candidate(c, lang=lang, when=res.when, mode=intent.mode)
        decorate(place, c.poi, lang, res.when)
        out.append(place)
    return out, (OPEN_FIRST if errand else BY_DISTANCE) if out else ""
