"""Variety within one dialogue: a place already shown is not offered again while other places answer the request
(unless the message names it), and an unnamed record («Парк / сквер», «Детская площадка») comes after the places of
its kind that have a name of their own."""

from __future__ import annotations

from .models import Candidate
from .radius import INFO_ABOUT


def generic_last(cands: list[Candidate]) -> list[Candidate]:
    """Each unnamed record moved right after the last named place of its kind (the rest of the order stays)."""
    out = list(cands)
    for c in [c for c in cands if c.poi.name_generated]:
        i = out.index(c)
        last = max(
            (
                j
                for j, x in enumerate(out)
                if x.poi.category == c.poi.category and not x.poi.name_generated
            ),
            default=-1,
        )
        if last > i:
            out.insert(last, out.pop(i))
    return out


def fresh_first(cands: list[Candidate], seen: list[str], wished: frozenset[str]) -> list[Candidate]:
    """The candidates without the places this dialogue showed before, unless the message names one (`INFO_ABOUT`), it
    is of a kind the person asked for and no new place of that kind is left (the wish beats variety: «музей?» shows the
    only museum again, never a café first), or nothing else is left; then the unnamed records after the named ones."""
    shown = set(seen)

    def new(c: Candidate) -> bool:
        return c.poi.id not in shown or INFO_ABOUT in c.reasons

    kinds = {c.poi.category for c in cands if new(c)}
    if not kinds:
        return generic_last(cands)
    return generic_last(
        [c for c in cands if new(c) or (c.poi.category in wished and c.poi.category not in kinds)]
    )


FOOD_KINDS = frozenset({"restaurant", "cafe", "fast_food"})


def priced_kinds(categories: list[str], budget: str) -> list[str]:
    """The data hold no prices, so «подешевле / подороже» can change only the KIND of a place to eat: fast food and a
    café are cheap by nature, a restaurant is the pricier one. Any other request has no such lever ([]): the chip is not
    offered there (walks.dialog_chips)."""
    if not set(categories) & FOOD_KINDS or "bar_nightlife" in categories:
        return []
    return {"low": ["fast_food", "cafe"], "high": ["restaurant"]}.get(budget, [])
