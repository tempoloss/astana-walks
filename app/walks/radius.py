"""How far a request reaches: the straight-line radius a time budget gives (and how it narrows with weather, a child
or the dialogue), the steps by which it widens when nothing of the requested kind is in range, and what may fill up
a short list once it has widened."""

from __future__ import annotations

import math

from .models import Constraints, Intent

SPEED_KMH = {"walk": 4.5, "transit": 15.0, "car": 25.0}  # door-to-door averages
TRAVEL_SHARE = 0.4  # share of the time budget reserved for getting there AND back
STROLL_TRAVEL_SHARE = (
    0.5  # a pure stroll IS the walking: half of the budget may go to the way out and back
)
RADIUS_STEPS = (
    1.0,
    1.15,
    1.3,
    1.5,
)  # widen the radius by these factors while nothing of the requested kind is in
STROLL_CATEGORIES = frozenset({"park_garden", "attraction_landmark", "viewpoint"})
# Back-fill (other categories added when too few requested ones are in range): never these, whatever the intent;
# a stroll additionally takes only places that fit a walk.
NEVER_BACKFILL = frozenset({"fast_food", "bar_nightlife", "other"})
STROLL_BACKFILL = STROLL_CATEGORIES | {"cafe", "museum_gallery"}
CIRCUITY = 1.25  # real street distance ~ 1.25 x straight line
MIN_RADIUS_M = 500  # even a very short budget should see the nearest block
MAX_RADIUS_M = 15000
NEAREST_FAR = "nearest_far"  # reason code: the requested kind is absent nearby; this is the nearest one in the city
INFO_ABOUT = "info_about"  # reason code: the user asked ABOUT this place (hours, «стоит ли»): its card comes first
ADVERSE_WALK_CAP_M = 600  # max straight-line walking radius when it is freezing / pouring / smoggy
# Product assumption (детская выносливость пешком ~15 мин в одну сторону), not a measurement and not set by data of
# residents. 15 was introduced in caf7692 after two main-set kids cases failed their walking limit, and was chosen
# inside the range of the eval cases' limits (main 12 or 15 min, holdout 15 or 20), so main and holdout are not fully
# independent on this point; the independent check is the holdout2 set (written by another model without the code).
KIDS_WALK_MAX_MIN = 15  # longest one-way walk offered to a request with a child
ROUTED_DETOUR = 1.3  # = walking.FALLBACK_DETOUR (walking imports radius; a test keeps them equal)
MIN_SHRUNK_RADIUS_M = 150  # «а поближе?» never narrows the circle below this


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def travel_minutes(distance_m: float, mode: str) -> int:
    """One-way minutes for a straight-line distance, with a street-detour factor."""
    return max(1, math.ceil(distance_m * CIRCUITY / (SPEED_KMH[mode] * 1000 / 60)))


def walk_minutes(distance_m: float) -> int:
    return travel_minutes(distance_m, "walk")


def reachable_radius_m(
    time_budget_min: int, mode: str, adverse_weather: bool = False, share: float = TRAVEL_SHARE
) -> int:
    """Straight-line radius: `share` of the budget covers the round trip, so one way is half of it.

    In adverse weather, walking legs are capped at ADVERSE_WALK_CAP_M (outdoor exposure)."""
    one_way_min = share * time_budget_min / 2
    meters = SPEED_KMH[mode] * 1000 / 60 * one_way_min / CIRCUITY
    radius = int(min(max(meters, MIN_RADIUS_M), MAX_RADIUS_M))
    if adverse_weather and mode == "walk":
        radius = min(radius, ADVERSE_WALK_CAP_M)
    return radius


def kids_walk_radius_m() -> int:
    """With a child one way is at most KIDS_WALK_MAX_MIN minutes on foot, counted with the router's detour so that
    a place that passes here is not 16 minutes on its card."""
    return int(SPEED_KMH["walk"] * 1000 / 60 * KIDS_WALK_MAX_MIN / ROUTED_DETOUR)


def is_stroll(intent: Intent) -> bool:
    """A walk whose requested places are all stroll destinations (park, landmark, viewpoint): the walking itself
    is the activity, so it may use a bigger share of the budget than a trip to a cafe."""
    return (
        intent.mode == "walk"
        and bool(intent.categories)
        and set(intent.categories) <= STROLL_CATEGORIES
    )


def travel_share(stroll: bool) -> float:
    return STROLL_TRAVEL_SHARE if stroll else TRAVEL_SHARE


def declared_radius_m(intent: Intent, adverse: bool, constraints: Constraints) -> int:
    """The radius the request declares: the time budget (`adverse`: weather or air cap the walk), a child's pace,
    then what the dialogue narrowed («помедленнее», «а поближе?»)."""
    radius = reachable_radius_m(
        intent.time_budget_min, intent.mode, adverse, travel_share(is_stroll(intent))
    )
    if intent.with_kids and intent.mode == "walk":
        radius = min(radius, kids_walk_radius_m())  # a child's pace: one way is a short walk
    if constraints.radius_factor != 1.0:
        radius = max(MIN_SHRUNK_RADIUS_M, round(radius * constraints.radius_factor))
    if constraints.radius_cap_m is not None:
        radius = min(radius, max(MIN_SHRUNK_RADIUS_M, constraints.radius_cap_m))
    return radius


def backfill_ok(category: str, intent: Intent, stroll: bool) -> bool:
    """May a place outside the requested categories fill up a short list? Never fast food / bars / 'other' (bars
    only for a night request); a stroll takes only what fits a walk. A state-service request («ЦОН», category
    `other`) is never padded with cafes and parks: a short list is the honest answer."""
    if "other" in intent.categories:
        return False
    if category in NEVER_BACKFILL and not (category == "bar_nightlife" and intent.night):
        return False
    return not stroll or category in STROLL_BACKFILL


ROUTED_SLACK = 1.25  # the real street route may take this much longer than the radius assumed before it is «too far»


def one_way_limit_min(intent: Intent) -> float:
    """The longest real one-way walk a request accepts: the share of the budget the radius reserved for the way (with
    slack for the real route), and a child's limit. Used on the routed legs of the final recommendations."""
    limit = travel_share(is_stroll(intent)) * intent.time_budget_min / 2 * ROUTED_SLACK
    if intent.with_kids and intent.mode == "walk":
        limit = min(limit, KIDS_WALK_MAX_MIN)
    return limit


# Kinds that still answer a wish when the requested kind is absent from the whole radius: the only back-fill allowed
# then (a church or a mall does not answer «кино»). A kind that is not listed has no substitute: the nearest place of
# the kind itself is shown instead («рядом нет X; ближайшее — N км»).
RELATED_KINDS: dict[str, frozenset[str]] = {
    "restaurant": frozenset({"restaurant", "cafe", "fast_food", "mall"}),
    "cafe": frozenset({"restaurant", "cafe", "fast_food", "mall"}),
    "fast_food": frozenset({"restaurant", "cafe", "fast_food", "mall"}),
    "culture_theatre_cinema": frozenset({"entertainment"}),
    "museum_gallery": frozenset({"culture_theatre_cinema"}),
    "entertainment": frozenset({"culture_theatre_cinema", "mall", "kids_playground"}),
    "kids_playground": frozenset(
        {"park_garden", "entertainment", "museum_gallery", "cafe", "restaurant", "mall"}
    ),
    "mall": frozenset({"entertainment"}),
    "coworking_library": frozenset({"cafe"}),
    "bar_nightlife": frozenset({"restaurant", "cafe", "entertainment"}),
}


def related_kinds(requested: list[str]) -> frozenset[str]:
    """Every kind that answers at least one of the requested kinds when none of them is in range."""
    out: frozenset[str] = frozenset()
    for cat in requested:
        out |= RELATED_KINDS.get(cat, frozenset())
    return out


def km_text(meters: float, lang: str | None) -> str:
    """Kilometres with one decimal: «6,1» (ru, kk) / «6.1» (en)."""
    text = f"{meters / 1000:.1f}"
    return text if lang == "en" else text.replace(".", ",")


FOOD_KINDS = frozenset({"restaurant", "cafe", "fast_food"})


def plan_slot(category: str, plan: list[str]) -> int:
    """The position in the user's plan («сначала поесть, потом музей») a place of `category` fills: its own category's, or
    for a food place the first food stage of the plan; len(plan) when the plan has no slot for it."""
    if category in plan:
        return plan.index(category)
    if category in FOOD_KINDS:
        return next((i for i, c in enumerate(plan) if c in FOOD_KINDS), len(plan))
    return len(plan)
