"""Apply the state-object facts to the dataset: data/poi.enriched.json (the merge + official-site stages' output) ->
the same file with `source: state_registry` facts, data/poi_enriched_stats.json extended (key `state_registry`).

Offline (cache + files only). Stages:
  1. verify: every evidence snippet is found in the cached page (`collect.gov.verify`), else the fact is dropped;
  2. geocode: records are matched to dataset POIs / OSM candidates by name and address (`collect.gov.geocode`); a record
     without a match is kept in `data/gov/joined.json`, marked unmapped and counted, never placed on the map;
  3. attach: a record matched to an existing POI adds
       * ЦОН venue hours -> `opening_hours` only when the POI has none and the schedule is day-qualified
         (`hours_state = known`, `field_sources.opening_hours.source = state_registry`), else `opening_hours_state`;
       * administration hours (register № 730) -> `admin_hours` {raw, scope: administration, ...}, NEVER `opening_hours`;
       * `address` when the POI has none; `address_kk` (kk street spelling) when the RCA register resolves the POI's
         street to exactly one street (`data/gazetteer/rca_streets.json`, `address_kk` on the POI, a pure accessor
         in `walks.models`, no UI); `state_registry_match` {record_id, kind, method, ...};
  4. create: a ЦОН record matched to an OSM element becomes a new POI (`id = gov/cson/<hash>`, `source = state_registry`,
     category `other`, tag `gov_service=cson`: the existing categories have no «государственная услуга»; the dialogue
     lexicon must add the words, see collect/gov/README.md) unless a similar-named POI is within 75 m (then it is
     attached). Sport records are attached only: an office of a sports school is not a place to recommend on its own.
The finished dataset is checked by `collect.gov.verify.check_dataset` and `collect.sites.verify.check_dataset`; a failure
aborts before anything is written.

Usage (repo root): uv run python -m collect.gov.apply [--poi data/poi.enriched.json] [--out data/poi.enriched.json]
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.gov import gazetteer
from collect.gov import rca as rca_stage
from collect.gov.addr import parse_address
from collect.gov.geocode import _rec_address, geocode_all, rca_address_kk
from collect.gov.model import LICENSE_NOTE, SOURCE, GovRecord
from collect.gov.verify import FACTS_DIR, check_dataset, verify_file
from collect.merge import stats_for
from collect.overpass_poi import haversine_m
from collect.sites.fetch import SiteFetcher
from collect.sites.join import name_similarity
from collect.sites.verify import Verifier
from collect.sites.verify import check_dataset as sites_check_dataset

ROOT = Path(__file__).resolve().parents[2]
POI_PATH = ROOT / "data" / "poi.enriched.json"
STATS_PATH = ROOT / "data" / "poi_enriched_stats.json"
DELTA_PATH = ROOT / "data" / "coverage_delta.md"
ATTRIBUTION_PATH = ROOT / "data" / "ATTRIBUTION.md"
OSM_PATH = ROOT / "data" / "gov" / "osm_candidates.json"
JOINED_PATH = ROOT / "data" / "gov" / "joined.json"
CATALOG_PATH = ROOT / "collect" / "gov" / "catalog.json"
GAZETTEER_PATH = gazetteer.OUT_PATH
RCA_GAZETTEER_PATH = rca_stage.GAZETTEER_PATH
DELTA_HEADING = "## State registries (ЦОН branches, sport register №730)"
ATTR_BEGIN, ATTR_END = "<!-- state_registry:begin -->", "<!-- state_registry:end -->"
CATEGORY = "other"
DUP_M, DUP_NAME = 75.0, 60.0
_FULL_PHONE = re.compile(r"^\+?[78][\s\-()]*\d{3}[\s\-()]*\d{3}[\s\-]*\d{2}[\s\-]*\d{2}$")
_QUOTES = re.compile(r"\"([^\"]+)\"")


def already_applied(pois: list[dict]) -> bool:
    return any("state_registry_match" in p or SOURCE in (p.get("sources") or []) for p in pois)


def display_name(rec: GovRecord) -> str:
    """The registry's own name; straight double quotes become «» (the page prints the name with entity quotes), and a
    word glued to a closing quote gets its space back («"Есиль"по обслуживанию»)."""
    return " ".join(re.sub(r"»(?=\w)", "» ", _QUOTES.sub(r"«\1»", rec.name)).split())


def registry_address(rec: GovRecord) -> str | None:
    """'ул. Мангилик ел, 30' from the parsed street + house (the printed text keeps stray spaces / 'здание');
    the printed form of the page is what the POI shows — the RCA layer only agrees on the street key."""
    a = rec.address
    text = ", ".join(x for x in (a.get("street"), a.get("house")) if x)
    return text or None


def field_source(rec: GovRecord, field: str, evidence_field: str | None = None) -> dict:
    ev = next((e for e in rec.evidence if e.field == (evidence_field or field) and e.lang in (None, "ru")), None)
    return {"source": SOURCE, "license": LICENSE_NOTE, "snapshot_date": (rec.fetched_at or "")[:10],
            "url": ev.url if ev else rec.url, "snippet": ev.snippet if ev else None, "record_id": rec.id}


def geo_source(rec: GovRecord) -> dict:
    g = rec.geocode
    return {"source": "osm", "license": g.license, "snapshot_date": (g.fetched_at or "")[:10], "ref": g.ref,
            "method": g.method, "matched_by": "name and address of the registry record", "record_id": rec.id}


def full_phone(raw: str | None) -> str | None:
    if raw and _FULL_PHONE.match(raw.strip()):
        digits = re.sub(r"\D", "", raw)
        return f"+7 {digits[1:4]} {digits[4:7]} {digits[7:9]} {digits[9:11]}"
    return None


def match_block(rec: GovRecord, method: str) -> dict:
    return {"record_id": rec.id, "source": rec.source, "kind": rec.kind, "method": method, "url": rec.url,
            "hours_scope": rec.hours.scope if rec.hours else None,
            "confidence": "high" if method in ("osm_name_address", "poi_name_address") else "medium"}


def _kk_source(rec: GovRecord) -> dict:
    """field_sources entry of `address_kk`: the RCA register page, no per-row snippet (a snapshot file)."""
    return {"source": SOURCE, "license": LICENSE_NOTE, "snapshot_date": (rec.fetched_at or "")[:10],
            "url": rec.url, "snippet": None, "record_id": rec.id,
            "basis": "kk spelling of the street from the RCA address register "
                     "(data/gazetteer/rca_streets.json); the register prints the address in ru and kk"}


def attach(p: dict, rec: GovRecord, method: str, rca: dict | None = None) -> list[str]:
    """Add the registry facts of `rec` to the existing POI `p` (in place); returns the touched fields."""
    fsrc, touched = p.setdefault("field_sources", {}), []
    h = rec.hours
    if h and h.scope == "venue" and h.opening_hours:
        if not p.get("opening_hours"):
            p["opening_hours"], p["hours_state"] = h.opening_hours, "known"
            fsrc["opening_hours"] = field_source(rec, "opening_hours")
            touched.append("opening_hours")
        elif p["opening_hours"] != h.opening_hours:
            p["opening_hours_state"] = h.opening_hours
            fsrc["opening_hours_state"] = field_source(rec, "opening_hours")
            touched.append("opening_hours_state")
    if h and h.scope == "administration":
        p["admin_hours"] = {"raw": h.raw, "scope": "administration", "registry": rec.name, "phone_raw": rec.phone_raw,
                            "note": "office week of the managing body, not the opening hours of the venue"}
        fsrc["admin_hours"] = field_source(rec, "admin_hours")
        touched.append("admin_hours")
    if (ph := full_phone(rec.phone_raw)) and not p.get("phone"):
        p["phone"], fsrc["phone"] = ph, field_source(rec, "phone")
        touched.append("phone")
    if not p.get("address") and (address := registry_address(rec)):
        p["address"], fsrc["address"] = address, field_source(rec, "address")
        touched.append("address")
    if SOURCE not in p["sources"]:
        p["sources"].append(SOURCE)
    if rca and not p.get("address_kk"):
        source_addr = parse_address(p["address"]) if p.get("address") else _rec_address(rec)
        if (kk := rca_address_kk(source_addr, rca)):
            p["address_kk"], fsrc["address_kk"] = kk, _kk_source(rec)
            touched.append("address_kk")
    p["state_registry_match"] = match_block(rec, method)
    return touched


def new_poi(rec: GovRecord, template: dict, rca: dict | None = None) -> dict:
    g, h, name = rec.geocode, rec.hours, display_name(rec)
    oh = h.opening_hours if h and h.scope == "venue" else None
    address = registry_address(rec)
    kk = rca_address_kk(_rec_address(rec), rca) if rca else None
    day = (rec.fetched_at or "")[:10]
    desc = f"Центр обслуживания населения (ЦОН): {name}" + (f", {address}." if address else ".")
    desc += f" Часы работы (gov4c.kz): {oh}." if oh else " Часы работы на gov4c.kz не разобраны."
    if h and h.note:
        desc += f" {h.note}."
    rec_p = {k: ([] if isinstance(v, list) else {} if isinstance(v, dict) else False if isinstance(v, bool) else None)
             for k, v in template.items()}
    rec_p.update({
        "id": rec.id, "name": name, "name_generated": False,
        "names": {"name": name, **{f"name:{k}": v for k, v in rec.names.items()}}, "lat": g.lat, "lon": g.lon,
        "category": CATEGORY, "tags": ["gov_service=cson"], "opening_hours": oh,
        "website": rec.url, "address": address, "address_kk": kk, "description_auto": desc,
        "description_source": "derived",
        "source": SOURCE, "collected_at": rec.fetched_at, "sources": [SOURCE],
        "hours_state": "known" if oh else "unknown",
        "hours_unqualified": h.raw if h and h.scope == "venue" and not oh else None,
        "state_registry_match": match_block(rec, g.method or ""),
    })
    for key in ("opening_hours_official", "hours_conflict_prefers", "description_official"):
        rec_p[key] = None
    fs = {"name": field_source(rec, "name"), "lat": geo_source(rec), "lon": geo_source(rec),
          "category": {"source": "derived", "license": "n/a", "snapshot_date": day,
                       "basis": "no existing category fits a state service centre; data-only mapping to `other` "
                                "with tag gov_service=cson"},
          "website": field_source(rec, "website", "name"),
          "description_auto": {"source": "derived", "license": "n/a", "snapshot_date": day}}
    if address:
        fs["address"] = field_source(rec, "address")
    if kk:
        fs["address_kk"] = _kk_source(rec)
    if oh:
        fs["opening_hours"] = field_source(rec, "opening_hours")
    elif h and h.scope == "venue":
        fs["hours_unqualified"] = field_source(rec, "opening_hours")
    rec_p["field_sources"] = fs
    return rec_p


def _blank_template(pois: list[dict]) -> dict:
    template: dict = {}
    for p in pois:
        for k, v in p.items():
            template.setdefault(k, v)
    return {k: v for k, v in template.items() if k in {
        "id", "name", "name_generated", "names", "lat", "lon", "category", "tags", "opening_hours", "website", "phone",
        "address", "address_kk", "wheelchair", "internet_access", "outdoor_seating", "description", "description_auto",
        "description_source", "source", "collected_at", "sources", "field_sources", "overture_id", "hours_state",
        "brand", "brand_wikidata", "opening_hours_official", "hours_conflict", "hours_conflict_prefers",
        "hours_unqualified", "hours_unqualified_flags", "description_official"}}


def _near_duplicate(rec: GovRecord, pois: list[dict]) -> dict | None:
    g, name = rec.geocode, display_name(rec)
    for p in pois:
        if haversine_m(g.lat, g.lon, p["lat"], p["lon"]) <= DUP_M and name_similarity(name, p) >= DUP_NAME:
            return p
    return None


def build(pois: list[dict], records: list[GovRecord], rca: dict | None = None) -> tuple[list[dict], list[dict], dict]:
    """(new dataset, joined entries, stats). `records` already carry `geocode`; `rca` (the RCA street gazetteer)
    fills `address_kk` where the register's street agrees with the POI's address uniquely."""
    out = copy.deepcopy(pois)
    by_id = {p["id"]: p for p in out}
    template = _blank_template(pois)
    joined: list[dict] = []
    new: list[dict] = []
    filled: Counter = Counter()
    for rec in records:
        g = rec.geocode
        entry = {"record_id": rec.id, "kind": rec.kind, "name": rec.name, "geocode": g.to_dict() if g else None,
                 "action": None, "poi_id": None}
        if g is None or g.status == "unmapped":
            entry["action"] = "kept_unmapped"
        elif rec.extra.get("display"):
            entry["action"] = "geocoded_not_created"  # the ps_centers display cross-checks, never overwrites a match
        elif g.status == "matched_poi":
            entry["poi_id"], entry["action"] = g.ref, "attached"
            for f in attach(by_id[g.ref], rec, g.method or "", rca):
                filled[f] += 1
        elif rec.kind != "cson":
            entry["action"] = "geocoded_not_created"
        elif (dup := _near_duplicate(rec, out + new)) is not None:
            entry["poi_id"], entry["action"] = dup["id"], "attached_nearby"
            for f in attach(dup, rec, "osm_near_poi", rca):
                filled[f] += 1
        else:
            poi = new_poi(rec, template, rca)
            new.append(poi)
            entry["poi_id"], entry["action"] = poi["id"], "created"
        joined.append(entry)
    return out + new, joined, stats_of(pois, out + new, new, records, joined, filled)


def stats_of(before: list[dict], after: list[dict], new: list[dict], records: list[GovRecord], joined: list[dict],
             filled: Counter) -> dict:
    kinds = Counter(r.kind for r in records)
    actions = Counter((j["kind"], j["action"]) for j in joined)
    geo = Counter(r.geocode.status for r in records if r.geocode)
    methods = Counter(r.geocode.method for r in records if r.geocode and r.geocode.method)
    h0, h1 = sum(1 for p in before if p.get("opening_hours")), sum(1 for p in after if p.get("opening_hours"))
    return {
        "generated_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "cson_found": kinds["cson"], "sport_records": kinds["sport_facility"],
        "geocoded": geo["matched_osm"] + geo["matched_poi"], "geocode_status": dict(geo), "geocode_methods": dict(methods),
        "unmapped": geo["unmapped"],
        "unmapped_records": [{"record_id": r.id, "kind": r.kind, "name": r.name, "address": r.address.get("raw"),
                              "reason": r.geocode.reason} for r in records if r.geocode and r.geocode.status == "unmapped"],
        "attached_to_existing_pois": sum(v for (k, a), v in actions.items() if a in ("attached", "attached_nearby")),
        "new_pois": len(new), "new_pois_by_category": dict(Counter(p["category"] for p in new)),
        "actions": {f"{k}:{a}": v for (k, a), v in sorted(actions.items())},
        "fields_filled_on_existing": dict(filled),
        "admin_hours_pois": sum(1 for p in after if p.get("admin_hours")),
        "poi_total_before": len(before), "poi_total_after": len(after),
        "hours_day_qualified_before": h0, "hours_day_qualified_after": h1,
        "licence": LICENSE_NOTE,
    }


def shipped_stats(prev: dict, dataset: list[dict], gov: dict) -> dict:
    sources = [[s for s in p["sources"] if s not in ("official_site", SOURCE)] for p in dataset]
    ps = {**prev.get("per_source_counts", {}),
          "state_registry_only": sum(1 for s, p in zip(sources, dataset, strict=True) if not s and SOURCE in p["sources"]),
          "with_state_registry": sum(1 for p in dataset if SOURCE in p["sources"])}
    # a record from the registry alone is neither official_site_only nor counted in the OSM/Overture buckets
    if "official_site_only" in ps:
        ps["official_site_only"] = sum(1 for s, p in zip(sources, dataset, strict=True)
                                       if not s and "official_site" in p["sources"] and SOURCE not in p["sources"])
    return {**prev, "after": stats_for(dataset), "per_source_counts": ps,
            "description_source_counts": {s: sum(1 for p in dataset if p["description_source"] == s)
                                          for s in ("osm", "wikipedia", "derived")},
            "state_registry": gov}


def _catalog_summary() -> dict | None:
    if not CATALOG_PATH.exists():
        return None
    cat = json.loads(CATALOG_PATH.read_text(encoding="utf-8"))
    return {"agency": cat["agency"], **cat["summary"]}


def render_delta(s: dict) -> str:
    cat = s.get("catalog")
    lines = [DELTA_HEADING, "",
             f"Generated {s['generated_at'][:10]} by `collect.gov.apply` (facts: `data/gov/facts`, joins: "
             "`data/gov/joined.json`). Source: gov4c.kz (ЦОН branches) and data.egov.kz register №730; licence: "
             f"{s['licence']}.", "",
             f"- ЦОН branches found: **{s['cson_found']}**; sport register records: **{s['sport_records']}**.",
             f"- Geocoded (matched to an OSM element or a POI by name+address): **{s['geocoded']}** "
             f"({s['geocode_methods']}); unmapped (kept, not on the map): **{s['unmapped']}**.",
             f"- Attached to existing POIs: **{s['attached_to_existing_pois']}** "
             f"(filled: {s['fields_filled_on_existing']}); new POIs: **{s['new_pois']}** ({s['new_pois_by_category']}).",
             f"- POIs with `admin_hours` (office week of the administration, never `opening_hours`): "
             f"**{s['admin_hours_pois']}**.",
             f"- POIs with `address_kk` (kk street spelling from the RCA register, "
             f"`data/gazetteer/rca_streets.json`): **{s.get('address_kk_pois', 0)}**.",
             f"- POIs: {s['poi_total_before']} -> {s['poi_total_after']}; day-qualified `opening_hours`: "
             f"{s['hours_day_qualified_before']} -> {s['hours_day_qualified_after']}."]
    if cat:
        lines.append(f"- Catalogue of {cat['agency']} on data.egov.kz: {cat['published_datasets']} published datasets, "
                     f"{cat['with_coordinates']} with coordinates, {cat['with_working_hours_field']} with a working-hours "
                     f"field (`collect/gov/catalog.json`).")
    return "\n".join(lines) + "\n"


def _replace_section(path: Path, begin: str, end: str | None, block: str) -> None:
    """Replace (or append) the block that starts with `begin`; it ends at `end`, or at the next '## ' heading."""
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    head, sep, tail = text.partition(begin)
    if sep:
        if end:
            tail = tail.partition(end)[2]
        else:
            nxt = re.search(r"^## ", tail, re.MULTILINE)
            tail = tail[nxt.start():] if nxt else ""
    path.write_text(head.rstrip("\n") + ("\n\n" if head.strip() else "") + block.rstrip("\n") + "\n"
                    + ("\n" + tail.lstrip("\n") if tail.strip() else ""), encoding="utf-8")


def write_attribution(path: Path) -> None:
    block = (f"{ATTR_BEGIN}\n- **State registries** (`collect/gov`, `sources` contains `state_registry`) — branch addresses and "
             "schedules of the ЦОН (gov4c.kz, НАО «Правительство для граждан») and register №730 «Перечень "
             "государственных спортивных объектов» of the Astana sports department (data.egov.kz); open data of a state "
             "body of the Republic of Kazakhstan, Law №401-V on access to information (art. 1 p. 5: free use, "
             "processing, re-publication). Coordinates of these records are never the registry's: they are those of the "
             "OpenStreetMap element matched by name and address (ODbL 1.0, © OpenStreetMap contributors). "
             "`data/gazetteer/`: street spellings of Astana from OpenAddresses KZ, attribution «Комитет по правовой "
             "статистике и специальным учетам Генеральной прокуратуры РК» (see `data/gazetteer/ATTRIBUTION.md`); "
             "`rca_streets.json` — the street layer of the same Committee's address register (ИС «Адресный регистр») "
             "via keyless data.egov.kz /api/detailed, the same attribution, Law №401-V; no coordinates.\n"
             f"{ATTR_END}")
    _replace_section(path, ATTR_BEGIN, ATTR_END, block)


def load_records(facts_dir: Path, verifier: Verifier) -> tuple[list[GovRecord], Counter]:
    records: list[GovRecord] = []
    stats: Counter = Counter()
    for path in sorted(facts_dir.glob("*.json")):
        payload, st = verify_file(json.loads(path.read_text(encoding="utf-8")), verifier)
        stats.update(st)
        records += [GovRecord.from_dict(d) for d in payload["records"]]
    return records, stats


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--poi", default=str(POI_PATH))
    ap.add_argument("--facts", default=str(FACTS_DIR))
    ap.add_argument("--osm", default=str(OSM_PATH))
    ap.add_argument("--out", default=str(POI_PATH))
    ap.add_argument("--joined", default=str(JOINED_PATH))
    ap.add_argument("--stats", default=str(STATS_PATH))
    ap.add_argument("--delta", default=str(DELTA_PATH))
    ap.add_argument("--attribution", default=str(ATTRIBUTION_PATH))
    args = ap.parse_args(argv)
    pois = json.loads(Path(args.poi).read_text(encoding="utf-8"))
    if already_applied(pois):
        print(f"[gov.apply] {args.poi} already carries state-registry facts; rebuild the base first "
              "(uv run python -m collect.build), then apply.", file=sys.stderr)
        return 1
    records, vstats = load_records(Path(args.facts), Verifier(SiteFetcher()))
    if vstats["evidence_dropped"] or vstats["records_dropped"]:
        print(f"[gov.apply] evidence not found in the cached pages: {dict(vstats)}", file=sys.stderr)
        return 1
    candidates = json.loads(Path(args.osm).read_text(encoding="utf-8"))
    rca_streets = rca_stage.load_gazetteer(RCA_GAZETTEER_PATH)
    geocode_all(records, candidates, pois, gazetteer.load(GAZETTEER_PATH), rca_streets or None)
    dataset, joined, stats = build(pois, records, rca_streets or None)
    stats["address_kk_pois"] = sum(1 for p in dataset if p.get("address_kk"))
    stats["catalog"] = _catalog_summary()
    problems = check_dataset(dataset) + sites_check_dataset(dataset)
    if problems:
        for line in problems:
            print(f"[gov.apply] {line}", file=sys.stderr)
        print(f"[gov.apply] {len(problems)} problem(s); nothing written", file=sys.stderr)
        return 1
    stats_path = Path(args.stats)
    prev = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    ship = shipped_stats(prev, dataset, stats) if "per_source_counts" in prev else {**prev, "state_registry": stats}
    Path(args.out).write_text(json.dumps(dataset, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    Path(args.joined).parent.mkdir(parents=True, exist_ok=True)
    Path(args.joined).write_text(json.dumps({"stats": stats, "records": joined}, ensure_ascii=False, indent=1) + "\n",
                                 encoding="utf-8")
    stats_path.write_text(json.dumps(ship, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _replace_section(Path(args.delta), DELTA_HEADING, None, render_delta(stats))
    write_attribution(Path(args.attribution))
    print(f"[gov.apply] ЦОН {stats['cson_found']}, sport {stats['sport_records']}; geocoded {stats['geocoded']} "
          f"({stats['geocode_methods']}), unmapped {stats['unmapped']}; attached {stats['attached_to_existing_pois']}, "
          f"new {stats['new_pois']}; POIs {stats['poi_total_before']} -> {stats['poi_total_after']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
