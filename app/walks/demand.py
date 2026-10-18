"""The city layer (variant B): what the anonymous request log and the place data say about the CITY, not about a person.

Two layers over a 500 m grid (the cell ids of walks.reqlog):

* demand: requests by cell x intent category x time of day with three separate indicators per request:
  `no_requested_category_nearby` (the dataset holds no place of the requested kind inside the declared radius: a
  fact about the city, the only one the demand map draws), `hours_unknown_nearby` (such places exist but none has
  opening hours the data confirm: a fact about data quality) and `padded` (the answer had to be widened or
  back-filled: a fact about the ranker, shown as service quality, never as a gap of the city);
* data quality: the share of places per cell that have opening hours, a human-written description and the
  anonymous marks of people.

Nothing here reads free text or a person's profile: the input is the aggregate record of `walks.reqlog` (cell, intent
categories, counts) and the place dataset. Every published group of requests has at least `k` of them (k-anonymity,
default 5); a smaller group is merged into the single row «прочее» that carries no location. The functions only
aggregate and format: files and the UI are the caller's business.
"""

from __future__ import annotations

import csv
import io
import json
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from .feedback import FeedbackEntry, hour_bucket
from .models import POI
from .reqlog import cell_bounds, grid_cell_id
from .retrieve import TRANSIT_CATEGORY

K_DEFAULT = 5  # a cell x category x time group is shown only with at least this many requests
OTHER = "прочее"  # the merged row of every group below k: no location
ANY_CATEGORY = "без категории"  # a request that asked for no particular kind of place
MIN_CATEGORY_POIS = 3  # a category with fewer places says nothing about hours coverage
BUCKET_RU = {
    "morning": "утро 05–11",
    "day": "день 11–17",
    "evening": "вечер 17–22",
    "night": "ночь 22–05",
}
DIMS = ("cell", "category", "bucket")
QUALITY_METRICS = ("hours", "description", "people")
QUALITY_METRIC_RU = {
    "hours": "часы работы",
    "description": "описание от человека",
    "people": "отметки людей",
}


# ---------------------------------------------------------------- demand


@dataclass(frozen=True)
class DemandRequest:
    """One logged request, reduced to what the city layer uses."""

    cell: str
    bucket: str
    categories: tuple[str, ...]
    no_requested_category_nearby: (
        bool  # dataset: zero places of the requested kinds inside the declared radius
    )
    hours_unknown_nearby: bool  # dataset: such places exist, none with confirmed hours
    padded: bool  # ranker: the answer needed widening or back-fill


@dataclass(frozen=True)
class DemandRow:
    """One published group. `category` / `bucket` are None when the aggregation did not split by them."""

    cell: str
    category: str | None
    bucket: str | None
    requests: int
    no_requested_category_nearby: int
    hours_unknown_nearby: int
    padded: int

    @property
    def no_category_share(self) -> float:
        return self.no_requested_category_nearby / self.requests if self.requests else 0.0

    @property
    def padded_share(self) -> float:
        return self.padded / self.requests if self.requests else 0.0


@dataclass(frozen=True)
class Aggregate:
    rows: list[DemandRow]  # groups with >= k requests, then the merged «прочее» rows
    k: int
    total_requests: int
    total_no_category: int
    total_hours_unknown: int
    total_padded: int
    cells_total: int
    cells_suppressed: int  # cells none of whose groups reached k
    groups_suppressed: int
    requests_suppressed: int  # requests inside the merged rows

    @property
    def shown(self) -> list[DemandRow]:
        return [r for r in self.rows if r.cell != OTHER]

    @property
    def merged(self) -> list[DemandRow]:
        return [r for r in self.rows if r.cell == OTHER]


def is_padded(rec: dict) -> bool:
    """The ranker had to widen the radius or back-fill: no candidate or no recommendation within the declared
    radius and of the requested kind. A weather substitution (an indoor place instead of a park in frost) is not a
    supply shortage: it counts like "none". A record from before the padding fields counts only when it ended
    with no recommendation at all."""
    cands, recs = rec.get("candidates_by_padding"), rec.get("recs_by_padding")
    if not isinstance(cands, dict) or not isinstance(recs, dict):
        return int(rec.get("recs", 0)) < 1
    return _matches(cands) < 1 or _matches(recs) < 1


def _matches(by_padding: dict) -> int:
    return int(by_padding.get("none", 0)) + int(by_padding.get("substituted", 0))


def has_no_category_nearby(rec: dict) -> bool:
    """The dataset has no place of the requested kinds inside the declared radius. A record without the supply
    counts (older log) says nothing about the city and is not counted."""
    nearby = rec.get("requested_nearby")
    return isinstance(nearby, int) and nearby < 1


def has_hours_unknown_nearby(rec: dict) -> bool:
    """Places of the requested kinds exist inside the radius, but none has hours the data confirm."""
    nearby, confirmed = rec.get("requested_nearby"), rec.get("requested_nearby_with_hours")
    return isinstance(nearby, int) and isinstance(confirmed, int) and nearby >= 1 and confirmed < 1


def request_from_record(rec: dict) -> DemandRequest | None:
    """None for a record that lacks the cell or the time (never raises on a damaged line)."""
    try:
        cell = str(rec["cell"])
        cell_bounds(cell)
        bucket = hour_bucket(datetime.fromisoformat(rec["ts_hour"]).hour)
        cats = tuple(str(c) for c in rec.get("categories") or ())
        return DemandRequest(
            cell,
            bucket,
            cats,
            has_no_category_nearby(rec),
            has_hours_unknown_nearby(rec),
            is_padded(rec),
        )
    except (KeyError, ValueError, TypeError):
        return None


def load_requests(path: Path | None) -> list[DemandRequest]:
    """Every readable record of a requests JSONL; a missing file or a broken line is skipped."""
    if path is None or not path.exists():
        return []
    out: list[DemandRequest] = []
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return []
    for line in lines:
        try:
            rec = json.loads(line)
        except ValueError:
            continue
        if isinstance(rec, dict) and (req := request_from_record(rec)) is not None:
            out.append(req)
    return out


def filter_requests(
    requests: Iterable[DemandRequest], category: str | None = None, bucket: str | None = None
) -> list[DemandRequest]:
    """Requests that asked for `category` (ANY_CATEGORY: asked for none) and/or fall into `bucket`."""
    out = []
    for r in requests:
        if bucket is not None and r.bucket != bucket:
            continue
        if category is not None and category not in (r.categories or (ANY_CATEGORY,)):
            continue
        out.append(r)
    return out


def aggregate_demand(
    requests: Sequence[DemandRequest], k: int = K_DEFAULT, by: Sequence[str] = DIMS
) -> Aggregate:
    """Group the requests by the dimensions `by` (a subset of DIMS that includes "cell"). A request with several
    categories counts once in each category group, so per-category rows do not add up to the request total.
    Groups below `k` are merged into one «прочее» row per remaining key, without a location."""
    if "cell" not in by or any(d not in DIMS for d in by):
        raise ValueError(f"`by` must be a subset of {DIMS} that includes 'cell': {tuple(by)}")
    groups: dict[tuple, list[int]] = {}
    for r in requests:
        for cat in (r.categories or (ANY_CATEGORY,)) if "category" in by else (None,):
            values = {"cell": r.cell, "category": cat, "bucket": r.bucket}
            g = groups.setdefault(tuple(values[d] for d in by), [0, 0, 0, 0])
            g[0] += 1
            g[1] += r.no_requested_category_nearby
            g[2] += r.hours_unknown_nearby
            g[3] += r.padded
    shown: list[DemandRow] = []
    merged: dict[
        tuple[str | None, str | None], list[int]
    ] = {}  # (category, bucket) -> [requests, no category, hours unknown, padded]
    cells_shown: set[str] = set()
    cells_all: set[str] = set()
    groups_suppressed = 0
    for key, counts in groups.items():
        v = dict(zip(by, key, strict=True))
        cells_all.add(v["cell"])
        if counts[0] >= k:
            cells_shown.add(v["cell"])
            shown.append(DemandRow(v["cell"], v.get("category"), v.get("bucket"), *counts))
            continue
        groups_suppressed += 1
        m = merged.setdefault((v.get("category"), v.get("bucket")), [0, 0, 0, 0])
        for i, n in enumerate(counts):
            m[i] += n
    shown.sort(
        key=lambda r: (
            -r.no_requested_category_nearby,
            -r.requests,
            r.cell,
            r.category or "",
            r.bucket or "",
        )
    )
    rows = shown + [
        DemandRow(OTHER, cat, bucket, *counts)
        for (cat, bucket), counts in sorted(
            merged.items(), key=lambda kv: (kv[0][0] or "", kv[0][1] or "")
        )
    ]
    return Aggregate(
        rows=rows,
        k=k,
        total_requests=len(requests),
        total_no_category=sum(r.no_requested_category_nearby for r in requests),
        total_hours_unknown=sum(r.hours_unknown_nearby for r in requests),
        total_padded=sum(r.padded for r in requests),
        cells_total=len(cells_all),
        cells_suppressed=len(cells_all - cells_shown),
        groups_suppressed=groups_suppressed,
        requests_suppressed=sum(c[0] for c in merged.values()),
    )


def categories_seen(requests: Iterable[DemandRequest]) -> list[str]:
    """Categories of the requests, the most requested first."""
    counts = Counter(c for r in requests for c in (r.categories or (ANY_CATEGORY,)))
    return [c for c, _ in counts.most_common()]


# ---------------------------------------------------------------- data quality


@dataclass(frozen=True)
class QualityCell:
    cell: str
    pois: int
    with_hours: int
    with_description: int
    with_people: int

    def share(self, metric: str) -> float:
        n = {
            "hours": self.with_hours,
            "description": self.with_description,
            "people": self.with_people,
        }[metric]
        return n / self.pois if self.pois else 0.0


@dataclass(frozen=True)
class CategoryQuality:
    category: str
    pois: int
    with_hours: int

    @property
    def hours_share(self) -> float:
        return self.with_hours / self.pois if self.pois else 0.0


def _quality_pois(pois: Iterable[POI]) -> list[POI]:
    return [p for p in pois if p.category != TRANSIT_CATEGORY]  # stations are never recommended


def quality_cells(pois: Iterable[POI], marked_ids: set[str]) -> list[QualityCell]:
    """Per grid cell: places, and how many have opening hours / a real description / marks of people."""
    acc: dict[str, list[int]] = {}
    for p in _quality_pois(pois):
        a = acc.setdefault(grid_cell_id(p.lat, p.lon), [0, 0, 0, 0])
        a[0] += 1
        a[1] += bool(p.opening_hours)
        a[2] += p.has_real_description()
        a[3] += p.id in marked_ids
    return [QualityCell(c, *a) for c, a in sorted(acc.items())]


def worst_hours_categories(
    pois: Iterable[POI], top: int = 10, min_pois: int = MIN_CATEGORY_POIS
) -> list[CategoryQuality]:
    """The `top` categories with the lowest share of places that have opening hours (categories with fewer than
    `min_pois` places are left out: a share of two places is noise)."""
    counts: dict[str, list[int]] = {}
    for p in _quality_pois(pois):
        a = counts.setdefault(p.category, [0, 0])
        a[0] += 1
        a[1] += bool(p.opening_hours)
    rows = [CategoryQuality(c, n, h) for c, (n, h) in counts.items() if n >= min_pois]
    rows.sort(key=lambda r: (r.hours_share, -r.pois, r.category))
    return rows[:top]


def marked_poi_ids(entries: Iterable[FeedbackEntry]) -> set[str]:
    return {e.poi_id for e in entries}


# ---------------------------------------------------------------- export (aggregates only)


def cell_center(cell: str) -> tuple[float, float]:
    s, w, n, e = cell_bounds(cell)
    return round((s + n) / 2, 5), round((w + e) / 2, 5)


def cell_polygon(cell: str) -> dict:
    s, w, n, e = cell_bounds(cell)
    return {"type": "Polygon", "coordinates": [[[w, s], [e, s], [e, n], [w, n], [w, s]]]}


def _csv(header: list[str], rows: Iterable[list]) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf, lineterminator="\n")
    writer.writerow(header)
    writer.writerows(rows)
    return buf.getvalue()


def demand_csv(rows: Iterable[DemandRow]) -> str:
    """cell, centre, category, time of day, requests and the three indicators; the merged «прочее» rows have no
    location."""
    out = []
    for r in rows:
        lat, lon = cell_center(r.cell) if r.cell != OTHER else ("", "")
        out.append(
            [
                r.cell,
                lat,
                lon,
                r.category or "",
                BUCKET_RU.get(r.bucket or "", ""),
                r.requests,
                r.no_requested_category_nearby,
                r.hours_unknown_nearby,
                r.padded,
                round(r.no_category_share, 3),
            ]
        )
    return _csv(
        [
            "cell",
            "lat",
            "lon",
            "category",
            "time_of_day",
            "requests",
            "no_requested_category_nearby",
            "hours_unknown_nearby",
            "padded",
            "no_category_share",
        ],
        out,
    )


def demand_geojson(rows: Iterable[DemandRow]) -> dict:
    """One polygon per published row; the merged «прочее» rows have no location and are left out."""
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": cell_polygon(r.cell),
                "properties": {
                    "cell": r.cell,
                    "category": r.category,
                    "time_of_day": BUCKET_RU.get(r.bucket or ""),
                    "requests": r.requests,
                    "no_requested_category_nearby": r.no_requested_category_nearby,
                    "hours_unknown_nearby": r.hours_unknown_nearby,
                    "padded": r.padded,
                    "no_category_share": round(r.no_category_share, 3),
                },
            }
            for r in rows
            if r.cell != OTHER
        ],
    }


def quality_csv(cells: Iterable[QualityCell]) -> str:
    out = []
    for c in cells:
        lat, lon = cell_center(c.cell)
        out.append(
            [c.cell, lat, lon, c.pois, c.with_hours, c.with_description, c.with_people]
            + [round(c.share(m), 3) for m in QUALITY_METRICS]
        )
    return _csv(
        ["cell", "lat", "lon", "pois", "with_hours", "with_description", "with_people"]
        + [f"share_{m}" for m in QUALITY_METRICS],
        out,
    )


def quality_geojson(cells: Iterable[QualityCell]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": cell_polygon(c.cell),
                "properties": {
                    "cell": c.cell,
                    "pois": c.pois,
                    "with_hours": c.with_hours,
                    "with_description": c.with_description,
                    "with_people": c.with_people,
                    **{f"share_{m}": round(c.share(m), 3) for m in QUALITY_METRICS},
                },
            }
            for c in cells
        ],
    }
