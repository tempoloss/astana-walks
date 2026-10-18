"""The final recommendations against the REAL walking legs: retrieval and the model judge distance by a straight line
times a street factor, the router knows the actual route (a river, a rail line or a fence can make 700 m into 1.9 km). A
card whose real way is too long for the request, or leaves less on site than the place's minimum stay, is replaced by
the best candidate that does fit; when nothing fits the card stays and the route says honestly that it does not.

The card's minutes on site follow the mini-route (`sync_stays`): the route is the one place that knows how the stays
were shrunk to fit the budget."""

from __future__ import annotations

from collections.abc import Callable

from .generate import _breaks_rules, template_rec
from .models import Candidate, Intent, Recommendation, RoutePlan, WeatherInfo
from .radius import INFO_ABOUT, NEAREST_FAR, one_way_limit_min
from .stay import TIGHT_FIT_MARGIN_MIN, min_stay

Point = tuple[float, float]
Leg = Callable[[Point, Point], tuple[int, int, str]]
MAX_EXTRA_LEGS = 4  # routing requests spent on looking for replacements


def apply_leg(rec: Recommendation, leg: tuple[int, int, str]) -> None:
    meters, minutes, method = leg
    rec.distance_m, rec.walk_min, rec.travel_min = meters, minutes, minutes
    rec.walk_method = method  # type: ignore[assignment]


def _fits(poi_category: str, one_way_min: int, intent: Intent) -> bool:
    """A real one-way walk inside the request's limit that leaves at least the minimum stay (within the tight-fit
    margin) of the budget."""
    if one_way_min > one_way_limit_min(intent):
        return False
    over = min_stay(poi_category) - (intent.time_budget_min - 2 * one_way_min)
    return over <= TIGHT_FIT_MARGIN_MIN


def replace_unreachable(
    recs: list[Recommendation],
    cands: list[Candidate],
    intent: Intent,
    weather: WeatherInfo | None,
    leg_fn: Leg,
    user: Point,
) -> list[tuple[str, str]]:
    """Replace, in place, every card whose real walk does not fit (see the module doc) by the next candidate whose
    routed leg fits; returns (replaced id, new id) pairs. A card of a kind that is absent nearby (NEAREST_FAR) is the
    answer by design and stays."""
    by_id = {c.poi.id: c for c in cands}
    used = {r.poi.id for r in recs}
    swapped: list[tuple[str, str]] = []
    legs_left = MAX_EXTRA_LEGS
    limit = one_way_limit_min(intent)
    for i, rec in enumerate(recs):
        own = by_id.get(rec.poi.id)
        if (
            own is None
            or NEAREST_FAR in own.reasons
            or INFO_ABOUT
            in own.reasons  # the place the user asked about stays whatever the route says
            or any(r == "halal" or r.startswith("diet:") for r in own.reasons)
            or _fits(rec.poi.category, rec.walk_min, intent)
        ):
            continue
        pool = [
            x
            for x in cands
            if x.poi.id not in used
            and x.padding == own.padding
            and not _breaks_rules(x)
            and NEAREST_FAR not in x.reasons
            and x.walk_min
            <= limit  # the straight-line estimate already fits; only the real route is unknown
        ]
        pool.sort(
            key=lambda x: x.poi.category != rec.poi.category
        )  # the same kind first; rank order otherwise
        for x in pool:
            if legs_left == 0:
                break
            legs_left -= 1
            leg = leg_fn(user, (x.poi.lat, x.poi.lon))
            if not _fits(x.poi.category, leg[1], intent):
                continue
            new = template_rec(x, intent, weather, cands)
            new.padding = x.padding
            apply_leg(new, leg)
            recs[i] = new
            used.add(x.poi.id)
            swapped.append((rec.poi.id, x.poi.id))
            break
    return swapped


def sync_stays(recs: list[Recommendation], route: RoutePlan | None) -> None:
    """The «на месте ~N мин» of a card is the stay the route allots after shrinking it to the budget; a card the route
    dropped keeps its own."""
    if route is None:
        return
    stay = dict(zip(route.stops, route.stay_min, strict=True))
    for r in recs:
        if r.poi.id in stay:
            r.time_on_site_min = stay[r.poi.id]
