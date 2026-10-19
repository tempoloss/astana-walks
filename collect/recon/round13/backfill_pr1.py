"""Backfill the PR-1 / PR-2 layers (pharmacy + grocery + toilets + money + lodging) into data/poi.enriched.json.

The full build() re-harvest churns 2 294 existing records and the frozen-snapshot
rule (collect/README.md) forbids that before the demo. This is the minimal,
additive path: run ONLY the new EXTRA_SELECTORS, normalize each element with
the production function (extra=True), skip ids already in the base, append, save.
Resume-safe: progress in collect/recon/round13/backfill_log.jsonl.

Usage (repo root): uv run python collect/recon/round13/backfill_pr1.py [--dry] [--only SUBSTRING ...]
(--only keeps the selectors that contain one of the substrings, e.g. `--only atm` for the money layer alone)
"""
import argparse, json, re, sys, time, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from collect.overpass_poi import EXTRA_SELECTORS, normalize  # production code path

MIRRORS = ["https://overpass-api.de/api/interpreter", "https://maps.mail.ru/osm/tools/overpass/api/interpreter"]
AREA = '[area["boundary"="administrative"]["name"="Астана"]]'
BASE = ROOT / "data" / "poi.enriched.json"
LOG = Path(__file__).with_name("backfill_log.jsonl")
COLLECTED_AT = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
UA = {"User-Agent": "astana-walks-recon/1.0", "Accept": "*/*"}
AREA = 'area["boundary"="administrative"]["name"="Астана"]'
LAYER_KEYS = ('pharmacy', 'supermarket', 'toilets', 'atm', 'hotel')
SELECTORS = [s for s in EXTRA_SELECTORS if any(k in s for k in LAYER_KEYS)]


def fetch(sel: str) -> list[dict]:
    q = f'[out:json][timeout:90];{AREA}->.a;nwr{sel}(area.a);out tags center;'
    for m in MIRRORS:
        for att in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(m, data=("data=" + q).encode(), headers=UA), timeout=120) as x:
                    return json.loads(x.read(40_000_000))["elements"]
            except Exception as e:
                print(f"  {m[:35]} att{att}: {str(e)[:70]}", flush=True)
                time.sleep(20 + 25 * att)
    raise RuntimeError(f"all mirrors failed for {sel}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--only", nargs="+", metavar="SUBSTRING")
    args = ap.parse_args()
    dry = args.dry
    selectors = [s for s in SELECTORS if not args.only or any(k in s for k in args.only)]
    base_recs = json.loads(BASE.read_text(encoding="utf-8"))
    existing = {r["id"] for r in base_recs}
    by_name: dict[str, list[dict]] = {}
    for r in base_recs:
        by_name.setdefault(r["name"].casefold(), []).append(r)
    added, skipped_dup, unnamed, skipped_near = [], 0, 0, 0
    # Lodging: an existing record that Overture files as a hotel-family place AND whose name says hotel (the one
    # «hotel_bar» «Айша Биби Отель», listed as a bar) is a hotel: reclassified, not duplicated, so the count in the
    # base and the count the answers can find agree.
    reclassified = {
        r["id"]: r for r in base_recs
        if r["category"] != "lodging"
        and any(t.startswith("overture_category=hotel") for t in r["tags"])
        and re.search(r"отел|отель|hotel|гостиниц|хостел|hostel", r["name"], re.I)
    } if any("hotel" in s for s in selectors) else {}
    for sel in selectors:
        els = fetch(sel)
        LOG.open("a", encoding="utf-8").write(json.dumps({"sel": sel, "elements": len(els)}) + "\n")
        print(sel, "->", len(els), "elements", flush=True)
        for el in els:
            try:
                rec = normalize(el, COLLECTED_AT, extra=True)
            except Exception:
                rec = None
            if rec is None:
                unnamed += 1
                continue
            if rec["id"] in existing:
                skipped_dup += 1
                continue
            rec["sources"] = ["osm"]  # license track like every other OSM record in the file
            # production add_extra semantics (overpass_poi.add_extra): a same-name neighbour within
            # DEDUP_RADIUS_M loses against the existing record
            from collect.overpass_poi import DEDUP_RADIUS_M, haversine_m
            if any(haversine_m(rec["lat"], rec["lon"], o["lat"], o["lon"]) <= DEDUP_RADIUS_M
                   for o in by_name.get(rec["name"].casefold(), ())):
                skipped_near += 1
                continue
            existing.add(rec["id"])
            by_name.setdefault(rec["name"].casefold(), []).append(rec)
            added.append(rec)
    print(f"added={len(added)} dup={skipped_dup} dropped(unnamed/geo-invalid)={unnamed} same-name-near={skipped_near}")
    for o in reclassified.values():
        print("reclassify ->lodging:", o["id"], o["name"], o["category"], o["tags"])
    from collections import Counter
    print("categories:", Counter(r["category"] for r in added))
    print("with hours:", sum(1 for r in added if r.get("opening_hours")))
    LOG.open("a", encoding="utf-8").write(json.dumps({"added": len(added), "dup": skipped_dup, "dropped": unnamed}) + "\n")
    if dry or not (added or reclassified):
        Path(__file__).with_name("backfill_preview.json").write_text(json.dumps(added[:80], ensure_ascii=False, indent=1), encoding="utf-8")
        print("DRY: preview saved, base untouched")
        return
    base = json.loads(BASE.read_text(encoding="utf-8"))
    BASE.with_suffix(".json.bak-pr1").write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    for r in base:
        if r["id"] in reclassified:
            r["category"] = "lodging"
    base.extend(added)
    BASE.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    print("base:", len(base), "records written (backup .bak-pr1)")


if __name__ == "__main__":
    main()
