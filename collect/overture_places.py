"""Overture Maps places for Astana (per-record licences, public S3, anonymous, via DuckDB).

Usage: uv run python -m collect.overture_places [--out data/overture_places.json]

Picks the latest release by listing `release/` on the public bucket (listing goes through collect.net,
cached for a day), reads `theme=places/type=place` with DuckDB `httpfs` filtered by the Astana bbox and
writes every record with its mapped category. The confidence cut-off is NOT applied here (merge.py
applies it and reports the effect); the file keeps the full distribution so the choice stays auditable.
Rerun with the same latest release and bbox is a no-op (output file is the cache).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from collect.net import Net, default_net
    from collect.overpass_poi import write_json
except ImportError:  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from collect.net import Net, default_net
    from collect.overpass_poi import write_json

BUCKET = "overturemaps-us-west-2"
BUCKET_URL = f"https://{BUCKET}.s3.amazonaws.com/"
REGION = "us-west-2"
BBOX = {"lat_min": 50.98, "lat_max": 51.25, "lon_min": 71.25, "lon_max": 71.60}
LICENSE = "per record: see places[].sources[].license (CDLA-Permissive-2.0 | Apache-2.0 | CC0-1.0)"

# 0.7: below it every record in our categories is single-source Meta (no corroboration from Foursquare /
# AllThePlaces / Microsoft), websites are present in <=37% and the share with an OSM counterpart stays flat at
# 0-8%; from 0.7 up non-Meta records (Microsoft/Foursquare/AllThePlaces) appear, website share rises to >=50%, the OSM match rate climbs
# (about 10% -> 15% -> 34%). See the tables in data/coverage_delta.md. False positives (a closed cafe on a
# walk) cost more than missed places, so the cut-off errs on the strict side.
CONFIDENCE_CUTOFF = 0.7

_RELEASE = re.compile(r"^\d{4}-\d{2}-\d{2}\.\d+$")

# Overture taxonomy.primary -> our category. Anything not listed (shops, services, clinics, schools,
# gyms, real estate, ...) is "other": kept in the file, excluded from recommendations by the app.
TAXONOMY_MAP: dict[str, str] = {}


def _add(category: str, *primaries: str) -> None:
    for p in primaries:
        TAXONOMY_MAP[p] = category


_add("cafe", "cafe", "coffee_shop", "bakery", "dessert_shop", "ice_cream_shop", "tea_room", "bubble_tea_shop",
     "smoothie_juice_bar", "chocolatier", "cupcake_shop", "frozen_yogurt_shop")
_add("fast_food", "fast_food_restaurant", "hot_dog_restaurant", "sandwich_shop", "food_truck_stand",
     "burger_restaurant", "pizza_restaurant", "doner_kebab_restaurant", "chicken_restaurant",
     "fish_and_chips_restaurant", "diner")
_add("bar_nightlife", "bar", "lounge", "pub", "irish_pub", "hookah_bar", "brewery", "sports_bar", "beer_bar",
     "cocktail_bar", "hotel_bar", "gastropub", "tapas_bar", "dance_club", "salsa_club", "karaoke_venue")
_add("museum_gallery", "museum", "history_museum", "art_museum", "science_museum", "art_gallery", "childrens_museum",
     "modern_art_museum", "contemporary_art_museum", "civilization_museum", "design_museum", "community_museum",
     "textile_museum", "photography_museum", "sports_museum", "computer_museum", "costume_museum", "state_museum",
     "asian_art_museum", "aviation_museum", "decorative_arts_museum", "planetarium", "observatory")
_add("attraction_landmark", "historic_site", "monument", "castle", "public_plaza", "public_fountain",
     "sculpture_statue", "muslim_place_of_worship", "christian_place_of_worship",
     "jewish_place_of_worship", "roman_catholic_place_of_worship", "memorial_site", "street_art", "palace", "fort",
     "water_feature")
_add("viewpoint", "scenic_viewpoint", "observation_deck", "lookout")
_add("park_garden", "park", "botanical_garden", "garden", "nature_reserve")
_add("kids_playground", "playground")
_add("entertainment", "amusement_park", "arcade", "escape_room", "bowling_alley", "laser_tag", "paintball",
     "zoo", "wildlife_sanctuary", "circus_venue", "aquarium", "water_park", "music_venue", "amusement_attraction",
     "animal_attraction", "petting_zoo", "indoor_playcenter", "go_kart_track", "go_kart_club",
     "miniature_golf_course", "roller_skating_rink", "rock_climbing_gym", "haunted_house", "fairgrounds",
     "pool_billiards", "pool_hall")
_add("mall", "shopping_mall", "department_store")
_add("culture_theatre_cinema", "movie_theater", "theatre_venue", "opera_and_ballet", "performing_arts_venue",
     "cultural_center", "comedy_club", "auditorium", "event_venue", "drive_in_theater")
_add("coworking_library", "library", "coworking_space")
_add("sport", "stadium_arena", "ice_skating_rink", "swimming_pool", "tennis_court", "soccer_field",
     "basketball_court", "volleyball_court", "hockey_field", "race_track")
_add("transit_station", "train_station", "light_rail_station", "metro_station")

# Unlisted *_restaurant primaries (italian_restaurant, sushi_restaurant, ...) are restaurants.
RESTAURANT_HIERARCHY = "restaurant"

# Primaries added to TAXONOMY_MAP in the relevance expansion of 2026-10-17 (the build report counts the records
# they bring; they were `other` before).
NEWLY_MAPPED = frozenset({
    "childrens_museum", "modern_art_museum", "contemporary_art_museum", "civilization_museum", "design_museum",
    "community_museum", "textile_museum", "photography_museum", "sports_museum", "computer_museum", "costume_museum",
    "state_museum", "asian_art_museum", "aviation_museum", "decorative_arts_museum", "planetarium", "observatory",
    "memorial_site", "street_art", "palace", "fort", "water_feature", "amusement_attraction", "animal_attraction",
    "petting_zoo", "indoor_playcenter", "go_kart_track", "go_kart_club", "miniature_golf_course",
    "roller_skating_rink", "rock_climbing_gym", "haunted_house", "fairgrounds", "pool_billiards", "pool_hall",
    "comedy_club", "auditorium", "event_venue", "drive_in_theater",
})

# Taxonomy primaries that say the place is aimed at children.
KIDS_PRIMARIES = frozenset({"indoor_playcenter", "childrens_museum", "playground", "petting_zoo"})

# Overture files many leisure venues under a generic bucket (`arts_and_entertainment`, `sports_and_recreation`,
# `party_and_event_planning`, ...): the venue type is only in the name. For such records, and only for them, a
# word-bounded name pattern may assign a category. One entry = (rule id, taxonomy primaries it may fire on,
# pattern, category, marks the venue as aimed at children). Schools and education centres are not in the buckets:
# "Kids", "Kinder" there are kindergartens and classes, not a place to take a child on a free afternoon.
_LEISURE_BUCKETS = frozenset({
    "arts_and_entertainment", "sports_and_recreation", "sport_or_fitness_facility", "party_and_event_planning",
    "event_or_party_service", "arts_and_crafts_space",
})
_KIDS_WORDS = (r"батут\w*|trampolin\w*|kango|мимори\w*|детск\w+\s+(?:развлек\w+|игров\w+|парк|клуб|центр\s+досуга)|"
               r"планета\s+икс|игров\w+\s+(?:центр|комнат\w*|зон\w*)|лего|lego|контактн\w+\s+зоопарк")
_FUN_WORDS = (r"аттракцион\w*|аквапарк\w*|aquapark|квест\w*|escape|лазер\s?таг|laser\s?tag|боулинг|bowling|"
              r"скалодром\w*|картинг|karting|развлекательн\w+\s+(?:центр|комплекс)|парк\s+развлечений|fun\s?park|"
              r"fame\s+city|лабиринт\s+страха")
_WB = r"(?<![\w])(?:{})(?![\w])"
NAME_RULES: list[tuple[str, frozenset[str], re.Pattern[str], str, bool]] = [
    ("mall_name", frozenset({"shopping", "arts_and_entertainment"}),
     re.compile(r"^\W*(?:торгово[- ]развлекательн\w+\s+(?:центр|комплекс)|торговый\s+(?:центр|дом)|трц|трк|тц)(?![\w])",
                re.I),
     "mall", False),
    ("kids_leisure_name", _LEISURE_BUCKETS, re.compile(_WB.format(_KIDS_WORDS), re.I), "entertainment", True),
    ("leisure_name", _LEISURE_BUCKETS, re.compile(_WB.format(_FUN_WORDS), re.I), "entertainment", False),
    ("museum_name", _LEISURE_BUCKETS, re.compile(r"музе[йяюе]|museum|мұражай|планетари\w*|planetarium", re.I),
     "museum_gallery", False),
]


def taxonomy_hash() -> str:
    """Fingerprint of the category mapping and name rules: the cached output is stale once either changes."""
    rules = [(r[0], sorted(r[1]), r[2].pattern, r[3], r[4]) for r in NAME_RULES]
    payload = json.dumps([sorted(TAXONOMY_MAP.items()), rules, sorted(KIDS_PRIMARIES)])
    return hashlib.sha1(payload.encode()).hexdigest()[:12]


def map_category(primary: str | None, hierarchy: list[str] | None) -> str:
    if not primary:
        return "other"
    if primary in TAXONOMY_MAP:
        return TAXONOMY_MAP[primary]
    if primary == "restaurant" or primary.endswith("_restaurant") or primary in ("steakhouse", "buffet_restaurant"):
        return "restaurant"
    if hierarchy and len(hierarchy) > 1 and hierarchy[1] == RESTAURANT_HIERARCHY:
        return "restaurant"
    return "other"


def classify(primary: str | None, hierarchy: list[str] | None, name: str | None = None) -> tuple[str, str | None, bool]:
    """(category, name rule id or None, aimed at children). Taxonomy first; name rules only for generic buckets."""
    category = map_category(primary, hierarchy)
    kids = primary in KIDS_PRIMARIES
    if category != "other" or not name:
        return category, None, kids
    for rule_id, primaries, rx, cat, rule_kids in NAME_RULES:
        if primary in primaries and rx.search(name):
            return cat, rule_id, kids or rule_kids
    return category, None, kids


def latest_release(net: Net) -> tuple[str, list[str]]:
    resp = net.get(BUCKET_URL, params={"list-type": "2", "prefix": "release/", "delimiter": "/"}, ttl=86400)
    releases = sorted(
        (r for r in re.findall(r"<Prefix>release/([^/<]+)/</Prefix>", resp.text) if _RELEASE.match(r)),
        key=lambda r: tuple(int(x) for x in re.split(r"[-.]", r)),
    )
    if not releases:
        raise RuntimeError(f"no Overture releases listed at {BUCKET_URL}")
    return releases[-1], releases


QUERY = """
SELECT id, confidence, operating_status, basic_category,
       taxonomy.primary AS tax_primary, taxonomy.hierarchy AS tax_hierarchy, taxonomy.alternates AS tax_alternates,
       names.primary AS name_primary,
       element_at(names.common, 'ru')[1] AS name_ru, element_at(names.common, 'kk')[1] AS name_kk,
       element_at(names.common, 'en')[1] AS name_en,
       bbox.xmin AS lon, bbox.ymin AS lat,
       websites, phones, socials,
       brand.names.primary AS brand_name, brand.wikidata AS brand_wikidata,
       addresses, sources
FROM read_parquet('s3://{bucket}/release/{release}/theme=places/type=place/*')
WHERE bbox.xmin BETWEEN {lon_min} AND {lon_max} AND bbox.ymin BETWEEN {lat_min} AND {lat_max}
ORDER BY id
"""


def clean(s: str | None) -> str | None:
    s = (s or "").strip()
    return s or None


# Overture carries some place names as social-media handles / slugified strings («kafel_laminat_astana»,
# «towerpub_lordloft») - underscores are not walking-map typography: split them into words. Not a rename of real
# names: only `_`/`-` runs are touched, so «KFC - Астана» keeps its dash and «Nurlyzhol_vokzaly» becomes readable.
def denormalize(s: str | None) -> str | None:
    if not s:
        return None
    if "_" not in s:
        return s
    out = re.sub(r"[_]+", " ", s).strip()
    return out or None


def to_record(row: tuple, cols: list[str]) -> dict:
    r = dict(zip(cols, row))
    addresses = [
        {k: clean(a.get(k)) for k in ("freeform", "locality", "postcode", "region", "country") if clean(a.get(k))}
        for a in (r["addresses"] or [])
    ]
    names = {"primary": denormalize(clean(r["name_primary"])), "ru": denormalize(clean(r["name_ru"])),
             "kk": denormalize(clean(r["name_kk"])), "en": denormalize(clean(r["name_en"]))}
    name = names["primary"] or names["ru"] or names["en"] or names["kk"]
    category, rule, for_kids = classify(r["tax_primary"], list(r["tax_hierarchy"] or []), name)
    return {
        "id": r["id"],
        "lat": round(r["lat"], 7),
        "lon": round(r["lon"], 7),
        "name": name,
        "names": {k: v for k, v in names.items() if v},
        "categories": {"primary": r["tax_primary"], "alternate": list(r["tax_alternates"] or []),
                       "hierarchy": list(r["tax_hierarchy"] or []), "basic": r["basic_category"]},
        "category": category,
        "category_rule": rule,
        "for_kids": for_kids,
        "confidence": round(r["confidence"], 4) if r["confidence"] is not None else None,
        "operating_status": r["operating_status"],
        "websites": [w for w in (r["websites"] or []) if w],
        "phones": [p for p in (r["phones"] or []) if p],
        "socials": [s for s in (r["socials"] or []) if s],
        "brand": {"name": clean(r["brand_name"]), "wikidata": clean(r["brand_wikidata"])}
        if (r["brand_name"] or r["brand_wikidata"]) else None,
        "addresses": [a for a in addresses if a],
        "sources": [
            {k: s.get(k) for k in ("dataset", "record_id", "update_time", "license") if s.get(k)}
            for s in (r["sources"] or []) if s.get("dataset") and s.get("provider") != "overture"
        ],
    }


def distribution(records: list[dict]) -> dict:
    buckets: dict[str, int] = {}
    for r in records:
        c = r["confidence"]
        key = "none" if c is None else f"{min(int(c * 10), 9) / 10:.1f}-{min(int(c * 10), 9) / 10 + 0.1:.1f}"
        buckets[key] = buckets.get(key, 0) + 1
    return dict(sorted(buckets.items()))


def collect(net: Net, out: Path) -> dict:
    release, releases = latest_release(net)
    if out.exists() and not net.refresh:
        meta = json.loads(out.read_text(encoding="utf-8")).get("meta", {})
        if (meta.get("release") == release and meta.get("bbox") == BBOX
                and meta.get("confidence_cutoff") == CONFIDENCE_CUTOFF
                and meta.get("taxonomy_map_hash") == taxonomy_hash()):
            print(f"[overture] cache hit: release {release} already in {out} (0 requests)", file=sys.stderr)
            return meta
    import duckdb

    print(f"[overture] latest release {release} of {releases}; querying S3 via DuckDB httpfs…", file=sys.stderr)
    con = duckdb.connect()
    con.execute("INSTALL httpfs; LOAD httpfs;")
    con.execute(f"SET s3_region='{REGION}';")
    cur = con.execute(QUERY.format(bucket=BUCKET, release=release, **BBOX))
    cols = [d[0] for d in cur.description]
    records = [to_record(row, cols) for row in cur.fetchall()]
    snapshot = datetime.now(timezone.utc).date().isoformat()
    meta = {
        "release": release, "releases_listed": releases, "bbox": BBOX, "license": LICENSE,
        "snapshot_date": snapshot, "count": len(records),
        "confidence_distribution": distribution(records),
        "confidence_cutoff": CONFIDENCE_CUTOFF,
        "taxonomy_map_hash": taxonomy_hash(),
        "count_per_category": dict(sorted(
            ((c, sum(1 for r in records if r["category"] == c)) for c in {r["category"] for r in records}),
            key=lambda kv: -kv[1])),
        "attribution": "Overture Maps Foundation, https://overturemaps.org (places theme). No theme-level licence: each "
                       "record's contributing dataset and its licence are in `sources[]` (Meta, Microsoft, PinMeTo = "
                       "CDLA-Permissive-2.0; Foursquare = Apache-2.0, NOTICE in data/NOTICE_overture.txt; "
                       "AllThePlaces = CC0-1.0).",
    }
    write_json(out, {"meta": meta, "places": records})
    return meta


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default="data/overture_places.json")
    args = parser.parse_args(argv)
    net = default_net()
    meta = collect(net, Path(args.out))
    net.log_summary("overture")
    print(json.dumps({k: meta[k] for k in ("release", "count", "confidence_distribution", "count_per_category")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
