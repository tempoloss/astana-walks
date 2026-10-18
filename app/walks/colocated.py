"""Overture-only records that share one coordinate (to 5 decimals, ~1 m): the position is a placeholder (a mall, a
whole airport, a district centre), not the place, so every card made from it would show the same distance and walking
time. Of such a group the best-scoring record stays, marked `SHARED_COORD` (the card says its position is
approximate and its confidence is low); the others are dropped and logged like the merged chains."""

from __future__ import annotations

from collections import defaultdict

from .models import Candidate, ClusterLog

SHARED_COORD = "shared_coord"  # reason code of the record that stands for its group
DECIMALS = 5


def _overture_only(c: Candidate) -> bool:
    sources = c.poi.sources or [c.poi.source]
    return "overture" in sources and "osm" not in sources


def collapse_shared_coordinates(
    cands: list[Candidate],
) -> tuple[list[Candidate], list[ClusterLog]]:
    """(candidates with one record per shared Overture coordinate, what was dropped)."""
    groups: dict[tuple[float, float], list[Candidate]] = defaultdict(list)
    for c in cands:
        if _overture_only(c):
            groups[(round(c.poi.lat, DECIMALS), round(c.poi.lon, DECIMALS))].append(c)
    dropped: set[str] = set()
    marked: dict[str, Candidate] = {}
    log: list[ClusterLog] = []
    for group in groups.values():
        if len(group) < 2:
            continue
        keep = max(group, key=lambda c: (c.score, -c.distance_m, c.poi.id))
        others = [c for c in group if c is not keep]
        dropped.update(c.poi.id for c in others)
        marked[keep.poi.id] = keep.model_copy(update={"reasons": [*keep.reasons, SHARED_COORD]})
        log.append(
            ClusterLog(
                kept_id=keep.poi.id,
                kept_name=keep.poi.name,
                merged=[f"{c.poi.name} ({c.poi.id}, {c.distance_m} м, same point)" for c in others],
            )
        )
    kept = [marked.get(c.poi.id, c) for c in cands if c.poi.id not in dropped]
    return kept, log
