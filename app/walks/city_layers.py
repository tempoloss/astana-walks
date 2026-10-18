"""OSM-derived city-state signals (collect/city data, ODbL), pure and JSON-serializable: no network, a missing or
damaged data file is «данных нет» (an honest absence, never a fact about the world).

Three signals, each a function over plain data + a point or a route:

- `signals_for_poi(poi)` — open OSM Notes within NOTE_RADIUS_M of the place whose text mentions the place's name
  or its kind; the card line says the place MAY have closed (a note is a suspicion, not a fact).
- `lit_share(route_coords)` — share of route length within LIT_RADIUS_M of a known lit=yes / lit=no way.
  Absence of a lit tag is NEVER read as unlit: unknown stays unknown and is reported separately.
- `construction_near_route(route_coords)` / `construction_near(lat, lon)` — roadworks on the route or near a point.

`city_summary()` feeds the «Город» page: counts + the open notes list. Files are read through env-overridable
paths (WALKS_CITY_DIR, like WALKS_FEEDBACK); tests pass their own fixtures directory.
"""

from __future__ import annotations

import json
import math
import os
import re
from dataclasses import dataclass
from functools import lru_cache
from itertools import pairwise
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "city"
NOTE_RADIUS_M = 50.0  # a note «about this place» must sit this close to the POI's own point
LIT_RADIUS_M = 15.0  # the corridor around the route that counts as «this stretch of the way»
MEANINGFUL_SHARE = 0.2  # a known share below this is not worth a card line
WS_RE = re.compile(r"\s+")


def _city_dir() -> Path:
    v = os.environ.get("WALKS_CITY_DIR", "").strip()
    return Path(v) if v else DATA_DIR


def _read(name: str) -> list[dict]:
    try:
        raw = json.loads((_city_dir() / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return raw if isinstance(raw, list) else []


def dist_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000.0 * math.asin(math.sqrt(a))


# ---- OSM notes ---------------------------------------------------------------------------------------------

CLOSURE = "closure"
CLASSIFICATIONS = ("closure", "new_place", "construction", "hours", "other")
# Words of the note that make it «about a place like this». The kind words are the app's own categories, so the
# matcher stays inside the vocabulary the user already sees (a «кафе» note may concern the neighbouring cafe).
KIND_WORDS: dict[str, tuple[str, ...]] = {
    "cafe": ("кафе", "кофейн", "coffee", "cafe"),
    "restaurant": ("ресторан", "столов", "restaurant"),
    "fast_food": ("фастфуд", "фаст-фуд", "fast food", "пицц", "бургер", "шаурм"),
    "bar_nightlife": ("бар", "паб", "клуб", "nightclub", "bar"),
    "park_garden": ("парк", "сквер", "сад", "park", "garden"),
    "mall": ("тц", "трц", "торгов", "mall"),
    "museum_gallery": ("музей", "галере", "museum"),
    "entertainment": ("развлекательн", "боулинг", "бильярд", "батут"),
    "culture_theatre_cinema": ("театр", "кинотеатр", "кино", "theatre", "cinema"),
    "kids_playground": ("площадк", "playground", "детск"),
    "sport": ("спорт", "фитнес", "бассейн", "каток"),
    "coworking_library": ("коворкинг", "библиотек", "coworking", "library"),
    "attraction_landmark": ("памятник", "монумент", "достопримеч", "attraction", "монумент"),
    "viewpoint": ("смотров", "viewpoint"),
    "public_toilet": ("туалет", "дәретхана", "toilet", "wc"),
    "transit_station": ("остановк", "вокзал", "станци", "station", "bus stop"),
}


@dataclass(frozen=True)
class NoteSignal:
    """One open note that may concern this place. `text` is the stored first-comment snippet (≤200 chars)."""

    id: int
    url: str
    text: str
    classification: str
    date_created: str | None
    distance_m: int

    def as_dict(self) -> dict:
        return {
            "id": self.id,
            "url": self.url,
            "text": self.text,
            "classification": self.classification,
            "date_created": self.date_created,
            "distance_m": self.distance_m,
        }


def _mentions(text: str, *needles: str) -> bool:
    t = WS_RE.sub(" ", text).lower()
    return any(tok.lower() in t for tok in needles if tok)


def _poi_name_tokens(
    poi,
) -> tuple[str, ...]:  # poi: walks.models.POI (duck-typed, no import: layers contract)
    name = (poi.name or "").strip()
    toks = [name] if len(name) >= 4 else []
    for n in (poi.names or {}).values():
        if len(n) >= 4:
            toks.append(n)
    return tuple(toks)


def _note_mentions_kind(text: str, poi) -> bool:
    for kind, words in KIND_WORDS.items():
        if poi.category == kind and _mentions(text, *words):
            return True
    return False


def _load(path: Path) -> list[dict]:
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    return raw if isinstance(raw, list) else []


def signals_for_poi(
    poi, notes: list[dict] | None = None, path: Path | None = None
) -> list[NoteSignal]:
    """Open notes within NOTE_RADIUS_M whose snippet mentions the place's name or its kind.

    Only OPEN notes: a closed one was already resolved on the map. A closure note is a SUSPICION — the wording
    lives in i18n_city (PLACE_OPEN_NOTE), never «закрыто».
    """
    rows = _read("osm_notes.json") if notes is None and path is None else (notes or _load(path))
    out: list[NoteSignal] = []
    for n in rows:
        if n.get("status") != "open":
            continue
        try:
            d = dist_m(poi.lat, poi.lon, float(n["lat"]), float(n["lon"]))
        except (KeyError, TypeError, ValueError):
            continue
        if d > NOTE_RADIUS_M:
            continue
        text = str(n.get("snippet") or "")
        if not (_mentions(text, *_poi_name_tokens(poi)) or _note_mentions_kind(text, poi)):
            continue
        out.append(
            NoteSignal(
                id=n["id"],
                url=str(n.get("url") or f"https://www.openstreetmap.org/note/{n['id']}"),
                text=text,
                classification=str(n.get("classification") or "other"),
                date_created=n.get("date_created"),
                distance_m=round(d),
            )
        )
    out.sort(key=lambda s: s.distance_m)
    return out


# ---- lit / construction ------------------------------------------------------------------------------------


@dataclass(frozen=True)
class LitShare:
    """Shares of the route length inside a 15 m corridor of known-lit ways. `unknown` is length whose corridor
    holds no tagged way at all — NOT evidence that it is dark."""

    lit_yes: float  # 0..1 of route length near a lit=yes way
    lit_no: float  # 0..1 near an explicitly lit=no way (a tagged fact, rare)
    unknown: float  # 0..1 near no tagged way: no data, never «не освещено»
    known_share: float  # lit_yes + lit_no

    def as_dict(self) -> dict:
        return {
            "lit_yes": round(self.lit_yes, 3),
            "lit_no": round(self.lit_no, 3),
            "unknown": round(self.unknown, 3),
            "known_share": round(self.known_share, 3),
        }


def _seg_dist_to_polyline_m(plat: float, plon: float, pts: list[tuple[float, float]]) -> float:
    """Min distance from the point to the way's vertices (vertex sampling, ~1 point / 5 m after simplification:
    a 15 m corridor needs no segment projection)."""
    return min(dist_m(plat, plon, lat, lon) for lat, lon in pts)


def route_length_m(route_coords: list[tuple[float, float]]) -> float:
    total = 0.0
    for a, b in pairwise(route_coords):
        total += dist_m(a[0], a[1], b[0], b[1])
    return total


def _sample(
    route_coords: list[tuple[float, float]], step_m: float = 15.0
) -> list[tuple[float, float]]:
    """Points along the polyline every ~step_m (endpoints included): the length shares are measured per sample."""
    if not route_coords:
        return []
    out = [route_coords[0]]
    carry = 0.0  # distance walked since the last emitted sample
    for a, b in pairwise(route_coords):
        seg = dist_m(a[0], a[1], b[0], b[1])
        if seg <= 0:
            continue
        pos = step_m - carry  # distance into this segment until the next sample
        while pos <= seg:
            t = pos / seg
            out.append((a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t))
            pos += step_m
        carry = seg - (pos - step_m)
    out.append(route_coords[-1])
    return out


def lit_share(
    route_coords: list[tuple[float, float]],
    lit_ways: list[dict] | None = None,
    path: Path | None = None,
) -> LitShare | None:
    """Shares of route length within LIT_RADIUS_M of lit=yes / lit=no ways; None without route or data."""
    rows = _read("lit.json") if lit_ways is None and path is None else (lit_ways or _load(path))
    if not route_coords or len(route_coords) < 2 or not rows:
        return None
    tagged: dict[str, list[list[tuple[float, float]]]] = {"yes": [], "no": []}
    for w in rows:
        val = w.get("lit")
        if val in tagged:
            geom = [(p[0], p[1]) for p in w.get("geometry") or [] if len(p) >= 2]
            if geom:
                tagged[val].append(geom)
    samples = _sample(route_coords)
    if len(samples) < 2:
        return None
    counts = {"yes": 0, "no": 0, "unknown": 0}
    for slat, slon in samples:
        state = "unknown"
        for val in ("yes", "no"):
            if any(
                _seg_dist_to_polyline_m(slat, slon, geom) <= LIT_RADIUS_M for geom in tagged[val]
            ):
                state = val
                break
        counts[state] += 1
    n = sum(counts.values())
    yes, no = counts["yes"] / n, counts["no"] / n
    return LitShare(lit_yes=yes, lit_no=no, unknown=1.0 - yes - no, known_share=yes + no)


LIT_PLACE_RADIUS_M = (
    60.0  # a place's point is its middle: a lit way this near «runs along» it (a park's own edge)
)
_CELL_DEG = 0.002  # the grid cell of the lit-way index, ~220 m
_M_LAT = 111_000.0


def _local_m(lat: float, lon: float, lat0: float) -> tuple[float, float]:
    return lon * _M_LAT * math.cos(math.radians(lat0)), lat * _M_LAT


def _seg_dist_m(plat: float, plon: float, a: tuple[float, float], b: tuple[float, float]) -> float:
    """Distance from a point to the segment a-b, on a local flat projection (a few hundred metres across)."""
    px, py = _local_m(plat, plon, plat)
    ax, ay = _local_m(a[0], a[1], plat)
    bx, by = _local_m(b[0], b[1], plat)
    dx, dy = bx - ax, by - ay
    span = dx * dx + dy * dy
    t = 0.0 if span == 0 else max(0.0, min(1.0, ((px - ax) * dx + (py - ay) * dy) / span))
    return math.hypot(px - (ax + t * dx), py - (ay + t * dy))


@lru_cache(maxsize=4)
def _lit_index(
    city_dir: str, stamp: int
) -> dict[tuple[int, int], list[tuple[tuple[float, float], tuple[float, float]]]]:
    """The lit=yes ways of the city as segments in a grid (cell -> the segments near it). `stamp` is the file's mtime:
    a replaced file is read again."""
    index: dict[tuple[int, int], list[tuple[tuple[float, float], tuple[float, float]]]] = {}
    pad = LIT_PLACE_RADIUS_M / _M_LAT
    pad_lon = pad / math.cos(
        math.radians(51.1)
    )  # a degree of longitude is shorter at Astana's latitude
    for way in _read("lit.json"):
        if way.get("lit") != "yes":
            continue
        pts = [(p[0], p[1]) for p in way.get("geometry") or [] if len(p) >= 2]
        for a, b in pairwise(pts):
            lo_i, hi_i = (
                int((min(a[0], b[0]) - pad) // _CELL_DEG),
                int((max(a[0], b[0]) + pad) // _CELL_DEG),
            )
            lo_j, hi_j = (
                int((min(a[1], b[1]) - pad_lon) // _CELL_DEG),
                int((max(a[1], b[1]) + pad_lon) // _CELL_DEG),
            )
            for i in range(lo_i, hi_i + 1):
                for j in range(lo_j, hi_j + 1):
                    index.setdefault((i, j), []).append((a, b))
    return index


def lit_near(lat: float, lon: float) -> bool:
    """Does a way the data tag `lit=yes` pass within LIT_PLACE_RADIUS_M of the point? True is a fact of the data; False
    is only «no tagged lit way near»: the absence of a tag is never read as darkness, so the caller says nothing
    against the place."""
    folder = _city_dir()
    try:
        stamp = (folder / "lit.json").stat().st_mtime_ns
    except OSError:
        return False
    segments = _lit_index(str(folder), stamp).get(
        (int(lat // _CELL_DEG), int(lon // _CELL_DEG)), ()
    )
    return any(_seg_dist_m(lat, lon, a, b) <= LIT_PLACE_RADIUS_M for a, b in segments)


def construction_near_route(
    route_coords: list[tuple[float, float]],
    constructions: list[dict] | None = None,
    path: Path | None = None,
) -> list[dict]:
    """Construction ways whose geometry enters the LIT_RADIUS_M corridor of the route (same 15 m test)."""
    rows = (
        _read("construction.json")
        if constructions is None and path is None
        else (constructions or _load(path))
    )
    if not route_coords or not rows:
        return []
    out = []
    for w in rows:
        geom = [(p[0], p[1]) for p in w.get("geometry") or [] if len(p) >= 2]
        if not geom:
            continue
        if any(
            _seg_dist_to_polyline_m(slat, slon, geom) <= LIT_RADIUS_M
            for slat, slon in _sample(route_coords)
        ):
            out.append(w)
    return out


def construction_near(lat: float, lon: float, radius_m: float = 50.0) -> list[dict]:
    """Construction ways within radius_m of a point (a card line for «что вокруг»)."""
    out = []
    for w in _read("construction.json"):
        geom = [(p[0], p[1]) for p in w.get("geometry") or [] if len(p) >= 2]
        if geom and min(dist_m(lat, lon, g[0], g[1]) for g in geom) <= radius_m:
            out.append(w)
    return out


# ---- «Город» page ------------------------------------------------------------------------------------------


@dataclass(frozen=True)
class CitySummary:
    notes_total: int
    notes_open: int
    notes_closed_kept: int
    by_classification: dict[str, int]
    lit_yes: int
    lit_no: int
    construction: int
    snapshot_date: str | None
    attribution: str
    open_notes: list[dict]  # the list for the page (id, url, snippet, classification, date, coords)

    def as_dict(self) -> dict:
        return {
            "notes_total": self.notes_total,
            "notes_open": self.notes_open,
            "notes_closed_kept": self.notes_closed_kept,
            "by_classification": self.by_classification,
            "lit_yes": self.lit_yes,
            "lit_no": self.lit_no,
            "construction": self.construction,
            "snapshot_date": self.snapshot_date,
            "attribution": self.attribution,
            "open_notes": self.open_notes,
        }


def city_summary(path: Path | None = None) -> CitySummary | None:
    """Counts + the open-note list for the «Город» page; None without the data files (honest absence)."""
    notes_rows = _read("osm_notes.json") if path is None else _load(path)
    lit_rows = _read("lit.json")
    constr_rows = _read("construction.json")
    if not notes_rows and not lit_rows and not constr_rows:
        return None
    open_notes = [n for n in notes_rows if n.get("status") == "open"]
    closed = len(notes_rows) - len(open_notes)
    by_cls: dict[str, int] = {}
    for n in notes_rows:
        c = str(n.get("classification") or "other")
        by_cls[c] = by_cls.get(c, 0) + 1
    snap = None
    for row in (*notes_rows, *lit_rows, *constr_rows):
        if row.get("fetched_at"):
            snap = str(row.get("fetched_at"))[:10]
            break
    return CitySummary(
        notes_total=len(notes_rows),
        notes_open=len(open_notes),
        notes_closed_kept=closed,
        by_classification=dict(sorted(by_cls.items(), key=lambda kv: -kv[1])),
        lit_yes=sum(1 for w in lit_rows if w.get("lit") == "yes"),
        lit_no=sum(1 for w in lit_rows if w.get("lit") == "no"),
        construction=len(constr_rows),
        snapshot_date=snap,
        attribution="© OpenStreetMap contributors, ODbL",
        open_notes=[
            {
                "id": n["id"],
                "url": n.get("url"),
                "snippet": n.get("snippet"),
                "classification": n.get("classification"),
                "date_created": n.get("date_created"),
                "lat": n.get("lat"),
                "lon": n.get("lon"),
            }
            for n in open_notes
        ],
    )
