"""Deterministic verifier of the state-object facts: every evidence snippet must be found (whitespace-normalised) in the
cached source page, otherwise the fact it backs is dropped; a record without evidenced name is dropped.

`check_dataset` is the guard of the finished dataset: every field a registry wrote must name its evidence page on an
allowed host, administration hours must never sit in `opening_hours`, and `opening_hours` taken from the registry must
be a day-qualified venue schedule.

Usage (repo root):
  uv run python -m collect.gov.verify [--write] [--strict]       facts in data/gov/facts (cache only)
  uv run python -m collect.gov.verify --dataset data/poi.enriched.json
"""

from __future__ import annotations

import argparse
import copy
import json
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.gov.model import SOURCE, GovRecord, validate_record
from collect.sites.fetch import SiteFetcher
from collect.sites.hours import validate_osm
from collect.sites.store import now_iso
from collect.sites.verify import Verifier

ROOT = Path(__file__).resolve().parents[2]
FACTS_DIR = ROOT / "data" / "gov" / "facts"
ALLOWED_HOSTS = ("gov4c.kz", "data.egov.kz")
REGISTRY_FIELDS = ("name", "address", "phone", "opening_hours", "admin_hours", "lat", "lon", "category",
                   "address_kk")
# address_kk sits with lat/lon/category: its source is the RCA snapshot gazetteer (data/gazetteer/rca_streets.json),
# not a per-row snippet of the page.


def verify_record(rec: dict, verifier: Verifier) -> tuple[dict | None, Counter]:
    """(cleaned record or None when its name is no longer evidenced, counters)."""
    stats: Counter = Counter()
    r = GovRecord.from_dict(copy.deepcopy(rec))
    good = []
    for e in r.evidence:
        stats["evidence_total"] += 1
        if verifier.snippet_found(e.url, e.snippet):
            stats["evidence_ok"] += 1
            good.append(e)
        else:
            stats["evidence_dropped"] += 1
            stats[f"evidence_dropped_{e.field}"] += 1
    r.evidence = good
    covered = {e.field for e in good}
    if "name" not in covered:
        stats["records_dropped"] += 1
        return None, stats
    if r.address.get("raw") and "address" not in covered:
        r.address = {**r.address, "raw": "", "street": "", "house": None, "key": ""}
        stats["fact_dropped_address"] += 1
    if r.phone_raw and "phone" not in covered:
        r.phone_raw = None
        stats["fact_dropped_phone"] += 1
    if r.hours and ("opening_hours" if r.hours.scope == "venue" else "admin_hours") not in covered:
        r.hours = None
        stats["fact_dropped_hours"] += 1
    stats["records_out"] += 1
    return r.to_dict(), stats


def verify_file(payload: dict, verifier: Verifier) -> tuple[dict, Counter]:
    total: Counter = Counter()
    kept = []
    for rec in payload["records"]:
        cleaned, st = verify_record(rec, verifier)
        total.update(st)
        if cleaned is not None:
            kept.append(cleaned)
    out = {**payload, "records": kept, "verified_at": now_iso()}
    for r in kept:
        total["schema_problems"] += len(validate_record(GovRecord.from_dict(r)))
    return out, total


def check_dataset(pois: list[dict]) -> list[str]:
    """Problems of the registry-backed fields of a built dataset (empty list = fine)."""
    problems: list[str] = []
    for p in pois:
        fsrc = p.get("field_sources") or {}
        reg = {f: s for f, s in fsrc.items() if isinstance(s, dict) and s.get("source") == SOURCE}
        who = f"{p['id']} {p['name']!r}"
        match = p.get("state_registry_match")
        if not reg and not match:
            continue
        if not match:
            problems.append(f"{who}: registry fields {sorted(reg)} without state_registry_match")
            continue
        for f, s in reg.items():
            host = urlsplit(s.get("url") or "").hostname or ""
            if host not in ALLOWED_HOSTS:
                problems.append(f"{who}: {f} evidence URL {s.get('url')!r} is not on {ALLOWED_HOSTS}")
            if f not in ("lat", "lon", "category", "address_kk") and not s.get("snippet"):
                problems.append(f"{who}: {f} has no evidence snippet")
        if "opening_hours" in reg:
            if match.get("kind") != "cson" or match.get("hours_scope") != "venue":
                problems.append(f"{who}: opening_hours from the registry with scope {match.get('hours_scope')!r}")
            if not validate_osm(p.get("opening_hours")):
                problems.append(f"{who}: registry opening_hours {p.get('opening_hours')!r} is not a valid schedule")
        if p.get("admin_hours") and p.get("opening_hours") and p["opening_hours"] == (p["admin_hours"] or {}).get("raw"):
            problems.append(f"{who}: admin_hours duplicated into opening_hours")
        if match.get("kind") == "sport_facility" and "opening_hours" in reg:
            problems.append(f"{who}: sport register fills opening_hours")
    return problems


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--facts", default=str(FACTS_DIR))
    ap.add_argument("--write", action="store_true", help="rewrite the facts files without the dropped facts")
    ap.add_argument("--strict", action="store_true", help="exit 1 if anything was dropped")
    ap.add_argument("--dataset", metavar="POI_JSON", help="check the registry fields of a built dataset instead")
    args = ap.parse_args(argv)
    if args.dataset:
        problems = check_dataset(json.loads(Path(args.dataset).read_text(encoding="utf-8")))
        for line in problems:
            print(f"[gov.verify] {line}", file=sys.stderr)
        print(f"[gov.verify] dataset {args.dataset}: {len(problems)} problem(s)")
        return 1 if problems else 0
    verifier = Verifier(SiteFetcher())
    grand: Counter = Counter()
    for path in sorted(Path(args.facts).glob("*.json")):
        out, st = verify_file(json.loads(path.read_text(encoding="utf-8")), verifier)
        grand.update(st)
        print(f"[gov.verify] {path.name}: " + ", ".join(f"{k}={v}" for k, v in sorted(st.items())))
        if args.write:
            path.write_text(json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    dropped = grand["evidence_dropped"] or grand["records_dropped"] or grand["schema_problems"]
    return 1 if args.strict and dropped else 0


if __name__ == "__main__":
    sys.exit(main())
