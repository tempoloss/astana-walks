"""Astana districts (OSM relations, admin_level=6) -> data/districts.geojson.

Usage: uv run python -m collect.districts

One Overpass query through the polite layer (cached). Polygons are assembled from the relation's outer / inner
way members. Licence: ODbL-1.0 (© OpenStreetMap contributors); every feature carries source, licence and the
snapshot date (the Overpass response cache time, so reruns are byte-identical).
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from collect.net import default_net
    from collect.overpass_poi import overpass, resolve_area, write_json
except ImportError:  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from collect.net import default_net
    from collect.overpass_poi import overpass, resolve_area, write_json

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "districts.geojson"
LICENSE = "ODbL-1.0"
NAME_KEYS = ("name", "name:ru", "name:kk", "name:en")


def query(area_id: int) -> str:
    return (
        "[out:json][timeout:180];\n"
        f"area({area_id})->.a;\n"
        'rel(area.a)["boundary"="administrative"]["admin_level"="6"];\n'
        "out geom;\n"
    )


def join_rings(ways: list[list[tuple[float, float]]]) -> list[list[tuple[float, float]]]:
    """Chain way fragments (lon, lat) end to end into closed rings."""
    pool = [w[:] for w in ways if len(w) >= 2]
    rings = []
    while pool:
        ring = pool.pop(0)
        grew = True
        while grew and ring[0] != ring[-1]:
            grew = False
            for i, w in enumerate(pool):
                if w[0] == ring[-1]:
                    ring += w[1:]
                elif w[-1] == ring[-1]:
                    ring += w[::-1][1:]
                elif w[-1] == ring[0]:
                    ring = w[:-1] + ring
                elif w[0] == ring[0]:
                    ring = w[::-1][:-1] + ring
                else:
                    continue
                pool.pop(i)
                grew = True
                break
        if ring[0] == ring[-1] and len(ring) >= 4:
            rings.append(ring)
    return rings


def ring_area(ring: list[tuple[float, float]]) -> float:
    return sum(x1 * y2 - x2 * y1 for (x1, y1), (x2, y2) in zip(ring, ring[1:])) / 2


def point_in_ring(pt: tuple[float, float], ring: list[tuple[float, float]]) -> bool:
    x, y = pt
    inside = False
    for (x1, y1), (x2, y2) in zip(ring, ring[1:]):
        if (y1 > y) != (y2 > y) and x < (x2 - x1) * (y - y1) / (y2 - y1) + x1:
            inside = not inside
    return inside


def to_polygons(outers: list[list], inners: list[list]) -> list[list[list]]:
    """MultiPolygon coordinates: every inner ring goes to the outer ring that contains it."""
    polys = [[o] for o in sorted(outers, key=lambda r: -abs(ring_area(r)))]
    for hole in inners:
        for poly in polys:
            if point_in_ring(hole[0], poly[0]):
                poly.append(hole)
                break
    return polys


def feature(el: dict, snapshot: str) -> dict:
    outers, inners = [], []
    for m in el.get("members", []):
        if m["type"] != "way" or not m.get("geometry"):
            continue
        (inners if m.get("role") == "inner" else outers).append([(p["lon"], p["lat"]) for p in m["geometry"]])
    polys = to_polygons(join_rings(outers), join_rings(inners))
    # GeoJSON: outer ring counter-clockwise, holes clockwise (RFC 7946)
    coords = [[[list(p) for p in (r if (ring_area(r) > 0) == (i == 0) else r[::-1])] for i, r in enumerate(poly)]
              for poly in polys]
    tags = el.get("tags", {})
    props = {k: tags[k] for k in NAME_KEYS if tags.get(k)}
    props.update({"osm_id": f"relation/{el['id']}", "admin_level": 6, "wikidata": tags.get("wikidata"),
                  "source": "osm", "license": LICENSE, "snapshot_date": snapshot})
    return {"type": "Feature", "properties": props, "geometry": {"type": "MultiPolygon", "coordinates": coords}}


def collect(out: Path) -> dict:
    net = default_net()
    area_id, _ = resolve_area(net)
    data, fetched = overpass(net, query(area_id))
    snapshot = datetime.fromtimestamp(fetched, timezone.utc).date().isoformat()
    feats = [feature(el, snapshot) for el in data.get("elements", []) if el["type"] == "relation"]
    feats.sort(key=lambda f: f["properties"]["osm_id"])
    if not feats:
        raise RuntimeError("no admin_level=6 relations inside the Astana area")
    fc = {"type": "FeatureCollection", "features": feats}
    write_json(out, fc)
    net.log_summary("districts")
    return fc


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    fc = collect(Path(args.out))
    for f in fc["features"]:
        p = f["properties"]
        print(f"{p['osm_id']:>20} {p.get('name:ru') or p.get('name')}  polygons={len(f['geometry']['coordinates'])}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
