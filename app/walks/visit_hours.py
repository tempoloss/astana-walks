"""What the hours say about THIS visit, not about the moment of the request: a place that is closed now but opens
before you arrive, and a place that closes while you would still be there."""

from __future__ import annotations

from datetime import datetime, timedelta

from opening_hours import OpeningHours

from .hours import is_24_7, poi_hours, to_local_naive
from .i18n import t
from .models import POI

CHECK_AFTER_CLOSE = timedelta(minutes=1)


def visit_note(
    poi: POI,
    when: datetime,
    travel_min: int,
    stay_min: int,
    state_on_arrival: str,
    lang: str | None,
) -> str:
    """One sentence, or '': «закрыто сейчас, но к вашему приходу откроется» / «скоро закроется, в 00:00». Only for a
    place the hours call open on arrival (the verdict of the card), never for 24/7 or a place without a schedule."""
    raw = poi.opening_hours
    if state_on_arrival != "open" or not raw or is_24_7(raw):
        return ""
    local = to_local_naive(when)
    arrival = local + timedelta(minutes=travel_min)
    if poi_hours(poi, local).state == "closed":
        return t("note_opens_by_arrival", lang, t=f"{arrival:%H:%M}")
    try:
        nxt = OpeningHours(raw).next_change(arrival)
    except (ValueError, OverflowError, TypeError):
        return ""
    if nxt is None or nxt - arrival > timedelta(minutes=stay_min):
        return ""
    if poi_hours(poi, nxt + CHECK_AFTER_CLOSE).state != "closed":
        return ""
    return t(
        "note_closes_soon", lang, t=f"{nxt:%H:%M}", n=round((nxt - arrival).total_seconds() / 60)
    )
