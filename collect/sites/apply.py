"""Apply official-site facts to the dataset: the merge stage's data/poi.enriched.json -> the shipped
data/poi.enriched.json (same file, official-site facts added), data/poi_enriched_stats.json extended.

Run it on the merge stage's output (`collect.build` does: merge, then this stage); a dataset that already carries the
facts is refused, rebuild the base first. Stages (all offline, cache only):
  1. `join.join_branches`: verified branches -> existing POIs (data/sites/joined.json, same as `collect.sites.join`);
  2. matched POIs: official fields are added next to the existing ones, never over them:
       * `opening_hours` is written from the site only when the POI has none (day-qualified OSM string);
       * both present and the weekly schedules differ -> `opening_hours` stays (OSM), the site value goes to
         `opening_hours_official`, `hours_conflict` is true. `hours_conflict_prefers` is advisory: "official_site"
         when the site page was fetched after the OSM snapshot of the POI's hours and its value is day-qualified
         (it always is: only a day-qualified schedule is stored as `opening_hours_osm`), else "osm". The OSM
         snapshot date is the download date, not the date of the last OSM edit, so this is a weak signal and the
         app keeps reading `opening_hours`;
       * text without days / ambiguous 00:00-00:00 -> `hours_unqualified` (+ `hours_unqualified_flags`), never
         `opening_hours`;
       * phone / address are filled only when empty; the site description goes to `description_official`;
     a domain speaks for a POI only with brand agreement and category compatibility (`agree.speaks_for`, applied by
     the join: proximity alone never matches); the finished dataset is re-checked by `verify.check_dataset` and a
     failure aborts the stage before anything is written;
  3. unmatched branches with first-party coordinates (a `geo` evidence on the site's own page, inside the Astana
     box, not from a third-party backend) become new POIs when the domain's category is known from its existing
     POIs, the name is usable and the point is neither within 75 m of a similar-named existing POI nor of an
     earlier new POI.

Usage: uv run python -m collect.sites.apply [--poi data/poi.enriched.json] [--out data/poi.enriched.json]
"""

from __future__ import annotations

import argparse
import copy
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.merge import CATEGORY_RU, stats_for
from collect.names import name_key, name_score
from collect.overpass_poi import haversine_m
from collect.sites import join as sj
from collect.sites.domains import poi_domains
from collect.sites.fetch import SiteFetcher
from collect.sites.hours import same_schedule
from collect.sites.store import FACTS_DIR, iter_facts
from collect.sites.verify import Verifier, check_dataset

ROOT = Path(__file__).resolve().parents[2]
POI_PATH = ROOT / "data" / "poi.enriched.json"
OUT_PATH = POI_PATH  # the shipped dataset: the base with the official-site facts, in place
STATS_PATH = ROOT / "data" / "poi_enriched_stats.json"  # the merge stage's stats, extended (see `shipped_stats`)
DELTA_PATH = ROOT / "data" / "coverage_delta.md"
DELTA_HEADING = "## Official-site facts (first-party hours, phone, address; new POIs)"
SITE_SOURCES = frozenset({sj.SOURCE, sj.REGISTER_SOURCE})  # `sources` labels this stage adds to a record

DUP_M = 75.0  # a new POI this close to a similar-named POI is a duplicate
DUP_NAME = 60.0
PLACEHOLDER_NAME = 60.0  # same point, dissimilar names -> the coordinates are a map default, not the venue
CATEGORY_SHARE = 0.5  # share of the domain's POIs in its top category; a tie goes to the first of CATEGORY_PRIORITY
CATEGORY_PRIORITY = ("cafe", "restaurant", "fast_food", "bar_nightlife", "entertainment", "kids_playground", "sport",
                     "culture_theatre_cinema", "museum_gallery", "coworking_library")
_OTHER_CITY = re.compile(r"Алматы|Almaty|Шымкент|Shymkent|Караганд|Karaganda|Актау|Атырау", re.IGNORECASE)
# A site whose POIs are malls / parks / landmarks lists tenants or sub-places, not outlets of that category.
NO_NEW_POI_CATEGORIES = frozenset({"mall", "park_garden", "attraction_landmark", "transit_station", "viewpoint",
                                   "other"})
OFFICIAL_FIELDS = ("opening_hours_official", "hours_conflict", "hours_conflict_prefers", "hours_unqualified",
                   "hours_unqualified_flags", "description_official")

_ZW = re.compile("[\u200b\u200c\u200d\u2060\ufeff]")
_CITY_PREFIX = re.compile(r"^(?:г\.?\s*)?(?:Астана|Astana|Нур-Султан)(?:\s+(?:қ\.|қаласы))?\s*,\s*", re.IGNORECASE)
_ADDRESS_LIKE = re.compile(r"^(?:г\.?\s*)?(?:Астана|Astana)\b|\b(?:ул|улица|пр|проспект|шоссе|даңғылы|көшесі|микрорайон)\b\.?"
                           r"|\d+\s*[а-яa-z]?\s*$", re.IGNORECASE)
_DASH = re.compile(r"\s+[—–]\s+")


def clean(text: str | None) -> str:
    return " ".join(_ZW.sub("", text or "").split())


def match_confidence(method: str, score: float) -> float:
    """How sure the join is that the branch is this POI (0..1): the name score, floored at 0.9 for a same street +
    house match, 0.6 for 'the only branch / the only POI of the domain'."""
    base = min(score, 100.0) / 100
    if method == "domain+address":
        base = max(base, 0.9)
    if method == "domain_unique":
        base = min(base, 0.6)
    return round(base, 2)


# ---------------------------------------------------------------- matched POIs
def _src(src: dict | None) -> dict | None:
    return dict(src) if src else None


def apply_matched(p: dict, j: dict) -> list[str]:
    """Add the official fields of join entry `j` to POI `p` (in place); returns the touched field names."""
    f, src, fsrc = j["fields"], j["field_sources"], p["field_sources"]
    touched: list[str] = []
    if oh := f.get("opening_hours"):
        official_src = _src(src.get("opening_hours"))
        if not p.get("opening_hours"):
            p["opening_hours"], p["hours_state"] = oh, "known"
            fsrc["opening_hours"] = official_src
            touched.append("opening_hours")
        else:
            p["opening_hours_official"] = oh
            fsrc["opening_hours_official"] = official_src
            touched.append("opening_hours_official")
            if not same_schedule(p["opening_hours"], oh):
                p["hours_conflict"] = True
                osm_date = (fsrc.get("opening_hours") or {}).get("snapshot_date") or ""
                newer = bool(official_src) and (official_src.get("snapshot_date") or "") > osm_date
                p["hours_conflict_prefers"] = "official_site" if newer else "osm"
    unq = f.get("hours_unqualified") or (f.get("opening_hours_raw") if not oh else None)
    if unq and not p.get("opening_hours"):
        p["hours_unqualified"] = unq
        p["hours_unqualified_flags"] = (src.get("hours_unqualified") or {}).get("hours_flags", [])
        fsrc["hours_unqualified"] = _src(src.get("hours_unqualified") or src.get("opening_hours_raw"))
        touched.append("hours_unqualified")
    for key in ("phone", "address", "price_text"):
        if f.get(key) and not p.get(key) and (key != "address" or address_ok(f[key])):
            p[key] = f[key]
            fsrc[key] = _src(src.get(key))
            touched.append(key)
    if f.get("description"):
        p["description_official"] = f["description"]
        fsrc["description_official"] = _src(src.get("description"))
        touched.append("description_official")
    if touched:
        # every source that wrote a field: a register's price next to the venue's own site's hours puts both labels
        # into `sources`, so that `shipped_stats` can strip them all and the field sources stay in step with it
        labels = [j.get("source_label") or sj.SOURCE]
        labels += sorted({fsrc[k]["source"] for k in touched if fsrc.get(k)} & SITE_SOURCES - set(labels))
        for label in labels:
            if label not in p["sources"]:
                p["sources"].append(label)
        # the dataset check binds each `official_site` field's evidence URL to official_site_match.domain: when
        # several sources contributed (a register's price + the venue's own site's hours), the domain that
        # carries the official_site fields is the one that must sit in official_site_match
        official_domain = j.get("official_domain") or j["domain"]
        p["official_site_match"] = {
            "domain": official_domain, "match_method": j["method"], "distance_m": j["distance_m"],
            "name_score": j["score"], "match_confidence": match_confidence(j["method"], j["score"])}
    return touched


# ---------------------------------------------------------------- new POIs
def domain_profile(pois: list[dict]) -> dict[str, dict]:
    """domain -> {brand: most common POI name, category: dominant category or None}."""
    names: dict[str, Counter] = defaultdict(Counter)
    cats: dict[str, Counter] = defaultdict(Counter)
    for p in pois:
        for d in poi_domains(p):
            names[d][p["name"]] += 1
            cats[d][p["category"]] += 1
    out = {}
    for d, c in cats.items():
        cat, n = min(c.items(), key=lambda kv: (-kv[1], CATEGORY_PRIORITY.index(kv[0])
                                               if kv[0] in CATEGORY_PRIORITY else len(CATEGORY_PRIORITY)))
        brand = sorted(names[d].items(), key=lambda kv: (-kv[1], len(kv[0])))[0][0]
        out[d] = {"brand": brand, "category": cat if n / sum(c.values()) >= CATEGORY_SHARE else None,
                  "categories": dict(c)}
    return out


def _norm(text: str) -> str:
    return re.sub(r"[\W_]+", " ", text.casefold()).strip()


def site_head(name: str, address: str) -> str:
    """The venue part of the site's name: '— address' / ', address' / '(address)' tails are cut."""
    parts = _DASH.split(name)
    head = parts[0].strip() if len(parts) > 1 and parts[0].strip() else name
    na = _norm(address)
    if na:
        m = re.search(r"\s*\(([^)]*)\)\s*$", head)
        if m and head[:m.start()].strip() and (_norm(m[1]) in na or re.search(r"Астана", m[1], re.IGNORECASE)):
            head = head[:m.start()].strip()
        if "," in head:
            first, _, rest = head.partition(",")
            if first.strip() and _norm(rest) and _norm(rest) in na:
                head = first.strip()
    return head


def address_ok(address: str | None) -> str | None:
    """The printed address, unless it names another city (a typo on the site: the coordinates are in Astana)."""
    address = clean(address)
    return address if address and not (_OTHER_CITY.search(address) and "Астан" not in address) else None


def display_name(branch: dict, profile: dict | None) -> tuple[str | None, str]:
    """(name or None, basis): the site's own venue name; a name that is an address or a place descriptor (it
    neither carries a '— address' tail nor starts with the domain's brand, e.g. coffeeboom's 'Орталық саябақтағы
    сағаттың жанында') becomes '<brand>, <address>'."""
    name = clean(branch["name"])
    address = _CITY_PREFIX.sub("", address_ok(branch.get("address")) or "")
    head = site_head(name, clean(branch.get("address")))
    basis = "site_name" if head == name else "site_name_without_address_tail"
    address_like = bool(_ADDRESS_LIKE.search(head))
    brand = profile["brand"] if profile else None
    if not address_like and len(head) >= 3:
        if not brand or head != name:
            return head, basis
        bk, hk = name_key(brand), name_key(head)
        if hk and bk and (hk.startswith(bk) or bk.startswith(hk) or name_score([head], [brand]) >= 75):
            return head, basis
    if brand:
        where = address or (_CITY_PREFIX.sub("", head) if address_like else "")
        if where:
            return f"{brand}, {where}", "domain_brand+address"
    return None, "no_usable_name"


def placeholder_points(cands: list[dict]) -> set[int]:
    """ids of branches sharing a point (5 decimals) with a dissimilar-named branch of the same domain: a map
    default (city centre), not an outlet."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for c in cands:
        b = c["branch"]
        if b.get("lat") is not None:
            groups[(c["domain"], round(b["lat"], 5), round(b["lon"], 5))].append(c)
    bad = set()
    for grp in groups.values():
        for i, a in enumerate(grp):
            for b in grp[i + 1:]:
                if name_score([clean(a["branch"]["name"])], [clean(b["branch"]["name"])]) < PLACEHOLDER_NAME:
                    bad.update((id(a["branch"]), id(b["branch"])))
    return bad


def _ev(branch: dict, fields: set[str]) -> dict | None:
    return next((e for e in branch["evidence"] if e["field"] in fields), None)


def _fsrc(branch: dict, fields: set[str], snapshot: str, *, fallback: bool = False) -> dict | None:
    ev = _ev(branch, fields) or (branch["evidence"][0] if fallback and branch["evidence"] else None)
    if ev is None:
        return None
    return {"source": sj.SOURCE, "license": sj.LICENSE_NOTE, "snapshot_date": (ev.get("fetched_at") or snapshot)[:10],
            "url": ev["url"], "snippet": ev["snippet"], "method": branch["method"], "confidence": branch["confidence"]}


def new_poi(c: dict, name: str, name_basis: str, category: str, dedup: dict) -> dict:
    b, domain, snap = c["branch"], c["domain"], c["snapshot"]
    lat, lon = b["lat"], b["lon"]
    pid = "site/" + domain + "/" + hashlib.sha1(f"{domain}|{name}|{lat:.5f}|{lon:.5f}".encode()).hexdigest()[:10]
    day = snap[:10]
    flags = b.get("hours_flags") or []
    oh = b.get("opening_hours_osm")
    raw = b.get("opening_hours_raw")
    address = address_ok(b.get("address"))
    if oh:
        hours_text = f" Часы работы (официальный сайт): {oh}."
    elif raw:
        hours_text = " Часы на официальном сайте указаны без дней недели."
    else:
        hours_text = " Часы работы на официальном сайте не указаны."
    desc_auto = f"{CATEGORY_RU[category]} «{name}»" + (f" по адресу {address}." if address else " в Астане.") + hours_text
    rec = {
        "id": pid, "name": name, "name_generated": False, "names": {"name": name}, "lat": lat, "lon": lon,
        "category": category, "tags": [f"official_site={domain}"], "opening_hours": oh,
        "website": b.get("url") or b["evidence"][0]["url"],
        "phone": b.get("phone"), "address": address, "wheelchair": None, "internet_access": None,
        "outdoor_seating": None, "description": None, "description_auto": desc_auto, "description_source": "derived",
        "source": sj.SOURCE, "collected_at": snap, "sources": [sj.SOURCE], "overture_id": None,
        "hours_state": "known" if oh else "unknown", "brand": None, "brand_wikidata": None,
        "opening_hours_official": None, "hours_conflict": False, "hours_conflict_prefers": None,
        "hours_unqualified": raw if raw and not oh else None,
        "hours_unqualified_flags": flags if raw and not oh else [],
        "description_official": b.get("description"),
        "match_confidence": b["confidence"],
        "official_site_match": {"domain": domain, "match_method": "new_poi", "match_confidence": b["confidence"],
                                "name_basis": name_basis, **dedup},
    }
    fs = {
        "name": _fsrc(b, {"name"}, snap, fallback=True), "lat": _fsrc(b, {"geo", "lat", "lon", "coords"}, snap),
        "lon": _fsrc(b, {"geo", "lat", "lon", "coords"}, snap),
        "category": {"source": "derived", "license": "n/a", "snapshot_date": day,
                     "basis": f"dominant category of existing POIs on {domain}"},
        "website": _fsrc(b, {"name", "opening_hours", "address", "phone", "geo"}, snap, fallback=True),
        "address": _fsrc(b, {"address"}, snap) if address else None,
        "phone": _fsrc(b, {"phone"}, snap) if b.get("phone") else None,
        "opening_hours": _fsrc(b, {"opening_hours"}, snap) if oh else None,
        "hours_unqualified": _fsrc(b, {"opening_hours"}, snap) if rec["hours_unqualified"] else None,
        "description_official": _fsrc(b, {"description"}, snap) if b.get("description") else None,
        "description_auto": {"source": "derived", "license": "n/a", "snapshot_date": day},
    }
    rec["field_sources"] = {k: v for k, v in fs.items() if v}
    return rec


def make_new_pois(candidates: list[dict], pois: list[dict], profiles: dict[str, dict]) -> tuple[list[dict], Counter]:
    skipped: Counter = Counter()
    bad_points = placeholder_points(candidates)
    ranked = sorted(candidates, key=lambda c: (-c["branch"]["confidence"], c["domain"], c["branch"]["name"]))
    out: list[dict] = []
    for c in ranked:
        b = c["branch"]
        if b.get("lat") is None:
            skipped["no first-party coordinates"] += 1
            continue
        if c["third_party"]:
            skipped["coordinates from a third-party backend"] += 1
            continue
        if id(b) in bad_points:
            skipped["placeholder coordinates (shared with a different venue)"] += 1
            continue
        prof = profiles.get(c["domain"])
        category = prof["category"] if prof else None
        if not category:
            skipped["domain category unknown/mixed (no existing POIs of the domain)"] += 1
            continue
        if category in NO_NEW_POI_CATEGORIES:
            skipped[f"domain category {category} lists tenants, not outlets"] += 1
            continue
        name, basis = display_name(b, prof)
        if not name:
            skipped["no usable name"] += 1
            continue
        raw_name = clean(b["name"])
        best_m, best_s, dup = None, 0.0, None
        for kind, pool in (("existing POI", pois), ("earlier new POI", out)):
            for p in pool:
                d = haversine_m(b["lat"], b["lon"], p["lat"], p["lon"])
                if d > DUP_M:
                    continue
                s = max(sj.name_similarity(name, p), sj.name_similarity(raw_name, p))
                if best_m is None or s > best_s:
                    best_m, best_s = round(d, 1), round(s, 1)
                if s >= DUP_NAME:
                    dup = kind
                    break
            if dup:
                break
        if dup:
            skipped[f"duplicate of an {dup} (<= {int(DUP_M)} m, similar name)"] += 1
            continue
        out.append(new_poi(c, name, basis, category,
                           {"nearest_poi_m": best_m, "nearest_poi_name_score": best_s if best_m is not None else None}))
    return out, skipped


# ---------------------------------------------------------------- build + report
def build(pois: list[dict], records: list[dict], verifier: Verifier) -> tuple[list[dict], dict, dict]:
    """(new dataset, joined result, stats)."""
    result, candidates = sj.join_branches(pois, records, verifier)
    out = copy.deepcopy(pois)
    for p in out:
        p.setdefault("opening_hours_official", None)
        p.setdefault("hours_conflict", False)
        p.setdefault("hours_conflict_prefers", None)
        p.setdefault("hours_unqualified", None)
        p.setdefault("hours_unqualified_flags", [])
        p.setdefault("description_official", None)
    by_id = {p["id"]: p for p in out}
    per_domain: dict[str, Counter] = defaultdict(Counter)
    touched_fields: Counter = Counter()
    for pid, j in result["pois"].items():
        touched = apply_matched(by_id[pid], j)
        d = per_domain[j["domain"]]
        d["matched"] += 1
        for k in touched:
            touched_fields[k] += 1
            d[k] += 1
        d["hours_conflict"] += bool(by_id[pid].get("hours_conflict"))
    new, skipped = make_new_pois(candidates, pois, domain_profile(pois))
    for r in new:
        d = per_domain[r["official_site_match"]["domain"]]
        d["new_pois"] += 1
        d["new_pois_with_hours"] += bool(r["opening_hours"])
        d["hours_unqualified"] += bool(r["hours_unqualified"])
    for j in result["pois"].values():  # verified branches per domain: matched + unmatched
        per_domain[j["domain"]]["site_branches"] += 1
    for c in candidates:
        per_domain[c["domain"]]["site_branches"] += 1
    dataset = out + new
    stats = dataset_stats(pois, dataset, new, skipped, result, per_domain, touched_fields)
    return dataset, result, stats


def has_hours(p: dict) -> bool:
    return bool(p.get("opening_hours"))


def dataset_stats(before: list[dict], after: list[dict], new: list[dict], skipped: Counter, result: dict,
                  per_domain: dict[str, Counter], touched: Counter) -> dict:
    n0, n1 = len(before), len(after)
    h0, h1 = sum(map(has_hours, before)), sum(map(has_hours, after))
    conflicts = [p for p in after if p.get("hours_conflict")]
    unq = [p for p in after if p.get("hours_unqualified")]
    rows = []
    for d, c in per_domain.items():
        rows.append({"domain": d, "branches": c["site_branches"], "matched_pois": c["matched"],
                     "new_hours": c["opening_hours"], "new_pois": c["new_pois"],
                     "new_pois_with_hours": c["new_pois_with_hours"], "hours_conflicts": c["hours_conflict"],
                     "hours_unqualified": c["hours_unqualified"]})
    rows.sort(key=lambda r: (-(r["matched_pois"] + r["new_pois"]), -r["branches"], r["domain"]))
    js = result["stats"]
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "poi_total_before": n0, "poi_total_after": n1, "new_pois": len(new),
        "new_pois_by_category": dict(Counter(p["category"] for p in new).most_common()),
        "new_pois_by_domain": dict(Counter(p["official_site_match"]["domain"] for p in new).most_common()),
        "new_pois_skipped": dict(skipped.most_common()),
        "hours_day_qualified_before": h0, "hours_day_qualified_after": h1,
        "hours_pct_before": round(100 * h0 / n0, 2), "hours_pct_after": round(100 * h1 / n1, 2),
        "hours_new_on_existing_pois": touched["opening_hours"],
        "hours_new_on_new_pois": sum(map(has_hours, new)),
        "hours_unqualified_pois": len(unq),
        "hours_unqualified_on_existing": sum(1 for p in unq if not p["id"].startswith("site/")),
        "hours_conflicts": len(conflicts),
        "hours_conflicts_prefer": dict(Counter(p["hours_conflict_prefers"] for p in conflicts)),
        "hours_confirmed_same": sum(1 for p in after if p.get("opening_hours_official") and not p.get("hours_conflict")),
        "price_text_pois": sum(1 for p in after if p.get("price_text")),
        "pois_matched": js["pois_matched"], "matched_by_method": js["by_method"],
        "branches_verified": js["branches"], "branches_unmatched": js["branches_unmatched"],
        "filled_on_existing": dict(touched.most_common()),
        "join_conflicts": {k: js.get(f"conflict_{k}", 0) for k in ("opening_hours", "phone", "address", "description")},
        "verify": js["verify"],
        "by_domain_top20": rows[:20],
    }


def render_delta(s: dict) -> str:
    def table(headers, rows):
        return "\n".join(["| " + " | ".join(headers) + " |", "|" + "---|" * len(headers),
                          *("| " + " | ".join(str(c) for c in r) + " |" for r in rows)])

    lines = [DELTA_HEADING, "",
             f"Generated {s['generated_at'][:10]} by `collect.sites.apply` into the shipped `data/poi.enriched.json` "
             "(stats: `data/poi_enriched_stats.json`, key `official_sites`). Facts come from the businesses' own pages (robots respected, "
             "verbatim evidence snippets); only schedules that name days count as hours.", "",
             table(["metric", "before", "after"], [
                 ["POIs", s["poi_total_before"], s["poi_total_after"]],
                 ["POIs with day-qualified `opening_hours`", f"{s['hours_day_qualified_before']} "
                  f"({s['hours_pct_before']}%)", f"{s['hours_day_qualified_after']} ({s['hours_pct_after']}%)"],
                 ["`hours_unqualified` (text without days / ambiguous 24h, not in `opening_hours`)", 0,
                  s["hours_unqualified_pois"]],
                 ["`hours_conflict` (OSM kept, site value in `opening_hours_official`)", 0, s["hours_conflicts"]],
                 ["`price_text` (the site's/register's own price wording, never parsed)", 0,
                  s["price_text_pois"]]]),
             "", f"Matched to existing POIs: **{s['pois_matched']}** ({s['matched_by_method']}); "
             f"hours added to existing POIs: **{s['hours_new_on_existing_pois']}**, to new POIs: "
             f"**{s['hours_new_on_new_pois']}**; identical-to-OSM confirmations: {s['hours_confirmed_same']}; "
             f"other join conflicts (kept POI value): {s['join_conflicts']}.", "",
             f"### New POIs from official branches with first-party coordinates: {s['new_pois']}", ""]
    lines += [table(["category", "new POIs"], [[k, v] for k, v in s["new_pois_by_category"].items()] or [["-", 0]]), "",
              "Skipped candidates: " + ("; ".join(f"{k}: {v}" for k, v in s["new_pois_skipped"].items()) or "-"), "",
              "### By domain (top 20 by POIs touched)", "",
              table(["domain", "branches", "matched POIs", "hours added", "new POIs", "new POIs with hours",
                     "hours conflicts", "hours_unqualified"],
                    [[r["domain"], r["branches"], r["matched_pois"], r["new_hours"], r["new_pois"],
                      r["new_pois_with_hours"], r["hours_conflicts"], r["hours_unqualified"]]
                     for r in s["by_domain_top20"]]), ""]
    return "\n".join(lines)


def write_delta(path: Path, section: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    head, sep, tail = text.partition(DELTA_HEADING)
    if sep:
        nxt = re.search(r"^## ", tail, re.MULTILINE)
        tail = tail[nxt.start():] if nxt else ""
    text = head.rstrip("\n") + ("\n\n" if head.strip() else "") + section.rstrip("\n") + "\n" + (
        "\n" + tail if tail else "")
    path.write_text(text, encoding="utf-8")


def already_applied(pois: list[dict]) -> bool:
    """The dataset carries official-site facts: applying again would count new POIs as duplicates of themselves."""
    return any("official_site_match" in p or "official_site" in (p.get("sources") or []) for p in pois)


def shipped_stats(prev: dict, dataset: list[dict], sites: dict) -> dict:
    """The stats of the shipped dataset: the merge stage's stats (`prev`) with `after` and the counts that depend on
    the records recomputed for the dataset with the official-site facts, and the stats of this stage under
    `official_sites`. `per_source_counts` count the records by their other sources (the same four buckets as before);
    records that come from official sites alone are `official_site_only`."""
    own = [[s for s in p["sources"] if s not in SITE_SOURCES] for p in dataset]
    ps = {
        **prev["per_source_counts"],
        "osm_only": sum(1 for s in own if s == ["osm"]),
        "overture_only": sum(1 for s in own if s == ["overture"]),
        "osm_and_overture": sum(1 for s in own if s == ["osm", "overture"]),
        "wikidata_only": sum(1 for s in own if s == ["wikidata"]),
        "official_site_only": sum(1 for s in own if not s),
        "with_official_site": sum(1 for p in dataset if "official_site" in p["sources"]),
    }
    return {
        **prev,
        "after": stats_for(dataset),
        "per_source_counts": ps,
        "description_source_counts": {
            s: sum(1 for p in dataset if p["description_source"] == s) for s in ("osm", "wikipedia", "derived")
        },
        "official_sites": sites,
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--poi", default=str(POI_PATH))
    ap.add_argument("--facts", default=str(FACTS_DIR))
    ap.add_argument("--out", default=str(OUT_PATH))
    ap.add_argument("--joined", default=str(sj.OUT_PATH))
    ap.add_argument("--stats", default=str(STATS_PATH))
    ap.add_argument("--delta", default=str(DELTA_PATH))
    args = ap.parse_args(argv)
    pois = json.loads(Path(args.poi).read_text(encoding="utf-8"))
    if already_applied(pois):
        print(f"[sites.apply] {args.poi} already carries official-site facts; rebuild the base first "
              "(uv run python -m collect.build), then apply.", file=sys.stderr)
        return 1
    records = list(iter_facts(Path(args.facts)))
    dataset, result, stats = build(pois, records, Verifier(SiteFetcher()))
    if problems := check_dataset(dataset):  # official hours must come from a domain that speaks for the POI
        for line in problems:
            print(f"[sites.apply] {line}", file=sys.stderr)
        print(f"[sites.apply] {len(problems)} official-site field(s) not backed by the POI's own name/brand/website; "
              "nothing written", file=sys.stderr)
        return 1
    stats_path = Path(args.stats)
    prev = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    ship = shipped_stats(prev, dataset, stats) if "per_source_counts" in prev else stats
    for path, payload in ((args.out, dataset), (args.joined, result), (args.stats, ship)):
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    write_delta(Path(args.delta), render_delta(stats))
    print(f"[sites.apply] POIs {stats['poi_total_before']} -> {stats['poi_total_after']} (+{stats['new_pois']} new); "
          f"hours {stats['hours_day_qualified_before']} -> {stats['hours_day_qualified_after']} "
          f"({stats['hours_pct_before']}% -> {stats['hours_pct_after']}%); unqualified {stats['hours_unqualified_pois']}; "
          f"conflicts {stats['hours_conflicts']} -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
