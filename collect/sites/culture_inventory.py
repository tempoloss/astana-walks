"""Culture inventory: the next first-party crawl — cultural institutions and landmarks without day-qualified hours.

Measures the hours hole per category from data/poi.enriched.json, lists the domains of POIs in the eight culture
categories that have no day-qualified `opening_hours` yet (OSM `website`, Wikidata P856 for records with a
`wikidata=Q…` tag, e-museum.kz register cards), drops domains that other partitions already own, and deals the
remaining domains into 3 balanced work lists.

Offline by default: P856 claims, e-museum cards and robots verdicts are read from the dated snapshots committed in
`collect/sites/snapshots/`. Usage:

    uv run python -m collect.sites.culture_inventory             # rebuild from snapshots + dataset
    uv run python -m collect.sites.culture_inventory --refresh   # re-fetch the snapshots (polite, 1 req/s, cached)
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.sites.domains import is_blocked, poi_domains, registrable_domain

ROOT = Path(__file__).resolve().parents[2]
POI_PATH = ROOT / "data" / "poi.enriched.json"
OUT_PATH = ROOT / "collect" / "sites" / "inventory_culture.json"
PARTS_DIR = ROOT / "collect" / "sites" / "partitions_culture"
SNAP_DIR = ROOT / "collect" / "sites" / "snapshots"  # tracked, dated: the inventory rebuilds offline from these

# Culture categories whose venues are this crawl's target.
CULTURE_CATEGORIES = ("museum_gallery", "culture_theatre_cinema", "attraction_landmark", "viewpoint",
                      "coworking_library", "park_garden", "entertainment", "kids_playground")

PARTS = 3
DOMAIN_BASE = 1.0  # same cost model as collect.sites.partition
TODAY = "2026-10-17"  # snapshot date of the files in collect/sites/snapshots

E_MUSEUM = "e-museum.kz"

# The Astana cards of the e-museum register (region=3952). region=3952 returns 5 unique museums; «Алжир» sits in
# Ақмол ауылы (Akmola district), not Astana — excluded from the Astana count. POI matching is name-based: the cards
# carry no coordinates. Snapshot: collect/sites/snapshots/e-museum_region3952_2026-10-17.json.
E_MUSEUM_CARDS = [
    {"museum": "Национальный музей Республики Казахстан", "original_id": 22,
     "url": "https://e-museum.kz/ru/museum/68da379b4b4fb9d59-ru/",
     "poi_ids": ["node/4894937300"], "own_site": "nmrk.kz",
     "note": "day-qualified hours already came from nmrk.kz (facts); card adds ticket_price"},
    {"museum": "Музей Сакена Сейфуллина", "original_id": 154,
     "url": "https://e-museum.kz/ru/museum/68da37a0228ab7ad4-ru/",
     "poi_ids": ["way/240376692"], "own_site": "astanamuseums.kz",
     "note": "official domain hg2astana.kz is in the existing partitions; card `site` = www.astanamuseums.kz "
             "(unreachable, connect timeout); e-museum card adds ticket_price"},
    {"museum": "Военно-исторический музей ВС Республики Казахстан", "original_id": 165,
     "url": "https://e-museum.kz/ru/museum/68da379da9894247d-ru/",
     "poi_ids": ["way/240391776", "overture/d2f834c2-bedd-4e70-9d4f-0e62c98a5298",
                 "overture/7972273c-f99e-4cd9-b552-c94b2a59adde", "way/1239171353"],
     "note": "4 duplicate POIs, no own domain; joined to overture/d2f834c2 (name 72.7 + address «Республики 2»); "
             "way/1239171353, overture/7972273c, way/240391776 reported as the others of the same place"},
    {"museum": "Государственный историко-культурный музей-заповедник «Бозоқ»", "original_id": 32,
     "url": "https://e-museum.kz/ru/museum/68da37a2c72b30113-ru/",
     "poi_ids": ["node/11968737470"], "own_site": "bozok.kz",
     "note": "card site field gives the institution's own domain bozok.kz"},
]

# Verdicts fetched once on TODAY (snapshot: collect/sites/snapshots/robots_culture_2026-10-17.json), UA per collect.net.
ROBOTS = {
    E_MUSEUM: "allowed (Disallow: /wp-admin/ only; REST /wp-json/ open)",
    "bozok.kz": "allowed (Disallow: /wp-admin/ only; sitemap open)",
    "akorda.kz": "allowed (User-agent: * Allow: /)",
    "museumgold.kz": "allowed (User-agent: * Allow: /)",
    "museum-alzhir.kz": "denied (robots.txt responds 403, Cloudflare interstitial)",
    "astanamuseums.kz": "unreachable (connect timeout — domain parked or dead)",
    "botsad-nursultan.kz": "unreachable (DNS does not resolve; the POI's OSM domain astanabotsad.kz is already assigned)",
}

# What this branch did with each domain: "collected" = a facts record exists (data/sites/facts/<domain>.json);
# "open" = a domain to crawl; "dead" / "denied" = documented, no crawl.
STATUS = {
    E_MUSEUM: "collected",  # crawlers/e-museum.kz.py: 4 Astana cards -> facts, price_text + hours_unqualified
    "akorda.kz": "collected",  # no visiting hours of the residence on the site (citizen reception only)
    "museumgold.kz": "collected",  # parked domain, nothing to take
    "bozok.kz": "open",  # the reserve's own site, robots allowed: the next crawl
    "astanamuseums.kz": "dead",  # the Сейфуллин card `site`: connect timeout, likely parked
    "botsad-nursultan.kz": "dead",
    "museum-alzhir.kz": "denied",
}

# Facts this branch collected itself: they stay in the inventory (status "collected"), not "already covered".
OWNED = frozenset({E_MUSEUM, "akorda.kz", "museumgold.kz"})


def _qid(poi: dict) -> str | None:
    for t in poi.get("tags") or []:
        if t.startswith("wikidata=Q"):
            return t.split("=", 1)[1]
    return None


def hours_measures(pois: list[dict]) -> dict:
    """Day-qualified hours share per category + POIs with a website but no day-qualified hours."""
    per_cat: dict[str, dict] = {}
    for p in pois:
        c = p["category"]
        row = per_cat.setdefault(c, {"pois": 0, "with_day_qualified_hours": 0})
        row["pois"] += 1
        if p.get("opening_hours"):
            row["with_day_qualified_hours"] += 1
    for row in per_cat.values():
        row["share_pct"] = round(100 * row["with_day_qualified_hours"] / row["pois"], 1) if row["pois"] else 0.0
    with_site = [p for p in pois if (p.get("website") or "").strip()]
    return {
        "poi_total": len(pois),
        "per_category": {c: per_cat[c] for c in sorted(per_cat)},
        "pois_with_website": len(with_site),
        "pois_with_website_no_day_qualified_hours": sum(1 for p in with_site if not p.get("opening_hours")),
    }


def _covered_domains() -> set[str]:
    """Domains another partition already owns: data/sites/facts/*.json + data/sites/inventory.json, MINUS the facts
    this branch collected itself (`OWNED`) — they stay in the inventory with status "collected"."""
    covered = {f.stem for f in (ROOT / "data" / "sites" / "facts").glob("*.json")}
    inv = ROOT / "data" / "sites" / "inventory.json"
    if inv.exists():
        covered |= {d["domain"] for d in json.loads(inv.read_text(encoding="utf-8"))["domains"]}
    return covered - OWNED


def _p856_snapshot() -> dict[str, list[str]]:
    path = SNAP_DIR / f"wikidata_p856_targets_{TODAY}.json"
    if not path.exists():
        return {}
    return {q: v.get("P856", []) for q, v in
            json.loads(path.read_text(encoding="utf-8")).get("entities", {}).items()}


def _candidate_domains(pois: list[dict], covered: set[str]) -> dict[str, dict]:
    """domain -> {poi_ids, names, categories, wikidata_ids, origin} for culture POIs without day-qualified hours,
    restricted to domains no other partition owns."""
    out: dict[str, dict] = {}
    for p in pois:
        if p["category"] not in CULTURE_CATEGORIES or p.get("opening_hours"):
            continue
        urls: list[str] = []
        origins: list[str] = []
        for d in poi_domains(p):
            urls.append(d)
            origins.append("osm_website")
        qid = _qid(p)
        if qid:
            for u in _p856_snapshot().get(qid, []):
                d = registrable_domain(u)
                if d and not is_blocked(d):
                    urls.append(d)
                    origins.append("wikidata_p856")
        for d, origin in zip(urls, origins, strict=True):
            if d in covered or is_blocked(d):
                continue
            rec = out.setdefault(d, {"domain": d, "poi_ids": [], "names": [], "categories": {},
                                     "wikidata_ids": [], "origins": set(), "notes": ""})
            rec["poi_ids"].append(p["id"])
            if p["name"] not in rec["names"]:
                rec["names"].append(p["name"])
            rec["categories"][p["category"]] = rec["categories"].get(p["category"], 0) + 1
            if qid and qid not in rec["wikidata_ids"]:
                rec["wikidata_ids"].append(qid)
            rec["origins"].add(origin)
    # the institution's own domain from the e-museum card's `site` field (bozok.kz for «Бозоқ»,
    # astanamuseums.kz for Сейфуллин); nmrk.kz is already covered by the existing partitions
    by_id = {p["id"]: p for p in pois}
    for card in E_MUSEUM_CARDS:
        own = registrable_domain(card.get("own_site") or "")
        if not own or own in covered or is_blocked(own):
            continue
        rec = out.setdefault(own, {"domain": own, "poi_ids": [], "names": [], "categories": {},
                                   "wikidata_ids": [], "origins": set(), "notes": ""})
        for pid in card["poi_ids"]:
            p = by_id.get(pid)
            if p is None or p["category"] not in CULTURE_CATEGORIES or p.get("opening_hours"):
                continue
            if pid not in rec["poi_ids"]:
                rec["poi_ids"].append(pid)
                if p["name"] not in rec["names"]:
                    rec["names"].append(p["name"])
                rec["categories"][p["category"]] = rec["categories"].get(p["category"], 0) + 1
            if (qid := _qid(p)) and qid not in rec["wikidata_ids"]:
                rec["wikidata_ids"].append(qid)
            rec["origins"].add("e_museum_site_field")
    return out


def _e_museum_entry(pois: list[dict]) -> dict:
    by_id = {p["id"]: p for p in pois}
    poi_ids, names, categories = [], [], {}
    for card in E_MUSEUM_CARDS:
        for pid in card["poi_ids"]:
            p = by_id.get(pid)
            if p is None or p.get("opening_hours"):
                continue  # e.g. the National Museum: hours already came from nmrk.kz
            poi_ids.append(pid)
            names.append(p["name"])
            categories[p["category"]] = categories.get(p["category"], 0) + 1
    return {
        "domain": E_MUSEUM, "poi_ids": poi_ids, "names": names, "categories": categories,
        "wikidata_ids": [],
        "robots": ROBOTS[E_MUSEUM],
        "notes": ("ГИС «Музеи Казахстана» (WP REST, keyless): GET /wp-json/wp/v2/museum?region=3952&lang=ru — "
                  "5 unique cards, of which 4 Astana museums + «Алжир» (Ақмол ауылы, region filter leaks it). "
                  "work_hours + ticket_price filled on all 5 (verified " + TODAY + "). The Сейфуллин card's `site` "
                  "field points to astanamuseums.kz — unreachable (connect timeout, likely parked); "
                  "the Алжир card's `site` museum-alzhir.kz blocks robots. Cards: "
                  + "; ".join(f"{c['museum']} {c['url']}" for c in E_MUSEUM_CARDS)),
        "origin": ["e_museum_register"],
        "poi_count": len(poi_ids),
        "kind": "register_portal",
    }


def build(pois: list[dict]) -> dict:
    covered = _covered_domains()
    measures = hours_measures(pois)
    culture_pois = [p for p in pois if p["category"] in CULTURE_CATEGORIES]
    targets = [p for p in culture_pois if not p.get("opening_hours")]
    candidates = _candidate_domains(pois, covered)
    entries = list(candidates.values())
    e_entry = _e_museum_entry(pois)
    if E_MUSEUM in covered:  # a crawler for one card exists; the remaining cards are new work
        e_entry["notes"] += ". Already in data/sites/facts for the Военно-исторический музей card only."
    entries.append(e_entry)
    # «Алжир» has no Astana POI (Ақмол ауылы, Akmola district) and its site blocks robots — kept as a 0-POI entry so
    # the e-museum verification (region=3952 leaks it) and the robots verdict are recorded.
    entries.append({
        "domain": "museum-alzhir.kz", "poi_ids": [], "names": [], "categories": {}, "wikidata_ids": [],
        "robots": ROBOTS["museum-alzhir.kz"], "origin": ["e_museum_register"], "poi_count": 0,
        "notes": ("Музейно-мемориальный комплекс «Алжир»: e-museum card region=3952 (city Ақмол ауылы — the leak "
                  "behind the '4 not 5' Astana count); own site blocks robots (403), no POI in the dataset — out "
                  "of scope for the Astana crawl."),
        "kind": "documentation_only",
    })
    for rec in entries:
        rec["poi_count"] = len(rec["poi_ids"])
        rec["robots"] = ROBOTS.get(rec["domain"], "not fetched")
        origins = sorted(rec.pop("origins", ["e_museum_register"]))
        rec["origin"] = origins
        collected = (ROOT / "data" / "sites" / "facts" / f"{rec['domain']}.json").exists()
        rec["status"] = "collected" if rec["domain"] in OWNED and collected else STATUS.get(rec["domain"], "open")
        if not rec["notes"]:
            rec["notes"] = ("domains from: " + ", ".join(origins)
                            + (f"; wikidata {', '.join(rec['wikidata_ids'])}" if rec["wikidata_ids"] else ""))
    entries.sort(key=lambda r: (-r["poi_count"], r["domain"]))
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "snapshot_date": TODAY,
        "source": POI_PATH.name,
        "categories": list(CULTURE_CATEGORIES),
        "measures": measures,
        "counts": {
            "culture_pois": len(culture_pois),
            "culture_pois_without_day_qualified_hours": len(targets),
            "domains_new_for_crawl": len(entries),
            "pois_in_new_domains": sum(r["poi_count"] for r in entries),
            "robots": {
                "allowed": sum(1 for r in entries if r["robots"].startswith("allowed")),
                "denied": sum(1 for r in entries if r["robots"].startswith("denied")),
                "unreachable": sum(1 for r in entries if r["robots"].startswith("unreachable")),
            },
        },
        "entries": entries,
    }


def partitions(inv: dict, parts: int = PARTS) -> list[dict]:
    bins = [{"partition": f"p{i + 1}", "weight": 0.0, "items": []} for i in range(parts)]
    for rec in sorted(inv["entries"], key=lambda r: (-r["poi_count"], r["domain"])):
        lightest = min(bins, key=lambda b: (b["weight"], b["partition"]))
        lightest["items"].append({k: rec[k] for k in ("domain", "poi_ids", "names", "categories", "wikidata_ids",
                                                      "robots", "notes", "origin", "poi_count", "status")})
        lightest["weight"] += DOMAIN_BASE + rec["poi_count"]
    for b in bins:
        b["weight"] = round(b["weight"], 1)
        b["domain_count"] = len(b["items"])
        b["poi_count"] = sum(i["poi_count"] for i in b["items"])
    return bins


def refresh_snapshots() -> None:
    """`--refresh`: the polite network half of the inventory — Wikidata P856 (wbgetentities, one batched call for
    the target qids) and robots.txt of the candidate domains, ≤1 req/s per host via collect.net; the answers are
    written to collect/sites/snapshots/ (dated) so every later rebuild is offline."""
    from collect.sites.fetch import SiteFetcher
    pois = json.loads(POI_PATH.read_text(encoding="utf-8"))
    qids = sorted({_qid(p) for p in pois
                   if p["category"] in CULTURE_CATEGORIES and not p.get("opening_hours") and _qid(p)})
    f = SiteFetcher()
    r = f.net.get("https://www.wikidata.org/w/api.php",
                  params={"action": "wbgetentities", "ids": "|".join(qids), "props": "claims",
                          "languages": "ru|kk|en", "format": "json"}, timeout=30.0)
    entities = {q: {"P856": [c["mainsnak"]["datavalue"]["value"]
                             for c in ent.get("claims", {}).get("P856", [])
                             if c["mainsnak"].get("datavalue", {}).get("type") == "string"]}
                for q, ent in r.json().get("entities", {}).items()}
    SNAP_DIR.mkdir(parents=True, exist_ok=True)
    (SNAP_DIR / f"wikidata_p856_targets_{TODAY}.json").write_text(
        json.dumps({"fetched_at": TODAY, "url": "https://www.wikidata.org/w/api.php?action=wbgetentities"
                                                  "&props=claims", "entities": entities},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    robots = []
    for d in sorted({*ROBOTS, *(registrable_domain(u) for e in entities.values() for u in e["P856"]),
                     *(registrable_domain(c["own_site"]) for c in E_MUSEUM_CARDS if c.get("own_site"))}):
        if not d:
            continue
        page = f._get(f"https://{d}/robots.txt")
        robots.append({"domain": d, "status": page.status, "fetched_at": TODAY,
                       "body_head": page.text[:1000]})
    (SNAP_DIR / f"robots_culture_{TODAY}.json").write_text(
        json.dumps({"fetched_at": TODAY, "user_agent": "astana-walks/0.1 (hackathon)", "results": robots},
                   ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    f.net.log_summary("culture-inventory")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--poi", default=str(POI_PATH))
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--refresh", action="store_true", help="re-fetch the snapshots first (network)")
    args = ap.parse_args(argv)
    if args.refresh:
        refresh_snapshots()
    pois = json.loads(Path(args.poi).read_text(encoding="utf-8"))
    inv = build(pois)
    out = Path(args.out)
    out.write_text(json.dumps(inv, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    part_dir = out.parent / "partitions_culture"
    part_dir.mkdir(parents=True, exist_ok=True)
    for b in partitions(inv):
        (part_dir / f"{b['partition']}.json").write_text(json.dumps(b, ensure_ascii=False, indent=1) + "\n",
                                                         encoding="utf-8")
        print(f"[culture-inventory] {b['partition']}: weight {b['weight']}, {b['domain_count']} domains, "
              f"{b['poi_count']} POIs")
    c = inv["counts"]
    print(f"[culture-inventory] {c['culture_pois_without_day_qualified_hours']} culture POIs without day-qualified "
          f"hours; {c['domains_new_for_crawl']} new domains ({c['pois_in_new_domains']} POIs); robots "
          f"allowed={c['robots']['allowed']} denied={c['robots']['denied']} "
          f"unreachable={c['robots']['unreachable']} -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
