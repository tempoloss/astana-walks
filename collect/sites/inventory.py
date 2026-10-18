"""Domain inventory: which official websites do our POIs point to, and which key places have none?

Usage: uv run python -m collect.sites.inventory     ->  data/sites/inventory.json
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.sites.domains import normalize_website, poi_domains, registrable_domain

ROOT = Path(__file__).resolve().parents[2]
POI_PATH = ROOT / "data" / "poi.enriched.json"
OUT_PATH = ROOT / "data" / "sites" / "inventory.json"

# Categories whose official pages (museum/theatre/mall/cinema/sport centre) are worth finding by hand.
MANUAL_CATEGORIES = ("museum_gallery", "culture_theatre_cinema", "mall", "sport")
SAMPLE_NAMES = 5


def build_inventory(pois: list[dict]) -> dict:
    by_domain: dict[str, dict] = defaultdict(lambda: {
        "poi_ids": [], "categories": Counter(), "names": [], "urls": Counter(), "brands": Counter()})
    no_site: list[dict] = []
    for p in pois:
        domains = poi_domains(p)
        if not domains:
            if p["category"] in MANUAL_CATEGORIES:
                social = [u for u in (p.get("website") or "").split(";") if u.strip()]
                no_site.append({
                    "poi_id": p["id"], "name": p["name"], "category": p["category"], "lat": p["lat"],
                    "lon": p["lon"], "address": p.get("address"), "opening_hours": p.get("opening_hours"),
                    "social_only_website": social[0].strip() if social else None})
            continue
        for d in domains:
            rec = by_domain[d]
            rec["poi_ids"].append(p["id"])
            rec["categories"][p["category"]] += 1
            if p["name"] not in rec["names"]:
                rec["names"].append(p["name"])
            for raw in (p.get("website") or "").split(";"):
                if registrable_domain(raw) == d and (u := normalize_website(raw)):
                    rec["urls"][u] += 1
            if p.get("brand"):
                rec["brands"][p["brand"]] += 1
    domains = [
        {
            "domain": d,
            "poi_count": len(r["poi_ids"]),
            "categories": dict(r["categories"].most_common()),
            "sample_names": r["names"][:SAMPLE_NAMES],
            "urls": [u for u, _ in r["urls"].most_common(5)],
            "brands": [b for b, _ in r["brands"].most_common(3)],
            "poi_ids": r["poi_ids"],
        }
        for d, r in by_domain.items()
    ]
    domains.sort(key=lambda r: (-r["poi_count"], r["domain"]))
    no_site.sort(key=lambda r: (MANUAL_CATEGORIES.index(r["category"]), r["name"]))
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "source": POI_PATH.name,
        "poi_total": len(pois),
        "pois_with_crawlable_site": len({i for r in domains for i in r["poi_ids"]}),
        "domain_count": len(domains),
        "domains": domains,
        "manual_targets": no_site,
        "manual_categories": list(MANUAL_CATEGORIES),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--poi", default=str(POI_PATH))
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args(argv)
    inv = build_inventory(json.loads(Path(args.poi).read_text(encoding="utf-8")))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(inv, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    top = ", ".join(f"{r['domain']}={r['poi_count']}" for r in inv["domains"][:8])
    print(f"[inventory] {inv['domain_count']} domains for {inv['pois_with_crawlable_site']}/{inv['poi_total']} POIs "
          f"(top: {top}); manual targets without website: {len(inv['manual_targets'])} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
