"""`lit=yes|no` walking ways and `highway=construction` ways of Astana via Overpass (SOURCES.md §14.2 verdict:
STORE, ODbL). One query, the mirror that answers from this host (maps.mail.ru — overpass-api.de is unreachable
from it, SOURCES §14.7); the polite layer adds the UA, the 0.2 rps cap and the disk cache.

Stored per way: id, highway value, lit value (for construction: `construction` tag / barrier note), simplified
geometry, source_url, fetched_at, licence. The app layer (`app/walks/city_layers.py`) reads these files; absence
of a `lit` tag is NOT stored at all — the honesty rule «неизвестно ≠ не освещено».
"""

from __future__ import annotations

import sys
from pathlib import Path

try:
    from collect.city.common import ATTRIBUTION, BBOX, LICENSE, now_iso, simplify, snapshot_date
    from collect.net import Net, default_net
    from collect.overpass_poi import overpass
except ImportError:  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from collect.city.common import ATTRIBUTION, BBOX, LICENSE, now_iso, simplify, snapshot_date
    from collect.net import Net, default_net
    from collect.overpass_poi import overpass

# This host cannot reach overpass-api.de / kumi at all (SOURCES §14.7); maps.mail.ru answers in seconds.
# collect.overpass_poi.ENDPOINTS is reordered in place so every mirror attempt hits the live one first.
CITY_FIRST_ENDPOINT = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"


def _reorder_endpoints() -> None:
    import collect.overpass_poi as op

    if op.ENDPOINTS and op.ENDPOINTS[0] != CITY_FIRST_ENDPOINT:
        op.ENDPOINTS.remove(CITY_FIRST_ENDPOINT)
        op.ENDPOINTS.insert(0, CITY_FIRST_ENDPOINT)

# Any highway* (includes footway/path/cycleway/steps) with an explicit lit=yes|no, plus highway=construction.
# The regex ["lit"~"^(yes|no)$"] keeps the answer honest (an explicit tag, never an inferred one) and the app
# filter below drops non-walking highway values (motorway ramps etc.). The mail.ru mirror answers this shape
# unreliably (504 bursts) — collect.net retries ride them out; the response is cached once it succeeds.
QUERY = f"""[out:json][timeout:90];
(
  way["highway"]["lit"~"^(yes|no)$"]({BBOX});
  way["highway"="construction"]({BBOX});
);
out tags geom;"""

WALK_HIGHWAYS = frozenset(
    {
        "footway",
        "path",
        "pedestrian",
        "steps",
        "cycleway",
        "living_street",
        "residential",
        "service",
        "track",
        "unclassified",
        "tertiary",
        "tertiary_link",
        "secondary",
        "secondary_link",
        "primary",
        "primary_link",
        "trunk",
        "trunk_link",
        "road",
        "crossing",
        "corridor",
    }
)
# Motorways and their ramps are not walking space; their lit tag says nothing about a pedestrian route.
DROP_HIGHWAYS = frozenset({"motorway", "motorway_link", "trunk_link", "escape", "raceway", "bus_guideway"})
CONSTRUCTION_KEEP_MIN_VERTICES = 2


def collect(net: Net | None = None) -> tuple[dict[str, list[dict]], dict]:
    """({"lit": […], "construction": […]}, meta)."""
    net = net or default_net()
    _reorder_endpoints()
    data, fetched = overpass(net, QUERY)
    fetched_iso = now_iso()
    snap = snapshot_date(fetched)
    lit: list[dict] = []
    construction: list[dict] = []
    for el in data.get("elements", []):
        if el.get("type") != "way":
            continue
        tags = el.get("tags") or {}
        hw = tags.get("highway")
        geom = [(p["lat"], p["lon"]) for p in el.get("geometry") or []]
        if len(geom) < 2:
            continue
        base = {
            "source_url": "https://maps.mail.ru/osm/tools/overpass/api/interpreter",
            "fetched_at": fetched_iso,
            "license": "ODbL-1.0",
            "attribution": ATTRIBUTION,
        }
        if hw == "construction":
            construction.append(
                {
                    "id": el["id"],
                    "highway": "construction",
                    "construction": tags.get("construction"),
                    "name": tags.get("name"),
                    "geometry": [[round(lat, 6), round(lon, 6)] for lat, lon in simplify(geom)],
                    **base,
                }
            )
        elif hw in WALK_HIGHWAYS and hw not in DROP_HIGHWAYS and tags.get("lit") in ("yes", "no"):
            lit.append(
                {
                    "id": el["id"],
                    "highway": hw,
                    "lit": tags["lit"],
                    "name": tags.get("name"),
                    "geometry": [[round(lat, 6), round(lon, 6)] for lat, lon in simplify(geom)],
                    **base,
                }
            )
    lit.sort(key=lambda w: w["id"])
    construction.sort(key=lambda w: w["id"])
    by_val = {"yes": sum(1 for w in lit if w["lit"] == "yes"), "no": sum(1 for w in lit if w["lit"] == "no")}
    by_hw: dict[str, int] = {}
    for w in lit:
        by_hw[w["highway"]] = by_hw.get(w["highway"], 0) + 1
    meta = {
        "lit_count": len(lit),
        "lit_by_value": by_val,
        "lit_by_highway": dict(sorted(by_hw.items(), key=lambda kv: -kv[1])),
        "construction_count": len(construction),
        "construction_by_kind": {
            str(k): sum(1 for w in construction if w.get("construction") == k)
            for k in sorted({w.get("construction") or "?" for w in construction})
        },
        "snapshot_date": snap,
        "license": "ODbL-1.0",
        "attribution": ATTRIBUTION,
        "source": "Overpass (maps.mail.ru mirror), simplified geometry, ~5 m tolerance",
    }
    return {"lit": lit, "construction": construction}, meta
