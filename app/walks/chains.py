"""The cards of one answer: one per place (branches of one chain, a place recorded twice), in the order of the wish."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from .attributes import coffee_shop
from .hours import poi_hours
from .models import POI, Candidate, ClusterLog, Intent, Recommendation, WeatherInfo
from .names import NAME_RATIO_MIN, best_ratio, name_keys, same_place_name
from .radius import FAR_ON_FOOT, haversine_m, travel_minutes
from .shelter import asks_outdoors
from .weather import INDOOR_CATEGORIES, harsh
from .wishes import FAR_WALK_MIN, GAP_SUBKINDS, errand, errand_order, of_subkind, subkind_of

CLUSTER_RADIUS_M = 150  # same-chain points this close to the nearest one are one card


def collapse_duplicates(cands: list[Candidate]) -> tuple[list[Candidate], list[ClusterLog]]:
    """One card per chain: a candidate whose normalised name is similar (rapidfuzz ratio >= NAME_RATIO_MIN) to the
    nearest member's, in the same category and within CLUSTER_RADIUS_M of it, collapses into that nearest member,
    which records how many others it stands for (`nearby_same`). Also returns what was merged, for the log."""
    reps: list[tuple[Candidate, set[str]]] = []
    merged: list[list[str]] = []
    for c in sorted(cands, key=lambda c: (c.distance_m, c.poi.id)):
        keys = name_keys(c.poi)
        for i, (rep, rep_keys) in enumerate(reps):
            apart = haversine_m(rep.poi.lat, rep.poi.lon, c.poi.lat, c.poi.lon)
            if rep.poi.category == c.poi.category and apart <= CLUSTER_RADIUS_M:
                ratio = best_ratio(keys, rep_keys)
                if ratio >= NAME_RATIO_MIN:
                    merged[i].append(f"{c.poi.name} ({c.poi.id}, {apart:.0f} м, {ratio:.0f}%)")
                    break
        else:
            reps.append((c, keys))
            merged.append([])
    kept = [
        rep.model_copy(update={"nearby_same": len(m)})
        for (rep, _), m in zip(reps, merged, strict=True)
    ]
    log = [
        ClusterLog(kept_id=rep.poi.id, kept_name=rep.poi.name, merged=m)
        for (rep, _), m in zip(reps, merged, strict=True)
        if m
    ]
    return kept, log


def distinct(recs: list[Recommendation]) -> list[Recommendation]:
    """The answer's cards without a second card of one place: the same id, or a name a person cannot tell apart (two
    branches of Coffee BOOM, one café recorded twice), whatever added it (the model, a back-fill, «поближе», a place
    shown again); the first stays."""
    out: list[Recommendation] = []
    for r in recs:
        if not any(r.poi.id == x.poi.id or same_place_name(r.poi, x.poi) for x in out):
            out.append(r)
    return out


def without_twins(recs: list[Recommendation], keep: list[Candidate]) -> list[Recommendation]:
    """The cards without a namesake of a card that must stay (`keep`): two «Alatau City Bank» are one card, and it is
    the one the request requires (the cash machine of walks.generate.required_cards), not the branch the model picked."""
    ids = {c.poi.id for c in keep}
    return [
        r for r in recs if r.poi.id in ids or not any(same_place_name(r.poi, c.poi) for c in keep)
    ]


def lead_order(
    recs: list[Recommendation], intent: Intent, weather: WeatherInfo | None
) -> list[Recommendation]:
    """The cards in the order of the wish (stable otherwise): a kind the person named first (the model may not lead
    «музей?» with a café), a meal place before a coffee shop when food is asked («го пожрать», whatever the model
    picked), and an outdoor wish («что посмотреть», «погулять») led by an outdoor place unless the weather is truly
    harsh (the model may not move it indoors «из-за непогоды» at +1 °C)."""
    wished = set() if intent.plan_order else set(intent.wished)
    held = asks_outdoors(intent) and not harsh(weather)
    return sorted(
        recs,
        key=lambda r: (
            bool(wished) and r.poi.category not in wished,
            intent.eat and coffee_shop(r.poi),
            held and r.poi.category in INDOOR_CATEGORIES,
        ),
    )


def walk_order(
    recs: list[Recommendation], intent: Intent, local: datetime, night: bool
) -> list[Recommendation]:
    """The routed cards of an errand in the order of the walking metres they show (wishes.errand_order), and «чуть
    дальше» (found beyond the declared radius) never on the nearest card of its kind: nobody declared a radius for a
    pharmacy, and next to a farther card it reads as «farther than the others». Other answers are left as they are."""
    if not errand(intent.wished or intent.categories):
        return recs
    recs = errand_order(recs, frozenset(intent.wished), local, night, sub=subkind_of(intent))
    nearest: dict[str, Recommendation] = {}
    for r in recs:
        if r.poi.category not in nearest or r.distance_m < nearest[r.poi.category].distance_m:
            nearest[r.poi.category] = r
    for r in nearest.values():
        if r.padding == "expanded":
            r.padding = "none"
    return recs


# «about an hour»: a walk whose cards (the way to each and its stay) fill less than this share of the stated time gets
# more stops, so an hour is not one monument for half an hour
FILL_SHARE = 2 / 3


def fill_time(
    recs: list[Recommendation],
    cands: list[Candidate],
    intent: Intent,
    make: Callable[[Candidate], Recommendation],
    max_cards: int,
) -> list[Recommendation]:
    """The cards of a walk the person gave a time to («прогулка на час», «about an hour»), with the next places of
    the kinds they asked for (`cands` in rank order, `make` writes the card) while the cards fill less than
    FILL_SHARE of that time: two or three stops for an hour. Any other answer is left as it is."""
    if not (recs and intent.time_stated and asks_outdoors(intent)):
        return recs
    out, wished = list(recs), set(intent.wished)
    for c in cands:
        filled = sum(r.walk_min + r.time_on_site_min for r in out)
        if len(out) >= max_cards or filled >= FILL_SHARE * intent.time_budget_min:
            break
        if c.poi.category in wished and not any(
            c.poi.id == r.poi.id or same_place_name(c.poi, r.poi) for r in out
        ):
            out.append(make(c))
    return out


def asked_on_the_way(
    recs: list[Recommendation],
    cands: list[Candidate],
    intent: Intent,
    make: Callable[[Candidate], Recommendation],
) -> list[Recommendation]:
    """Along the way to a bookmark («something nice to see on my way back to the hotel»): every card is of a kind the
    person asked for; one of another kind (an entertainment centre the model added) gives its place to the next asked
    one of `cands` (in the order toward the bookmark, walks.bookmarks.prefer_toward), when there is one."""
    wished = set(intent.wished)
    spare = (
        c
        for c in cands
        if c.poi.category in wished
        and not any(c.poi.id == r.poi.id or same_place_name(c.poi, r.poi) for r in recs)
    )
    return [
        r
        if not wished or r.poi.category in wished
        else make(alt)
        if (alt := next(spare, None))
        else r
        for r in recs
    ]


def far_subkind(
    recs: list[Recommendation],
    pois: list[POI],
    intent: Intent,
    origin: tuple[float, float],
    local: datetime,
    make: Callable[[Candidate], Recommendation],
    max_cards: int,
) -> list[Recommendation]:
    """The nearest record of the sub-kind asked (a dentist, a children's clinic, a cash machine) as the last card when
    no card is one, however far it is: the answer names it (walks.dialog_facts.subkind_gap), and its card leads the way
    there in 2GIS / Yandex. It takes the place of the last card when the answer is full."""
    sub = subkind_of(intent)
    if sub not in GAP_SUBKINDS or not recs or any(of_subkind(r.poi, sub) for r in recs):
        return recs
    far = [(haversine_m(*origin, p.lat, p.lon), p) for p in pois if of_subkind(p, sub)]
    if not far:
        return recs
    meters, poi = min(far, key=lambda x: (x[0], x[1].id))
    card = make(
        Candidate(
            poi=poi,
            distance_m=round(meters),
            walk_min=travel_minutes(meters, "walk"),
            travel_min=travel_minutes(meters, intent.mode),
            hours_state=poi_hours(poi, local).state,
            score=0.0,
            reasons=[FAR_ON_FOOT] if travel_minutes(meters, "walk") >= FAR_WALK_MIN else [],
        )
    )
    return [*recs[: max_cards - 1], card]
