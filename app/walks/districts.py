"""Districts of Astana (OSM admin_level 6, cached in data/districts.geojson by collect/districts.py) and the lookup
«which district holds this point». Pure geometry, no network: a missing file means no district names (the callers fall
back to the cell id), never a guess."""

from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

DEFAULT_PATH = Path(__file__).resolve().parents[2] / "data" / "districts.geojson"
_PREFIX = "район "

Ring = list[tuple[float, float]]  # (lon, lat)


@dataclass(frozen=True)
class District:
    name: str
    polygons: tuple[tuple[Ring, ...], ...]  # polygon = outer ring followed by holes

    def contains(self, lat: float, lon: float) -> bool:
        for outer, *holes in self.polygons:
            if _in_ring(lat, lon, outer) and not any(_in_ring(lat, lon, h) for h in holes):
                return True
        return False


def _in_ring(lat: float, lon: float, ring: Ring) -> bool:
    """Even-odd rule: a ray towards +lon crosses an odd number of edges for an inner point."""
    inside = False
    j = len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def _name(props: dict) -> str:
    raw = str(props.get("name:ru") or props.get("name") or "").strip()
    return raw.removeprefix(_PREFIX).strip()


def _rings(polygon: list) -> tuple[Ring, ...]:
    return tuple([(float(x), float(y)) for x, y, *_ in ring] for ring in polygon)


@lru_cache(maxsize=4)
def load_districts(path: Path = DEFAULT_PATH) -> tuple[District, ...]:
    """Districts of a GeoJSON FeatureCollection of Polygon / MultiPolygon; a missing or damaged file gives ()."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return ()
    out: list[District] = []
    for f in data.get("features", []):
        geom = f.get("geometry") or {}
        coords = geom.get("coordinates") or []
        polygons = [coords] if geom.get("type") == "Polygon" else coords
        name = _name(f.get("properties") or {})
        if name and polygons and geom.get("type") in ("Polygon", "MultiPolygon"):
            out.append(District(name, tuple(_rings(p) for p in polygons)))
    return tuple(out)


def district_of(
    lat: float, lon: float, districts: tuple[District, ...] | None = None
) -> str | None:
    """Name of the district that contains the point, None outside all of them (or without the file)."""
    for d in load_districts() if districts is None else districts:
        if d.contains(lat, lon):
            return d.name
    return None
