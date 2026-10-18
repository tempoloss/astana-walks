"""A question ABOUT a place («какие часы у Хан Шатыра», «стоит ли идти в музей сейчас»): that place's card comes first,
with its facts, wherever it is."""

from __future__ import annotations

from datetime import datetime, timedelta

from .feedback import FeedbackIndex
from .hours import poi_hours
from .models import POI, Candidate, Intent
from .names import names_place
from .radius import INFO_ABOUT, MAX_RADIUS_M, haversine_m, travel_minutes, walk_minutes

INFO_SCORE = 50.0  # the place asked about outranks everything
TRANSIT_CATEGORY = "transit_station"


def info_first(
    top: list[Candidate],
    pois: list[POI],
    lat: float,
    lon: float,
    intent: Intent,
    local: datetime,
    feedback: FeedbackIndex | None,
    declared_m: int,
) -> list[Candidate]:
    """The place the user asks ABOUT, first in `top` with its facts (hours state by the data, source), wherever it is
    (up to MAX_RADIUS_M), whether the ranking liked it or not. A place already in the list moves up; a missing one is
    built from the record (even closed: «закрыто» is the answer). Nothing matches: the list stays as it is."""
    named = [
        (p, d)
        for p in pois
        if p.category != TRANSIT_CATEGORY
        and names_place(p, intent.info_about)
        and (d := haversine_m(lat, lon, p.lat, p.lon)) <= MAX_RADIUS_M
    ]
    if not named:
        return top
    p, d = min(named, key=lambda pd: (pd[1], pd[0].id))
    have = next((c for c in top if c.poi.id == p.id), None)
    if have is None:
        travel = travel_minutes(d, intent.mode)
        arrival = local + timedelta(minutes=travel)
        hours = poi_hours(p, arrival)
        have = Candidate(
            poi=p,
            distance_m=round(d),
            walk_min=walk_minutes(d),
            travel_min=travel,
            hours_state=hours.state,
            hours_note=hours.note,
            hours_issue=hours.issue,
            score=INFO_SCORE,
            reasons=[],
            people=feedback.evidence(p.id, arrival) if feedback else None,
            padding="expanded" if d > declared_m else "none",
        )
    first = have.model_copy(update={"reasons": [*have.reasons, INFO_ABOUT], "score": INFO_SCORE})
    return [first, *(c for c in top if c.poi.id != p.id)]
