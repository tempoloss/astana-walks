"""Time on site: the typical stay per category, the clamps of a card's stay (its category's range, then the route
budget), and the budget check that drops (or flags) places whose minimum stay does not fit what is left after the
round trip."""

from __future__ import annotations

from .models import Candidate, Intent

# Typical time on site per category, minutes (lo, hi): the generation step clamps the model's value into this
# range, and retrieval drops places whose lo does not fit the budget that is left after the round trip.
STAY_RANGE_MIN = {
    "cafe": (30, 60),
    "restaurant": (45, 90),
    "fast_food": (15, 30),
    "bar_nightlife": (30, 120),
    "museum_gallery": (60, 90),
    "attraction_landmark": (15, 30),
    "viewpoint": (10, 20),
    "park_garden": (30, 60),
    "kids_playground": (30, 60),
    "entertainment": (60, 120),
    "mall": (30, 90),
    "culture_theatre_cinema": (120, 150),
    "coworking_library": (60, 180),
    "sport": (45, 90),
    "other": (15, 45),
}
TIGHT_FIT_MARGIN_MIN = (
    15  # a minimum stay up to this much over the time left is kept, flagged "tight"
)
MIN_STAY_OVER_BUDGET = (
    "min_stay_over_budget"  # reason code: kept although its minimum stay does not fit
)
TIGHT_FIT = "tight_fit"  # reason code: minimum stay exceeds the time left, but only slightly
NAMED_OVER_BUDGET = (
    "named_over_budget"  # reason code: a kind the person named is kept, its stay is longer
)


def min_stay(category: str) -> int:
    return STAY_RANGE_MIN.get(category, STAY_RANGE_MIN["other"])[0]


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


def fit_stay_budget(
    cands: list[Candidate], budget_min: int, wished: frozenset[str] = frozenset()
) -> tuple[list[Candidate], int]:
    """Drop candidates whose category minimum stay exceeds the budget left after walking there and back by more
    than TIGHT_FIT_MARGIN_MIN (a cinema in a 90-minute window); one that is over by up to that margin stays,
    flagged TIGHT_FIT so the card says «впритык». A kind the person NAMED is never replaced by this rule: when every
    place of it would go, they stay, flagged NAMED_OVER_BUDGET (the card says the usual stay is longer than the time
    left). Only when nothing would remain at all they are all kept, flagged MIN_STAY_OVER_BUDGET. Returns (kept,
    number dropped)."""
    kept: list[Candidate] = []
    for c in cands:
        over = min_stay(c.poi.category) - (budget_min - 2 * c.travel_min)
        if over <= 0:
            kept.append(c)
        elif over <= TIGHT_FIT_MARGIN_MIN:
            kept.append(c.model_copy(update={"reasons": [*c.reasons, TIGHT_FIT]}))
    if kept or not cands:
        saved = _named_over_budget(cands, kept, wished)
        return [*kept, *saved], len(cands) - len(kept) - len(saved)
    return [c.model_copy(update={"reasons": [*c.reasons, MIN_STAY_OVER_BUDGET]}) for c in cands], 0


def _named_over_budget(
    cands: list[Candidate], kept: list[Candidate], wished: frozenset[str]
) -> list[Candidate]:
    """The places of a named kind of which none fit the time, flagged."""
    have = {c.poi.category for c in kept}
    return [
        c.model_copy(update={"reasons": [*c.reasons, NAMED_OVER_BUDGET]})
        for c in cands
        if c.poi.category in wished and c.poi.category not in have
    ]
