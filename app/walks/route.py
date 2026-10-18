"""Mini-route: up to 3 stops, nearest-neighbour from the user, with a time-budget check."""

from __future__ import annotations

from collections.abc import Callable

from .models import Recommendation, RoutePlan
from .radius import haversine_m, plan_slot, travel_minutes

MAX_STOPS = 3
MIN_STAY_MIN = 10  # never shrink a stop below this to make the loop fit

Point = tuple[float, float]
# (meters, minutes, method) for one leg a -> b; method is "valhalla" / "straight" / "estimate"
LegFn = Callable[[Point, Point], tuple[int, int, str]]


def estimate_leg_fn(mode: str) -> LegFn:
    """Modelled leg: straight line x street factor at the mode's average speed (no network)."""

    def leg(a: Point, b: Point) -> tuple[int, int, str]:
        d = haversine_m(a[0], a[1], b[0], b[1])
        return round(d), travel_minutes(d, mode), "estimate"

    return leg


def _pt(r: Recommendation) -> Point:
    return (r.poi.lat, r.poi.lon)


def nearest_neighbour_order(
    lat: float, lon: float, stops: list[Recommendation]
) -> list[Recommendation]:
    left = list(stops)
    order: list[Recommendation] = []
    cur: Point = (lat, lon)
    while left:
        nxt = min(left, key=lambda r: (haversine_m(cur[0], cur[1], r.poi.lat, r.poi.lon), r.poi.id))
        left.remove(nxt)
        order.append(nxt)
        cur = _pt(nxt)
    return order


def _straight_total(lat: float, lon: float, order: list[Recommendation]) -> float:
    total, cur = 0.0, (lat, lon)
    for r in order:
        total += haversine_m(cur[0], cur[1], r.poi.lat, r.poi.lon)
        cur = _pt(r)
    return total + haversine_m(cur[0], cur[1], lat, lon)


def _fit_stays(desired: list[int], available: int) -> list[int] | None:
    """Stay minutes that sum to <= available: the desired ones, or scaled down (>= MIN_STAY_MIN); else None."""
    if sum(desired) <= available:
        return list(desired)
    if available < MIN_STAY_MIN * len(desired):
        return None
    scale = available / sum(desired)
    stays = [max(MIN_STAY_MIN, int(d * scale)) for d in desired]
    while sum(stays) > available:  # the floor at MIN_STAY_MIN can overshoot; trim the longest stay
        i = max(range(len(stays)), key=lambda k: stays[k])
        stays[i] -= 1
    return stays


def _aggregate(methods: list[str]) -> str:
    kinds = set(methods)
    return kinds.pop() if len(kinds) == 1 else "mixed"


def _plan(
    lat: float,
    lon: float,
    order: list[Recommendation],
    budget_min: int,
    dropped: list[str],
    leg_fn: LegFn,
) -> tuple[RoutePlan, bool]:
    """Build a plan for a fixed order. Second value: True when the stays fit the budget without dropping."""
    points: list[Point] = [(lat, lon)] + [_pt(r) for r in order] + [(lat, lon)]
    legs = [
        leg_fn(points[i], points[i + 1]) for i in range(len(points) - 1)
    ]  # last one is the way back
    out_legs, back = legs[:-1], legs[-1]
    travel = sum(m for _, m, _ in legs)
    desired = [r.time_on_site_min for r in order]
    stays = _fit_stays(desired, budget_min - travel)
    feasible = stays is not None
    if stays is None:  # even minimal stays do not fit; report honestly with the minimum
        stays = [min(d, MIN_STAY_MIN) for d in desired]
    total = travel + sum(stays)
    methods = [meth for _, _, meth in legs]
    return RoutePlan(
        stops=[r.poi.id for r in order],
        legs_m=[m for m, _, _ in out_legs],
        legs_min=[t for _, t, _ in out_legs],
        walk_min_total=sum(t for _, t, _ in out_legs),
        return_min=back[1],
        stay_min=stays,
        on_site_min_total=sum(stays),
        shrunk=stays != desired,
        legs_method=methods,
        method=_aggregate(methods),  # type: ignore[arg-type]
        total_min=total,
        budget_min=budget_min,
        fits=total <= budget_min,
        dropped=dropped,
    ), feasible


def build_route(
    lat: float,
    lon: float,
    recs: list[Recommendation],
    mode: str,
    budget_min: int,
    preferred_order: list[str] | None = None,
    leg_fn: LegFn | None = None,
    stage_order: list[str] | None = None,
) -> RoutePlan | None:
    """Order up to MAX_STOPS recommendations and make the round trip fit the time budget.

    Order: nearest neighbour from the user; an LLM-suggested order is used only if it is a permutation of the
    stops with a strictly shorter straight-line loop. Leg times come from `leg_fn` (real pedestrian routing for
    mode=walk, a modelled estimate otherwise). If the loop does not fit, stays are first shrunk (>= MIN_STAY_MIN
    each), and only then stops are dropped; which stop to drop is judged on straight-line estimates so that the
    search does not trigger routing requests.
    """
    recs = recs[:MAX_STOPS]
    if not recs:
        return None
    leg_fn = leg_fn or estimate_leg_fn(mode)
    memo: dict[tuple[Point, Point], tuple[int, int, str]] = {}

    def cached_leg(a: Point, b: Point) -> tuple[int, int, str]:
        if (a, b) not in memo:
            memo[(a, b)] = leg_fn(a, b)
        return memo[(a, b)]

    order = nearest_neighbour_order(lat, lon, recs)
    if (
        stage_order
    ):  # «сначала поесть, потом музей»: the user's order of the stops beats the shortest loop
        order = sorted(order, key=lambda r: plan_slot(r.poi.category, stage_order))
    elif (
        preferred_order
        and len(recs) > 1
        and sorted(preferred_order) == sorted(r.poi.id for r in recs)
    ):
        by_id = {r.poi.id: r for r in recs}
        cand = [by_id[i] for i in preferred_order]
        if _straight_total(lat, lon, cand) < _straight_total(lat, lon, order):
            order = cand
    dropped: list[str] = []
    plan, feasible = _plan(lat, lon, order, budget_min, dropped, cached_leg)
    estimate = estimate_leg_fn(mode)
    while not feasible and len(order) > 1:
        best = min(
            range(len(order)),
            key=lambda i: (
                _plan(lat, lon, order[:i] + order[i + 1 :], budget_min, [], estimate)[0].total_min,
                -i,
            ),
        )
        dropped.append(order[best].poi.id)
        order = order[:best] + order[best + 1 :]
        plan, feasible = _plan(lat, lon, order, budget_min, dropped, cached_leg)
    return plan
