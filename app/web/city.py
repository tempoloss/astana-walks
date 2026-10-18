"""The «Город» page (for the city and the research centre): the same data that feeds the assistant, as aggregates over
the 500 m grid of walks.reqlog. Three layers, each a JSON endpoint:

* demand - requests per cell with three indicators that are never mixed: no place of the requested kind in the radius
  (a fact about the dataset, the only one drawn on the map), places exist but none has confirmed hours (data
  quality), the answer had to be padded (ranker quality). A group below k requests is merged into «прочее» with no
  location; for the real log k never goes below 5. The simulated demand file is served only under WALKS_DEMAND_SIM=1
  and the page says so;
* data quality - the share of places per cell with opening hours, a human-written description and residents' marks;
* residents' reports - the anonymous marks of walks.feedback («закрыто», «другие часы», «всё верно», ...).

Only aggregates leave this module (and the CSV / GeoJSON exports are built from the same groups)."""

from __future__ import annotations

import json
from collections import Counter, defaultdict
from functools import cache, lru_cache
from pathlib import Path

from i18n import tr
from walks.city_actions import NO_DISTRICT, hours_actions, supply_actions
from walks.city_layers import city_summary
from walks.demand import (
    ANY_CATEGORY,
    DIMS,
    K_DEFAULT,
    QUALITY_METRICS,
    DemandRequest,
    DemandRow,
    aggregate_demand,
    categories_seen,
    cell_center,
    cell_polygon,
    demand_csv,
    demand_geojson,
    filter_requests,
    load_requests,
    marked_poi_ids,
    quality_cells,
    quality_csv,
    quality_geojson,
    worst_hours_categories,
)
from walks.districts import district_of
from walks.envcfg import demand_sim
from walks.events import load_snapshot
from walks.feedback import read_entries
from walks.hours import local_now
from walks.i18n import category_name, signal_label
from walks.i18n_events import SOURCE_LABELS, source_label
from walks.models import POI
from walks.pipeline import get_pois
from walks.reqlog import log_path

DATA = Path(__file__).resolve().parents[2] / "data"
SIM_PATH = DATA / "demand_sim.jsonl"
SIM_META_PATH = DATA / "demand_sim.meta.json"
DISTRICTS_PATH = DATA / "districts.geojson"
OSM_ATTRIBUTION = (
    "Contains information from OpenStreetMap, which is made available here under the Open Database License (ODbL). "
    "© OpenStreetMap contributors. https://www.openstreetmap.org/copyright "
    "https://opendatacommons.org/licenses/odbl/1-0/"
)
ATTRIBUTION_MEMBERS = {"attribution": OSM_ATTRIBUTION, "license": "ODbL-1.0"}
K_SIM_MIN = 2  # the simulated file may show how k works; real people never below K_DEFAULT
K_MAX = 100
TOP_ROWS = 10
RECENT_REPORTS = 20
BUCKETS = ("morning", "day", "evening", "night")


def _sources() -> dict[str, Path]:
    out: dict[str, Path] = {}
    if demand_sim() and SIM_PATH.exists():
        out["sim"] = SIM_PATH
    if (real := log_path()) is not None:
        out["real"] = real
    return out


@lru_cache(maxsize=4)
def _requests_at(path: str, _stamp: tuple[float, int]) -> tuple[DemandRequest, ...]:
    return tuple(load_requests(Path(path)))


def _requests(path: Path) -> list[DemandRequest]:
    """The requests of a log, re-read only when the file changed."""
    try:
        st = path.stat()
    except OSError:
        return []
    return list(_requests_at(str(path), (st.st_mtime, st.st_size)))


def _sim_meta() -> dict:
    try:
        meta = json.loads(SIM_META_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return {k: meta[k] for k in ("seed", "n", "date") if k in meta}


@cache
def _district(cell: str) -> str | None:
    return district_of(*cell_center(cell))


def _district_name(name: str | None, lang: str) -> str:
    return tr("city_no_district", lang) if name in (None, NO_DISTRICT) else name


def _category(category: str | None, lang: str) -> str:
    if not category:
        return "—"
    if category == ANY_CATEGORY:
        return tr("city_any_category", lang)
    return category_name(category, lang)


def _bucket(bucket: str | None, lang: str) -> str:
    return tr(f"bucket_{bucket}", lang) if bucket in BUCKETS else "—"


def _features(items: list[tuple[str, dict]]) -> dict:
    return {
        "type": "FeatureCollection",
        "features": [
            {
                "type": "Feature",
                "geometry": cell_polygon(cell),
                "properties": {"cell": cell, **props},
            }
            for cell, props in items
        ],
    }


def _choice(value: str | None, allowed: list[str]) -> str | None:
    return value if value in allowed else None


def demand(
    source: str | None, k: int | None, category: str | None, bucket: str | None, lang: str
) -> dict:
    paths = _sources()
    if not paths:
        return {"sources": [], "empty": True}
    source = source if source in paths else next(iter(paths))
    k_min = K_DEFAULT if source == "real" else K_SIM_MIN
    k = min(max(k or K_DEFAULT, k_min), K_MAX)
    requests = _requests(paths[source])
    cats = categories_seen(requests)
    category, bucket = _choice(category, cats), _choice(bucket, list(BUCKETS))
    head = {
        "sources": list(paths),
        "source": source,
        "simulated": source == "sim",
        "meta": _sim_meta() if source == "sim" else {},
        "k": k,
        "k_min": k_min,
        "k_max": K_MAX,
        "categories": [{"id": c, "label": _category(c, lang)} for c in cats],
        "buckets": [{"id": b, "label": _bucket(b, lang)} for b in BUCKETS],
        "category": category,
        "bucket": bucket,
    }
    if not requests:
        return {**head, "empty": True}
    chosen = filter_requests(requests, category, bucket)
    cells = aggregate_demand(chosen, k, by=("cell",))
    top = max((r.no_requested_category_nearby for r in cells.shown), default=0)
    detail = aggregate_demand(requests, k, by=DIMS)
    rows = [r for r in detail.shown if r.no_requested_category_nearby][:TOP_ROWS]
    return {
        **head,
        "empty": False,
        "totals": {
            "requests": cells.total_requests,
            "no_place": cells.total_no_category,
            "hours_unknown": cells.total_hours_unknown,
            "padded": cells.total_padded,
            "cells_shown": cells.cells_total - cells.cells_suppressed,
            "cells_hidden": cells.cells_suppressed,
            "requests_hidden": cells.requests_suppressed,
        },
        "cells": _features(
            [
                (
                    r.cell,
                    {
                        "district": _district_name(_district(r.cell), lang),
                        "requests": r.requests,
                        "no_place": r.no_requested_category_nearby,
                        "hours_unknown": r.hours_unknown_nearby,
                        "t": r.no_requested_category_nearby / top if top else 0.0,
                    },
                )
                for r in cells.shown
            ]
        ),
        "top": [_row(r, lang) for r in rows],
        "merged": {"requests": detail.requests_suppressed, "groups": detail.groups_suppressed},
        "actions": [
            {
                "district": _district_name(a.district, lang),
                "category": _category(a.category, lang),
                "count": a.count,
                "of": a.of,
            }
            for a in supply_actions(detail.rows, _district, lambda c: c)
        ],
    }


def _row(r: DemandRow, lang: str) -> dict:
    return {
        "district": _district_name(_district(r.cell), lang),
        "cell": r.cell,
        "category": _category(r.category, lang),
        "bucket": _bucket(r.bucket, lang),
        "requests": r.requests,
        "no_place": r.no_requested_category_nearby,
        "hours_unknown": r.hours_unknown_nearby,
        "share": round(r.no_category_share, 3),
    }


QUEUE_KINDS = (
    "closure",
    "hours",
)  # the notes that say a place may have closed or changed its hours
SNIPPET_CHARS = 140


def _clip(text: str | None) -> str:
    text = " ".join((text or "").split())
    return text if len(text) <= SNIPPET_CHARS else text[:SNIPPET_CHARS].rsplit(" ", 1)[0] + "…"


def _layers() -> dict:
    """What the data layers behind the assistant's extra lines hold, for the data-quality tab: the open OpenStreetMap
    notes about closures and opening hours as a queue to check (each with its link), the road-works count, and how far
    the afisha reaches. A layer without its file is None: the page says «данных нет», never «нет»."""
    summary = city_summary()
    snap = load_snapshot()
    by_source = Counter(e["source"] for e in snap.events)
    ordered = [s for s in SOURCE_LABELS if s in by_source]
    ordered += sorted(set(by_source) - set(SOURCE_LABELS))
    return {
        "notes": None
        if summary is None
        else {
            "open_total": summary.notes_open,
            "snapshot_date": summary.snapshot_date,
            "attribution": summary.attribution,
            "queue": [
                {
                    "id": n["id"],
                    "url": n["url"] or f"https://www.openstreetmap.org/note/{n['id']}",
                    "kind": n["classification"],
                    "date": n["date_created"],
                    "snippet": _clip(n["snippet"]),
                    "lat": n["lat"],
                    "lon": n["lon"],
                }
                for n in summary.open_notes
                if n["classification"] in QUEUE_KINDS
            ],
        },
        "construction": None if summary is None else summary.construction,
        "events": None
        if not snap.events
        else {
            "total": len(snap.events),
            "located": sum(e["venue"].get("lat") is not None for e in snap.events),
            "sources": [{"label": source_label(s), "count": by_source[s]} for s in ordered],
            "fetched_at": snap.fetched_at,
            "stale": snap.is_stale(local_now()),
        },
    }


def quality(metric: str | None, lang: str) -> dict:
    metric = metric if metric in QUALITY_METRICS else QUALITY_METRICS[0]
    pois = get_pois()
    entries = read_entries()
    cells = quality_cells(pois, marked_poi_ids(entries))
    total = sum(c.pois for c in cells)
    return {
        "metric": metric,
        "metrics": list(QUALITY_METRICS),
        "total": total,
        "shares": {
            m: round(sum(getattr(c, f"with_{m}") for c in cells) / total, 3) if total else 0.0
            for m in QUALITY_METRICS
        },
        "demo_marks": bool(entries) and all(e.demo for e in entries),
        "layers": _layers(),
        "cells": _features(
            [
                (
                    c.cell,
                    {
                        "pois": c.pois,
                        "hours": c.with_hours,
                        "description": c.with_description,
                        "people": c.with_people,
                        "t": round(c.share(metric), 3),
                    },
                )
                for c in cells
                if c.pois
            ]
        ),
        "worst": [
            {
                "category": _category(r.category, lang),
                "pois": r.pois,
                "with_hours": r.with_hours,
                "share": round(r.hours_share, 3),
            }
            for r in worst_hours_categories(pois)
        ],
        "actions": [
            {
                "district": _district_name(a.district, lang),
                "category": _category(a.category, lang),
                "missing": a.count,
                "of": a.of,
                "have": a.of - a.count,
            }
            for a in hours_actions(pois, district_of, lambda c: c)
        ],
    }


def reports(lang: str) -> dict:
    """The residents' anonymous marks: how many of each kind, the latest ones, and the places they are about."""
    entries = read_entries()
    by_id: dict[str, POI] = {p.id: p for p in get_pois()}
    counts = Counter(e.signal for e in entries)
    per_place: dict[str, Counter] = defaultdict(Counter)
    for e in entries:
        per_place[e.poi_id][e.signal] += 1
    recent = [
        {
            "name": by_id[e.poi_id].name,
            "kind": _category(by_id[e.poi_id].category, lang),
            "signal": e.signal,
            "label": signal_label(e.signal, lang),
            "date": e.date,
            "bucket": tr(f"part_{e.hour_bucket}", lang),
            "demo": e.demo,
        }
        for e in reversed(entries)
        if e.poi_id in by_id
    ][:RECENT_REPORTS]
    return {
        "total": len(entries),
        "demo": sum(e.demo for e in entries),
        "counts": dict(counts),
        "labels": {s: signal_label(s, lang) for s in counts},
        "recent": recent,
        "places": {
            "type": "FeatureCollection",
            "features": [
                {
                    "type": "Feature",
                    "geometry": {"type": "Point", "coordinates": [by_id[pid].lon, by_id[pid].lat]},
                    "properties": {
                        "name": by_id[pid].name,
                        "closed": c["was_closed"],
                        "open": c["was_open"],
                        "differ": c["hours_differ"],
                        "total": sum(c.values()),
                    },
                }
                for pid, c in per_place.items()
                if pid in by_id
            ],
        },
    }


def _csv_with_attribution(body: str) -> str:
    """A leading `#` line (pandas `comment="#"`, R and most CSV readers skip it) carries the ODbL notice."""
    return f"# {OSM_ATTRIBUTION}\n{body}"


def _geojson_with_attribution(collection: dict) -> str:
    """RFC 7946 allows foreign members: the notice rides in the file, next to `features`."""
    return json.dumps({**collection, **ATTRIBUTION_MEMBERS}, ensure_ascii=False)


def districts_geojson() -> dict:
    """The district outlines (OSM relations, ODbL) with the attribution of the data in the body of the answer."""
    outlines = json.loads(DISTRICTS_PATH.read_text(encoding="utf-8"))
    return {**outlines, **ATTRIBUTION_MEMBERS}


def export(name: str, source: str | None, k: int | None) -> tuple[str, str] | None:
    """(body, media type) of a download: the demand groups (k-anonymous) or the data-quality cells. Every body names
    OpenStreetMap: the cells are counted against the place database, which is an ODbL derivative (data/NOTICE.md)."""
    if name.startswith("demand."):
        paths = _sources()
        if not paths:
            return None
        source = source if source in paths else next(iter(paths))
        k_min = K_DEFAULT if source == "real" else K_SIM_MIN
        rows = aggregate_demand(
            _requests(paths[source]), min(max(k or K_DEFAULT, k_min), K_MAX), by=DIMS
        ).rows
        if name == "demand.csv":
            return _csv_with_attribution(demand_csv(rows)), "text/csv; charset=utf-8"
        if name == "demand.geojson":
            return _geojson_with_attribution(demand_geojson(rows)), "application/geo+json"
        return None
    cells = quality_cells(get_pois(), marked_poi_ids(read_entries()))
    if name == "quality.csv":
        return _csv_with_attribution(quality_csv(cells)), "text/csv; charset=utf-8"
    if name == "quality.geojson":
        return _geojson_with_attribution(quality_geojson(cells)), "application/geo+json"
    return None
