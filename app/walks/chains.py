"""The cards of one answer: one per place (branches of one chain, a place recorded twice), in the order of the wish."""

from __future__ import annotations

from .models import Candidate, ClusterLog, Intent, Recommendation, WeatherInfo
from .names import NAME_RATIO_MIN, best_ratio, name_keys, same_place_name
from .radius import haversine_m
from .shelter import asks_outdoors
from .weather import INDOOR_CATEGORIES, harsh

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


def lead_order(
    recs: list[Recommendation], intent: Intent, weather: WeatherInfo | None
) -> list[Recommendation]:
    """The cards in the order of the wish (stable otherwise): a kind the person named first (the model may not lead
    «музей?» with a café), and an outdoor wish («что посмотреть», «погулять») led by an outdoor place unless the
    weather is truly harsh (the model may not move it indoors «из-за непогоды» at +1 °C)."""
    wished = set() if intent.plan_order else set(intent.wished)
    held = asks_outdoors(intent) and not harsh(weather)
    return sorted(
        recs,
        key=lambda r: (
            bool(wished) and r.poi.category not in wished,
            held and r.poi.category in INDOOR_CATEGORIES,
        ),
    )
