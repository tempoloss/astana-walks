"""Merge the records of one venue: the dataset keeps one card per museum, theatre, landmark, park and mall.

OSM, Overture and the Wikidata places list the same venue under different names («Национальный музей Республики
Казахстан», «Historical Museum Astana», «Kazakistan Tarihi Müzesi @astana»), so the stages before this one leave a
sight twice or five times, with the hours on one record and the price on another. This stage runs after `gov` (every
fact is attached by then) and before `wikivoyage`, and merges records of the **same category** (museum_gallery,
culture_theatre_cinema, attraction_landmark, park_garden, mall) that are one venue by one of these rules:

* `wikidata`  - the same Wikidata id (<= 500 m, any category).
* `name`      - the names agree in ru / kk / en / transliteration (`collect.venue_names.same_name`: every identity word of
                the shorter name is in the longer one, the numbers are equal, no word on either side is missing - «Зенит»
                is not «Союз», «Евразия-2» is not «Евразия-3») within 120 m (parks 300 m: their point is a centroid);
                records that print the same street address and house number may be 300 m apart.
* `colocated` - <= 20 m apart and one identity word in common.
* `worship`   - mosques, synagogues, churches and cathedrals are one building: two records of the same faith <= 30 m
                apart are one place, whatever language their names are in.
* `kind_pin`  - a bare Overture pin whose name only says what kind of venue it is («Historical Museum Astana»: no
                identity word, no contact, no hours, no description) <= 250 m from a record of the same category whose
                name speaks of the same kind («National Museum ...»): a visitor's pin on the museum.

Never merged: records of different Wikidata ids, chain branches (the same `brand`), a name that venues in three or
more separate places of the category carry (a series, not a venue), venues of different categories (a cinema inside a
mall), generated names («Парк / сквер»). A cluster stays within 350 m, so a series of same-named parks a kilometre
apart is not collapsed either.

The richest record survives (Wikidata id, official/register facts, hours, price, contacts, description, kk/en names);
it takes every fact the others have and it lacks, with the field's source; the others' ids stay in `aliases` and each
absorbed record is described in `merged_from` (rule, distance, sources and the values that were not taken), so a join
log, a pinned demo key or an old link to an absorbed id still resolves (`resolve_alias`). One run per build: a dataset
that already carries `aliases` is refused.

Usage (repo root): uv run python -m collect.dedupe [--poi data/poi.enriched.json] [--out ...]
"""

from __future__ import annotations

import argparse
import copy
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collect import venue_names as vn
from collect.merge import stats_for
from collect.overpass_poi import haversine_m
from collect.sites.hours import same_schedule

ROOT = Path(__file__).resolve().parents[1]
POI_PATH = ROOT / "data" / "poi.enriched.json"
STATS_PATH = ROOT / "data" / "poi_enriched_stats.json"
DELTA_PATH = ROOT / "data" / "coverage_delta.md"
LOG_PATH = ROOT / "data" / "duplicates_merged.json"
DELTA_HEADING = "## Same-venue duplicates (one card per venue)"

FAMILIES = frozenset({"museum_gallery", "culture_theatre_cinema", "attraction_landmark", "park_garden", "mall"})
MEASURED_ONLY = ("sport", "entertainment", "coworking_library", "transit_station")  # counted, never merged

WIKIDATA_M = 500.0
NAME_M = 120.0
PARK_NAME_M = 300.0
ADDRESS_M = 300.0
COLOCATED_M = 20.0
WORSHIP_M = 30.0
PIN_M = 250.0
DIAMETER_M = 350.0
SERIES_MIN = 3  # a name that venues in this many separate places carry names a series, not a venue

# `sources` labels that a stage after the base datasets adds (not part of the record's origin)
FACT_SOURCES = frozenset({"official_site", "museum_register", "state_registry", "wikivoyage"})
VERIFIED_SOURCES = ("museum_register", "official_site", "state_registry")
INFO_FIELDS = ("opening_hours", "website", "phone", "price_text")
_SKIP = frozenset({
    "id", "name", "names", "labels", "lat", "lon", "category", "source", "collected_at", "sources", "field_sources",
    "tags", "name_generated", "description_auto", "hours_state", "aliases", "merged_from", "alt_names",
    "opening_hours_official", "hours_conflict", "hours_conflict_prefers", "address", "overture_id",
    "overture_match", "overture_confidence", "official_site_match", "description", "description_source",
    "wikipedia", "price_text", "opening_hours", "hours_unqualified", "hours_unqualified_flags", "wiki_match",
    "wikidata_id", "description_official",
})


# ---------------------------------------------------------------- records
def names_of(p: dict) -> list[str]:
    """Every real name of the record (nothing for a generated one: «Парк / сквер» names no venue)."""
    if p.get("name_generated"):
        return []
    out: list[str] = []
    for n in (p["name"], *(p.get("names") or {}).values(), *(p.get("labels") or {}).values(),
              *(p.get("alt_names") or [])):
        if n and n not in out:
            out.append(n)
    return out


def empty(v: object) -> bool:
    return v is None or v == "" or v == [] or v == {}


def specific_address(address: str | None) -> bool:
    return bool(address) and bool(re.search(r"\d", address))


SOURCE_ORDER = ("osm", "overture", "wikidata", "official_site", "museum_register", "state_registry", "wikivoyage")


def bucket_of(sources: list[str]) -> str:
    """The `per_source_counts` bucket of a record: which collecting sources it carries, ignoring the labels the fact
    stages add and the order they are written in. On the datasets the stages produce this reproduces their counts."""
    own = {x for x in sources if x not in FACT_SOURCES}
    if "osm" in own and "overture" in own:
        return "osm_and_overture"
    if own == {"osm"}:
        return "osm_only"
    if own == {"overture"}:
        return "overture_only"
    if own == {"wikidata"}:
        return "wikidata_only"
    if not own and "state_registry" in sources:
        return "state_registry_only"
    if not own:
        return "official_site_only"
    return "other"


def is_bare(p: dict) -> bool:
    """An Overture pin and nothing else: no site, phone, hours, price, description, Wikidata id, other source."""
    return (p["sources"] == ["overture"] and not p.get("wikidata_id")
            and all(empty(p.get(k)) for k in (*INFO_FIELDS, "description")))


def richness(p: dict) -> tuple:
    verified = sum(1 for s in VERIFIED_SOURCES if s in p["sources"])
    info = sum(1 for k in INFO_FIELDS if not empty(p.get(k)))
    info += bool(specific_address(p.get("address"))) + bool(p.get("description_source") in ("osm", "wikipedia"))
    info += bool(p.get("wikipedia")) + min(len(p.get("names") or {}), 3)
    return (verified, info + bool(p.get("wikidata_id")), len(p["sources"]), p["source"] == "osm")


class Context:
    """Per-run caches: parsed names and where each name key of a category occurs."""

    def __init__(self, pois: list[dict]):
        self.parts: dict[str, list[vn.NameParts]] = {}
        self.places: defaultdict[tuple, list[tuple[float, float]]] = defaultdict(list)
        for p in pois:
            parsed = [vn.parse(n) for n in names_of(p)]
            self.parts[p["id"]] = parsed
            for key in {(p["category"], q.words, q.nums) for q in parsed if q.words}:
                self.places[key].append((p["lat"], p["lon"]))

    def is_series(self, p: dict, other: dict) -> bool:
        """True when the name that makes the pair agree is also the name of venues elsewhere in the city: a series
        (chain branches, «Памятник Абаю»), not one venue. Records within one cluster's span of `p` do not count: the
        duplicates of a venue are the very thing this stage merges."""
        for x in self.parts[p["id"]]:
            for y in self.parts[other["id"]]:
                if x.words and vn.same_name(x, y):
                    far = sum(1 for lat, lon in self.places[(p["category"], x.words, x.nums)]
                              if haversine_m(p["lat"], p["lon"], lat, lon) > DIAMETER_M)
                    if far >= SERIES_MIN - 1:
                        return True
        return False

    def same_name(self, a: dict, b: dict) -> bool:
        """The names agree; so do two names that are only a kind and descriptors and say the same («Национальный
        музей Республики Казахстан» / «National Museum of the Republic of Kazakhstan»)."""
        return any(vn.same_name(x, y) or (x.descriptors and vn.kind_only_equal(x, y))
                   for x in self.parts[a["id"]] for y in self.parts[b["id"]])

    def shared_identity(self, a: dict, b: dict) -> bool:
        return any(vn.word_equal(u, w) for x in self.parts[a["id"]] for y in self.parts[b["id"]]
                   for u in x.words for w in y.words)

    def kinds(self, p: dict) -> frozenset[str]:
        return frozenset(k for x in self.parts[p["id"]] for k in x.kinds)

    def worship(self, p: dict) -> frozenset[str]:
        return frozenset(vn.WORSHIP[k] for k in self.kinds(p) if k in vn.WORSHIP)


def same_brand(a: dict, b: dict) -> bool:
    return any(a.get(k) and a.get(k) == b.get(k) for k in ("brand_wikidata", "brand"))


def pair_rule(a: dict, b: dict, d: float, ctx: Context, families: frozenset[str] = FAMILIES) -> str | None:
    """The rule under which `a` and `b` (`d` metres apart) are one venue, or None."""
    wa, wb = a.get("wikidata_id"), b.get("wikidata_id")
    if wa and wb:
        return "wikidata" if wa == wb and d <= WIKIDATA_M else None
    cat = a["category"]
    if cat != b["category"] or cat not in families or same_brand(a, b):
        return None
    if not ctx.parts[a["id"]] or not ctx.parts[b["id"]]:
        return None
    radius = PARK_NAME_M if cat == "park_garden" else NAME_M
    key_a, key_b = vn.address_key(a.get("address")), vn.address_key(b.get("address"))
    if key_a and key_a == key_b:
        radius = max(radius, ADDRESS_M)
    if d <= radius and ctx.same_name(a, b) and not ctx.is_series(a, b):
        return "name"
    if d <= COLOCATED_M and ctx.shared_identity(a, b):
        return "colocated"
    if d <= WORSHIP_M and ctx.worship(a) & ctx.worship(b):
        return "worship"
    return None


class Grid:
    def __init__(self, pois: list[dict], cell: float = 0.004):
        self.cell, self.cells = cell, defaultdict(list)
        for p in pois:
            self.cells[self._key(p)].append(p)

    def _key(self, p: dict) -> tuple[int, int]:
        return round(p["lat"] / self.cell), round(p["lon"] / self.cell)

    def near(self, p: dict, radius_m: float) -> list[tuple[float, dict]]:
        kx, ky = self._key(p)
        out = []
        for dx in (-2, -1, 0, 1, 2):
            for dy in (-2, -1, 0, 1, 2):
                for q in self.cells.get((kx + dx, ky + dy), []):
                    if q is not p and (d := haversine_m(p["lat"], p["lon"], q["lat"], q["lon"])) <= radius_m:
                        out.append((d, q))
        return out


def find_pairs(pois: list[dict], ctx: Context, families: frozenset[str] = FAMILIES) -> list[tuple[float, str, dict, dict]]:
    grid = Grid(pois)
    pairs, seen = [], set()
    for p in pois:
        if p["category"] not in families and not p.get("wikidata_id"):
            continue
        for d, q in grid.near(p, max(WIKIDATA_M, PARK_NAME_M, ADDRESS_M)):
            if (key := tuple(sorted((p["id"], q["id"])))) in seen:
                continue
            seen.add(key)
            if rule := pair_rule(p, q, d, ctx, families):
                a, b = sorted((p, q), key=lambda r: r["id"])
                pairs.append((d, rule, a, b))
    return sorted(pairs, key=lambda t: (t[0], t[2]["id"], t[3]["id"]))


# ---------------------------------------------------------------- clusters
def cluster(pairs: list[tuple[float, str, dict, dict]]) -> list[dict]:
    """Union the pairs nearest first; a union that would put two Wikidata ids or a > 350 m span into one cluster is
    refused. Returns [{members: [records], links: [(rule, distance, id, id)]}] with more than one member."""
    parent: dict[str, str] = {}
    members: dict[str, list[dict]] = {}
    links: dict[str, list[tuple]] = {}

    def find(i: str) -> str:
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for d, rule, a, b in pairs:
        for r in (a, b):
            if r["id"] not in parent:
                parent[r["id"]], members[r["id"]], links[r["id"]] = r["id"], [r], []
        ra, rb = find(a["id"]), find(b["id"])
        if ra == rb:
            links[ra].append((rule, round(d, 1), a["id"], b["id"]))
            continue
        union = members[ra] + members[rb]
        wd = {m["wikidata_id"] for m in union if m.get("wikidata_id")}
        span = max(haversine_m(x["lat"], x["lon"], y["lat"], y["lon"]) for x in union for y in union)
        if len(wd) > 1 or span > DIAMETER_M:
            continue
        parent[rb] = ra
        members[ra], links[ra] = union, links[ra] + links[rb] + [(rule, round(d, 1), a["id"], b["id"])]
        del members[rb], links[rb]
    return [{"members": sorted(members[r], key=lambda m: m["id"]), "links": links[r]} for r in sorted(members)]


# ---------------------------------------------------------------- merge of two records
def _fsrc_of(p: dict, field: str) -> dict | None:
    return (p.get("field_sources") or {}).get(field)


def _carry(dst: dict, src: dict, field: str) -> None:
    dst[field] = copy.deepcopy(src[field])
    if fs := _fsrc_of(src, field):
        dst.setdefault("field_sources", {})[field] = copy.deepcopy(fs)


def merge_into(survivor: dict, other: dict, rule: str, distance: float) -> None:
    """Add what `other` knows and `survivor` lacks (in place); the rest is described in `merged_from`."""
    not_taken: dict[str, object] = {}

    def conflict(field: str) -> None:
        if not empty(other.get(field)) and other.get(field) != survivor.get(field):
            not_taken[field] = other[field]

    # names: language keys the survivor lacks, the remaining distinct names as `alt_names`
    names = survivor.setdefault("names", {})
    known = set(names_of(survivor)) | set(names.values())
    for key, val in (other.get("names") or {}).items():
        if key != "name" and key not in names and val not in known:
            names[key] = val
            known.add(val)
    for val in [other["name"], *(other.get("names") or {}).values(), *(other.get("alt_names") or [])]:
        if val and val not in known and not other.get("name_generated"):
            survivor.setdefault("alt_names", []).append(val)
            known.add(val)
    if empty(survivor.get("labels")) and other.get("labels"):
        survivor["labels"] = copy.deepcopy(other["labels"])
    for tag in other.get("tags") or []:
        if tag not in survivor["tags"]:
            survivor["tags"].append(tag)
    for label in other["sources"]:
        if label not in survivor["sources"]:
            survivor["sources"].append(label)
    survivor["sources"].sort(key=SOURCE_ORDER.index)

    for field in ("website", "phone", "price_text", "opening_hours", "hours_unqualified"):
        if empty(survivor.get(field)) and not empty(other.get(field)):
            _carry(survivor, other, field)
            if field == "hours_unqualified":
                survivor["hours_unqualified_flags"] = list(other.get("hours_unqualified_flags") or [])
        elif field != "hours_unqualified":
            conflict(field)
    if not empty(survivor.get("opening_hours")):
        survivor["hours_state"] = "known"
        survivor["hours_unqualified"], survivor["hours_unqualified_flags"] = None, []
    if not specific_address(survivor.get("address")) and specific_address(other.get("address")):
        _carry(survivor, other, "address")
    else:
        conflict("address")
    # a value another source of the other record has for the hours: official schedule, kept next to the survivor's
    if empty(survivor.get("opening_hours_official")) and not empty(other.get("opening_hours_official")):
        _carry(survivor, other, "opening_hours_official")
        if survivor.get("opening_hours") and not same_schedule(survivor["opening_hours"],
                                                                other["opening_hours_official"]):
            survivor["hours_conflict"] = True
            survivor["hours_conflict_prefers"] = other.get("hours_conflict_prefers") or "osm"
    if empty(survivor.get("description_official")) and not empty(other.get("description_official")):
        _carry(survivor, other, "description_official")
    # the real description (OSM / Wikipedia) beats a derived one
    if survivor.get("description_source") == "derived" and other.get("description_source") in ("osm", "wikipedia"):
        for field in ("description", "description_source", "wikipedia"):
            if not empty(other.get(field)):
                _carry(survivor, other, field)
    elif empty(survivor.get("wikipedia")) and other.get("wikipedia"):
        _carry(survivor, other, "wikipedia")
    # identifiers and the joins that came with them
    for field in ("wikidata_id", "wiki_match", "overture_match", "overture_confidence", "official_site_match"):
        if empty(survivor.get(field)) and not empty(other.get(field)):
            if field == "official_site_match" and not _official_fields_agree(survivor, other):
                continue
            _carry(survivor, other, field)
    if empty(survivor.get("overture_id")) and other.get("overture_id"):
        survivor["overture_id"] = other["overture_id"]
    for field, val in other.items():  # facts of later stages (`admin_hours`, `address_kk`, `price_text` ...)
        if field not in _SKIP and field not in survivor and not empty(val):
            _carry(survivor, other, field)

    fsrc = survivor.setdefault("field_sources", {})
    for field, src in (other.get("field_sources") or {}).items():
        if field not in fsrc and field in survivor and not empty(survivor[field]):
            fsrc[field] = copy.deepcopy(src)

    ids = [other["id"]]
    if other.get("overture_id") and not other["id"].endswith(other["overture_id"]):
        ids.append(f"overture/{other['overture_id']}")
    for alias in [*ids, *other.get("aliases", [])]:
        if alias not in survivor.setdefault("aliases", []) and alias != survivor["id"]:
            survivor["aliases"].append(alias)
    survivor.setdefault("merged_from", []).append({
        "id": other["id"], "name": other["name"], "names": dict(other.get("names") or {}),
        "category": other["category"], "rule": rule, "distance_m": round(distance, 1), "source": other["source"], "sources": list(other["sources"]), "overture_id": other.get("overture_id"),
        "lat": other["lat"], "lon": other["lon"], "address": other.get("address"),
        "wikidata_id": other.get("wikidata_id"), "values_not_taken": not_taken,
    })
    survivor["merged_from"].extend(other.get("merged_from") or [])


def _official_fields_agree(survivor: dict, other: dict) -> bool:
    """`official_site_match` names the one domain that backs the record's official-site fields: the other's match
    is taken only while the survivor has no official-site field of its own."""
    return not any((v or {}).get("source") == "official_site" for v in (survivor.get("field_sources") or {}).values())


# ---------------------------------------------------------------- the pass
def merge_cluster(members: list[dict], links: list[tuple]) -> dict:
    ordered = sorted(sorted(members, key=lambda m: m["id"]), key=richness, reverse=True)  # a tie: the smaller id
    survivor, others = ordered[0], ordered[1:]
    by_id = {m["id"]: m for m in members}
    rule_of: dict[str, tuple[str, float]] = {}
    for rule, d, a, b in links:
        for x in (a, b):
            if x != survivor["id"] and (x not in rule_of or d < rule_of[x][1]):
                rule_of[x] = (rule, d)
    for o in others:
        rule, d = rule_of.get(o["id"], (links[0][0], links[0][1]))
        d_surv = haversine_m(survivor["lat"], survivor["lon"], o["lat"], o["lon"])
        merge_into(survivor, o, rule, d_surv if d_surv else d)
    choose_display_name(survivor, ordered)
    return survivor


def local_name(ordered: list[dict]) -> tuple[str, str | None] | None:
    """(display name, raw `names["name"]` of its record) for a merged card: the name of the cluster's OSM record
    (the local naming; the richest one when there are several), else a Wikidata ru / kk label, else None."""
    for m in ordered:
        if m["source"] == "osm" and not m.get("name_generated"):
            return m["name"], (m.get("names") or {}).get("name")
    for lang in ("ru", "kk"):
        for m in ordered:
            if label := (m.get("labels") or {}).get(lang):
                return label, label
    return None


def choose_display_name(survivor: dict, ordered: list[dict]) -> None:
    """The survivor of a cluster keeps the facts of its richest record but is shown under the local name, not under
    the English / Latin spelling of an Overture pin: `local_name` of the cluster becomes `name`, the name the card had
    goes to `alt_names` (no name is lost), `description_auto` is quoted with the shown name."""
    if not (pick := local_name(ordered)) or pick[0] == survivor["name"]:
        return
    shown, raw = pick
    old = survivor["name"]
    names = survivor.setdefault("names", {})
    if names.get("name") == old:
        names["name"] = raw or shown
    alt = [n for n in survivor.get("alt_names") or [] if n != shown]
    if old not in alt and not survivor.get("name_generated"):
        alt.append(old)
    survivor["alt_names"] = alt
    survivor["name"], survivor["name_generated"] = shown, False
    if survivor.get("description_auto"):
        survivor["description_auto"] = survivor["description_auto"].replace(f"«{old}»", f"«{shown}»")


def kind_pins(dataset: list[dict], ctx: Context) -> list[tuple[dict, dict, float]]:
    """(pin, anchor, distance) for every bare kind-only Overture pin that has a same-kind anchor within 250 m."""
    grid = Grid(dataset)
    out = []
    for p in dataset:
        if p["category"] not in FAMILIES or not is_bare(p) or not ctx.parts[p["id"]]:
            continue
        if not all(x.descriptive_only for x in ctx.parts[p["id"]]):
            continue
        kinds = ctx.kinds(p)
        anchors = [(d, q) for d, q in grid.near(p, PIN_M)
                   if q["category"] == p["category"] and not is_bare(q) and kinds & ctx.kinds(q)]
        if anchors:
            d, anchor = min(anchors, key=lambda t: (t[0], t[1]["id"]))
            out.append((p, anchor, d))
    return out


def dedupe(pois: list[dict]) -> tuple[list[dict], dict]:
    """(new dataset, log). The input is not modified."""
    pre = {p["id"]: (bucket_of(p["sources"]), p["source"]) for p in pois}
    ov_pin = {p["id"]: bool(p.get("overture_id")) for p in pois}
    data = copy.deepcopy(pois)
    ctx = Context(data)
    absorbed: set[str] = set()
    log_clusters = []
    for c in cluster(find_pairs(data, ctx)):
        record_names = {m["id"]: m["name"] for m in c["members"]}
        survivor = merge_cluster(c["members"], c["links"])
        absorbed |= {m["id"] for m in c["members"]} - {survivor["id"]}
        entry = _log_cluster(survivor, c, pre)
        if record_names[survivor["id"]] != survivor["name"]:  # shown under the local name of another record
            entry["renamed_from"] = record_names[survivor["id"]]
        log_clusters.append(entry)
    data = [p for p in data if p["id"] not in absorbed]

    by_id = {p["id"]: p for p in data}
    log_pins, absorbed_pins = [], set()
    for pin, anchor, d in sorted(kind_pins(data, ctx), key=lambda t: t[0]["id"]):
        merge_into(by_id[anchor["id"]], by_id[pin["id"]], "kind_pin", d)
        absorbed_pins.add(pin["id"])
        log_pins.append({"category": pin["category"], "survivor": anchor["id"], "survivor_name": anchor["name"],
                         "absorbed": pin["id"], "absorbed_name": pin["name"], "source": pin["source"],
                         "sources": list(pin["sources"]), "rule": "kind_pin", "distance_m": round(d, 1)})
    data = [p for p in data if p["id"] not in absorbed_pins]
    for row in log_pins:  # a kind-only pin is a cluster of one absorbed record on the same survivor
        log_clusters.append({"category": row["category"], "survivor": row["survivor"],
                             "survivor_name": row["survivor_name"],
                             "absorbed": [{"id": row["absorbed"], "name": row["absorbed_name"],
                                           "category": row["category"], "source": row["source"],
                                           "sources": row["sources"], "wikidata_id": None,
                                           "distance_m": row["distance_m"]}],
                             "links": [{"rule": "kind_pin", "distance_m": row["distance_m"],
                                        "a": row["survivor"], "b": row["absorbed"]}],
                             "origins": sorted({pre[row["absorbed"]][1]}), "kind_pins": 1})
    absorbed |= absorbed_pins

    before_c = Counter(b for b, _ in pre.values())
    after_c = Counter(bucket_of(p["sources"]) for p in data)
    origins = Counter(pre[i][1] for i in absorbed)
    # of the absorbed records that carried an Overture id, whose surviving card took it over
    by_survivor = {a["id"]: c["survivor"] for c in log_clusters for a in c["absorbed"]}
    taken_over = Counter(pre[by_survivor[i]][1] for i in absorbed if ov_pin[i] and i in by_survivor)
    kept = Counter(p["source"] for p in data)
    by_rule = Counter(l["rule"] for c in log_clusters for l in c["links"])
    merged_by_cat = Counter(c["category"] for c in log_clusters for _ in c["absorbed"])
    log = {
        "stats": {"poi_total_before": len(pois), "poi_total_after": len(data), "records_merged_away": len(absorbed),
                  "clusters": sum(1 for c in log_clusters if not c.get("kind_pins")),
                  "kind_pins": len(log_pins),
                  "by_category": dict(sorted(merged_by_cat.items())),
                  "absorbed_from_bucket": {k: before_c[k] - after_c.get(k, 0)
                                           for k in sorted(set(before_c) | set(after_c))},

                  "absorbed_by_origin": dict(sorted(origins.items())),
                  "overture_pins_taken_over": dict(sorted(taken_over.items())),
                  "kept_by_origin": dict(sorted(kept.items())),
                  "records_before_by_origin": dict(sorted(Counter(s for _, s in pre.values()).items())),
                  "link_rules": dict(sorted(by_rule.items())),
                  "not_merged_outside_scope": _measure_outside(pois)},
        "rules": {"wikidata": f"same Wikidata id, <= {WIKIDATA_M:.0f} m",
                  "name": f"names agree (ru/kk/en/translit), <= {NAME_M:.0f} m (parks {PARK_NAME_M:.0f} m; the same "
                          f"street address {ADDRESS_M:.0f} m)",
                  "colocated": f"<= {COLOCATED_M:.0f} m and one identity word in common",
                  "worship": f"mosque / synagogue / church-cathedral of the same faith <= {WORSHIP_M:.0f} m",
                  "kind_pin": f"bare Overture pin named only by its kind, <= {PIN_M:.0f} m from a same-kind record",
                  "never": "different Wikidata ids, chain branches (same brand), series names "
                           f"(>= {SERIES_MIN} records), generated names, different categories, cluster > "
                           f"{DIAMETER_M:.0f} m"},
        "clusters": log_clusters, "kind_pin_rows": log_pins,
    }
    return data, log


def _log_cluster(survivor: dict, c: dict, pre: dict[str, tuple[str, str]]) -> dict:
    return {"category": survivor["category"], "survivor": survivor["id"], "survivor_name": survivor["name"],
            "origins": sorted({pre[m["id"]][1] for m in c["members"]}),
            "absorbed": [{"id": m["id"], "name": m["name"], "category": m["category"], "source": m["source"],
                          "sources": m["sources"], "wikidata_id": m.get("wikidata_id"),
                          "distance_m": round(haversine_m(survivor["lat"], survivor["lon"], m["lat"], m["lon"]), 1)}
                         for m in c["members"] if m["id"] != survivor["id"]],
            "links": [{"rule": r, "distance_m": d, "a": a, "b": b} for r, d, a, b in c["links"]]}


def _measure_outside(pois: list[dict]) -> dict:
    """Pairs the same rules would merge in categories this stage leaves alone (counted, not merged)."""
    ctx = Context(pois)
    fam = frozenset(MEASURED_ONLY)
    pairs = [t for t in find_pairs(pois, ctx, fam) if t[2]["category"] in fam]
    by_cat = Counter(t[2]["category"] for t in pairs)
    return {"pairs_by_category": dict(sorted(by_cat.items())),
            "examples": [f"{t[2]['name']} | {t[3]['name']} ({t[1]}, {round(t[0])} m)" for t in pairs[:6]]}


def resolve_alias(pois: list[dict], poi_id: str) -> dict | None:
    """The record `poi_id` is (or was merged into)."""
    for p in pois:
        if p["id"] == poi_id or poi_id in (p.get("aliases") or ()):
            return p
    return None


# ---------------------------------------------------------------- stats / delta
def already_applied(pois: list[dict]) -> bool:
    return any(p.get("aliases") for p in pois)


def shipped_stats(prev: dict, dataset: list[dict], log: dict) -> dict:
    """`per_source_counts` stays the merge / sites / gov stages' count of the records they wrote: this stage removes
    duplicates, it does not relabel the survivors. `duplicates` carries what was absorbed and from which bucket."""
    ps = {**prev.get("per_source_counts", {}),
          "with_wikidata": sum(1 for p in dataset if p.get("wikidata_id")),
          "with_wikipedia_article": sum(1 for p in dataset if p.get("wikipedia")),
          "with_popularity_pageviews": sum(1 for p in dataset if "popularity_pageviews" in p),
          "with_official_site": sum(1 for p in dataset if "official_site" in p["sources"]),
          "with_state_registry": sum(1 for p in dataset if "state_registry" in p["sources"])}
    if "with_wikivoyage" in ps:
        ps["with_wikivoyage"] = sum(1 for p in dataset if "wikivoyage" in p["sources"])
    return {**prev, "after": stats_for(dataset), "per_source_counts": ps,
            "description_source_counts": {s: sum(1 for p in dataset if p["description_source"] == s)
                                          for s in ("osm", "wikipedia", "derived")},
            "duplicates": log["stats"]}


def render_delta(log: dict) -> str:
    st = log["stats"]
    rows = ["| category | records merged away |", "|---|---|",
            *[f"| {c} | {n} |" for c, n in st["by_category"].items()]]
    ex = []
    for c in sorted(log["clusters"], key=lambda c: (c["category"], c["survivor"])):
        names = "; ".join(n for n in [c.get("renamed_from"), *(a["name"] for a in c["absorbed"])]
                          if n and n != c["survivor_name"])
        ex.append(f"- {c['category']}: **{c['survivor_name']}** ← {names} ({', '.join(sorted({l['rule'] for l in c['links']}))})")
    for p in log["kind_pin_rows"]:
        ex.append(f"- {p['category']}: **{p['survivor_name']}** ← {p['absorbed_name']} (kind_pin, {round(p['distance_m'])} m)")
    lines = [DELTA_HEADING, "",
             "Generated by `collect.dedupe` (rules: `collect/dedupe.py`, names: `collect/venue_names.py`; log with "
             "every cluster: `data/duplicates_merged.json`). The absorbed ids stay on the surviving record as "
             "`aliases`.", "",
             f"- POIs: {st['poi_total_before']} -> {st['poi_total_after']} ({st['records_merged_away']} records merged "
             f"into {st['clusters'] + st['kind_pins']} venues' cards: {st['clusters']} clusters, {st['kind_pins']} "
             "kind-only pins).",
             f"- Links by rule: {st['link_rules']}.",
             f"- Same rules in categories left alone (not merged): {st['not_merged_outside_scope']['pairs_by_category']}.",
             "", *rows, "", *ex, ""]
    return "\n".join(lines)


def _replace_section(path: Path, begin: str, block: str) -> None:
    text = path.read_text(encoding="utf-8") if path.exists() else ""
    head, sep, tail = text.partition(begin)
    if sep:
        nxt = re.search(r"^## ", tail, re.MULTILINE)
        tail = tail[nxt.start():] if nxt else ""
    path.write_text(head.rstrip("\n") + ("\n\n" if head.strip() else "") + block.rstrip("\n") + "\n"
                    + ("\n" + tail.lstrip("\n") if tail.strip() else ""), encoding="utf-8")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--poi", default=str(POI_PATH))
    ap.add_argument("--out", default=str(POI_PATH))
    ap.add_argument("--stats", default=str(STATS_PATH))
    ap.add_argument("--delta", default=str(DELTA_PATH))
    ap.add_argument("--log", default=str(LOG_PATH))
    args = ap.parse_args(argv)
    pois = json.loads(Path(args.poi).read_text(encoding="utf-8"))
    if already_applied(pois):
        print(f"[dedupe] {args.poi} already carries merged records (`aliases`); rebuild the base first "
              "(uv run python -m collect.build), then apply.", file=sys.stderr)
        return 1
    dataset, log = dedupe(pois)
    from collect.sites.verify import check_dataset as sites_check_dataset

    if problems := sites_check_dataset(dataset):
        for line in problems:
            print(f"[dedupe] {line}", file=sys.stderr)
        print(f"[dedupe] {len(problems)} official-site field(s) not backed by the record's own names; nothing written",
              file=sys.stderr)
        return 1
    stats_path = Path(args.stats)
    prev = json.loads(stats_path.read_text(encoding="utf-8")) if stats_path.exists() else {}
    ship = shipped_stats(prev, dataset, log) if "per_source_counts" in prev else {**prev, "duplicates": log["stats"]}
    Path(args.out).write_text(json.dumps(dataset, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    Path(args.log).write_text(json.dumps(log, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    stats_path.write_text(json.dumps(ship, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    _replace_section(Path(args.delta), DELTA_HEADING, render_delta(log))
    st = log["stats"]
    print(f"[dedupe] POIs {st['poi_total_before']} -> {st['poi_total_after']}: {st['clusters']} clusters, "
          f"{st['kind_pins']} kind-only pins; by category {st['by_category']}; rules {st['link_rules']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
