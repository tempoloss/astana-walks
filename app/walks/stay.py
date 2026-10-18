"""Time on site: the typical stay per category, and the budget check that drops (or flags) places whose minimum
stay does not fit what is left after the round trip."""

from __future__ import annotations

from .models import Candidate

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


def min_stay(category: str) -> int:
    return STAY_RANGE_MIN.get(category, STAY_RANGE_MIN["other"])[0]


def fit_stay_budget(cands: list[Candidate], budget_min: int) -> tuple[list[Candidate], int]:
    """Drop candidates whose category minimum stay exceeds the budget left after walking there and back by more
    than TIGHT_FIT_MARGIN_MIN (a cinema in a 90-minute window); one that is over by up to that margin stays,
    flagged TIGHT_FIT so the card says «впритык». Only when nothing would remain they are all kept, flagged
    MIN_STAY_OVER_BUDGET. Returns (kept, number dropped)."""
    kept: list[Candidate] = []
    for c in cands:
        over = min_stay(c.poi.category) - (budget_min - 2 * c.travel_min)
        if over <= 0:
            kept.append(c)
        elif over <= TIGHT_FIT_MARGIN_MIN:
            kept.append(c.model_copy(update={"reasons": [*c.reasons, TIGHT_FIT]}))
    if kept or not cands:
        return kept, len(cands) - len(kept)
    return [c.model_copy(update={"reasons": [*c.reasons, MIN_STAY_OVER_BUDGET]}) for c in cands], 0
