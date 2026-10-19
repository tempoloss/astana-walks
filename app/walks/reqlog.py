"""Anonymised per-request log for a later demand/coverage report.

One JSON line per served request, in app/.local/requests.jsonl. At MAX_LOG_BYTES the file is moved to
requests.jsonl.1 (replacing the previous one), so a public instance cannot fill the disk.
Contains ONLY: timestamp rounded to the hour,
the id of a ~500 m grid cell (derived from the already-rounded location; never raw coordinates), the parsed
intent categories/flags, the declared and the searched radius, how many places of the requested kinds the dataset
holds inside the time-budget radius (and how many of them have confirmed hours), candidate and recommendation
counts (also split by padding: none / expanded / backfill / substituted), hours_state counts, and how long the answer
took (`total_ms`: the pipeline's own time, or, for a request of the web page, the whole turn from the message to the
ready answer, see `held`).
No free text, no names, no POI ids. Answers that used a personal profile (Result.private) are not logged at all.

Set WALKS_REQUEST_LOG=off to disable, or to a file path to redirect.

Only requests from inside Astana (ASTANA_BBOX) are logged: the demand map is the city's, and a request from Moscow or
the pole says nothing about it.
"""

from __future__ import annotations

import json
import math
import os
from collections import Counter
from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar
from pathlib import Path

from .models import Result

_HELD: ContextVar[list[dict] | None] = ContextVar("reqlog_held", default=None)

DEFAULT_PATH = Path(__file__).resolve().parents[1] / ".local" / "requests.jsonl"
MAX_LOG_BYTES = 5_000_000
CELL_M = 500
_LAT_REF = 51.1  # Astana: one fixed reference latitude keeps cells a uniform grid
_M_PER_DEG = 111_320.0
ASTANA_BBOX = (50.98, 71.25, 51.25, 71.65)  # south, west, north, east


def in_astana(lat: float, lon: float) -> bool:
    """True for a point inside the city bounding box (False for NaN / inf)."""
    south, west, north, east = ASTANA_BBOX
    return south <= lat <= north and west <= lon <= east


def _cell_deg() -> tuple[float, float]:
    """(degrees of latitude, degrees of longitude) of one cell side."""
    return CELL_M / _M_PER_DEG, CELL_M / (_M_PER_DEG * math.cos(math.radians(_LAT_REF)))


def grid_cell_id(lat: float, lon: float) -> str:
    """Id of the 500 m x 500 m cell containing the point, e.g. '1021_1830'."""
    dlat, dlon = _cell_deg()
    return f"{math.floor(lat / dlat)}_{math.floor(lon / dlon)}"


def cell_bounds(cell: str) -> tuple[float, float, float, float]:
    """(south, west, north, east) in degrees of a cell id made by `grid_cell_id`."""
    dlat, dlon = _cell_deg()
    i, j = (int(p) for p in cell.split("_"))
    return i * dlat, j * dlon, (i + 1) * dlat, (j + 1) * dlon


def log_path() -> Path | None:
    """The request log file (WALKS_REQUEST_LOG redirects it), or None when logging is off."""
    v = os.environ.get("WALKS_REQUEST_LOG", "").strip()
    if v.lower() == "off":
        return None
    return Path(v) if v else DEFAULT_PATH


def record_for(res: Result) -> dict:
    i = res.intent.intent
    return {
        "ts_hour": res.when.strftime("%Y-%m-%dT%H:00"),
        "cell": grid_cell_id(res.lat, res.lon),  # res.lat/lon are already rounded to ~100 m
        "mode": i.mode,
        "time_budget_min": i.time_budget_min,
        "categories": list(i.categories),
        "flags": {
            "with_kids": i.with_kids,
            "quiet": i.quiet,
            "needs_wifi_socket": i.needs_wifi_socket,
            "night": i.night,
            "accessibility": i.accessibility,
            "budget": i.budget,
        },
        "radius_m": res.retrieval.filters.radius_declared_m,
        "radius_effective_m": res.retrieval.filters.radius_effective_m,
        "requested_nearby": res.retrieval.filters.requested_nearby,
        "requested_nearby_with_hours": res.retrieval.filters.requested_nearby_with_hours,
        "candidates": len(res.retrieval.candidates),
        "candidates_by_padding": dict(Counter(c.padding for c in res.retrieval.candidates)),
        "recs_by_padding": dict(Counter(r.padding for r in res.recs)),
        "recs": len(res.recs),
        "hours_state_counts": {
            "candidates": dict(Counter(c.hours_state for c in res.retrieval.candidates)),
            "recs": dict(Counter(r.hours_state for r in res.recs)),
        },
        "total_ms": res.timings_ms.get("total"),
    }


@contextmanager
def held() -> Iterator[list[dict]]:
    """Inside, the records of the served requests wait in the yielded list instead of the file: the caller (the web
    turn) knows how long the whole answer took and writes them with that time (`write_held`)."""
    records: list[dict] = []
    token = _HELD.set(records)
    try:
        yield records
    finally:
        _HELD.reset(token)


def write_held(records: list[dict], total_ms: int) -> None:
    for record in records:
        _write({**record, "total_ms": total_ms})


def log_request(res: Result) -> None:
    if res.private:
        return  # a profile was involved: personal data is never written to the log
    if not in_astana(res.lat, res.lon):
        return  # outside the city: not demand for Astana
    if log_path() is None:
        return
    record = record_for(res)
    waiting = _HELD.get()
    if waiting is not None:
        waiting.append(record)
        return
    _write(record)


def _write(record: dict) -> None:
    path = log_path()
    if path is None:
        return
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists() and path.stat().st_size >= MAX_LOG_BYTES:
            os.replace(path, path.with_name(path.name + ".1"))
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass  # logging must never break serving
