"""Before / after metrics of the relevance expansion (museums, kids indoor, viewpoints, opening hours).

`data/poi_enriched_v1_stats.json` freezes the enriched dataset of 2026-10-16 (OSM + Overture + Wikipedia, 2178
records) so every later build can be compared with it: `python -m collect.metrics --freeze data/poi.enriched.json`
writes it (only ever run on a dataset built before the expansion; the file is committed).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

try:
    from collect.overpass_poi import CATEGORIES, pct, write_json
except ImportError:  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from collect.overpass_poi import CATEGORIES, pct, write_json

DATA = Path(__file__).resolve().parents[1] / "data"
V1_PATH = DATA / "poi_enriched_v1_stats.json"

# Indoor categories as the app sees them (app/walks/weather.py INDOOR_CATEGORIES).
INDOOR = ("museum_gallery", "culture_theatre_cinema", "entertainment", "mall", "coworking_library", "cafe")
KIDS_RX = re.compile(r"детск|kids|children|игров\w+\s+(?:центр|комнат|зон)|батут|trampolin|мимори|планета\s+икс|"
                     r"интерактив|лего|lego|планетари|planetari|зоопарк|аквариум|цирк|контактн", re.I)


def is_kids_indoor(rec: dict) -> bool:
    """An indoor place aimed at / suited for children: entertainment, museum, theatre or cinema with a kids signal
    (taxonomy `for_kids`, an OSM `indoor_play` / museum=children tag, or a kids word in the name or description)."""
    if rec["category"] not in ("entertainment", "museum_gallery", "culture_theatre_cinema"):
        return False
    tags = set(rec.get("tags") or [])
    if "for_kids=yes" in tags or "leisure=indoor_play" in tags or "museum=children" in tags:
        return True
    if rec["category"] == "entertainment" and "leisure=playground" in tags:  # indoor playground (indoor=yes)
        return True
    return bool(KIDS_RX.search(f"{rec['name']} {rec.get('description') or ''}"))


def summarize(records: list[dict]) -> dict:
    per = {c: [r for r in records if r["category"] == c] for c in CATEGORIES}
    hours = sum(1 for r in records if r["opening_hours"])
    real = sum(1 for r in records if r["description_source"] in ("osm", "wikipedia"))
    return {
        "total": len(records),
        "per_category": {c: len(v) for c, v in per.items()},
        "kids_playground_outdoor": len(per["kids_playground"]),
        "kids_indoor": sum(1 for r in records if is_kids_indoor(r)),
        "indoor_places": sum(1 for r in records if r["category"] in INDOOR),
        "with_opening_hours": hours,
        "pct_opening_hours": pct(hours, len(records)),
        "pct_opening_hours_museum_gallery": pct(sum(1 for r in per["museum_gallery"] if r["opening_hours"]),
                                                len(per["museum_gallery"])),
        "with_real_description": real,
        "pct_real_description": pct(real, len(records)),
        "ids": sorted(r["id"] for r in records),
        "names": {r["id"]: r["name"] for r in sorted(records, key=lambda r: r["id"])},
    }


def load_v1(path: Path = V1_PATH) -> dict:
    return json.loads(path.read_text(encoding="utf-8"))


def sample_new(records: list[dict], v1_ids: set[str], n: int = 10) -> list[dict]:
    """n new records, round-robin over their categories (highest-priority categories first), id order inside."""
    order = ["museum_gallery", "entertainment", "viewpoint", "culture_theatre_cinema", "attraction_landmark",
             "park_garden", "coworking_library", "sport", "cafe", "mall"]
    groups = {c: [r for r in records if r["category"] == c and r["id"] not in v1_ids] for c in order}
    out: list[dict] = []
    while len(out) < n and any(groups.values()):
        for c in order:
            if groups[c] and len(out) < n:
                out.append(groups[c].pop(0))
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--freeze", metavar="POI_JSON", help="write data/poi_enriched_v1_stats.json from this file")
    args = parser.parse_args(argv)
    if args.freeze:
        records = json.loads(Path(args.freeze).read_text(encoding="utf-8"))
        write_json(V1_PATH, summarize(records))
        print(f"frozen {len(records)} records -> {V1_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
