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
MONEY_CATEGORY = "money"  # used, not strolled: it counts only when asked for


def supply_counts(
    pois_in_radius: Iterable[POI], requested: Iterable[str], local: datetime
) -> tuple[int, int]:
    """(places of the requested kinds, of them with confirmed hours). No requested kind: every place except «other»
    and money counts. Hours are confirmed when the data give a verdict (open / closed, a public holiday included). The
    caller leaves transit stations out: they are never recommended."""
    kinds = set(requested)
    total = confirmed = 0
    for p in pois_in_radius:
        if p.category not in kinds if kinds else p.category in (OTHER_CATEGORY, MONEY_CATEGORY):
            continue
        total += 1
        hours = poi_hours(p, local)
        confirmed += hours.state != "unknown" or bool(hours.note)
    return total, confirmed
