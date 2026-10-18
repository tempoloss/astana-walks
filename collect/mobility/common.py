"""Shared helpers of the mobility collectors: JSON writing, evidence snippets, time in Astana."""

from __future__ import annotations

import re
from datetime import datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
OUT_DIR = ROOT / "data" / "mobility"

# Same Astana sanity box as collect/sites/store.py / overpass_poi.py; anything outside is not an Astana fact.
ASTANA_LAT, ASTANA_LON = (50.8, 51.4), (71.1, 71.9)

_WS = re.compile(r"\s+")
SNIPPET_MAX = 300


def now_iso() -> str:
    return datetime.now(tz=None).astimezone().isoformat(timespec="seconds")


def norm_ws(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def clip_snippet(text: str) -> str:
    return norm_ws(text)[:SNIPPET_MAX]


def in_astana(lat: float | None, lon: float | None) -> bool:
    return (
        lat is not None
        and lon is not None
        and ASTANA_LAT[0] <= lat <= ASTANA_LAT[1]
        and ASTANA_LON[0] <= lon <= ASTANA_LON[1]
    )


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json_dumps(obj) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def json_dumps(obj) -> str:
    import json

    return json.dumps(obj, ensure_ascii=False, indent=2)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    import math

    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
