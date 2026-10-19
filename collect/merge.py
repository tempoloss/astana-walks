"""Merge OSM + Overture + Wikidata/Wikipedia into data/poi.enriched.json.

Usage: uv run python -m collect.merge

Inputs : data/poi.osm.json, data/overture_places.json, data/wiki_enrichment.json
Outputs: data/poi.enriched.json, data/poi_enriched_stats.json, data/coverage_delta.md
data/ATTRIBUTION.md is maintained by hand (docs/licensing.md): a rebuild never rewrites it.
Never touches data/poi.json / data/poi_stats.json (frozen app input and its "before" statistics).

Every OSM field name is kept; added fields: sources[], field_sources{}, overture_id, overture_match,
hours_state, brand, brand_wikidata, wikidata_id, wikipedia{lang:{title,url,extract}}, labels{ru,kk,en},
popularity_pageviews, wiki_match{method,confidence}, overture_confidence.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from datetime import datetime, timezone
from urllib.parse import urlsplit
from pathlib import Path

try:
    from collect import metrics, wiki_merge
    from collect.names import is_generic_name, name_key, name_score
    from collect.nonpoi import non_poi_reason
    from collect.overpass_poi import CATEGORIES, haversine_m, pct, write_json
    from collect.overture_places import CONFIDENCE_CUTOFF, NEWLY_MAPPED
except ImportError:  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from collect import metrics, wiki_merge
    from collect.names import is_generic_name, name_key, name_score
    from collect.nonpoi import non_poi_reason
    from collect.overpass_poi import CATEGORIES, haversine_m, pct, write_json
    from collect.overture_places import CONFIDENCE_CUTOFF, NEWLY_MAPPED

DATA = Path(__file__).resolve().parents[1] / "data"

# OSM <-> Overture entity resolution: close + similar name, or a bit farther + (almost) same name.
NEAR_M, NEAR_SCORE = 75.0, 75.0
FAR_M, FAR_SCORE = 150.0, 92.0
OVERTURE_DEDUP_M = 50.0
# Overture-only record vs OSM record of the same chain venue (same normalised name key, any category pair):
# within CHAIN_M when the key comes from the name or the brand / brand:wikidata, up to CHAIN_SAME_NAME_M when the
# names themselves are identical (OSM and Overture put one airport kiosk 240 m apart).
CHAIN_M, CHAIN_SAME_NAME_M = 150.0, 250.0
EXAMPLES = 10
NON_POI_EXAMPLES = 15

CLOSED_STATUSES = {"closed", "permanently_closed", "temporarily_closed"}

LICENSE_OSM = "ODbL-1.0"
OSM_FIELDS = ("name", "lat", "lon", "category", "opening_hours", "website", "phone", "address", "wheelchair",
              "internet_access", "outdoor_seating", "description")

KIDS_KIND = {"entertainment": "Детский развлекательный центр", "museum_gallery": "Детский музей"}
CATEGORY_RU = {
    "cafe": "Кафе", "restaurant": "Ресторан", "fast_food": "Заведение быстрого питания",
    "bar_nightlife": "Бар / ночная жизнь", "museum_gallery": "Музей или галерея",
    "attraction_landmark": "Достопримечательность", "viewpoint": "Смотровая площадка",
    "park_garden": "Парк или сад", "kids_playground": "Детская площадка", "entertainment": "Место для развлечений",
    "mall": "Торговый центр", "culture_theatre_cinema": "Театр, кино или культурный центр",
    "coworking_library": "Библиотека или коворкинг", "sport": "Спортивный объект",
    "transit_station": "Станция", "pharmacy": "Аптека", "grocery": "Продуктовый магазин", "money": "Банкомат или банк",
    "lodging": "Гостиница", "other": "Объект",
}

_ABBR = {"г", "гг", "ул", "им", "км", "м", "тыс", "млн", "св", "др", "пр", "англ", "каз", "рус", "лат", "ок", "кв",
         "вв", "нач", "кон", "ж", "р", "о", "оз", "пос", "обл", "рис", "см", "напр", "проч", "тел", "ст", "nr", "st",
         "mt", "dr", "jr", "sr", "vs", "etc", "ca", "approx", "c"}
_BREAK = re.compile(r"(?<=[.!?…])\s+(?=[«\"“(]?[A-ZА-ЯЁӘҒҚҢӨҰҮІҺ0-9])")


def first_sentences(text: str, max_sentences: int = 2, max_chars: int = 420) -> str:
    """First 1-2 sentences of a Wikipedia intro (abbreviation-aware); 1 if two would be too long."""
    text = " ".join(text.split())
    sentences: list[str] = []
    start = 0
    for m in _BREAK.finditer(text):
        word = re.findall(r"[\w-]+", text[start:m.start()].rsplit(" ", 1)[-1])
        last = word[-1].casefold() if word else ""
        if len(last) <= 1 or last in _ABBR:
            continue
        sentences.append(text[start:m.start()])
        start = m.end()
        if len(sentences) >= max_sentences:
            break
    if len(sentences) < max_sentences:
        sentences.append(text[start:])
    out = sentences[0]
    for s in sentences[1:max_sentences]:
        if len(out) + 1 + len(s) <= max_chars:
            out += " " + s
    return out.strip()


def date_of(iso: str | None) -> str | None:
    return iso[:10] if iso else None


# ---- Overture preparation -------------------------------------------------------------------------


def overture_names(ov: dict) -> list[str]:
    return list(dict.fromkeys(ov["names"].values()))


def overture_usable(ov: dict, cutoff: float) -> bool:
    return (
        ov["name"] is not None
        and (ov["confidence"] or 0.0) >= cutoff
        and ov["operating_status"] not in CLOSED_STATUSES
    )


class Grid:
    def __init__(self, items: list[dict], cell: float = 0.003):
        self.cell = cell
        self.cells: dict[tuple[int, int], list[dict]] = {}
        for it in items:
            self.cells.setdefault(self.key(it["lat"], it["lon"]), []).append(it)

    def key(self, lat: float, lon: float) -> tuple[int, int]:
        return int(lat // self.cell), int(lon // self.cell)

    def near(self, lat: float, lon: float):
        ky, kx = self.key(lat, lon)
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                yield from self.cells.get((ky + dy, kx + dx), ())


def pair_ok(dist: float, score: float, ov: dict) -> bool:
    """Close + similar name, or farther + near-identical name. Overture records outside our category set
    (a shop inside a mall, an office in a business centre) must match near-identically at any distance."""
    if ov["category"] == "other":
        return dist <= FAR_M and score >= FAR_SCORE
    return (dist <= NEAR_M and score >= NEAR_SCORE) or (dist <= FAR_M and score >= FAR_SCORE)


def osm_names(p: dict) -> list[str]:
    if p["name_generated"]:
        return []
    return list(dict.fromkeys([*p["names"].values(), p["name"]]))


def resolve(osm: list[dict], ovs: list[dict]) -> dict[str, tuple[dict, float, float]]:
    """1:1 greedy assignment (best name score, then nearest) -> {osm id: (overture record, dist, score)}."""
    grid = Grid(ovs)
    pairs = []
    for p in osm:
        names = osm_names(p)
        if not names:
            continue
        for ov in grid.near(p["lat"], p["lon"]):
            dist = haversine_m(p["lat"], p["lon"], ov["lat"], ov["lon"])
            if dist > FAR_M:
                continue
            score = name_score(names, overture_names(ov))
            if pair_ok(dist, score, ov):
                pairs.append((-score, dist, p["id"], ov["id"], ov))
    pairs.sort(key=lambda x: x[:4])
    used_osm, used_ov, out = set(), set(), {}
    for neg, dist, pid, oid, ov in pairs:
        if pid in used_osm or oid in used_ov:
            continue
        used_osm.add(pid)
        used_ov.add(oid)
        out[pid] = (ov, dist, -neg)
    return out


def demote_non_poi(ovs: list[dict]) -> tuple[list[dict], list[dict]]:
    """Overture records that are not walkable POI (ЖК, offices, schools...) -> category `other`.

    Returns (records with the demotions applied, one log row per demotion)."""
    out, log = [], []
    for ov in ovs:
        reason = non_poi_reason(ov)
        if reason is None:
            out.append(ov)
            continue
        log.append({"id": ov["id"], "name": ov["name"], "from": ov["category"], "reason": reason,
                    "primary": ov["categories"]["primary"], "confidence": ov["confidence"]})
        out.append({**ov, "category": "other"})
    return out, log


def _chain_keys(names: list[str | None]) -> set[str]:
    return {k for n in names if n and not is_generic_name(n) and len(k := name_key(n)) >= 3}


def chain_match(rec: dict, ov: dict, dist: float) -> str | None:
    """How `ov` is the same chain venue as OSM record `rec` ('name' | 'brand_wikidata' | 'brand'), or None."""
    if dist > CHAIN_SAME_NAME_M:
        return None
    rec_keys = _chain_keys(osm_names(rec))
    ov_keys = _chain_keys(overture_names(ov))
    if rec_keys & ov_keys:
        return "name"
    if dist > CHAIN_M:
        return None
    ov_brand = ov["brand"] or {}
    if ov_brand.get("wikidata") and ov_brand["wikidata"] == rec["brand_wikidata"]:
        return "brand_wikidata"
    if (rec_keys | _chain_keys([rec["brand"]])) & (ov_keys | _chain_keys([ov_brand.get("name")])):
        return "brand"
    return None


def chain_duplicate(ov: dict, grid: Grid) -> tuple[dict, float, str] | None:
    """Nearest OSM record that `ov` duplicates (see `chain_match`)."""
    best = None
    for rec in grid.near(ov["lat"], ov["lon"]):
        dist = haversine_m(rec["lat"], rec["lon"], ov["lat"], ov["lon"])
        if (best is None or dist < best[1]) and (how := chain_match(rec, ov, dist)):
            best = (rec, dist, how)
    return best


def match_rate_by_confidence(osm: list[dict], ovs: list[dict]) -> dict[str, dict]:
    """For Overture records in our categories: share with an OSM counterpart, per 0.1 confidence bucket.

    Ghost records have no counterpart on the ground, so a falling match rate marks where the noise begins.
    """
    grid = Grid(osm)
    rows: dict[str, list[int]] = {}
    for ov in ovs:
        if ov["category"] == "other" or ov["confidence"] is None:
            continue
        names = overture_names(ov)
        hit = False
        for p in grid.near(ov["lat"], ov["lon"]):
            p_names = osm_names(p)
            if not p_names:
                continue
            dist = haversine_m(p["lat"], p["lon"], ov["lat"], ov["lon"])
            if dist <= FAR_M and pair_ok(dist, name_score(p_names, names), ov):
                hit = True
                break
        b = min(int(ov["confidence"] * 10), 9) / 10
        row = rows.setdefault(f"{b:.1f}-{b + 0.1:.1f}", [0, 0])
        row[0] += 1
        row[1] += hit
    return {k: {"records": n, "matched_osm": m, "match_rate_pct": pct(m, n)} for k, (n, m) in sorted(rows.items())}



# ---- record building ------------------------------------------------------------------------------


def fs(source: str, license_: str, snapshot: str | None, **extra) -> dict:
    return {"source": source, "license": license_, "snapshot_date": snapshot, **extra}


def overture_fs(ov: dict, snapshot: str | None, meta: dict) -> dict:
    """field_sources entry of a field taken from an Overture record. The places theme has no single licence: it is the
    licence of the contributing dataset, as carried in the record's own `sources[].license` (Meta / Microsoft / PinMeTo
    = CDLA-Permissive-2.0, Foursquare = Apache-2.0, AllThePlaces = CC0-1.0). A record with no licence is an error,
    never a default."""
    licences = sorted({s["license"] for s in ov["sources"] if s.get("license")})
    if not licences:
        raise ValueError(f"Overture record {ov['id']} carries no source licence")
    contributors = ", ".join(sorted({s["dataset"] for s in ov["sources"]}))
    return fs("overture", " + ".join(licences), snapshot, release=meta["release"], record_id=ov["id"],
              contributor=contributors)


NOT_A_WEBSITE = ("api.whatsapp.com", "wa.me", "instagram.com", "facebook.com", "fb.com", "t.me", "vk.com",
                 "tiktok.com", "ok.ru", "linktr.ee", "taplink.cc")


def pick_website(ov: dict) -> str | None:
    """First Overture website that is a real site (messenger / social links are not websites)."""
    for url in ov["websites"]:
        host = (urlsplit(url).hostname or "").removeprefix("www.")
        if not any(host == h or host.endswith("." + h) for h in NOT_A_WEBSITE):
            return url
    return None


def ov_address(ov: dict) -> str | None:
    for a in ov["addresses"]:
        parts = [a.get("locality"), a.get("freeform")]
        text = ", ".join(p for p in parts if p)
        if text:
            return text
    return None


def osm_tag(p: dict, key: str) -> str | None:
    prefix = key + "="
    for t in p["tags"]:
        if t.startswith(prefix):
            return t[len(prefix):].strip('"') or None
    return None


def build_osm_record(p: dict) -> dict:
    rec = dict(p)
    snap = date_of(p["collected_at"])
    rec["sources"] = ["osm"]
    rec["field_sources"] = {f: fs("osm", LICENSE_OSM, snap) for f in OSM_FIELDS if rec.get(f) not in (None, "")}
    rec["overture_id"] = None
    rec["hours_state"] = "known" if rec["opening_hours"] else "unknown"
    rec["brand"] = osm_tag(p, "brand")
    rec["brand_wikidata"] = osm_tag(p, "brand:wikidata")
    for f in ("brand", "brand_wikidata"):
        if rec[f]:
            rec["field_sources"][f] = fs("osm", LICENSE_OSM, snap)
    return rec


def apply_overture(rec: dict, ov: dict, dist: float, score: float, meta: dict) -> None:
    snap = meta["snapshot_date"]
    rec["sources"].append("overture")
    rec["overture_id"] = ov["id"]
    rec["overture_match"] = {"distance_m": round(dist, 1), "name_score": round(score, 1)}
    rec["overture_confidence"] = ov["confidence"]
    fsrc = overture_fs(ov, snap, meta)
    if not rec["phone"] and ov["phones"]:
        rec["phone"] = ov["phones"][0]
        rec["field_sources"]["phone"] = fsrc
    website = pick_website(ov)
    if not rec["website"] and website:
        rec["website"] = website
        rec["field_sources"]["website"] = fsrc
    if ov["brand"]:
        if not rec["brand"] and ov["brand"].get("name"):
            rec["brand"] = ov["brand"]["name"]
            rec["field_sources"]["brand"] = fsrc
        if not rec["brand_wikidata"] and ov["brand"].get("wikidata"):
            rec["brand_wikidata"] = ov["brand"]["wikidata"]
            rec["field_sources"]["brand_wikidata"] = fsrc


def build_overture_record(ov: dict, meta: dict) -> dict:
    snap = meta["snapshot_date"]
    names = {}
    if ov["names"].get("primary"):
        names["name"] = ov["names"]["primary"]
    for lang in ("ru", "kk", "en"):
        if ov["names"].get(lang):
            names[f"name:{lang}"] = ov["names"][lang]
    address = ov_address(ov)
    category = ov["category"]
    kind = KIDS_KIND.get(category, CATEGORY_RU[category]) if ov.get("for_kids") else CATEGORY_RU[category]
    desc = f"{kind} «{ov['name']}»" + (f" по адресу {address}." if address else " в Астане.")
    desc += " Часы работы и подробности в Overture Maps не указаны."
    tags = [f"overture_category={ov['categories']['primary']}"] if ov["categories"]["primary"] else []
    if ov.get("for_kids"):
        tags.append("for_kids=yes")
    if ov.get("category_rule"):
        tags.append(f"category_rule={ov['category_rule']}")
    brand = ov["brand"] or {}
    if brand.get("name"):
        tags.append(f"brand={brand['name']}")
    fsrc = overture_fs(ov, snap, meta)
    rec = {
        "id": f"overture/{ov['id']}",
        "name": ov["name"],
        "name_generated": False,
        "names": names,
        "lat": ov["lat"],
        "lon": ov["lon"],
        "category": category,
        "tags": tags,
        "opening_hours": None,
        "website": pick_website(ov),
        "phone": ov["phones"][0] if ov["phones"] else None,
        "address": address,
        "wheelchair": None,
        "internet_access": None,
        "outdoor_seating": None,
        "description": None,
        "description_auto": desc,
        "description_source": "derived",
        "source": "overture",
        "collected_at": f"{snap}T00:00:00+00:00",
        "sources": ["overture"],
        "overture_id": ov["id"],
        "overture_confidence": ov["confidence"],
        "hours_state": "unknown",
        "brand": brand.get("name"),
        "brand_wikidata": brand.get("wikidata"),
    }
    rec["field_sources"] = {f: fsrc for f in OSM_FIELDS if rec.get(f) not in (None, "")}
    rec["field_sources"]["description_auto"] = {"source": "derived", "license": "n/a", "snapshot_date": snap}
    if ov.get("category_rule"):
        rec["field_sources"]["category"] = fs("derived", "n/a", snap, basis=f"name_rule:{ov['category_rule']}",
                                              taxonomy=ov["categories"]["primary"])
    for f in ("brand", "brand_wikidata"):
        if rec[f]:
            rec["field_sources"][f] = fsrc
    return rec


def apply_wiki(rec: dict, match: dict, ent: dict, wiki: dict) -> None:
    snap = wiki["snapshot_date"]
    mm = {"match_method": match["method"], "match_confidence": match["confidence"]}
    rec["wikidata_id"] = ent["qid"]
    rec["labels"] = {l: ent["labels"][l] for l in ("ru", "kk", "en") if l in ent["labels"]}
    rec["wiki_match"] = {"method": match["method"], "confidence": match["confidence"]}
    rec["field_sources"]["wikidata_id"] = fs("wikidata", wiki["licenses"]["wikidata"], snap, **mm)
    rec["field_sources"]["labels"] = fs("wikidata", wiki["licenses"]["wikidata"], snap, **mm)
    articles = {l: a for l, a in ent.get("wikipedia", {}).items()}
    if articles:
        rec["wikipedia"] = {l: {"title": a["title"], "url": a["url"], "extract": a["extract"]}
                            for l, a in articles.items()}
        rec["field_sources"]["wikipedia"] = fs("wikipedia", wiki["licenses"]["wikipedia"], snap, **mm)
    if ent.get("popularity_pageviews") is not None:
        rec["popularity_pageviews"] = ent["popularity_pageviews"]
        rec["field_sources"]["popularity_pageviews"] = fs(
            "wikimedia_pageviews", wiki["licenses"]["wikimedia_pageviews"], snap, period=wiki["pageviews_period"], **mm)
    if rec["description_source"] != "osm":
        for lang in ("ru", "en", "kk"):
            extract = (articles.get(lang) or {}).get("extract")
            if extract:
                text = first_sentences(extract)
                rec["description"] = rec["description_auto"] = text
                rec["description_source"] = "wikipedia"
                rec["field_sources"]["description"] = fs(
                    "wikipedia", wiki["licenses"]["wikipedia"], snap, lang=lang, url=articles[lang]["url"], **mm)
                break


# ---- statistics -----------------------------------------------------------------------------------


def stats_for(pois: list[dict]) -> dict:
    total = len(pois)
    per = {c: [p for p in pois if p["category"] == c] for c in CATEGORIES}

    def has_hours(v):
        return pct(sum(1 for p in v if p["opening_hours"]), len(v))

    def real(v):
        return pct(sum(1 for p in v if p["description_source"] in ("osm", "wikipedia")), len(v))

    return {
        "total": total,
        "count_per_category": {c: len(v) for c, v in per.items()},
        "pct_opening_hours_total": has_hours(pois),
        "pct_opening_hours_per_category": {c: has_hours(v) for c, v in per.items()},
        "pct_real_description": real(pois),
        "pct_real_description_by_source": {
            s: pct(sum(1 for p in pois if p["description_source"] == s), total) for s in ("osm", "wikipedia")
        },
        "pct_derived_description": pct(sum(1 for p in pois if p["description_source"] == "derived"), total),
        "pct_real_description_per_category": {c: real(v) for c, v in per.items()},
        "pct_website": pct(sum(1 for p in pois if p["website"]), total),
        "pct_phone": pct(sum(1 for p in pois if p["phone"]), total),
    }


def md_table(headers: list[str], rows: list[list]) -> str:
    out = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    out += ["| " + " | ".join(str(c) for c in r) + " |" for r in rows]
    return "\n".join(out)


def spread(rows: list[dict], n: int, key: str = "reason") -> list[dict]:
    """n rows, round-robin over the `key` groups (rows keep their order inside a group)."""
    groups: dict[str, list[dict]] = {}
    for r in rows:
        groups.setdefault(r[key], []).append(r)
    out: list[dict] = []
    while len(out) < n and any(groups.values()):
        for g in groups.values():
            if g and len(out) < n:
                out.append(g.pop(0))
    return out


def cell(s: object) -> str:
    return str(s).replace("|", "\\|")


def delta_cleanup_sections(ov: dict) -> str:
    chain, non_poi = ov["chain_duplicates"], ov["non_poi_demoted"]
    chain_rows = [[cell(c["osm_name"]), f"{c['osm_category']} `{c['osm_id']}`", cell(c["overture_name"]),
                   f"{c['overture_category']} `{c['overture_id'][:8]}`", c["distance_m"], c["by"],
                   "dropped (OSM already has a counterpart)" if c["absorbed"] else "merged into OSM record"]
                  for c in chain["examples"]]
    non_poi_rows = [[cell(d["name"]), d["primary"], d["from"], d["reason"], d["confidence"]]
                    for d in non_poi["examples"]]
    return f"""## Overture <-> OSM chain duplicates

An Overture-only record is the same venue as an OSM record when the normalised name key (casefold, Cyrillic incl.
kk -> Latin, punctuation dropped; same rules as `name_key` in `app/walks/retrieve.py`) is equal, or brand /
brand:wikidata are equal, within {CHAIN_M:.0f} m; for identical names the radius is {CHAIN_SAME_NAME_M:.0f} m. Category
mismatches (cafe / fast_food / restaurant ...) do not block the match; type-only names ("Кафе") never match.

- merged into the OSM record (phone / website / brand taken over): **{chain['merged_into_osm']}**
- dropped because that OSM record already has its Overture counterpart: **{chain['absorbed_by_already_matched_osm']}**
- by signal: {', '.join(f'{k} {v}' for k, v in chain['by'].items()) or '-'}

Examples (the {len(chain['examples'])} farthest):

{md_table(['OSM', 'OSM category / id', 'Overture', 'Overture category / id', 'm', 'by', 'result'], chain_rows)}

## Overture records demoted to `other` (not a walkable POI)

Residential complexes, offices / business centres, real estate and construction, schools, clinics, government
offices, banks / ATMs and car services by name or taxonomy; Overture `historic_site` records whose name says
nothing about heritage (in Astana that label is mostly put on residential complexes and addresses). Demoted records
stay in `overture_places.json` and are never added to `poi.enriched.json`.

{md_table(['reason', 'records passing the cut-off', 'all usable records'],
          [[k, v, non_poi['by_reason_all_usable'].get(k, 0)] for k, v in non_poi['by_reason_passing_cutoff'].items()])}

Demoted from category (passing the cut-off): {', '.join(f'{k} {v}' for k, v in non_poi['demoted_from_category_passing_cutoff'].items()) or '-'}.

Examples ({len(non_poi['examples'])}, round-robin over reasons, most confident first):

{md_table(['name', 'Overture taxonomy', 'was', 'reason', 'confidence'], non_poi_rows)}

"""


def coord_verdict(ov: dict, geo: dict) -> dict | None:
    """Coordinate-quality verdict of an Overture-only record (collect/coord_quality.py): drop | flag | None."""
    if ev := geo["collapsed_point"].get(ov["id"]):
        return {"action": "drop", **ev}
    chk = geo["address_check"].get(ov["id"])
    if chk and chk["verdict"] == "address_far":
        return {"action": "drop", "reason": "address_far", "street_ref_distance_m": chk["street_ref_distance_m"],
                "geocoder_distance_m": chk["distance_m"]}
    if chk and chk["verdict"] == "unverified":
        return {"action": "flag", "reason": "address_far_unverified",
                "street_ref_distance_m": chk["street_ref_distance_m"]}
    return None


def coord_row(ov: dict, verdict: dict) -> dict:
    addr = ov_address(ov)
    return {"id": ov["id"], "name": ov["name"], "category": ov["category"], "confidence": ov["confidence"],
            "address": addr, **verdict}


def coord_summary(geo: dict, rows: list[dict]) -> dict:
    dropped = [r for r in rows if r["action"] == "drop"]
    return {
        "overture_records_on_collapsed_points": geo["meta"]["counts"]["collapsed_point_records"],
        "collapsed_point_clusters": geo["meta"]["counts"]["collapsed_point_clusters"],
        "params": geo["meta"]["params"],
        "address_far_nominees_geocoded": geo["meta"]["counts"]["address_far_nominees"],
        "geocoder_verdicts": geo["meta"]["counts"]["verdicts"],
        "overture_only_dropped": len(dropped),
        "dropped_by_reason": dict(Counter(r["reason"] for r in dropped)),
        "overture_only_flagged_kept": sum(1 for r in rows if r["action"] == "flag"),
        "examples_dropped": [{k: r.get(k) for k in ("name", "category", "confidence", "address", "reason",
                                                    "records_on_point", "street_ref_distance_m",
                                                    "geocoder_distance_m")} for r in dropped[:12]],
    }


def merge_wiki_places(records: list[dict], wp: dict) -> tuple[wiki_merge.WikiMergeLog, list[dict]]:
    """Wikidata / Wikipedia places -> (log, new records); matching existing records get the Wikidata item."""
    meta, log, new = wp["meta"], wiki_merge.WikiMergeLog(), []
    wmeta = wiki_merge.wiki_meta(meta)
    have = {r["wikidata_id"] for r in records if "wikidata_id" in r}
    grid = Grid(records)
    for pl in wp["places"]:
        if pl["qid"] in have:
            log.already_known += 1
            continue
        row = {"qid": pl["qid"], "name": pl["name"], "category": pl["category"], "coord_source": pl["coord_source"]}
        if dup := wiki_merge.best_duplicate(pl, grid, osm_names):
            rec, dist, score, same = dup
            row |= {"record": rec["id"], "record_name": rec["name"], "distance_m": round(dist), "score": round(score)}
            if wiki_merge.strong(dist, score, same) and "wikidata_id" not in rec:
                conf = round(min(0.99, score / 100 * (1 - 0.25 * dist / wiki_merge.DUP_M)), 2)
                apply_wiki(rec, {"method": "wikipedia_list", "confidence": conf}, wiki_merge.entity_of(pl), wmeta)
                have.add(pl["qid"])
                log.enriched_existing.append(row)
            else:
                log.duplicate_not_enriched.append(row)
            continue
        rec = wiki_merge.new_record(pl, meta, CATEGORY_RU, fs)
        apply_wiki(rec, {"method": "source", "confidence": 1.0}, wiki_merge.entity_of(pl), wmeta)
        new.append(rec)
        have.add(pl["qid"])
        grid.cells.setdefault(grid.key(rec["lat"], rec["lon"]), []).append(rec)
        log.added.append(row)
    return log, new


def overture_rule_new(rec: dict) -> bool:
    """Overture-only record that the previous mapping dropped as `other` (new taxonomy value or name rule)."""
    primary = next((t.split("=", 1)[1] for t in rec["tags"] if t.startswith("overture_category=")), None)
    return any(t.startswith("category_rule=") for t in rec["tags"]) or primary in NEWLY_MAPPED


def fmt_counts(counts: dict) -> str:
    return ", ".join(f"{k} {v}" for k, v in counts.items()) or "-"


def sample_row(r: dict) -> dict:
    fsrc = r["field_sources"].get("lat") or {}
    return {"id": r["id"], "name": r["name"], "category": r["category"], "source": r["source"],
            "sources": r["sources"], "lat": r["lat"], "lon": r["lon"],
            "coord_source": fsrc.get("source"), "confidence": r.get("overture_confidence"),
            "basis": next((t for t in r["tags"] if t.startswith(("category_rule=", "overture_category=",
                                                                 "leisure=", "amenity=", "wikidata_class="))), None),
            "description": r.get("description_auto")}


def delta_relevance_sections(info: dict) -> str:
    rel, ov, wp, cq = info["relevance"], info["overture"], info["wiki_places"], info["coord_quality"]
    v1, now = rel["v1"], rel["now"]

    def row(label: str, key: str, fmt=str) -> list:
        a, b = v1[key], now[key]
        return [label, fmt(a), fmt(b), fmt(round(b - a, 1)) if isinstance(a, float) else b - a]

    cats = [[c, v1["per_category"][c], now["per_category"][c], now["per_category"][c] - v1["per_category"][c]]
            for c in CATEGORIES if c != "other"]
    key_rows = [
        row("records, total", "total"),
        ["museum_gallery", v1["per_category"]["museum_gallery"], now["per_category"]["museum_gallery"],
         now["per_category"]["museum_gallery"] - v1["per_category"]["museum_gallery"]],
        ["entertainment", v1["per_category"]["entertainment"], now["per_category"]["entertainment"],
         now["per_category"]["entertainment"] - v1["per_category"]["entertainment"]],
        row("kids, indoor (entertainment / museum / theatre with a kids signal)", "kids_indoor"),
        row("kids, outdoor playgrounds (`kids_playground`)", "kids_playground_outdoor"),
        ["viewpoint", v1["per_category"]["viewpoint"], now["per_category"]["viewpoint"],
         now["per_category"]["viewpoint"] - v1["per_category"]["viewpoint"]],
        row("indoor places (app INDOOR_CATEGORIES)", "indoor_places"),
        row("records with opening_hours", "with_opening_hours"),
        row("% with opening_hours", "pct_opening_hours"),
        row("% museum_gallery with opening_hours", "pct_opening_hours_museum_gallery"),
        row("records with a real description (osm / wikipedia)", "with_real_description"),
        row("% real description", "pct_real_description"),
    ]
    sample = [[r["id"], cell(r["name"]), r["category"], f"{r['lat']:.5f}, {r['lon']:.5f}",
               f"{'+'.join(r['sources'])}; coords: {r['coord_source']}", r["basis"] or "-"] for r in rel["sample_new"]]
    dropped = [[cell(r["name"]), r["category"], r["confidence"], cell(r["address"] or "-"), r["reason"],
                r.get("records_on_point") or r.get("geocoder_distance_m") or r.get("street_ref_distance_m")]
               for r in cq["examples_dropped"]]
    return f"""## Relevance expansion (2026-10-17): before = enriched v1 of 2026-10-16, after = this build

v1 = `data/poi_enriched_v1_stats.json` (frozen; OSM + Overture + Wikipedia, 2178 records). Ids of existing records are
kept except **{rel['dropped_v1_ids']}**: {rel['dropped_v1_by_coordinates']} Overture-only records were dropped for suspect
coordinates (below) and {rel['dropped_v1_replaced']} Overture-only records are now the OSM record of the same place
({', '.join(rel['dropped_v1_replaced_names'])}). New records: **{rel['new_total']}**
({', '.join(f'{k} {v}' for k, v in rel['new_by_source'].items())}).

{md_table(['metric', 'v1', 'now', 'delta'], key_rows)}

Per category:

{md_table(['category', 'v1', 'now', 'delta'], cats)}

What the new records come from:

- OSM, second Overpass request (tags the first selector set missed; `collect/overpass_poi.py` `EXTRA_SELECTORS`):
  `leisure=indoor_play`, `playground=indoor`, `amenity=planetarium|events_venue|fountain(named)|community_centre(palaces)`,
  `club=sport`, `shop=books` with a cafe in the name, `man_made=tower`+`tower:type=observation`. Live count inside the
  Astana area: `tourism=viewpoint` 1 (unnamed, already in v1), observation towers 0, planetariums 0, trampoline parks 0,
  `leisure=indoor_play` 1.
- Overture, remapped taxonomy + name rules for generic buckets: **{ov['new_taxonomy_or_name_rule_records']}** Overture-only records
  that v1 left as `other` (name rules: {', '.join(f'{k} {v}' for k, v in ov['by_name_rule'].items()) or '-'}).
  The confidence cut-off {ov['cutoff']} is unchanged.
- Wikidata / Wikipedia (`collect/wiki_places.py`): {wp['candidates']} candidates (Wikidata P131* + ru/en Wikipedia
  geosearch + categories), {wp['classified']} of a mapped class, {wp['places']} located inside the Astana districts
  (Nominatim lookups {wp['nominatim_lookups']}, accepted {wp['nominatim_accepted']}); {wp['already_in_dataset']} already
  in the dataset, {wp['enriched_existing_records']} existing records got a Wikidata item + Wikipedia extract,
  {wp['duplicates_not_enriched']} were duplicates of an existing record (not enriched), **{wp['new_records']} new**
  ({', '.join(f'{k} {v}' for k, v in wp['new_by_category'].items()) or '-'}).

### Opening hours: what was checked (2026-10-17)

- Overture release `{ov['release']}`: the places schema has no hours field (`DESCRIBE` of the parquet: id, geometry,
  confidence, websites, emails, socials, phones, brand, addresses, names, sources, operating_status, basic_category,
  taxonomy, version, bbox); `operating_status` is set on 1 of {ov['total']} Astana records. 0 hours gained.
- Wikidata: 0 items located in Astana (P131*) have P3025 (open days) or P8626 (opening time) — SPARQL counts. 0 hours gained.
- Foursquare OS Places: the open schema has no hours column (Foursquare documentation; hours are a premium attribute) and the
  dataset is gated — not used.
- visitastana.kz: its place pages carry injected spam JSON-LD (casino/slot advertising inside `application/ld+json`) and the
  site has no terms page that allows storing its data — not used, nothing stored.
- OSM `opening_hours` stays the only source: v1 {v1['pct_opening_hours']}% -> now {now['pct_opening_hours']}%.
  The data-quality map (`city_ui`) and the «часы неизвестны» label in the app are the honest answer to this gap.

### Viewpoints

OSM has exactly one `tourism=viewpoint` in Astana (unnamed) and no observation tower; Overture has no `scenic_viewpoint` /
`observation_deck` / `lookout` record in the bbox; Wikidata knows one observation tower (Baiterek, already a landmark
record). The category stays at {now['per_category']['viewpoint']}: a viewpoint is not invented from a tower or a high building.

### Overture coordinate quality (Overture-only records; OSM records are never touched)

- {cq['overture_records_on_collapsed_points']} Overture records ({cq['collapsed_point_clusters']} points) share one point (5 decimals) with
  >= {cq['params']['cluster_min'] - 1} other records and their addresses disagree (no street, or no address above
  {cq['params']['share_max']:.0%}): placeholder / centroid coordinates. {cq['address_far_nominees_geocoded']} records passing the
  cut-off have a street >{cq['params']['far_m'] / 1000:.0f} km from every other record of that street and were geocoded with Nominatim: {fmt_counts(cq['geocoder_verdicts'])}.
- Overture-only records dropped for it: **{cq['overture_only_dropped']}** ({fmt_counts(cq['dropped_by_reason'])}); kept but flagged
  `coord_quality.status = suspect_unverified`: {cq['overture_only_flagged_kept']}.

{md_table(['name', 'category', 'confidence', 'address', 'reason', 'records on point / geocoder m / street m'], dropped)}

### 10 new records

{md_table(['id', 'name', 'category', 'lat, lon', 'sources', 'basis'], sample)}

"""


def write_delta(path: Path, before: dict, after: dict, info: dict) -> None:
    cats = [[c, before["count_per_category"].get(c, 0), after["count_per_category"][c],
             after["count_per_category"][c] - before["count_per_category"].get(c, 0)] for c in CATEGORIES]
    cats.append(["**total**", before["total"], after["total"], after["total"] - before["total"]])
    ov, ws = info["overture"], info["wiki"]
    text = f"""# Coverage delta: OSM-only (`poi.json`) vs enriched (`poi.enriched.json`)

Overture release `{ov['release']}`, bbox 50.98–51.25 / 71.25–71.60; Wikidata snapshot {ws['snapshot_date']}.

{delta_relevance_sections(info)}

## Totals

{md_table(['metric', 'value'], [
    ['OSM POI in the re-collected snapshot (`poi.osm.json`)', info['osm_total']],
    ['Overture places in bbox (all)', ov['total']],
    [f"Overture passing confidence >= {ov['cutoff']}", ov['passing_cutoff']],
    ['  ...of them dropped as closed / nameless', ov['dropped_unusable']],
    [f"Overture dropped by confidence < {ov['cutoff']}", ov['dropped_by_cutoff']],
    ['OSM ∩ Overture matched (1:1)', info['osm_overture_matched']],
    ['Overture-only, mapped category (added to `poi.enriched.json`)', ov['overture_only_added']],
    ["Overture-only, category `other` (not added; stays in `overture_places.json`)", ov['overture_only_other_not_added']],
    ['Wikidata matched POI', ws['matched_pois']],
])}

## Per category (before = frozen `poi.json`, after = `poi.enriched.json`)

{md_table(['category', 'before', 'after', 'delta'], cats)}

## Attribute coverage

{md_table(['metric', 'before', 'after'], [
    ['% with opening_hours (all records)', before['pct_opening_hours_total'], after['pct_opening_hours_total']],
    ['% with opening_hours (OSM-origin records only)', before['pct_opening_hours_total'], info['pct_hours_osm_origin']],
    ['% real description (osm + wikipedia)', before['pct_real_description'], after['pct_real_description']],
    ['  of which osm', before['pct_real_description'], after['pct_real_description_by_source']['osm']],
    ['  of which wikipedia', 0.0, after['pct_real_description_by_source']['wikipedia']],
    ['% derived description', before['pct_derived_description'], after['pct_derived_description']],
    ['% with website', before['pct_website'], after['pct_website']],
    ['% with phone', info['before_pct_phone'], after['pct_phone']],
])}

Opening hours: none of the added sources carries `opening_hours` (Overture adds *objects*, not hours; Wikidata has no Astana
item with P3025 / P8626; Foursquare OS Places has no hours column), so the share over all records moves only with the
OSM-origin extras: {before['pct_opening_hours_total']}% in `poi.json`, {after['pct_opening_hours_total']}% over all
records now, {info['pct_hours_osm_origin']}% among OSM-origin records. Every Overture-only and Wikidata-only record
enters with `hours_state: "unknown"`.

## Overture confidence cut-off

{ov['cutoff_rationale']}

Overture records in our categories, share with an OSM counterpart by confidence bucket:

{md_table(['confidence', 'records', 'matched to OSM', 'match rate %'],
          [[k, v['records'], v['matched_osm'], v['match_rate_pct']] for k, v in ov['match_rate_by_confidence'].items()])}

## Wikidata/Wikipedia matches by method

{md_table(['method', 'POI'], [[k, v] for k, v in ws['matches_by_method'].items()])}

{delta_cleanup_sections(ov)}
"""
    path.write_text(text, encoding="utf-8", newline="\n")


# ---- main -----------------------------------------------------------------------------------------


def merge(data_dir: Path, cutoff: float) -> dict:
    osm = json.loads((data_dir / "poi.osm.json").read_text(encoding="utf-8"))
    ov_file = json.loads((data_dir / "overture_places.json").read_text(encoding="utf-8"))
    wiki = json.loads((data_dir / "wiki_enrichment.json").read_text(encoding="utf-8"))
    wp = json.loads((data_dir / "wiki_places.json").read_text(encoding="utf-8"))
    geo = json.loads((data_dir / "overture_geocheck.json").read_text(encoding="utf-8"))
    before = json.loads((data_dir / "poi_stats.json").read_text(encoding="utf-8"))
    ov_meta, ov_all = ov_file["meta"], ov_file["places"]

    usable, demoted = demote_non_poi([o for o in ov_all if o["name"] and o["operating_status"] not in CLOSED_STATUSES])
    passing = [o for o in usable if overture_usable(o, cutoff)]
    matches = resolve(osm, passing)

    records = []
    for p in osm:
        rec = build_osm_record(p)
        if p["id"] in matches:
            ov, dist, score = matches[p["id"]]
            apply_overture(rec, ov, dist, score, ov_meta)
        m = wiki["matches"].get(p["id"])
        if m:
            apply_wiki(rec, m, wiki["entities"][m["qid"]], wiki)
        records.append(rec)

    matched_ids = {ov["id"] for ov, _, _ in matches.values()}
    leftovers = [o for o in passing if o["id"] not in matched_ids]
    osm_grid = Grid(records)
    added, other_skipped, chain_log, coord_log = [], 0, [], []
    for ov in sorted(leftovers, key=lambda o: (-o["confidence"], o["id"])):
        if ov["category"] == "other":
            other_skipped += 1
            continue
        if hit := chain_duplicate(ov, osm_grid):
            rec, dist, how = hit
            absorbed = rec["overture_id"] is not None  # that OSM record already has its Overture counterpart
            if not absorbed:
                apply_overture(rec, ov, dist, name_score(osm_names(rec), overture_names(ov)), ov_meta)
                rec["overture_match"]["method"] = f"chain:{how}"
            chain_log.append({"osm_id": rec["id"], "osm_name": rec["name"], "osm_category": rec["category"],
                              "overture_id": ov["id"], "overture_name": ov["name"],
                              "overture_category": ov["category"], "distance_m": round(dist), "by": how,
                              "absorbed": absorbed})
            continue
        key = name_key(ov["name"])
        if any(name_key(a["name"]) == key
               and haversine_m(a["lat"], a["lon"], ov["lat"], ov["lon"]) <= OVERTURE_DEDUP_M for a in added):
            continue
        verdict = coord_verdict(ov, geo)
        if verdict and verdict["action"] == "drop":
            coord_log.append(coord_row(ov, verdict))
            continue
        rec = build_overture_record(ov, ov_meta)
        if verdict:  # address far from its street and the geocoder found nothing: keep, flagged
            rec["coord_quality"] = {"status": "suspect_unverified", "reason": verdict["reason"],
                                    "street_ref_distance_m": verdict["street_ref_distance_m"]}
            coord_log.append(coord_row(ov, verdict))
        added.append(rec)
    records.extend(added)
    wiki_log, wiki_new = merge_wiki_places(records, wp)
    records.extend(wiki_new)
    records.sort(key=lambda r: r["id"])

    after = stats_for(records)
    osm_origin = [r for r in records if r["source"] == "osm"]
    by_method: dict[str, int] = {}
    for r in records:
        if "wiki_match" in r:
            by_method[r["wiki_match"]["method"]] = by_method.get(r["wiki_match"]["method"], 0) + 1
    rationale = (
        f"Cut-off **{cutoff}**. The bbox holds {len(ov_all)} Overture places, 94% from the Meta dataset, with a wide "
        "confidence spread (0.2-0.9, see `overture_places.json` -> meta). Evidence for 0.7 in our categories: below "
        "0.7 every record is single-source Meta, websites are present in at most 37% and only 0-8% of records have "
        "an OSM counterpart (same name within 150 m) with no trend; from 0.7 records from other datasets "
        "(Microsoft, Foursquare, AllThePlaces) appear, the "
        "website share rises to 50-74% and the OSM match rate climbs steeply (see table). The table below "
        "is the independent check. Below the cut-off a record is dropped entirely (not merged into an OSM POI, not "
        "added as Overture-only); records must also have a name and not be marked closed. A false positive "
        "(a closed cafe on a walking route) costs more than a missed place, hence the strict side."
    )
    passing_ids = {o["id"] for o in passing}
    demoted_passing = [d for d in demoted if d["id"] in passing_ids]
    non_poi = {
        "by_reason_passing_cutoff": dict(Counter(d["reason"] for d in demoted_passing).most_common()),
        "by_reason_all_usable": dict(Counter(d["reason"] for d in demoted).most_common()),
        "demoted_from_category_passing_cutoff": dict(Counter(d["from"] for d in demoted_passing).most_common()),
        "examples": spread(sorted(demoted_passing, key=lambda d: (-d["confidence"], d["id"])), NON_POI_EXAMPLES),
    }
    chain = {
        "merged_into_osm": sum(1 for c in chain_log if not c["absorbed"]),
        "absorbed_by_already_matched_osm": sum(1 for c in chain_log if c["absorbed"]),
        "by": dict(Counter(c["by"] for c in chain_log).most_common()),
        "examples": sorted(chain_log, key=lambda c: (-c["distance_m"], c["osm_id"]))[:EXAMPLES],
    }
    v1 = metrics.load_v1(data_dir / "poi_enriched_v1_stats.json")
    now = metrics.summarize(records)
    v1_gone = set(v1["ids"]) - {r["id"] for r in records}
    v1_names = v1["names"]
    info = {
        "osm_total": len(osm),
        "osm_overture_matched": len(matches),
        "pct_hours_osm_origin": pct(sum(1 for r in osm_origin if r["opening_hours"]), len(osm_origin)),
        "before_pct_phone": pct(sum(1 for r in json.loads((data_dir / "poi.json").read_text(encoding="utf-8"))
                                    if r["phone"]), before["total"]),
        "overture": {
            "release": ov_meta["release"], "total": len(ov_all), "cutoff": cutoff,
            "passing_cutoff": len(passing),
            "dropped_unusable": sum(1 for o in ov_all if (o["confidence"] or 0) >= cutoff) - len(passing),
            "dropped_by_cutoff": sum(1 for o in ov_all if (o["confidence"] or 0) < cutoff),
            "overture_only_added": len(added), "overture_only_other_not_added": other_skipped,
            "non_poi_demoted": non_poi, "chain_duplicates": chain,
            "match_rate_by_confidence": match_rate_by_confidence(osm, usable),
            "cutoff_rationale": rationale,
            "new_taxonomy_or_name_rule_records": sum(1 for r in added if overture_rule_new(r)),
            "by_name_rule": dict(Counter(t.split("=", 1)[1] for r in added for t in r["tags"]
                                         if t.startswith("category_rule="))),
        },
        "wiki": {"snapshot_date": wiki["snapshot_date"], "matched_pois": sum(by_method.values()),
                 "matches_by_method": by_method},
        "wiki_places": {
            "snapshot_date": wp["meta"]["snapshot_date"], **{k: wp["meta"]["counts"][k] for k in (
                "candidates", "classified", "places", "per_category", "nominatim_lookups", "nominatim_accepted",
                "dropped")},
            "already_in_dataset": wiki_log.already_known,
            "enriched_existing_records": len(wiki_log.enriched_existing),
            "duplicates_not_enriched": len(wiki_log.duplicate_not_enriched),
            "new_records": len(wiki_new),
            "new_by_category": dict(Counter(r["category"] for r in wiki_new)),
            "enriched_rows": wiki_log.enriched_existing,
            "duplicate_rows": wiki_log.duplicate_not_enriched,
        },
        "coord_quality": coord_summary(geo, coord_log),
        "relevance": {
            "v1": {k: v for k, v in v1.items() if k not in ("ids", "names")},
            "now": {k: v for k, v in now.items() if k not in ("ids", "names")},
            "sample_new": [sample_row(r) for r in metrics.sample_new(records, set(v1["ids"]))],
            "new_total": sum(1 for r in records if r["id"] not in set(v1["ids"])),
            "new_by_source": dict(Counter(r["source"] for r in records if r["id"] not in set(v1["ids"]))),
            "dropped_v1_ids": len(v1_gone),
            "dropped_v1_by_coordinates": len(v1_gone & {f"overture/{r['id']}" for r in coord_log
                                                       if r["action"] == "drop"}),
            "dropped_v1_replaced": len(v1_gone) - len(v1_gone & {f"overture/{r['id']}" for r in coord_log
                                                                if r["action"] == "drop"}),
            "dropped_v1_replaced_names": sorted(v1_names[i] for i in v1_gone - {f"overture/{r['id']}"
                                                                                  for r in coord_log
                                                                                  if r["action"] == "drop"}),
        },
    }
    stats = {
        "before": {k: before[k] for k in ("total", "count_per_category", "pct_opening_hours_total",
                                          "pct_real_description", "pct_derived_description", "pct_website")},
        "after": after,
        "per_source_counts": {
            "osm_only": sum(1 for r in records if r["sources"] == ["osm"]),
            "overture_only": sum(1 for r in records if r["sources"] == ["overture"]),
            "osm_and_overture": sum(1 for r in records if r["sources"] == ["osm", "overture"]),
            "wikidata_only": sum(1 for r in records if r["sources"] == ["wikidata"]),
            "with_wikidata": sum(1 for r in records if "wikidata_id" in r),
            "with_wikipedia_article": sum(1 for r in records if "wikipedia" in r),
            "with_popularity_pageviews": sum(1 for r in records if "popularity_pageviews" in r),
        },
        "wikidata_matches_by_method": by_method,
        "osm_overture_matched": len(matches),
        "overture": {k: v for k, v in info["overture"].items() if k not in ("cutoff_rationale",)},
        "description_source_counts": {
            s: sum(1 for r in records if r["description_source"] == s) for s in ("osm", "wikipedia", "derived")
        },
        "release": ov_meta["release"],
        "wiki_places": info["wiki_places"],
        "coord_quality": info["coord_quality"],
        "relevance": info["relevance"],
    }
    write_json(data_dir / "poi.enriched.json", records)
    write_json(data_dir / "poi_enriched_stats.json", stats)
    write_delta(data_dir / "coverage_delta.md", before, after, info)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(DATA))
    parser.add_argument("--cutoff", type=float, default=CONFIDENCE_CUTOFF)
    args = parser.parse_args(argv)
    stats = merge(Path(args.data), args.cutoff)
    print(json.dumps({k: stats[k] for k in ("per_source_counts", "wikidata_matches_by_method",
                                            "description_source_counts", "osm_overture_matched")},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
