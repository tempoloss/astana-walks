"""Join official Magnum store hours (Strapi dump, collect/recon/round13/magnum_shops_raw.json)
into data/poi.enriched.json for grocery POIs of the Magnum chain.

The dump gives open_hour/close_hour WITHOUT days of the week, so per the repo's §13 / §24.13
convention it is never written as an OSM-style opening_hours with invented days:

* the pair 00:00 / 00:00 means around-the-clock -> opening_hours="24/7", hours_state="known";
* any other pair -> hours_unqualified="с HH:MM до HH:MM", hours_unqualified_flags=["needs_days"]
  (hours_state stays "unknown"; the consumer is walks/hours.py:93, walks/reasons.py:253);
* a record that already has opening_hours (or hours_unqualified) is NEVER touched — counted
  as `already`.

Match rule: nearest dump point within 120 m (haversine from collect.overpass_poi).
Idempotent. Backup: .bak-magnum next to the base; log: magnum_hours_log.jsonl.

Usage (repo root): uv run python collect/recon/round13/magnum_hours_join.py [--dry]
"""
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "app"))

from collect.overpass_poi import haversine_m  # production code path

BASE = ROOT / "data" / "poi.enriched.json"
DUMP = Path(__file__).with_name("magnum_shops_raw.json")
LOG = Path(__file__).with_name("magnum_hours_log.jsonl")
SNAPSHOT_DATE = "2026-10-19"
FIELD_SOURCE = {
    "source": "magnum_official",
    "license": "facts from the business's own site",
    "snapshot_date": SNAPSHOT_DATE,
}
MAX_M = 120.0


def load_shops() -> list[dict]:
    """Normalized dump rows: {lat, lon, open_h, close_h} with raw «HH:MM:SS» strings."""
    raw = json.loads(DUMP.read_text(encoding="utf-8"))
    rows = raw["data"] if isinstance(raw, dict) else raw
    shops = []
    for row in rows:
        attrs = row["attributes"]
        geo = attrs.get("geo") or {}
        lat, lon = geo.get("latitude"), geo.get("longitude")
        if lat is None or lon is None or not attrs.get("open_hour") or not attrs.get("close_hour"):
            continue
        shops.append({"lat": lat, "lon": lon, "open_h": attrs["open_hour"], "close_h": attrs["close_hour"]})
    return shops


def match_shop(lat: float, lon: float, shops: list[dict], max_m: float = MAX_M) -> dict | None:
    """Nearest dump shop within max_m of (lat, lon), or None."""
    best, best_d = None, None
    for s in shops:
        d = haversine_m(lat, lon, s["lat"], s["lon"])
        if d <= max_m and (best_d is None or d < best_d):
            best, best_d = s, d
    return best


def hours_official_text(pair: tuple[str, str]) -> str:
    """Hours text for a dump (open_hour, close_hour) pair: «с HH:MM до HH:MM», or «24/7»
    for the 00:00 / 00:00 pair (the site's way of saying around-the-clock)."""
    open_h, close_h = pair[0][:5], pair[1][:5]
    if open_h == "00:00" and close_h == "00:00":
        return "24/7"
    return f"с {open_h} до {close_h}"


def is_magnum(rec: dict) -> bool:
    if rec.get("category") != "grocery":
        return False
    if "magnum" in (rec.get("name") or "").lower():
        return True
    tags = rec.get("tags") or []  # list of «key=value» strings (POI.tag_dict)
    return any(t.lower() == "brand=magnum" for t in tags)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    args = ap.parse_args()

    shops = load_shops()
    base = json.loads(BASE.read_text(encoding="utf-8"))

    filled_unqualified, filled_247, already, no_match = 0, 0, 0, 0
    for rec in base:
        if not is_magnum(rec):
            continue
        if rec.get("opening_hours") or rec.get("hours_unqualified"):
            already += 1
            continue
        hit = match_shop(rec.get("lat"), rec.get("lon"), shops)
        if hit is None:
            no_match += 1
            continue
        text = hours_official_text((hit["open_h"], hit["close_h"]))
        if text == "24/7":
            rec["opening_hours"] = "24/7"
            rec["hours_state"] = "known"
            fs_key = "opening_hours"
            filled_247 += 1
        else:
            rec["hours_unqualified"] = text
            rec["hours_unqualified_flags"] = ["needs_days"]
            rec.setdefault("hours_state", None)
            if not rec.get("hours_state"):
                rec["hours_state"] = "unknown"
            fs_key = "hours_unqualified"
            filled_unqualified += 1
        fs = rec.get("field_sources")
        if not isinstance(fs, dict):
            fs = {}
            rec["field_sources"] = fs
        fs[fs_key] = dict(FIELD_SOURCE)

    print(
        f"filled_unqualified={filled_unqualified} filled_247={filled_247} "
        f"already={already} no_match={no_match} (shops={len(shops)})"
    )
    LOG.open("a", encoding="utf-8").write(
        json.dumps(
            {
                "dry": args.dry,
                "filled_unqualified": filled_unqualified,
                "filled_247": filled_247,
                "already": already,
                "no_match": no_match,
            }
        )
        + "\n"
    )
    if args.dry:
        print("DRY: base untouched")
        return
    if filled_unqualified or filled_247:
        BASE.with_suffix(".json.bak-magnum").write_text(
            json.dumps(json.loads(BASE.read_text(encoding="utf-8")), ensure_ascii=False), encoding="utf-8"
        )
        BASE.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
        print(f"base: {len(base)} records written (backup .bak-magnum)")
    else:
        print("nothing to write")


if __name__ == "__main__":
    main()
