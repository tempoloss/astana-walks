"""What the records of the places in range say about a wish they can only partly confirm: how many food places carry a
halal mark and how many places of the requested kinds have a step-free entrance. The data are thin, so the count (not a
promise) is what the answer says: «отмечен у 1 из 24 мест рядом» or «в данных ничего нет»."""

from __future__ import annotations

from datetime import datetime
from typing import NamedTuple

from .attributes import halal_signal, wheelchair_access
from .models import POI, Candidate, Intent
from .radius import FOOD_KINDS, haversine_m, reachable_radius_m, travel_share
from .supply import supply_counts


class Marks(NamedTuple):
    halal_marked: int = 0
    halal_checked: int = 0
    step_free_marked: int = 0
    step_free_checked: int = 0


def count_marks(scored: list[Candidate], intent: Intent) -> Marks:
    """Halal among the food places that stayed in range, a step-free entrance among the places of the requested kinds."""
    requested = set(intent.categories)
    food = [c for c in scored if c.poi.category in FOOD_KINDS]
    asked = [c for c in scored if not requested or c.poi.category in requested]
    return Marks(
        halal_marked=sum(halal_signal(c.poi) for c in food),
        halal_checked=len(food),
        step_free_marked=sum(wheelchair_access(c.poi) == "yes" for c in asked),
        step_free_checked=len(asked),
    )


def supply_nearby(
    pois: list[POI], lat: float, lon: float, intent: Intent, local: datetime, stroll: bool
) -> tuple[int, int]:
    """The dataset's supply inside the radius the time budget gives in ordinary weather (walks.supply): not the
    weather cap, the dialogue's narrowing or the exclusions, so it stays a fact about the city, not the ranker."""
    radius = reachable_radius_m(intent.time_budget_min, intent.mode, False, travel_share(stroll))
    near = [
        p
        for p in pois
        if p.category != "transit_station" and haversine_m(lat, lon, p.lat, p.lon) <= radius
    ]
    return supply_counts(near, intent.categories, local)
