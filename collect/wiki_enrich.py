"""Wikidata / Wikipedia enrichment of the OSM POI snapshot.

Usage: uv run python -m collect.wiki_enrich [--poi data/poi.osm.json] [--out data/wiki_enrichment.json]

Matching, in order of trust (a POI is matched at most once, ambiguous matches are dropped):
  tag    OSM `wikidata=Q…` (conf 1.0) or `wikipedia=lang:Title` resolved through pageprops (conf 0.95);
  sparql candidate from the SPARQL set "items located in Astana (P131* wd:Q1520) with P625" whose labels
         (ru/kk/en, transliteration-insensitive) are similar to the POI name and within 150 m;
  fuzzy  same name/distance test, but the item only came from the bounding-box query (no P131 chain to
         Astana in Wikidata, so its location is unverified).
Then: wbgetentities (50 ids/request) for labels/descriptions/sitelinks, the Wikipedia action API
(extracts, 50 titles/request) for ru/kk/en and Wikimedia monthly pageviews as popularity.
Licences: Wikidata CC0 1.0; Wikipedia text CC BY-SA 4.0.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import quote

try:
    from collect.names import name_score
    from collect.net import Net, NetError, default_net
    from collect.overpass_poi import haversine_m, write_json
except ImportError:  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from collect.names import name_score
    from collect.net import Net, NetError, default_net
    from collect.overpass_poi import haversine_m, write_json

SPARQL_URL = "https://query.wikidata.org/sparql"
WIKIDATA_API = "https://www.wikidata.org/w/api.php"
PAGEVIEWS_URL = "https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article"
LANGS = ("ru", "kk", "en")
BATCH = 50

ASTANA_QID = "Q1520"
BBOX = {"south": 50.98, "north": 51.25, "west": 71.25, "east": 71.60}

MAX_DISTANCE_M = 150.0
MIN_NAME_SCORE = 88.0  # skeleton similarity (0..100) below which a candidate is not considered
AMBIGUITY_MARGIN = 5.0  # runner-up (different item) within this many points of the best -> drop

LICENSES = {
    "wikidata": "CC0-1.0",
    "wikipedia": "CC-BY-SA-4.0",
    "wikimedia_pageviews": "CC0-1.0",
}

_PREFIXES = (
    "PREFIX wd: <http://www.wikidata.org/entity/>\n"
    "PREFIX wdt: <http://www.wikidata.org/prop/direct/>\n"
    "PREFIX p: <http://www.wikidata.org/prop/>\n"
    "PREFIX psv: <http://www.wikidata.org/prop/statement/value/>\n"
    "PREFIX wikibase: <http://wikiba.se/ontology#>\n"
    "PREFIX bd: <http://www.bigdata.com/rdf#>\n"
    "PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>\n"
    "PREFIX geo: <http://www.opengis.net/ont/geosparql#>\n"
)

Q_VERIFY = _PREFIXES + (
    f"SELECT ?lang ?label WHERE {{ wd:{ASTANA_QID} rdfs:label ?label . BIND(LANG(?label) AS ?lang) "
    'FILTER(?lang IN ("ru","kk","en")) }'
)

_ITEM_TAIL = (
    "  ?item p:P625/psv:P625 ?c . ?c wikibase:geoLatitude ?lat ; wikibase:geoLongitude ?lon .\n"
    '  OPTIONAL { ?item wdt:P31 ?type . BIND(STRAFTER(STR(?type), "entity/") AS ?t) }\n'
    '} GROUP BY ?item ?lat ?lon'
)

Q_LOCATED_IN = _PREFIXES + (
    "SELECT ?item ?lat ?lon (GROUP_CONCAT(DISTINCT ?t; separator=\",\") AS ?types) WHERE {\n"
    f"  ?item wdt:P131* wd:{ASTANA_QID} .\n" + _ITEM_TAIL
)

Q_BBOX = _PREFIXES + (
    "SELECT ?item ?lat ?lon (GROUP_CONCAT(DISTINCT ?t; separator=\",\") AS ?types) WHERE {\n"
    "  SERVICE wikibase:box {\n"
    "    ?item wdt:P625 ?loc .\n"
    f'    bd:serviceParam wikibase:cornerSouthWest "Point({BBOX["west"]} {BBOX["south"]})"^^geo:wktLiteral .\n'
    f'    bd:serviceParam wikibase:cornerNorthEast "Point({BBOX["east"]} {BBOX["north"]})"^^geo:wktLiteral .\n'
    "  }\n" + _ITEM_TAIL
)

_QID = re.compile(r"^Q\d+$")


def batched(seq: list, n: int = BATCH):
    for i in range(0, len(seq), n):
        yield seq[i:i + n]


def tag_value(poi: dict, key: str) -> str | None:
    prefix = key + "="
    for t in poi["tags"]:
        if t.startswith(prefix):
            return t[len(prefix):].strip() or None
    return None


# ---- SPARQL ---------------------------------------------------------------------------------------


def sparql(net: Net, query: str):
    resp = net.get(SPARQL_URL, params={"query": query, "format": "json"}, timeout=120)
    return resp.json()["results"]["bindings"], resp.fetched_at


def verify_astana(net: Net) -> tuple[dict, float]:
    rows, fetched = sparql(net, Q_VERIFY)
    labels = {r["lang"]["value"]: r["label"]["value"] for r in rows}
    if labels.get("ru") != "Астана" and labels.get("en") != "Astana":
        raise RuntimeError(f"{ASTANA_QID} is not Astana: labels={labels}")
    return labels, fetched


def fetch_candidates(net: Net) -> tuple[dict[str, dict], float]:
    """Union of the two SPARQL result sets; `p131` marks items with a located-in chain to Astana."""
    pool: dict[str, dict] = {}
    fetched_at = 0.0
    for flag, query in (("p131", Q_LOCATED_IN), ("bbox", Q_BBOX)):
        rows, fetched = sparql(net, query)
        fetched_at = max(fetched_at, fetched)
        for r in rows:
            qid = r["item"]["value"].rsplit("/", 1)[-1]
            if not _QID.match(qid):
                continue
            lat, lon = float(r["lat"]["value"]), float(r["lon"]["value"])
            c = pool.setdefault(qid, {"lat": lat, "lon": lon, "p131": False, "types": set()})
            c["p131"] = c["p131"] or flag == "p131"
            c["types"].update(t for t in r.get("types", {}).get("value", "").split(",") if t)
        print(f"[wiki] SPARQL {flag}: {len(rows)} rows, pool={len(pool)}", file=sys.stderr)
    return pool, fetched_at


# ---- Wikidata entities ---------------------------------------------------------------------------


def fetch_entities(net: Net, qids: list[str]) -> dict[str, dict]:
    """wbgetentities, 50 ids/request: labels + descriptions (ru/kk/en) and ru/kk/en wiki sitelinks."""
    ck = net.checkpoint("wbgetentities")
    out: dict[str, dict] = {}
    for batch in batched(sorted(set(qids))):
        key = ",".join(batch)
        cached = ck.get(key)
        if cached is None:
            resp = net.get(WIKIDATA_API, params={
                "action": "wbgetentities", "format": "json", "formatversion": "2", "ids": "|".join(batch),
                "props": "labels|descriptions|sitelinks", "languages": "|".join(LANGS),
                "sitefilter": "|".join(f"{l}wiki" for l in LANGS),
            })
            cached = {}
            for qid, ent in resp.json().get("entities", {}).items():
                if "missing" in ent:
                    continue
                cached[qid] = {
                    "id": ent.get("id", qid),
                    "labels": {l: v["value"] for l, v in ent.get("labels", {}).items()},
                    "descriptions": {l: v["value"] for l, v in ent.get("descriptions", {}).items()},
                    "sitelinks": {k[:-4]: v["title"] for k, v in ent.get("sitelinks", {}).items()
                                  if k.endswith("wiki") and k[:-4] in LANGS},
                }
            ck.put(key, cached)
        out.update(cached)
    return out


# ---- Wikipedia ------------------------------------------------------------------------------------


def wiki_url(lang: str, title: str) -> str:
    return f"https://{lang}.wikipedia.org/wiki/{quote(title.replace(' ', '_'), safe='')}"


def query_pages(net: Net, lang: str, titles: list[str], *, extracts: bool) -> dict[str, dict]:
    """Action API for <=50 titles. Returns requested title -> {title, extract?, qid?, disambiguation}."""
    base = {
        "action": "query", "format": "json", "formatversion": "2", "redirects": "1",
        "prop": "extracts|pageprops" if extracts else "pageprops", "ppprop": "wikibase_item|disambiguation",
        "titles": "|".join(titles),
    }
    if extracts:
        base.update({"exintro": "1", "explaintext": "1", "exlimit": "max"})
    url = f"https://{lang}.wikipedia.org/w/api.php"
    pages: dict[int, dict] = {}
    maps: dict[str, str] = {}
    cont: dict = {}
    while True:
        data = net.get(url, params={**base, **cont}).json()
        q = data.get("query", {})
        for step in ("normalized", "redirects"):
            for m in q.get(step, []):
                maps[m["from"]] = m["to"]
        for pg in q.get("pages", []):
            cur = pages.setdefault(pg.get("pageid", pg["title"]), {"title": pg["title"], "missing": pg.get("missing", False)})
            if pg.get("extract"):
                cur["extract"] = pg["extract"].strip()
            pp = pg.get("pageprops") or {}
            if "wikibase_item" in pp:
                cur["qid"] = pp["wikibase_item"]
            if "disambiguation" in pp:
                cur["disambiguation"] = True
        if "continue" not in data:
            break
        cont = data["continue"]
    by_title = {p["title"]: p for p in pages.values()}
    out = {}
    for t in titles:
        final = t
        for _ in range(3):  # normalized -> redirect chains
            final = maps.get(final, final)
        page = by_title.get(final)
        if page and not page["missing"]:
            out[t] = page
    return out


def resolve_wikipedia_tags(net: Net, pois: list[dict]) -> dict[str, str]:
    """poi id -> QID for POIs carrying `wikipedia=lang:Title` (no usable wikidata tag)."""
    by_lang: dict[str, dict[str, list[str]]] = {}
    for p in pois:
        wp = tag_value(p, "wikipedia")
        if not wp or ":" not in wp or _QID.match(tag_value(p, "wikidata") or ""):
            continue
        lang, title = wp.split(":", 1)
        if lang in LANGS:
            by_lang.setdefault(lang, {}).setdefault(title.strip(), []).append(p["id"])
    out: dict[str, str] = {}
    for lang, titles in by_lang.items():
        for batch in batched(sorted(titles)):
            for title, page in query_pages(net, lang, batch, extracts=False).items():
                if page.get("qid") and not page.get("disambiguation"):
                    for pid in titles[title]:
                        out[pid] = page["qid"]
    return out


def fetch_extracts(net: Net, entities: dict[str, dict]) -> None:
    """Fill entity["wikipedia"][lang] = {title, url, extract} for every sitelink; 50 titles/request."""
    for lang in LANGS:
        titles = {e["sitelinks"][lang]: qid for qid, e in entities.items() if lang in e["sitelinks"]}
        for batch in batched(sorted(titles)):
            pages = query_pages(net, lang, batch, extracts=True)
            for title in batch:
                page = pages.get(title)
                if not page or page.get("disambiguation"):
                    continue
                ent = entities[titles[title]]
                ent.setdefault("wikipedia", {})[lang] = {
                    "title": page["title"], "url": wiki_url(lang, page["title"]),
                    "extract": page.get("extract", ""),
                }


def last_full_month(ref: date) -> tuple[str, str, str]:
    end = ref.replace(day=1) - timedelta(days=1)
    start = end.replace(day=1)
    return start.strftime("%Y%m%d"), end.strftime("%Y%m%d"), end.strftime("%Y-%m")


def fetch_pageviews(net: Net, entities: dict[str, dict], ref: date) -> str:
    start, end, period = last_full_month(ref)
    ck = net.checkpoint(f"pageviews-{period}")
    for qid, ent in entities.items():
        views: dict[str, int] = {}
        for lang, art in ent.get("wikipedia", {}).items():
            key = f"{lang}:{art['title']}"
            n = ck.get(key)
            if n is None:
                title = quote(art["title"].replace(" ", "_"), safe="")
                url = f"{PAGEVIEWS_URL}/{lang}.wikipedia/all-access/user/{title}/monthly/{start}/{end}"
                resp = net.get(url, ok_statuses=(200, 404), cache_statuses=(200, 404))
                items = resp.json().get("items", []) if resp.status_code == 200 else []
                n = sum(i["views"] for i in items)
                ck.put(key, n)
            views[lang] = n
        if views:
            ent["pageviews"] = views
            ent["popularity_pageviews"] = sum(views.values())
    return period


# ---- matching -------------------------------------------------------------------------------------


def poi_names(poi: dict) -> list[str]:
    """Real names only: generated placeholders («Детская площадка») never match anything."""
    if poi["name_generated"]:
        return []
    names = list(poi["names"].values())
    if poi["name"] not in names:
        names.append(poi["name"])
    return names


def match_confidence(score: float, dist: float) -> float:
    return round(min(0.99, score / 100 * (1 - 0.25 * dist / MAX_DISTANCE_M)), 2)


def fuzzy_match(pois: list[dict], pool: dict[str, dict], entities: dict[str, dict], taken: set[str]) -> tuple[dict, dict]:
    """Name+distance matching of unmatched POIs against the SPARQL pool. Returns (matches, counters)."""
    cand_names = {qid: [v for v in entities[qid]["labels"].values()] for qid in pool if qid in entities}
    dlat, dlon = MAX_DISTANCE_M / 111_000 * 1.05, MAX_DISTANCE_M / 69_000 * 1.05
    counters = {"no_candidate": 0, "ambiguous": 0, "claimed_by_better": 0}
    proposals: dict[str, list[tuple]] = {}
    for poi in pois:
        if poi["id"] in taken:
            continue
        names = poi_names(poi)
        if not names:
            continue
        cands = []
        for qid, c in pool.items():
            if qid not in cand_names or abs(c["lat"] - poi["lat"]) > dlat or abs(c["lon"] - poi["lon"]) > dlon:
                continue
            dist = haversine_m(poi["lat"], poi["lon"], c["lat"], c["lon"])
            if dist > MAX_DISTANCE_M:
                continue
            score = name_score(names, cand_names[qid])
            if score >= MIN_NAME_SCORE:
                cands.append((score, dist, qid))
        if not cands:
            counters["no_candidate"] += 1
            continue
        cands.sort(key=lambda x: (-x[0], x[1]))
        best = cands[0]
        if len(cands) > 1 and best[0] - cands[1][0] < AMBIGUITY_MARGIN:
            counters["ambiguous"] += 1
            continue
        proposals.setdefault(best[2], []).append((best[0], best[1], poi["id"]))
    matches: dict[str, dict] = {}
    for qid, props in proposals.items():
        props.sort(key=lambda x: (-x[0], x[1], x[2]))
        score, dist, pid = props[0]
        counters["claimed_by_better"] += len(props) - 1
        matches[pid] = {
            "qid": qid, "method": "sparql" if pool[qid]["p131"] else "fuzzy",
            "confidence": match_confidence(score, dist), "distance_m": round(dist, 1), "name_score": round(score, 1),
        }
    return matches, counters


# ---- main -----------------------------------------------------------------------------------------


def enrich(pois: list[dict], net: Net) -> dict:
    labels, verify_fetched = verify_astana(net)
    print(f"[wiki] {ASTANA_QID} labels={labels}", file=sys.stderr)
    pool, sparql_fetched = fetch_candidates(net)
    snapshot = datetime.fromtimestamp(sparql_fetched, timezone.utc).date()

    matches: dict[str, dict] = {}
    for p in pois:
        qid = (tag_value(p, "wikidata") or "").split(";")[0].strip()
        if _QID.match(qid):
            matches[p["id"]] = {"qid": qid, "method": "tag", "confidence": 1.0, "distance_m": 0.0, "name_score": None}
    for pid, qid in resolve_wikipedia_tags(net, [p for p in pois if p["id"] not in matches]).items():
        matches[pid] = {"qid": qid, "method": "tag", "confidence": 0.95, "distance_m": 0.0, "name_score": None}
    n_tag = len(matches)

    entities = fetch_entities(net, sorted(set(pool) | {m["qid"] for m in matches.values()}))
    fuzzy, counters = fuzzy_match(pois, pool, entities, set(matches))
    matches.update(fuzzy)
    matches = {pid: m for pid, m in matches.items() if m["qid"] in entities}

    used = {m["qid"] for m in matches.values()}
    ents = {qid: {k: v for k, v in entities[qid].items() if k != "id"} | {"qid": entities[qid]["id"]}
            for qid in sorted(used)}
    fetch_extracts(net, ents)
    period = fetch_pageviews(net, ents, snapshot)

    by_method: dict[str, int] = {}
    for m in matches.values():
        by_method[m["method"]] = by_method.get(m["method"], 0) + 1
    return {
        "snapshot_date": snapshot.isoformat(),
        "licenses": LICENSES,
        "astana": {"qid": ASTANA_QID, "labels": labels},
        "queries": {"verify_astana": Q_VERIFY, "located_in_astana": Q_LOCATED_IN, "bbox": Q_BBOX},
        "thresholds": {"max_distance_m": MAX_DISTANCE_M, "min_name_score": MIN_NAME_SCORE,
                       "ambiguity_margin": AMBIGUITY_MARGIN},
        "pageviews_period": period,
        "counts": {
            "pool_items": len(pool), "pool_p131": sum(1 for c in pool.values() if c["p131"]),
            "tag_matches": n_tag, "matches_by_method": by_method, "matched_pois": len(matches),
            "matched_entities": len(ents), "fuzzy_dropped": counters,
            "entities_with_wikipedia": sum(1 for e in ents.values() if e.get("wikipedia")),
            "entities_with_ru_extract": sum(1 for e in ents.values() if e.get("wikipedia", {}).get("ru", {}).get("extract")),
        },
        "matches": dict(sorted(matches.items())),
        "entities": ents,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--poi", default="data/poi.osm.json")
    parser.add_argument("--out", default="data/wiki_enrichment.json")
    args = parser.parse_args(argv)
    pois = json.loads(Path(args.poi).read_text(encoding="utf-8"))
    net = default_net()
    try:
        result = enrich(pois, net)
    except NetError as exc:
        raise SystemExit(f"[wiki] network failure: {exc}")
    write_json(Path(args.out), result)
    net.log_summary("wiki")
    print(json.dumps(result["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
