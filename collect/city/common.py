"""Shared constants and helpers of the city collectors (bbox, licence, snapshot stamps, geometry simplification).

The bbox is the same Astana box as `collect.sites.store` / `overture_places.BBOX` / the notes query in
SOURCES.md §14.6: (lat 50.98..51.25, lon 71.25..71.60).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone

LAT_MIN, LAT_MAX = 50.98, 51.25
LON_MIN, LON_MAX = 71.25, 71.60
BBOX = f"{LAT_MIN},{LON_MIN},{LAT_MAX},{LON_MAX}"  # Overpass order: south,west,north,east
BBOX_OSM_API = f"{LON_MIN},{LAT_MIN},{LON_MAX},{LAT_MAX}"  # OSM API (notes) order: minlon,minlat,maxlon,maxlat

LICENSE = "ODbL-1.0"
ATTRIBUTION = "© OpenStreetMap contributors, ODbL"
COPYRIGHT_URL = "https://www.openstreetmap.org/copyright"

# Geometry simplification tolerance: drop vertices closer than this to the previous kept one (~5 m of ground).
SIMPLIFY_M = 5.0
_EARTH_R = 6_371_000.0


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def snapshot_date(fetched_at: float) -> str:
    return datetime.fromtimestamp(fetched_at, timezone.utc).date().isoformat()


def dist_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * _EARTH_R * math.asin(math.sqrt(a))


def simplify(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    """Drop consecutive vertices closer than SIMPLIFY_M to the previously kept one; first and last stay.

    A pure thinning (never reorders, never invents a vertex), so the shape stays honest while the stored
    geometry of a 500-point way shrinks to the tens of points the 15 m corridor test needs.
    """
    if len(points) <= 2:
        return list(points)
    out = [points[0]]
    for lat, lon in points[1:-1]:
        plat, plon = out[-1]
        if dist_m(plat, plon, lat, lon) > SIMPLIFY_M:
            out.append((lat, lon))
    out.append(points[-1])
    return out


def count_by(items: list[dict], key: str) -> dict[str, int]:
    out: dict[str, int] = {}
    for it in items:
        k = str(it.get(key))
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
