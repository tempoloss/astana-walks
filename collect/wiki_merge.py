"""Merge data/wiki_places.json (Wikidata / Wikipedia places) into the enriched POI list.

A place from `wiki_places.json` is
  * skipped when a record already carries its Wikidata item (`wikidata_id`);
  * a duplicate of an existing record when one lies close with a similar name (tier A: same category, <= SAME_CAT_M,
    name score >= SAME_CAT_SCORE; tier B: any category, <= DUP_M, score >= DUP_SCORE); the record gets the Wikidata
    item + Wikipedia extract (match method `wikipedia_list`) when the match is strong enough (`strong`), nothing
    else changes (id, category, coordinates stay);
  * otherwise a new record `wikidata/Q…` with `source: "wikidata"`.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field

from collect.names import name_score
from collect.overpass_poi import haversine_m

DUP_M = 300.0
DUP_SCORE = 75.0
SAME_CAT_M = 150.0
SAME_CAT_SCORE = 60.0
ENRICH_SCORE = 88.0  # any tier
ENRICH_SAME_CAT_SCORE = 70.0  # tier A
ENRICH_NEAR_M, ENRICH_NEAR_SCORE = 50.0, 75.0  # on top of each other, any category
LICENSE_NOMINATIM = "ODbL-1.0"


@dataclass
class WikiMergeLog:
    already_known: int = 0
    enriched_existing: list[dict] = field(default_factory=list)
    duplicate_not_enriched: list[dict] = field(default_factory=list)
    added: list[dict] = field(default_factory=list)  # slim log rows of the new records


def place_names(pl: dict) -> list[str]:
    return list(dict.fromkeys([pl["name"], *pl["names"].values()]))


def best_duplicate(pl: dict, grid, rec_names: Callable[[dict], list[str]]) -> tuple[dict, float, float, bool] | None:
    """(record, distance m, name score, same category) of the best existing duplicate, same-category first."""
    names = place_names(pl)
    best = None
    for rec in grid.near(pl["lat"], pl["lon"]):
        dist = haversine_m(rec["lat"], rec["lon"], pl["lat"], pl["lon"])
        if dist > DUP_M:
            continue
        same = rec["category"] == pl["category"]
        score = name_score(rec_names(rec), names)
        ok = (same and dist <= SAME_CAT_M and score >= SAME_CAT_SCORE) or score >= DUP_SCORE
        if ok and (best is None or (same, score, -dist) > (best[3], best[2], -best[1])):
            best = (rec, dist, score, same)
    return best


def strong(dist: float, score: float, same_category: bool) -> bool:
    """Sure enough that the Wikidata item is the existing record (and not a neighbour) to attach it."""
    return (score >= ENRICH_SCORE or (same_category and score >= ENRICH_SAME_CAT_SCORE)
            or (dist <= ENRICH_NEAR_M and score >= ENRICH_NEAR_SCORE))


def entity_of(pl: dict) -> dict:
    labels = {k.split(":", 1)[1]: v for k, v in pl["names"].items()}
    return {"qid": pl["qid"], "labels": labels, "wikipedia": pl.get("wikipedia", {})}


def wiki_meta(meta: dict) -> dict:
    return {"snapshot_date": meta["snapshot_date"], "licenses": meta["licenses"]}


def new_record(pl: dict, meta: dict, category_ru: dict, fs: Callable) -> dict:
    snap = meta["snapshot_date"]
    kind = category_ru[pl["category"]]
    desc = f"{kind} «{pl['name']}» в Астане. Часы работы и подробности в Wikidata не указаны."
    names = {"name": pl["name"], **pl["names"]}
    wd = fs("wikidata", meta["licenses"]["wikidata"], snap, qid=pl["qid"], found_via=pl["found_via"])
    rec = {
        "id": f"wikidata/{pl['qid']}",
        "name": pl["name"],
        "name_generated": False,
        "names": names,
        "lat": pl["lat"],
        "lon": pl["lon"],
        "category": pl["category"],
        "tags": [f"wikidata={pl['qid']}", *(f"wikidata_class={c}" for c in pl["classes"])],
        "opening_hours": None,
        "website": None,
        "phone": None,
        "address": None,
        "wheelchair": None,
        "internet_access": None,
        "outdoor_seating": None,
        "description": None,
        "description_auto": desc,
        "description_source": "derived",
        "source": "wikidata",
        "collected_at": f"{snap}T00:00:00+00:00",
        "sources": ["wikidata"],
        "overture_id": None,
        "hours_state": "unknown",
        "brand": None,
        "brand_wikidata": None,
    }
    rec["field_sources"] = {"name": wd, "category": wd, "lat": wd, "lon": wd}
    if pl["coord_source"] == "nominatim":
        geo = fs("nominatim", LICENSE_NOMINATIM, snap, geocode_confidence=pl["geocode_confidence"],
                 method="search by Wikidata label inside Astana")
        rec["field_sources"]["lat"] = rec["field_sources"]["lon"] = geo
        rec["coord_quality"] = {"status": "geocoded", "geocode_confidence": pl["geocode_confidence"]}
    elif pl["coord_source"] == "wikipedia_coordinates":
        art = fs("wikipedia", meta["licenses"]["wikipedia"], snap, note="coordinates of the article")
        rec["field_sources"]["lat"] = rec["field_sources"]["lon"] = art
    rec["field_sources"]["description_auto"] = {"source": "derived", "license": "n/a", "snapshot_date": snap}
    return rec
