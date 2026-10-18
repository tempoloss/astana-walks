"""One occurrence listed by several sources becomes one record: the first-party source wins, the others are recorded
in `also_listed` (source + link). Two records are one occurrence when their starts are within 30 minutes (standing
exhibits: the same place), their titles agree and their venues agree (same POI, same street + house, agreeing venue
names, or coordinates within 150 m).
"""

from __future__ import annotations

from rapidfuzz import fuzz

from collect.events import model
from collect.events.venues import (
    address_key,
    addresses_agree,
    haversine_m,
    keys_agree,
    skeleton_tokens,
    venue_keys,
)

PRIORITY = ("alem.ai", "qazaqconcert.kz", "youticket.kz", "inastana.kz", "sxodim.com")
START_WINDOW_S = 30 * 60
SAME_PLACE_M = 150.0
TOKEN_RATIO = 80


def _rank(source: str) -> int:
    return PRIORITY.index(source) if source in PRIORITY else len(PRIORITY)


def titles_agree(a: str, b: str) -> bool:
    ta, tb = skeleton_tokens(a), skeleton_tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    return any(len(x) >= 5 and len(y) >= 5 and fuzz.ratio(x, y) >= TOKEN_RATIO for x in ta for y in tb)


def venues_agree(a: dict, b: dict) -> bool:
    if a.get("poi_id") and a.get("poi_id") == b.get("poi_id"):
        return True
    if addresses_agree(address_key(a.get("address")), address_key(b.get("address"))):
        return True
    if keys_agree(venue_keys(a["name"]), venue_keys(b["name"])):
        return True
    if a.get("lat") is not None and b.get("lat") is not None:
        return haversine_m(a["lat"], a["lon"], b["lat"], b["lon"]) <= SAME_PLACE_M
    return False


def same_occurrence(a: dict, b: dict) -> bool:
    if a["kind"] != b["kind"] or a["kind"] in ("run", "sessions"):
        return False
    if not (venues_agree(a["venue"], b["venue"]) and titles_agree(a["title"], b["title"])):
        return False
    if a["kind"] == "standing":
        return True
    sa, sb = model.parse_iso(a["start"]), model.parse_iso(b["start"])
    return abs((sa - sb).total_seconds()) <= START_WINDOW_S


def _adopt_coordinates(twin: dict, dup: dict) -> None:
    """A first-party record without coordinates takes the duplicate's own page coordinates, with that page's
    evidence (the coordinates stay verifiable against the page they came from)."""
    tv, dv = twin["venue"], dup["venue"]
    if tv.get("coords_source") == "page" or dv.get("coords_source") != "page":
        return
    tv.update(lat=dv["lat"], lon=dv["lon"], coords_source="page")
    twin["evidence"] += [x for x in dup["evidence"] if x["field"] == "coords"]


def dedupe(events: list[dict]) -> list[dict]:
    kept: list[dict] = []
    for e in sorted(events, key=lambda x: (_rank(x["source"]), x["id"])):
        twin = next((k for k in kept if k["source"] != e["source"] and same_occurrence(k, e)), None)
        if twin is None:
            kept.append(e)
        else:
            twin["also_listed"].append({"source": e["source"], "url": e["url"]})
            _adopt_coordinates(twin, e)
    return kept
