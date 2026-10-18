"""House addresses and street positions of Astana from OpenStreetMap, for the page's address search (app/web/geocode.py).

ONE Overpass request for the Astana area: every node / way / relation with `addr:housenumber` + `addr:street`, and the
named roads. The answer is reduced to what an address search needs: the streets (every spelling OSM has for one
street, one position) and the houses (street, number, centre). Nothing else of the elements is kept.

  data/gazetteer/astana_addresses.json   {source, license, attribution, retrieved_at, counts, streets, houses}
    streets: [{"id": 0, "names": ["проспект Мәңгілік Ел", "Мәңгілік Ел даңғылы", ...], "lat": …, "lon": …, "houses": N}]
    houses:  [[street id, "55/22", lat, lon], …]      (centre of the building, 5 decimals ~ 1 m)

Two names belong to one street when a road of OSM carries both (`name`, `name:ru`, `name:kk`, `name:en`, `alt_name`) or a
house says `addr:street` of a name some road carries. A street with one name in several far-apart places stays one
street here: its position is the point of it nearest to the middle of all of them, which lies on the street.

Licence: ODbL 1.0, © OpenStreetMap contributors (data/gazetteer/ATTRIBUTION.md). All HTTP goes through collect.net
(UA astana-walks/0.1 (hackathon; an8kk.sa@gmail.com), ≤ 1 request/s, on-disk cache).

Usage (repo root): uv run python -m collect.osm_addresses [--out data/gazetteer/astana_addresses.json]
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from collections import defaultdict
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collect.net import default_net
from collect.overpass_poi import LAT_RANGE, LON_RANGE, TIMEOUT, coords, overpass, resolve_area

ROOT = Path(__file__).resolve().parents[1]
OUT_PATH = ROOT / "data" / "gazetteer" / "astana_addresses.json"
ROADS = "motorway|trunk|primary|secondary|tertiary|unclassified|residential|living_street|pedestrian|road"
NAME_KEYS = ("name", "name:ru", "name:kk", "name:en", "alt_name", "official_name")
PLACES = 5  # decimals of a point


def build_query(area_id: int) -> str:
    return (
        f"[out:json][timeout:{TIMEOUT}];\n"
        f"area({area_id})->.a;\n(\n"
        '  nwr(area.a)["addr:housenumber"]["addr:street"];\n'
        f'  way(area.a)["highway"~"^({ROADS})$"]["name"];\n'
        ");\nout center tags;\n"
    )


class Names:
    """Union-find over exact name spellings: the spellings of one street are one set."""

    def __init__(self) -> None:
        self.parent: dict[str, str] = {}

    def find(self, name: str) -> str:
        self.parent.setdefault(name, name)
        root = name
        while self.parent[root] != root:
            root = self.parent[root]
        while self.parent[name] != root:
            self.parent[name], name = root, self.parent[name]
        return root

    def union(self, names: list[str]) -> None:
        first = self.find(names[0])
        for other in names[1:]:
            self.parent[self.find(other)] = first


def road_names(tags: dict) -> list[str]:
    seen: list[str] = []
    for key in NAME_KEYS:
        value = " ".join((tags.get(key) or "").split())
        if value and value not in seen:
            seen.append(value)
    return seen


def inside(lat: float, lon: float) -> bool:
    return LAT_RANGE[0] <= lat <= LAT_RANGE[1] and LON_RANGE[0] <= lon <= LON_RANGE[1]


def nearest_to_middle(points: list[tuple[float, float]]) -> tuple[float, float]:
    mid_lat = statistics.median(p[0] for p in points)
    mid_lon = statistics.median(p[1] for p in points)
    return min(points, key=lambda p: (p[0] - mid_lat) ** 2 + ((p[1] - mid_lon) * 0.63) ** 2)


def reduce(elements: list[dict]) -> tuple[list[dict], list[list]]:
    """(streets, houses) of the elements of the request."""
    names = Names()
    roads: list[tuple[list[str], tuple[float, float]]] = []
    houses: list[tuple[str, str, tuple[float, float]]] = []
    for el in elements:
        tags = el.get("tags") or {}
        at = coords(el)
        if not at or not inside(*at):
            continue
        if "highway" in tags:
            spellings = road_names(tags)
            if spellings:
                names.union(spellings)
                roads.append((spellings, at))
        else:
            street = " ".join((tags.get("addr:street") or "").split())
            number = " ".join((tags.get("addr:housenumber") or "").split())
            if street and number:
                houses.append((street, number, at))
    points: dict[str, list[tuple[float, float]]] = defaultdict(list)
    spellings_of: dict[str, list[str]] = defaultdict(list)
    for spellings, at in roads:
        root = names.find(spellings[0])
        points[root].append(at)
        for s in spellings:
            if s not in spellings_of[root]:
                spellings_of[root].append(s)
    count: dict[str, int] = defaultdict(int)
    for street, _, at in houses:
        root = names.find(street)
        points[root].append(at)
        count[root] += 1
        if street not in spellings_of[root]:
            spellings_of[root].append(street)
    ids: dict[str, int] = {}
    streets: list[dict] = []
    for root in sorted(points, key=lambda r: spellings_of[r][0]):
        lat, lon = nearest_to_middle(points[root])
        ids[root] = len(streets)
        streets.append(
            {
                "id": len(streets),
                "names": spellings_of[root],
                "lat": round(lat, PLACES),
                "lon": round(lon, PLACES),
                "houses": count[root],
            }
        )
    rows: dict[tuple[int, str], list] = {}
    for street, number, (lat, lon) in houses:
        key = (ids[names.find(street)], number.casefold())
        rows.setdefault(key, [key[0], number, round(lat, PLACES), round(lon, PLACES)])
    return streets, sorted(rows.values(), key=lambda r: (r[0], r[1]))


def build(data: dict, retrieved_at: str, area_id: int) -> dict:
    streets, houses = reduce(data.get("elements", []))
    return {
        "source": "OpenStreetMap, Overpass API",
        "license": "ODbL 1.0",
        "attribution": "© OpenStreetMap contributors",
        "url": "https://www.openstreetmap.org/copyright",
        "retrieved_at": retrieved_at,
        "area": f"relation of Astana, area id {area_id}",
        "use": "address search (app/web/geocode.py): street and house positions; nothing is stored per visitor",
        "counts": {"elements": len(data.get("elements", [])), "streets": len(streets), "houses": len(houses)},
        "streets": streets,
        "houses": houses,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--out", type=Path, default=OUT_PATH)
    args = ap.parse_args(argv)
    net = default_net()
    area_id, bounds = resolve_area(net)
    print(f"[area] id={area_id} bbox={bounds}", file=sys.stderr)
    data, fetched_at = overpass(net, build_query(area_id))
    stamp = datetime.fromtimestamp(fetched_at, UTC).replace(microsecond=0).isoformat()
    out = build(data, stamp, area_id)
    if not out["houses"] or not out["streets"]:
        raise SystemExit("the answer holds no addresses: nothing written")
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(out, ensure_ascii=False, separators=(",", ":")) + "\n", encoding="utf-8")
    print(json.dumps(out["counts"]), f"retrieved_at={stamp} -> {args.out}", file=sys.stderr)
    net.log_summary("osm_addresses")
    return 0


if __name__ == "__main__":
    sys.exit(main())
