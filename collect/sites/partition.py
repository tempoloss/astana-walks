"""Split the inventory into 6 balanced crawl work lists: data/sites/partitions/p1..p6.json.

Domains are dealt out heaviest-first to the currently lightest list, so big chains (many branches = many pages) land in
different lists. The places without any website (manual discovery of the official page) start in p6 and p6 is then only
topped up with domains until its weight matches the others.

Usage: uv run python -m collect.sites.partition
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.sites.inventory import OUT_PATH as INVENTORY_PATH

PARTS = 6
OUT_DIR = INVENTORY_PATH.parent / "partitions"
MANUAL_WEIGHT = 1.0  # one place = one lookup of its official page, then the same crawl as a 1-POI domain
DOMAIN_BASE = 1.0  # fixed cost of a domain; each POI adds 1 (a chain locator costs about one page per branch)


def build_partitions(inv: dict, parts: int = PARTS) -> list[dict]:
    bins = [{"partition": f"p{i + 1}", "weight": 0.0, "items": []} for i in range(parts)]
    for t in inv["manual_targets"]:
        bins[-1]["items"].append({"kind": "manual", **t})
        bins[-1]["weight"] += MANUAL_WEIGHT
    domains = [{"kind": "domain", **{k: d[k] for k in ("domain", "poi_count", "categories", "sample_names", "urls",
                                                           "brands", "poi_ids")}} for d in inv["domains"]]
    for d in sorted(domains, key=lambda d: (-d["poi_count"], d["domain"])):
        lightest = min(bins, key=lambda b: (b["weight"], b["partition"]))
        lightest["items"].append(d)
        lightest["weight"] += DOMAIN_BASE + d["poi_count"]
    for b in bins:
        b["weight"] = round(b["weight"], 1)
        b["domain_count"] = sum(i["kind"] == "domain" for i in b["items"])
        b["manual_count"] = sum(i["kind"] == "manual" for i in b["items"])
        b["poi_count"] = sum(i.get("poi_count", 1) for i in b["items"])
    return bins


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--inventory", default=str(INVENTORY_PATH))
    ap.add_argument("--out-dir", default=str(OUT_DIR))
    args = ap.parse_args(argv)
    inv = json.loads(Path(args.inventory).read_text(encoding="utf-8"))
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    for b in build_partitions(inv):
        (out_dir / f"{b['partition']}.json").write_text(json.dumps(b, ensure_ascii=False, indent=1) + "\n",
                                                        encoding="utf-8")
        print(f"[partition] {b['partition']}: weight {b['weight']}, {b['domain_count']} domains, "
              f"{b['manual_count']} manual, {b['poi_count']} POIs")
    return 0


if __name__ == "__main__":
    sys.exit(main())
