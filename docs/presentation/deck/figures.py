"""The map data of the deck's animations, from the repository: places, districts and the Esil in a 1920 x 1080 frame.

build.py writes it to data/geo.js (window.GEO) so that slides.html works from the file system without a server.
"""

from __future__ import annotations

import json
import math
from dataclasses import dataclass
from functools import cache
from pathlib import Path

DECK = Path(__file__).resolve().parent
ROOT = DECK.parents[2]
POI_PATH = ROOT / "data" / "poi.enriched.json"
DISTRICTS_PATH = ROOT / "data" / "districts.geojson"
RIVERS_PATH = DECK / "data" / "rivers.geojson"
API_PATH = DECK / "data" / "api_data_2026-10-19.json"

TRANSIT = "transit_station"  # app/web/datainfo.py leaves stations out of the coverage numbers
# The record's own `source`, in the order of the data slide's bar (the index is what geo.js stores per place).
SOURCES = ("osm", "overture", "state_registry", "official_site", "wikidata")


@dataclass(frozen=True)
class Place:
    lat: float
    lon: float
    source: str  # where the record came from: one of SOURCES


@cache
def places() -> tuple[Place, ...]:
    rows = json.loads(POI_PATH.read_text(encoding="utf-8"))
    return tuple(Place(p["lat"], p["lon"], p["source"]) for p in rows if p["category"] != TRANSIT)


@cache
def api() -> dict:
    return json.loads(API_PATH.read_text(encoding="utf-8"))


@cache
def districts() -> tuple[tuple[str, list[list[list[tuple[float, float]]]]], ...]:
    out = []
    for f in json.loads(DISTRICTS_PATH.read_text(encoding="utf-8"))["features"]:
        name = f["properties"]["name:ru"].removeprefix("район ").strip()
        geom = f["geometry"]
        polys = geom["coordinates"] if geom["type"] == "MultiPolygon" else [geom["coordinates"]]
        out.append((name, [[[(x, y) for x, y in ring] for ring in poly] for poly in polys]))
    return tuple(out)


@cache
def rivers() -> tuple[tuple[str, list[list[tuple[float, float]]]], ...]:
    fc = json.loads(RIVERS_PATH.read_text(encoding="utf-8"))
    return tuple(
        (f["properties"]["name"], [[(x, y) for x, y in line] for line in f["geometry"]["coordinates"]])
        for f in fc["features"]
    )


KX = 111_320 * math.cos(math.radians(51.14))
KY = 110_540


@dataclass(frozen=True)
class Frame:
    """An equirectangular lon/lat box fitted into a w x h pixel box."""

    w: float
    h: float
    lon0: float
    lat0: float
    lon1: float
    lat1: float

    def xy(self, lon: float, lat: float) -> tuple[float, float]:
        x0, y1 = self.lon0 * KX, -self.lat0 * KY
        x1, y0 = self.lon1 * KX, -self.lat1 * KY
        s = min(self.w / (x1 - x0), self.h / (y1 - y0))
        ox, oy = (self.w - (x1 - x0) * s) / 2, (self.h - (y1 - y0) * s) / 2
        return ox + (lon * KX - x0) * s, oy + (-lat * KY - y0) * s


CITY = Frame(1920, 1080, 71.29, 51.015, 71.62, 51.245)  # 99 % of the places; the video's stage uses the same frame
WHOLE = Frame(1920, 1080, 71.215, 50.928, 71.79, 51.355)  # every district whole

# Where the name of each district is written on the whole-district map, and the point a leader line goes to.
CHORO_LABEL_AT = {
    "Сарыарка": ((71.262, 51.262), (71.335, 51.212)),
    "Байконур": ((71.49, 51.262), None),
    "Алматы": ((71.63, 51.172), None),
    "Сарайшык": ((71.69, 51.052), (71.64, 51.103)),
    "Нура": ((71.30, 51.075), None),
    "Есиль": ((71.48, 51.015), None),
}


def _rdp(pts: list[tuple[float, float]], eps: float) -> list[tuple[float, float]]:
    if len(pts) < 3:
        return pts
    (ax, ay), (bx, by) = pts[0], pts[-1]
    dx, dy = bx - ax, by - ay
    norm = math.hypot(dx, dy)
    best, idx = 0.0, 0
    for i in range(1, len(pts) - 1):
        px, py = pts[i]
        d = math.hypot(px - ax, py - ay) if norm < 1e-9 else abs(dy * px - dx * py + bx * ay - by * ax) / norm
        if d > best:
            best, idx = d, i
    if best <= eps:
        return [pts[0], pts[-1]]
    return _rdp(pts[: idx + 1], eps)[:-1] + _rdp(pts[idx:], eps)


def _rings(fr: Frame, polys) -> list[list[list[float]]]:
    out = []
    for poly in polys:
        for ring in poly:
            pts = _rdp([fr.xy(x, y) for x, y in ring], 0.8)
            if len(pts) > 2:
                out.append([[round(x, 1), round(y, 1)] for x, y in pts])
    return out


def _river(fr: Frame) -> list[dict]:
    out = []
    for name, lines in rivers():
        for line in lines:
            pts = _rdp([fr.xy(x, y) for x, y in line], 0.6)
            d = "M" + "L".join(f"{x:.1f} {y:.1f}" for x, y in pts)
            out.append({"d": d, "w": 3.2 if name == "Есіл" else 1.6})
    return out


def geo() -> dict:
    """places: [x, y, source index] in the city frame; districts and river in the same frame; full: the whole
    districts (name, rings, the share of places with known hours that shades them, where the name goes)."""
    shares = {d["label"]: d for d in api()["coverage"]["districts"]}
    full = []
    for name, polys in districts():
        (lab, leader) = CHORO_LABEL_AT[name]
        full.append({
            "name": name,
            "rings": _rings(WHOLE, polys),
            "hours": shares[name]["hours"],
            "label": [round(v, 1) for v in WHOLE.xy(*lab)],
            "leader": [round(v, 1) for v in WHOLE.xy(*leader)] if leader else None,
        })
    return {
        "places": [[round(x, 1), round(y, 1), SOURCES.index(p.source)] for p in places()
                   for x, y in [CITY.xy(p.lon, p.lat)]],
        "districts": [{"name": n, "rings": _rings(CITY, polys)} for n, polys in districts()],
        "river": _river(CITY),
        "full": {"districts": full, "river": _river(WHOLE)},
    }


def origin_counts() -> dict[str, int]:
    """How many of the places came from each source (the record's own `source`): every place counted once."""
    out: dict[str, int] = dict.fromkeys(SOURCES, 0)
    for p in places():
        out[p.source] += 1
    return out
