"""Join stage: official-site branches -> POIs. Writes data/sites/joined.json; poi.enriched.json is never modified.

Matching (1:1 per domain, best pair first):
  * branch has coordinates: POI within 150 m whose name matches (`names.name_score` >= 75, or a shared chain key),
    or whose own website is on the same domain (name score >= 40);
  * no coordinates: among POIs whose website is on the domain, same street + house number; or the only branch of
    the domain vs the only POI of the domain with a similar name.
Only verified facts are joined (`verify.verify_record`, cache only, no network).

Usage: uv run python -m collect.sites.join [--poi data/poi.enriched.json] [--out data/sites/joined.json]
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.names import is_generic_name, name_key, name_score
from collect.overpass_poi import haversine_m
from collect.sites.agree import own_categories, speaks_for
from collect.sites.domains import poi_domains, registrable_domain
from collect.sites.fetch import SiteFetcher
from collect.sites.hours import same_schedule
from collect.sites.store import FACTS_DIR, SITES_DIR, iter_facts
from collect.sites.verify import Verifier, verify_record

ROOT = Path(__file__).resolve().parents[2]
POI_PATH = ROOT / "data" / "poi.enriched.json"
OUT_PATH = SITES_DIR / "joined.json"

MAX_DIST_M = 150.0
NAME_OK = 75.0
DOMAIN_NAME_OK = 40.0
ADDR_STREET_OK = 80.0
LICENSE_NOTE = "facts from the business's own website"
SOURCE = "official_site"
REGISTER_SOURCE = "museum_register"  # e-museum.kz: a ministry register, not the institution's own site
REGISTER_LICENSE = "facts from the ministry museum register (e-museum.kz)"


def rec_label(rec: dict) -> tuple[str, str, bool]:
    """(source label, licence note, register matching) of a facts record; register records opt in via
    `source_label: museum_register` — see store.new_record."""
    if rec.get("source_label") == REGISTER_SOURCE:
        return REGISTER_SOURCE, REGISTER_LICENSE, True
    return SOURCE, LICENSE_NOTE, False

_STREET_NOISE = re.compile(
    r"\b(?:астана|г|город|ул|улица|пр|проспект|пр-т|шоссе|көшесі|даңғылы|көш|даңғ|микрорайон|мкр|казахстан|kz|"
    r"astana|street|st|avenue|ave|road|rd|bld|building|здание|зд|дом|д)\b\.?", re.IGNORECASE)
_HOUSE = re.compile(r"(?<![\w/])(\d{1,4}\s?[а-яa-z]?(?:/\d{1,3})?)(?![\w])", re.IGNORECASE)


def poi_names(p: dict) -> list[str]:
    return list(dict.fromkeys([p["name"], *p["names"].values()]))


def split_address(addr: str | None) -> tuple[str, str]:
    """(street words, house number) of a free-form address; either may be ''."""
    if not addr:
        return "", ""
    house = _HOUSE.search(addr)
    street = _STREET_NOISE.sub(" ", _HOUSE.sub(" ", addr))
    return re.sub(r"[^\w\s]+", " ", street).strip().lower(), (re.sub(r"\s", "", house[1]).lower() if house else "")


def address_match(a: str | None, b: str | None) -> bool:
    sa, ha = split_address(a)
    sb, hb = split_address(b)
    return bool(sa and sb and ha and ha == hb and name_score([sa], [sb]) >= ADDR_STREET_OK)


def name_similarity(branch_name: str, p: dict) -> float:
    """0..100: skeleton similarity, or 85 when one non-generic name key is the *start* of the other ('KFC Астана |
    Мега' ~ 'KFC': the brand leads). A key at the end does not count: the mall 'Керуен' is not 'KFC Астана | Керуен'."""
    names = poi_names(p)
    best = name_score([branch_name], names)
    bk = name_key(branch_name)
    if not is_generic_name(branch_name) and len(bk) >= 3:
        for n in names:
            nk = name_key(n)
            if not is_generic_name(n) and len(nk) >= 3 and (bk.startswith(nk) or nk.startswith(bk)):
                best = max(best, 85.0)
    return best


class Grid:
    def __init__(self, pois: list[dict], cell: float = 0.003):
        self.cell, self.cells = cell, defaultdict(list)
        for p in pois:
            self.cells[(int(p["lat"] // cell), int(p["lon"] // cell))].append(p)

    def near(self, lat: float, lon: float):
        cy, cx = int(lat // self.cell), int(lon // self.cell)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                yield from self.cells.get((cy + dy, cx + dx), ())


def match_domain(domain: str, branches: list[dict], pois: list[dict], grid: Grid, domain_pois: list[dict],
                 speaks=None, register: bool = False) -> list[tuple[dict, dict, str, float | None, float]]:
    """[(branch, poi, method, distance_m|None, score)] 1:1, best pair first. `speaks(poi)` says whether the domain
    may speak for the POI (`agree.speaks_for`: brand agreement + category compatibility); a POI it rejects is never
    paired, however close the branch stands (a coffee shop inside a mall is not the mall). A register record
    (`register=True`, e.g. e-museum.kz) has no brand key of its own: a branch without coordinates matches by
    name + address across all POIs (`register_name_address`), the address beats a bare name (the co-located
    duplicates of one museum are told apart by their addresses)."""
    speaks = speaks or (lambda p: True)
    domain_pois = [p for p in domain_pois if speaks(p)]
    domain_ids = {p["id"] for p in domain_pois}
    pairs = []
    for bi, b in enumerate(branches):
        if b.get("lat") is not None:
            for p in grid.near(b["lat"], b["lon"]):
                dist = haversine_m(b["lat"], b["lon"], p["lat"], p["lon"])
                if dist > MAX_DIST_M or not speaks(p):
                    continue
                score = name_similarity(b["name"], p)
                dom = p["id"] in domain_ids
                if score >= NAME_OK or (dom and score >= DOMAIN_NAME_OK):
                    method = "coords+name" if score >= NAME_OK else "coords+domain"
                    pairs.append((-(score + (20 if dom else 0)), dist, bi, p["id"], method, score))
        else:  # no coordinates: same domain + (same street and house | clearly the best name)
            pool = pois if register else domain_pois
            scored = sorted(((name_similarity(b["name"], p), p) for p in pool), key=lambda t: -t[0])
            clear = bool(scored) and scored[0][0] >= NAME_OK + 10 and (
                len(scored) == 1 or scored[0][0] - scored[1][0] >= 10)
            for rank, (score, p) in enumerate(scored):
                addr = address_match(b.get("address"), p.get("address"))
                # a register record has no brand key: an address alone matches the wrong co-located museum
                # (the «Бозоқ» reserve and the National Museum share Тәуелсіздік 54), so an address match also
                # needs the name to clear DOMAIN_NAME_OK; a clearly best name still matches without an address
                ok = ((addr and score >= DOMAIN_NAME_OK) or (rank == 0 and clear)) if register \
                    else addr or (rank == 0 and clear)
                if ok:
                    pairs.append((-(score + (30 if addr else 0)), 0.0, bi, p["id"],
                                  "register_name_address" if register and addr
                                  else "domain+address" if addr else "domain+name", score))
    if len(branches) == 1 and len(domain_pois) == 1 and branches[0].get("lat") is None:
        score = name_similarity(branches[0]["name"], domain_pois[0])
        if score >= DOMAIN_NAME_OK:
            pairs.append((-50.0, 0.0, 0, domain_pois[0]["id"], "domain_unique", score))
    by_id = {p["id"]: p for p in pois}
    out, used_b, used_p = [], set(), set()
    for _, dist, bi, pid, method, score in sorted(pairs, key=lambda t: (t[0], t[1])):
        if bi in used_b or pid in used_p:
            continue
        used_b.add(bi)
        used_p.add(pid)
        b = branches[bi]
        d = round(haversine_m(b["lat"], b["lon"], by_id[pid]["lat"], by_id[pid]["lon"]), 1) if b.get(
            "lat") is not None else None
        out.append((b, by_id[pid], method, d, round(score, 1)))
    return out


def _source(b: dict, field_names: set[str], snapshot: str, source: str = SOURCE,
            license_note: str = LICENSE_NOTE) -> dict | None:
    ev = next((e for e in b["evidence"] if e["field"] in field_names), None)
    if ev is None:
        return None
    return {"source": source, "license": license_note, "snapshot_date": (ev.get("fetched_at") or snapshot)[:10],
            "url": ev["url"], "snippet": ev["snippet"], "method": b["method"], "confidence": b["confidence"]}


def official_fields(b: dict, snapshot: str, source: str = SOURCE,
                    license_note: str = LICENSE_NOTE) -> tuple[dict, dict]:
    """(fields, field_sources) the branch contributes to a POI.

    A schedule that was not converted because it names no days (or is an ambiguous 00:00-00:00) never becomes the
    POI's `opening_hours`: its raw text goes to `hours_unqualified` (source entry carries `hours_flags`)."""
    fields, sources = {}, {}
    flags = b.get("hours_flags") or []
    for key, ev_fields, out_key in (
        ("opening_hours_osm", {"opening_hours"}, "opening_hours"),
        ("opening_hours_raw", {"opening_hours"}, "hours_unqualified" if flags else "opening_hours_raw"),
        ("phone", {"phone"}, "phone"),
        ("address", {"address"}, "address"),
        ("description", {"description"}, "description"),
        ("price_text", {"price"}, "price_text"),
    ):
        if b.get(key) and (src := _source(b, ev_fields, snapshot, source, license_note)):
            fields[out_key], sources[out_key] = b[key], src
            if out_key == "hours_unqualified":
                src["hours_flags"] = flags
    return fields, sources


def _same_value(key: str, poi_value, official) -> bool:
    """Equal after whitespace normalisation; opening hours are equal when both schedules open the same minutes of a
    reference week (two spellings of one schedule are not a conflict)."""
    if " ".join(str(poi_value).split()) == " ".join(str(official).split()):
        return True
    return key == "opening_hours" and same_schedule(str(poi_value), str(official))


def join_branches(pois: list[dict], records: list[dict], verifier: Verifier) -> tuple[dict, list[dict]]:
    """(joined result, unmatched candidates [{domain, branch, snapshot, third_party, reason}]).

    The candidates carry the full verified branch so `apply` can turn the ones with first-party coordinates into
    new POIs; `joined.json` itself only lists their name/address/coords."""
    grid = Grid(pois)
    categories = own_categories(pois)
    by_domain: dict[str, list[dict]] = defaultdict(list)
    for p in pois:
        for d in poi_domains(p):
            by_domain[d].append(p)
    joined: dict[str, dict] = {}
    unmatched: list[dict] = []
    candidates: list[dict] = []
    stats: Counter = Counter()
    verify_stats: Counter = Counter()
    by_method: Counter = Counter()
    for rec in records:
        clean, vs = verify_record(rec, verifier)
        verify_stats.update(vs)
        branches = clean["branches"]
        stats["domains"] += 1
        stats["branches"] += len(branches)
        snapshot = rec["fetched_at"]
        third_party = rec.get("notes", "").lower().startswith("third-party")
        # A register record (rec["source_label"] set, e.g. e-museum.kz) is a ministry portal, not each institution's
        # own site: its fields carry that label, and check_dataset binds only `official_site` fields to brand
        # agreement. `register_name` lets a no-coords branch match a POI by name + address across all POIs.
        label, license_note, register = rec_label(rec)
        matched = match_domain(rec["domain"], branches, pois, grid, by_domain.get(rec["domain"], []),
                               lambda p, d=rec["domain"]: speaks_for(d, p, categories), register=register)
        matched_ids = {id(b) for b, *_ in matched}
        for b in branches:
            if id(b) not in matched_ids:
                unmatched.append({"domain": rec["domain"], "name": b["name"], "address": b.get("address"),
                                  "lat": b.get("lat"), "lon": b.get("lon"), "reason": "no POI matched"})
                candidates.append({"domain": rec["domain"], "branch": b, "snapshot": snapshot,
                                   "third_party": third_party, "reason": "no POI matched"})
        for b, p, method, dist, score in matched:
            fields, sources = official_fields(b, snapshot, label, license_note)
            if not fields:
                continue
            prev = joined.get(p["id"])
            # never trade a day-qualified schedule (e.g. the museum's own site) for a register card's day-less one;
            # fields the earlier entry lacks (the register's ticket price) merge into it
            if prev and (prev["score"] >= score or ("opening_hours" in prev["fields"]
                                                    and "opening_hours" not in fields)):
                for k in fields:
                    if k not in prev["fields"] and k not in prev["conflicts"]:
                        prev["fields"][k] = fields[k]
                        prev["field_sources"][k] = sources[k]
                        prev["new_fields"] = sorted({*prev["new_fields"], k})
                if not prev.get("official_domain"):
                    prev["official_domain"] = next((registrable_domain(src.get("url") or "")
                                                    for src in prev["field_sources"].values()
                                                    if src.get("source") == SOURCE
                                                    and registrable_domain(src.get("url") or "")), None)
                unmatched.append({"domain": rec["domain"], "name": b["name"], "address": b.get("address"),
                                  "lat": b.get("lat"), "lon": b.get("lon"),
                                  "reason": f"POI taken by {prev['domain']} (fields merged)"})
                candidates.append({"domain": rec["domain"], "branch": b, "snapshot": snapshot,
                                   "third_party": third_party, "reason": f"POI taken by {prev['domain']}"})
                continue
            if prev:
                by_method[prev["method"]] -= 1
            by_method[method] += 1
            current = {"opening_hours": p.get("opening_hours"), "phone": p.get("phone"),
                       "address": p.get("address"), "description": p.get("description"),
                       "price_text": p.get("price_text")}
            new = sorted(k for k in fields if k in current and not current[k])
            if "opening_hours_raw" in fields and not p.get("opening_hours"):
                new.append("opening_hours_raw")
            if "hours_unqualified" in fields and not p.get("opening_hours"):
                new.append("hours_unqualified")
            conflicts = {k: {"poi": current[k], "official": fields[k]} for k in fields
                         if k in current and current[k] and not _same_value(k, current[k], fields[k])}
            official_domain = next((registrable_domain(src.get("url") or "") for src in sources.values()
                                    if src.get("source") == SOURCE and registrable_domain(src.get("url") or "")),
                                   None)
            joined[p["id"]] = {
                "poi_id": p["id"], "poi_name": p["name"], "category": p["category"], "domain": rec["domain"],
                "branch_name": b["name"], "method": method, "distance_m": dist, "score": score,
                "fields": fields, "new_fields": new, "conflicts": conflicts, "field_sources": sources,
                "source_label": label, "official_domain": official_domain,
            }
    for j in joined.values():
        for k in ("opening_hours", "phone", "address", "description", "hours_unqualified", "price_text"):
            stats[f"new_{k}"] += k in j["new_fields"]
            stats[f"conflict_{k}"] += k in j["conflicts"]
    had = sum(1 for p in pois if p.get("opening_hours"))
    gained = stats["new_opening_hours"]
    result = {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "stats": {
            **dict(sorted(stats.items())), "branches_matched": len(joined), "branches_unmatched": len(unmatched),
            "pois_matched": len(joined), "by_method": {k: v for k, v in by_method.items() if v},
            "hours_before": had, "hours_after": had + gained, "poi_total": len(pois),
            "hours_pct_before": round(100 * had / len(pois), 2) if pois else 0,
            "hours_pct_after": round(100 * (had + gained) / len(pois), 2) if pois else 0,
            "verify": dict(sorted(verify_stats.items())),
        },
        "pois": dict(sorted(joined.items())),
        "unmatched": unmatched,
    }
    return result, candidates


def join(pois: list[dict], records: list[dict], verifier: Verifier) -> dict:
    return join_branches(pois, records, verifier)[0]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--poi", default=str(POI_PATH))
    ap.add_argument("--facts", default=str(FACTS_DIR))
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args(argv)
    pois = json.loads(Path(args.poi).read_text(encoding="utf-8"))
    records = list(iter_facts(Path(args.facts)))
    result = join(pois, records, Verifier(SiteFetcher()))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    s = result["stats"]
    print(f"[sites.join] {s['domains']} domains, {s['branches']} verified branches -> {s['pois_matched']} POIs "
          f"matched ({s['by_method']}), {s['branches_unmatched']} unmatched; new hours {s.get('new_opening_hours', 0)}, "
          f"phone {s.get('new_phone', 0)}, address {s.get('new_address', 0)}, description "
          f"{s.get('new_description', 0)}; conflicts hours {s.get('conflict_opening_hours', 0)}; hours_unqualified "
          f"{s.get('new_hours_unqualified', 0)}; hours coverage "
          f"{s['hours_pct_before']}% -> {s['hours_pct_after']}% -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
