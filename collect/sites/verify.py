"""Deterministic verifier: every evidence snippet must be found (whitespace-normalised) in the cached page.

Facts without a surviving snippet are dropped (a branch keeps only the fields whose evidence verified; a branch with
no facts left disappears) and `opening_hours_osm` / `hours_flags` are recomputed from the raw text with the current
`hours.analyze` rules (so `--write` also corrects files crawled under older rules). No LLM, no network by default.

`check_dataset` is the other half: it re-checks a *built* dataset (`--dataset data/poi.enriched.json`): every POI
field whose `field_sources` say `official_site` must come from a domain that speaks for the POI (`agree`: brand
agreement + category compatibility). `collect.sites.apply` refuses to write a dataset that fails it.

Usage: uv run python -m collect.sites.verify [domain ...] [--write] [--network] [--strict]
       uv run python -m collect.sites.verify --dataset data/poi.enriched.json
"""

from __future__ import annotations

import argparse
import copy
import html as htmllib
import json
import re
import sys
from collections import Counter
from pathlib import Path
from urllib.parse import urlsplit

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.sites.agree import brand_agrees, category_ok, own_categories, same_brand
from collect.sites.domains import registrable_domain
from collect.sites.fetch import Page, SiteFetcher, visible_text
from collect.sites.hours import analyze
from collect.sites.store import FACTS_DIR, FIELD_EVIDENCE, in_astana, iter_facts, norm_ws, now_iso, save_facts

_FACT_KEYS = ("address", "phone", "opening_hours_raw", "description", "coords")


def page_variants(page: Page) -> list[str]:
    """Normalised text views of a page a snippet may legitimately come from: source, entity-decoded source,
    visible text, JSON re-serialised / un-escaped."""
    raw = page.text
    views = [raw, htmllib.unescape(raw), visible_text(raw)]
    unescaped = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), raw).replace("\\/", "/")
    views += [unescaped, htmllib.unescape(unescaped)]
    try:
        data = json.loads(raw)
    except ValueError:
        data = None
    if data is not None:
        views += [json.dumps(data, ensure_ascii=False), json.dumps(data, ensure_ascii=False, indent=2),
                  json.dumps(data, ensure_ascii=False, separators=(",", ":"))]
    return [norm_ws(v) for v in views]


class Verifier:
    def __init__(self, fetcher: SiteFetcher, network: bool = False):
        self.fetcher, self.network = fetcher, network
        self._views: dict[str, list[str] | None] = {}

    def views(self, url: str) -> list[str] | None:
        if url not in self._views:
            page = self.fetcher.cached_page(url)
            if page is None and self.network:
                page = self.fetcher.fetch(url)
            self._views[url] = page_variants(page) if page is not None and page.status == 200 else None
        return self._views[url]

    def snippet_found(self, url: str, snippet: str) -> bool:
        needle = norm_ws(snippet)
        return bool(needle) and any(needle in v for v in self.views(url) or [])


def verify_record(rec: dict, verifier: Verifier) -> tuple[dict, Counter]:
    """(cleaned copy of the record, counters). Pure with respect to the input."""
    stats: Counter = Counter()
    out = copy.deepcopy(rec)
    kept: list[dict] = []
    if not rec.get("robots_ok"):
        stats["branches_dropped_robots"] += len(rec.get("branches", []))
        out["branches"] = []
        out["verified_at"] = now_iso()
        return out, stats
    for b in out.get("branches", []):
        stats["branches_in"] += 1
        if b.get("lat") is not None and not in_astana(b.get("lat"), b.get("lon")):
            stats["branches_dropped_outside_astana"] += 1
            continue
        good = []
        for e in b.get("evidence", []):
            stats["evidence_total"] += 1
            if verifier.views(e["url"]) is None:
                stats["evidence_page_not_cached"] += 1
            if verifier.snippet_found(e["url"], e["snippet"]):
                stats["evidence_ok"] += 1
                good.append(e)
            else:
                stats["evidence_dropped"] += 1
        b["evidence"] = good
        covered = {e["field"] for e in good}
        for key in _FACT_KEYS:
            present = b.get("lat") is not None if key == "coords" else bool(b.get(key))
            if present and not covered & FIELD_EVIDENCE[key]:
                stats[f"fact_dropped_{key}"] += 1
                if key == "coords":
                    b["lat"] = b["lon"] = None
                else:
                    b[key] = None
        raw = b.get("opening_hours_raw")
        osm, flags = analyze(raw) if raw else (None, [])
        if b.get("opening_hours_osm") and b["opening_hours_osm"] != osm:
            stats["osm_recomputed"] += 1
            if osm is None and raw:
                stats["hours_downgraded"] += 1  # an earlier (looser) rule had converted it
                stats.update(f"hours_downgraded_{f}" for f in flags)
        stats.update(f"hours_flag_{f}" for f in flags)
        b["opening_hours_osm"] = osm
        b["hours_flags"] = flags
        has_fact = any(b.get(k) for k in
                       ("address", "phone", "opening_hours_raw", "description", "price_text")) or b.get(
            "lat") is not None
        if good and has_fact:
            kept.append(b)
            stats["branches_out"] += 1
            stats["facts_hours_osm"] += bool(osm)
            stats["facts_hours_raw"] += bool(raw)
        else:
            stats["branches_dropped"] += 1
    out["branches"] = kept
    out["verified_at"] = now_iso()
    return out, stats


def check_dataset(pois: list[dict]) -> list[str]:
    """Problems of a built dataset's official-site fields (empty list = fine).

    For every field of every POI whose `field_sources[field].source` is `official_site`: the POI must carry
    `official_site_match.domain`; that domain must be backed by the POI's own name / brand / website keys and agree
    with its category (`agree.speaks_for`); the evidence URL must be on that domain or on another domain of the same
    brand (`chabad.kz` / `chabadkz.org`): a vendor platform that serves many brands is not the POI's own site.
    `hours_conflict` needs an official schedule to conflict with."""
    cats = own_categories(pois)
    problems: list[str] = []
    for p in pois:
        who = f"{p['id']} {p['name']!r} [{p['category']}]"
        fsrc = p.get("field_sources") or {}
        official = {f: s for f, s in fsrc.items() if isinstance(s, dict) and s.get("source") == "official_site"}
        if p.get("hours_conflict") and "opening_hours_official" not in official:
            problems.append(f"{who}: hours_conflict without an official schedule in field_sources")
        if not official:
            continue
        domain = (p.get("official_site_match") or {}).get("domain")
        if not domain:
            problems.append(f"{who}: official_site fields {sorted(official)} but no official_site_match.domain")
            continue
        if not brand_agrees(domain, p):
            problems.append(f"{who}: {sorted(official)} come from {domain}, which is not backed by the POI's name / "
                            "brand / website keys")
        elif not category_ok(domain, p["category"], cats):
            problems.append(f"{who}: {sorted(official)} come from {domain}, whose own POIs are of other categories")
        for f, s in official.items():
            host = urlsplit(s.get("url") or "").hostname or ""
            on_domain = host == domain or host.endswith("." + domain) or same_brand(domain, registrable_domain(host) or "")
            if not on_domain:
                problems.append(f"{who}: {f} evidence URL {s.get('url')} is not on {domain} or a domain of its brand")
    return problems


def summarize(stats: Counter) -> str:
    return ", ".join(f"{k}={stats[k]}" for k in sorted(stats)) or "empty"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("domains", nargs="*", help="default: every file in data/sites/facts")
    ap.add_argument("--write", action="store_true", help="rewrite the facts files without the dropped facts")
    ap.add_argument("--network", action="store_true", help="fetch evidence pages missing from the cache")
    ap.add_argument("--strict", action="store_true", help="exit 1 if anything was dropped")
    ap.add_argument("--dataset", metavar="POI_JSON", help="instead of the facts: check the official-site fields of a "
                    "built dataset (exit 1 on any problem)")
    args = ap.parse_args(argv)
    if args.dataset:
        problems = check_dataset(json.loads(Path(args.dataset).read_text(encoding="utf-8")))
        for line in problems:
            print(f"[verify] {line}", file=sys.stderr)
        print(f"[verify] dataset {args.dataset}: {len(problems)} problem(s)")
        return 1 if problems else 0
    verifier = Verifier(SiteFetcher(), network=args.network)
    total: Counter = Counter()
    for rec in iter_facts():
        if args.domains and rec["domain"] not in args.domains:
            continue
        cleaned, stats = verify_record(rec, verifier)
        total.update(stats)
        print(f"[verify] {rec['domain']}: {summarize(stats)}")
        if args.write:
            save_facts(cleaned, FACTS_DIR)
    print(f"[verify] TOTAL: {summarize(total)}")
    return 1 if args.strict and (total["evidence_dropped"] or total["branches_dropped"]) else 0


if __name__ == "__main__":
    sys.exit(main())
