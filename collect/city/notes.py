"""OSM Notes in the Astana bbox: one API page (open + closed, any age), classified (SOURCES.md §14.6 verdict: STORE, ODbL).

The OSM Notes API (`https://api.openstreetmap.org/api/0.6/notes/search.json?bbox=…&closed=-1&limit=…`) returns a
GeoJSON FeatureCollection. Stored per note (never the full thread, never author names, never html):

    {"id", "lat", "lon", "status": "open"|"closed", "date_created", "date_closed"?, "url",
     "classification": "closure"|"new_place"|"construction"|"hours"|"other", "snippet", "source_url",
     "fetched_at", "license", "attribution"}

The snippet is only the first comment's text (whitespace-normalised, clipped) — evidence for the classification
and the only text kept. Author names/uids and comment counts are dropped on purpose: the product layer needs
«есть открытая заметка рядом» + a link, not the discussion.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

try:
    from collect.city.common import (
        ATTRIBUTION,
        BBOX_OSM_API,
        LICENSE,
        count_by,
        now_iso,
        snapshot_date,
    )
    from collect.net import Net, default_net
except ImportError:  # plain script run
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from collect.city.common import (
        ATTRIBUTION,
        BBOX_OSM_API,
        LICENSE,
        count_by,
        now_iso,
        snapshot_date,
    )
    from collect.net import Net, default_net

API_URL = "https://api.openstreetmap.org/api/0.6/notes/search.json"
LIMIT = 300  # the API page cap. NOTE: closed=-1 returns ALL statuses ordered by last_updated desc; this bbox
# holds far more than one page, so the snapshot is "the 300 most recently updated notes" (date_created spans
# 2016→2026), NOT a recent-window filter. The app's notes_open / closed counts (walks.city_layers) are counts
# within this page only, i.e. a LOWER BOUND on open notes — paging over dates is a post-22.10 item. There is no
# 45-day filter here.
# Classifications whose text snippet the app actually shows (walks.city_layers): for everything else the text
# is dropped at collection time — spam ads and personal notes stay out of the stored data entirely.
USED_CLASSIFICATIONS = frozenset({"closure", "hours", "new_place", "construction"})
WS = re.compile(r"\s+")

# Classification by the note text (the first comment). Ordered; the first match wins. The closure patterns are the
# stock sentences of the map apps' auto-reports (Organic Maps / MAPS.ME: «The place has gone or never existed»)
# plus the plain words a person writes when a place is gone. «Stroika» is a fact about the map (a building site),
# separate from highway=construction.
_CLOSURE = re.compile(
    r"place has (?:gone|closed)|no longer|not there anymore|never existed|is closed|closed (?:down|permanently)"
    r"|нету|нет такого|исчез|закрыт[оы]?|вывеска снята|больше не работает|переехал|снес|разрушен|с rub|снесены"
    r"|already demolished|демонтаж|не работает|no such (?:office|place|object)",
    re.I,
)
_NEW_PLACE = re.compile(
    r"new (?:shop|road|building|place|cafe|restaurant|sport)|открыл\w* (?:кафе|магазин|бар|ресторан|аптека|салон)"
    r"|нов\w+ (?:магазин|кафе|дорога|трасса|здание|тротуар)|здесь (?:есть|находится) |открылось|началось строительство"
    r"|prosu dobavit|прошу (?:вас )?добавить|добавить здание|не существующего объекта|no longer exists.*new",
    re.I,
)
_CONSTRUCTION = re.compile(r"строительств\w+|under construction|стройк\w+|строительн\w+|demolish\w*|снос\b", re.I)
_HOURS = re.compile(r"opening hours|часы работы|круглосуточн\w*|24/7|график работы", re.I)


def classify(text: str) -> str:
    t = WS.sub(" ", text or "")
    if _CLOSURE.search(t):
        return "closure"
    if _NEW_PLACE.search(t):
        return "new_place"
    if _CONSTRUCTION.search(t):
        return "construction"
    if _HOURS.search(t):
        return "hours"
    return "other"


def note_url(note_id: int) -> str:
    return f"https://www.openstreetmap.org/note/{note_id}"


def collect(net: Net | None = None) -> tuple[list[dict], dict]:
    """(notes, meta). One GET through the polite layer (api.openstreetmap.org, default policy 2 rps; the query is
    cached in .local/http_cache.sqlite, so reruns are identical without touching the server)."""
    net = net or default_net()
    params = {"bbox": BBOX_OSM_API, "closed": "-1", "limit": str(LIMIT)}
    resp = net.get(API_URL, params=params, timeout=60.0)
    data = resp.json()
    fetched = now_iso()
    snap = snapshot_date(resp.fetched_at)
    out: list[dict] = []
    for feat in data.get("features", []):
        props = feat.get("properties") or {}
        geom = feat.get("geometry") or {}
        coords = geom.get("coordinates") or [None, None]
        note_id = props.get("id")
        if note_id is None or coords[0] is None:
            continue
        comments = props.get("comments") or []
        first = comments[0] if comments else {}
        text = WS.sub(" ", str(first.get("text") or "")).strip()
        status = props.get("status") or ("open" if not props.get("closed_at") else "closed")
        classification = classify(text)
        # Privacy: the text of an «other» note (spam ads, personal addresses, jokes) is never used by the app
        # and is not stored — only the classification, the date and the note URL are.
        out.append(
            {
                "id": note_id,
                "lat": round(float(coords[1]), 6),
                "lon": round(float(coords[0]), 6),
                "status": status,
                "date_created": (props.get("date_created") or "")[:10] or None,
                "date_closed": (props.get("closed_at") or "")[:10] or None,
                "classification": classification,
                "snippet": text[:200] or None if classification in USED_CLASSIFICATIONS else None,
                "url": note_url(note_id),
                "source_url": API_URL,
                "fetched_at": fetched,
                "license": LICENSE,
                "attribution": ATTRIBUTION,
            }
        )
    out.sort(key=lambda n: n["id"])
    meta = {
        "count": len(out),
        "by_status": count_by(out, "status"),
        "by_classification": count_by(out, "classification"),
        "page_limit": LIMIT,
        "window": "single API page, most recently updated, any status — not a date window; open count is a lower bound",
        "bbox": BBOX_OSM_API,
        "snapshot_date": snap,
        "license": LICENSE,
        "attribution": ATTRIBUTION,
        "source": "OpenStreetMap Notes API (api.openstreetmap.org/api/0.6/notes/search.json)",
    }
    return out, meta
