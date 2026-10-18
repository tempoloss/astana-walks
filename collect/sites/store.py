"""Fact schema and on-disk store: one JSON file per domain, `data/sites/facts/<domain>.json`.

    {"domain": "kfc.kz", "robots_ok": true, "fetched_at": "2026-10-17T10:00:00+00:00",
     "pages": ["https://kfc.kz/stores"],
     "branches": [{"name", "address", "lat", "lon", "phone", "opening_hours_raw", "opening_hours_osm",
                   "description", "url",
                   "evidence": [{"field", "url", "snippet", "fetched_at"?}],
                   "method": "jsonld" | "locator_json" | "html" | "agent_extract", "confidence": 0..1}],
     "notes": "free text: what was tried, what is missing"}

Rules (enforced by `validate_branch`): no fact without evidence; a snippet is a verbatim (whitespace-normalised)
substring of the page at `url`, <= 300 chars; `opening_hours_osm` exists only when `hours.to_osm(raw)` produced it.
`hours_flags` (["needs_days"] | ["ambiguous_24h"] | both | []) records why a schedule text was kept only as
`opening_hours_raw`: it names no days, or is a `00:00-00:00` range without "круглосуточно".
"""

from __future__ import annotations

import json
import re
from collections.abc import Iterator
from datetime import UTC, datetime
from pathlib import Path

from collect.sites.hours import hours_flags, to_osm

ROOT = Path(__file__).resolve().parents[2]
SITES_DIR = ROOT / "data" / "sites"
FACTS_DIR = SITES_DIR / "facts"

METHODS = ("jsonld", "locator_json", "html", "agent_extract")
SNIPPET_MAX = 300
# Same Astana box as overture_places.BBOX / wiki_enrich.BBOX; coordinates outside it are not Astana facts.
ASTANA_LAT, ASTANA_LON = (50.98, 51.25), (71.25, 71.60)
# Which evidence `field` values justify which branch field.
FIELD_EVIDENCE: dict[str, frozenset[str]] = {
    "address": frozenset({"address"}),
    "phone": frozenset({"phone"}),
    "opening_hours_raw": frozenset({"opening_hours"}),
    "opening_hours_osm": frozenset({"opening_hours"}),
    "description": frozenset({"description"}),
    "price_text": frozenset({"price"}),
    "coords": frozenset({"geo", "lat", "lon", "coords"}),
}
EVIDENCE_FIELDS = frozenset({"name"}).union(*FIELD_EVIDENCE.values())
_WS = re.compile(r"\s+")


def now_iso() -> str:
    return datetime.now(UTC).isoformat(timespec="seconds")


def norm_ws(text: str) -> str:
    return _WS.sub(" ", text or "").strip()


def in_astana(lat: float | None, lon: float | None) -> bool:
    return lat is not None and lon is not None and ASTANA_LAT[0] <= lat <= ASTANA_LAT[1] \
        and ASTANA_LON[0] <= lon <= ASTANA_LON[1]


def clip_snippet(text: str) -> str:
    return norm_ws(text)[:SNIPPET_MAX]


def evidence(field: str, url: str, snippet: str, fetched_at: str | None = None) -> dict:
    ev = {"field": field, "url": url, "snippet": clip_snippet(snippet)}
    if fetched_at:
        ev["fetched_at"] = fetched_at
    return ev


def make_branch(
    name: str, evidence: list[dict], method: str, confidence: float, *, address: str | None = None,
    lat: float | None = None, lon: float | None = None, phone: str | None = None,
    opening_hours_raw: str | None = None, opening_hours_osm: str | None = None, description: str | None = None,
    price_text: str | None = None, url: str | None = None,
) -> dict:
    """A schema-conforming branch. `opening_hours_osm` is always recomputed from the raw text (None if not
    deterministic), so callers never hand-write OSM strings."""
    raw = norm_ws(opening_hours_raw) or None
    return {
        "name": norm_ws(name),
        "address": norm_ws(address) or None,
        "lat": None if lat is None or lon is None else float(lat),
        "lon": None if lat is None or lon is None else float(lon),
        "phone": norm_ws(phone) or None,
        "opening_hours_raw": raw,
        "opening_hours_osm": to_osm(raw) if raw else None,
        "hours_flags": hours_flags(raw),  # why raw was not converted: "needs_days" | "ambiguous_24h"
        "description": norm_ws(description) or None,
        "price_text": norm_ws(price_text) or None,  # the site's own price wording, never parsed into a number
        "url": url or None,
        "evidence": [{**e, "snippet": clip_snippet(e["snippet"])} for e in evidence],
        "method": method,
        "confidence": round(float(confidence), 3),
    }


def validate_branch(b: dict) -> list[str]:
    errs: list[str] = []
    if not isinstance(b.get("name"), str) or not b["name"].strip():
        errs.append("name missing")
    if b.get("method") not in METHODS:
        errs.append(f"method {b.get('method')!r} not in {METHODS}")
    conf = b.get("confidence")
    if not isinstance(conf, int | float) or not 0 <= conf <= 1:
        errs.append("confidence must be a number in [0, 1]")
    lat, lon = b.get("lat"), b.get("lon")
    if (lat is None) != (lon is None):
        errs.append("lat and lon go together")
    elif lat is not None and not (isinstance(lat, int | float) and isinstance(lon, int | float)
                                  and -90 <= lat <= 90 and -180 <= lon <= 180):
        errs.append("lat/lon out of range")
    evs = b.get("evidence")
    if not isinstance(evs, list) or not evs:
        return [*errs, "no evidence"]
    covered: set[str] = set()
    for i, e in enumerate(evs):
        if not isinstance(e, dict) or not all(isinstance(e.get(k), str) and e[k].strip()
                                              for k in ("field", "url", "snippet")):
            errs.append(f"evidence[{i}] needs non-empty field/url/snippet")
            continue
        if e["field"] not in EVIDENCE_FIELDS:
            errs.append(f"evidence[{i}].field {e['field']!r} unknown")
        if len(e["snippet"]) > SNIPPET_MAX:
            errs.append(f"evidence[{i}].snippet longer than {SNIPPET_MAX}")
        covered.add(e["field"])
    if not covered:
        errs.append("no usable evidence")
    for key, fields in FIELD_EVIDENCE.items():
        has = (lat is not None) if key == "coords" else bool(b.get(key))
        if has and not covered & fields:
            errs.append(f"{key} has no evidence (need field in {sorted(fields)})")
    raw, osm = b.get("opening_hours_raw"), b.get("opening_hours_osm")
    if osm and (not raw or to_osm(raw) != osm):
        errs.append("opening_hours_osm is not the deterministic conversion of opening_hours_raw")
    if (b.get("hours_flags") or []) != hours_flags(raw):
        errs.append(f"hours_flags {b.get('hours_flags')!r} is not what hours.hours_flags(opening_hours_raw) gives "
                    f"({hours_flags(raw)!r}); save_facts fills it")
    return errs


def new_record(domain: str, *, robots_ok: bool, pages: list[str] | None = None, branches: list[dict] | None = None,
               notes: str = "", fetched_at: str | None = None, source_label: str | None = None) -> dict:
    rec = {
        "domain": domain, "robots_ok": robots_ok, "fetched_at": fetched_at or now_iso(),
        "pages": list(dict.fromkeys(pages or [])), "branches": branches or [], "notes": notes,
    }
    if source_label:
        rec["source_label"] = source_label  # e.g. "museum_register": a register, not the institutions' own site
    return rec


def validate_record(rec: dict) -> list[str]:
    errs = []
    for key, typ in (("domain", str), ("robots_ok", bool), ("fetched_at", str), ("pages", list), ("branches", list),
                     ("notes", str)):
        if not isinstance(rec.get(key), typ):
            errs.append(f"{key}: expected {typ.__name__}")
    for i, b in enumerate(rec.get("branches") or []):
        errs.extend(f"branches[{i}] ({b.get('name') if isinstance(b, dict) else '?'}): {e}"
                    for e in validate_branch(b if isinstance(b, dict) else {}))
    if rec.get("robots_ok") is False and rec.get("branches"):
        errs.append("robots_ok is false but branches are present (crawling was not allowed)")
    return errs


def facts_path(domain: str, facts_dir: Path | None = None) -> Path:
    if not re.fullmatch(r"[a-z0-9.-]+", domain):
        raise ValueError(f"bad domain {domain!r}")
    return (facts_dir or FACTS_DIR) / f"{domain}.json"


def save_facts(rec: dict, facts_dir: Path | None = None) -> Path:
    """Validate and write the record (atomic). Raises ValueError listing every schema violation.

    `hours_flags` is derived data: it is (re)filled from `opening_hours_raw` before validation."""
    for b in rec.get("branches") or []:
        if isinstance(b, dict):
            b["hours_flags"] = hours_flags(b.get("opening_hours_raw"))
    errs = validate_record(rec)
    if errs:
        raise ValueError(f"{rec.get('domain')}: " + "; ".join(errs))
    path = facts_path(rec["domain"], facts_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(rec, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    tmp.replace(path)
    return path


def load_facts(domain: str, facts_dir: Path | None = None) -> dict | None:
    path = facts_path(domain, facts_dir)
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def iter_facts(facts_dir: Path | None = None) -> Iterator[dict]:
    for path in sorted((facts_dir or FACTS_DIR).glob("*.json")):
        yield json.loads(path.read_text(encoding="utf-8"))
