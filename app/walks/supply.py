"""What the dataset holds near a request, apart from what the ranker did with it.

`supply_counts` says how many places of the requested kinds there are among the places inside the radius that the time
budget gives, and how many of them have opening hours the data confirm. It is a fact about the dataset: closed-now,
the weather cap, the dialogue's narrowing and exclusions do not change it. The city layer (walks.demand) turns the two
numbers into «no place of the kind nearby» and «places exist, but no confirmed hours»."""

from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime

from .hours import poi_hours
from .models import POI

OTHER_CATEGORY = "other"
# used, not strolled (a cash machine, a pharmacy, a food shop, a clinic, a post office): a walk destination on demand,
# not generic supply - only a request that names one counts or retrieves it
UTILITY_KINDS = frozenset({"money", "pharmacy", "grocery", "clinic", "post"})


def supply_counts(
    pois_in_radius: Iterable[POI], requested: Iterable[str], local: datetime
) -> tuple[int, int]:
    """(places of the requested kinds, of them with confirmed hours). No requested kind: every place except «other»
    and the utilities counts. Hours are confirmed when the data give a verdict (open / closed, a public holiday
    included). The caller leaves transit stations out: they are never recommended."""
    kinds = set(requested)
    total = confirmed = 0
    for p in pois_in_radius:
        if (
            p.category not in kinds
            if kinds
            else p.category == OTHER_CATEGORY or p.category in UTILITY_KINDS
        ):
            continue
        total += 1
        hours = poi_hours(p, local)
        confirmed += hours.state != "unknown" or bool(hours.note)
    return total, confirmed
