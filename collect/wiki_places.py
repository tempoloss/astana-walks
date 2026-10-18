"""Astana places that live in Wikidata / Wikipedia but not (yet) in OSM or Overture -> data/wiki_places.json.

Usage: uv run python -m collect.wiki_places

Candidates (union by Wikidata item):
  1. Wikidata: items located in Astana (P131*) whose class (P31/P279*) is in CLASS_MAP (museum, theatre, monument,
     memorial, sculpture, observation tower, library, ...);
  2. Wikipedia (ru, en) geosearch: every geotagged article within ~10 km grid circles over the city;
  3. Wikipedia (ru, en) categories (CATEGORIES, depth <= 2): museums, theatres, monuments, parks of Astana.
Every candidate is then classified by its Wikidata class (P31/P279*, same CLASS_MAP) - items of no mapped class
(streets, ministries, hotels, companies...) are dropped - and located:
  wikidata P625 > Wikipedia article coordinates > Nominatim by name (1 req/s, geocode_confidence = name similarity),
and must fall inside the Astana district polygons (data/districts.geojson, OSM admin_level=6).
Licences: Wikidata CC0-1.0, Wikipedia extracts CC-BY-SA-4.0, Nominatim results ODbL-1.0 (OSM data).
Opening hours: Wikidata has no Astana item with P3025 / P8626 (checked by SPARQL); none are collected.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from collect import wiki_enrich as we
    from collect.districts import DEFAULT_OUT as DISTRICTS_PATH
    from collect.districts import point_in_ring
    from collect.names import name_score
    from collect.net import Net, NetError, default_net
    from collect.overpass_poi import write_json
except ImportError:  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from collect import wiki_enrich as we
    from collect.districts import DEFAULT_OUT as DISTRICTS_PATH
    from collect.districts import point_in_ring
    from collect.names import name_score
    from collect.net import Net, NetError, default_net
    from collect.overpass_poi import write_json

DEFAULT_OUT = Path(__file__).resolve().parents[1] / "data" / "wiki_places.json"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
LICENSE_NOMINATIM = "ODbL-1.0"
LANGS = we.LANGS
GEO_CENTRES = [(51.13, 71.43), (51.10, 71.35), (51.17, 71.45), (51.16, 71.38), (51.09, 71.50), (51.06, 71.42),
               (51.20, 71.50), (51.13, 71.52), (51.18, 71.40), (51.05, 71.35)]
GEO_RADIUS_M = 10000
NOMINATIM_MIN_CONFIDENCE = 0.75

CATEGORIES = {
    "ru": ["Музеи Астаны", "Театры Астаны", "Здания и сооружения Астаны", "Достопримечательности Астаны",
           "Памятники истории и культуры местного значения Астаны", "Сады и парки Астаны",
           "Спортивные сооружения Астаны", "Памятники Астаны", "Мечети Астаны"],
    "en": ["Museums in Astana", "Theatres in Astana", "Buildings and structures in Astana",
           "Tourist attractions in Astana", "Monuments and memorials in Astana", "Parks in Astana",
           "Sports venues in Astana", "Mosques in Astana", "Culture in Astana"],
}

# Items that Wikidata files under a mapped class (the AIFC is a "park" through a business-park class) but that are
# organisations, not places to visit.
NOT_A_VISITOR_PLACE = re.compile(r"финансов\w+\s+центр|financial\s+cent|биржа|exchange|университет|university|"
                                 r"министерств|ministry|банк\b|bank\b|отель|hotel", re.I)
CATEGORY_DEPTH = 2
CATEGORY_PAGE_CAP = 600

# Wikidata class -> our category. Several classes may match (P279* closure): CLASS_PRIORITY decides.
CLASS_MAP: dict[str, str] = {
    "Q33506": "museum_gallery",  # museum
    "Q207694": "museum_gallery",  # art museum
    "Q2087181": "museum_gallery",  # history museum
    "Q756102": "museum_gallery",  # open-air museum
    "Q1007870": "museum_gallery",  # art gallery
    "Q16735822": "museum_gallery",  # museum building
    "Q24354": "culture_theatre_cinema",  # theatre building
    "Q153562": "culture_theatre_cinema",  # opera house
    "Q1060829": "culture_theatre_cinema",  # concert hall
    "Q41253": "culture_theatre_cinema",  # movie theater
    "Q16889960": "culture_theatre_cinema",  # circus building
    "Q1181413": "culture_theatre_cinema",  # palace of culture
    "Q4989906": "attraction_landmark",  # monument
    "Q5003624": "attraction_landmark",  # memorial
    "Q860861": "attraction_landmark",  # sculpture
    "Q20437094": "attraction_landmark",  # installation artwork
    "Q2319498": "attraction_landmark",  # architectural landmark
    "Q483453": "attraction_landmark",  # fountain
    "Q174782": "attraction_landmark",  # square
    "Q32815": "attraction_landmark",  # mosque
    "Q2977": "attraction_landmark",  # cathedral
    "Q2031836": "attraction_landmark",  # Eastern Orthodox church building
    "Q34627": "attraction_landmark",  # synagogue
    "Q1128637": "attraction_landmark",  # national symbol
    "Q481289": "attraction_landmark",  # official residence
    "Q1440300": "viewpoint",  # observation tower
    "Q22698": "park_garden",  # park
    "Q167346": "park_garden",  # botanical garden
    "Q974968": "park_garden",  # miniature park
    "Q43501": "entertainment",  # zoo
    "Q2281788": "entertainment",  # public aquarium
    "Q194195": "entertainment",  # amusement park
    "Q483110": "sport",  # stadium
    "Q641226": "sport",  # arena
    "Q12019965": "sport",  # indoor ice rink
    "Q11315": "mall",  # shopping center
    "Q7075": "coworking_library",  # library
    "Q22806": "coworking_library",  # national library
}
CLASS_PRIORITY = ["viewpoint", "museum_gallery", "culture_theatre_cinema", "entertainment", "park_garden",
                  "sport", "mall", "coworking_library", "attraction_landmark"]

_WKT = re.compile(r"Point\(\s*(-?[\d.]+)\s+(-?[\d.]+)\s*\)")
_CAT_NS = {"ru": "Категория", "en": "Category"}


def _values(qids) -> str:
    return " ".join(f"wd:{q}" for q in qids)


def q_typed() -> str:
    return we._PREFIXES + (
        "SELECT ?item ?cls ?c WHERE {\n"
        f"  ?item wdt:P131* wd:{we.ASTANA_QID} .\n"
        f"  ?item wdt:P31/wdt:P279* ?cls . VALUES ?cls {{ {_values(CLASS_MAP)} }}\n"
        "  OPTIONAL { ?item wdt:P625 ?c }\n}"
    )


def q_classify(qids: list[str]) -> str:
    return we._PREFIXES + (
        "SELECT ?item ?cls ?c WHERE {\n"
        f"  VALUES ?item {{ {_values(qids)} }}\n"
        f"  ?item wdt:P31/wdt:P279* ?cls . VALUES ?cls {{ {_values(CLASS_MAP)} }}\n"
        "  OPTIONAL { ?item wdt:P625 ?c }\n}"
    )


def _qid(row: dict, key: str = "item") -> str:
    return row[key]["value"].rsplit("/", 1)[-1]


def _point(row: dict) -> tuple[float, float] | None:
    m = _WKT.match(row.get("c", {}).get("value", ""))
    return (float(m.group(2)), float(m.group(1))) if m else None


def pick_category(classes: set[str]) -> str | None:
    cats = {CLASS_MAP[c] for c in classes if c in CLASS_MAP}
    return next((c for c in CLASS_PRIORITY if c in cats), None)


# ---- candidate sources ----------------------------------------------------------------------------


def wiki_api(lang: str) -> str:
    return f"https://{lang}.wikipedia.org/w/api.php"


def geosearch(net: Net, lang: str) -> dict[str, dict]:
    """title -> {lat, lon} for every geotagged article around the city (articles can repeat across circles)."""
    out: dict[str, dict] = {}
    for lat, lon in GEO_CENTRES:
        data = net.get(wiki_api(lang), params={
            "action": "query", "format": "json", "list": "geosearch", "gscoord": f"{lat}|{lon}",
            "gsradius": GEO_RADIUS_M, "gslimit": 500,
        }).json()
        for g in data.get("query", {}).get("geosearch", []):
            out[g["title"]] = {"lat": g["lat"], "lon": g["lon"]}
    return out


def category_titles(net: Net, lang: str) -> set[str]:
    """Article titles in CATEGORIES[lang] and their subcategories (depth <= CATEGORY_DEPTH)."""
    seen_cats: set[str] = set()
    titles: set[str] = set()
    frontier = [(f"{_CAT_NS[lang]}:{c}", 0) for c in CATEGORIES[lang]]
    while frontier and len(titles) < CATEGORY_PAGE_CAP:
        cat, depth = frontier.pop(0)
        if cat in seen_cats:
            continue
        seen_cats.add(cat)
        cont: dict = {}
        while True:
            data = net.get(wiki_api(lang), params={
                "action": "query", "format": "json", "list": "categorymembers", "cmtitle": cat,
                "cmlimit": 500, "cmtype": "page|subcat", **cont,
            }).json()
            for m in data.get("query", {}).get("categorymembers", []):
                if m["ns"] == 14:
                    if depth < CATEGORY_DEPTH:
                        frontier.append((m["title"], depth + 1))
                elif m["ns"] == 0:
                    titles.add(m["title"])
            if "continue" not in data:
                break
            cont = data["continue"]
    return titles


def title_qids(net: Net, lang: str, titles: list[str]) -> dict[str, str]:
    out: dict[str, str] = {}
    for batch in we.batched(sorted(titles)):
        for title, page in we.query_pages(net, lang, batch, extracts=False).items():
            if page.get("qid") and not page.get("disambiguation"):
                out[title] = page["qid"]
    return out


def article_coords(net: Net, lang: str, titles: list[str]) -> dict[str, tuple[float, float]]:
    out: dict[str, tuple[float, float]] = {}
    for batch in we.batched(sorted(titles)):
        data = net.get(wiki_api(lang), params={
            "action": "query", "format": "json", "formatversion": "2", "prop": "coordinates", "colimit": "max",
            "redirects": "1", "titles": "|".join(batch),
        }).json()
        for pg in data.get("query", {}).get("pages", []):
            for c in pg.get("coordinates", [])[:1]:
                out[pg["title"]] = (c["lat"], c["lon"])
    return out


# ---- Nominatim ------------------------------------------------------------------------------------


def nominatim(net: Net, names: list[str], districts: list[list]) -> tuple[tuple[float, float], float, str] | None:
    """Best Nominatim hit inside Astana for any of `names`: ((lat, lon), name similarity 0..1, matched name)."""
    best = None
    for q in dict.fromkeys(names):
        data = net.get(NOMINATIM, params={
            "q": f"{q}, Астана", "format": "jsonv2", "limit": 5, "accept-language": "ru",
            "viewbox": "71.2,51.3,71.7,50.95", "bounded": 1,
        }).json()
        for r in data:
            pt = (float(r["lat"]), float(r["lon"]))
            if not inside(pt, districts):
                continue
            cand = [r.get("name") or "", r.get("display_name", "").split(",")[0]]
            score = name_score(names, [c for c in cand if c]) / 100
            if best is None or score > best[1]:
                best = (pt, round(score, 2), cand[0] or cand[1])
    return best if best and best[1] >= NOMINATIM_MIN_CONFIDENCE else None


# ---- geometry -------------------------------------------------------------------------------------


def load_districts(path: Path = DISTRICTS_PATH) -> list[list]:
    """Outer rings of every district polygon as [(lon, lat), ...]."""
    fc = json.loads(path.read_text(encoding="utf-8"))
    return [[tuple(p) for p in poly[0]] for f in fc["features"] for poly in f["geometry"]["coordinates"]]


def inside(pt: tuple[float, float], rings: list[list]) -> bool:
    lon_lat = (pt[1], pt[0])
    return any(point_in_ring(lon_lat, r) for r in rings)


# ---- main -----------------------------------------------------------------------------------------


def collect(net: Net, districts: list[list]) -> dict:
    snapshot_ts = 0.0
    classes: dict[str, set[str]] = {}
    coords: dict[str, dict] = {}
    cand_origin: dict[str, set[str]] = {}

    def note(qid: str, origin: str, pt: tuple[float, float] | None = None, source: str | None = None) -> None:
        cand_origin.setdefault(qid, set()).add(origin)
        if pt and qid not in coords:
            coords[qid] = {"lat": pt[0], "lon": pt[1], "source": source}

    rows, fetched = we.sparql(net, q_typed())
    snapshot_ts = max(snapshot_ts, fetched)
    for r in rows:
        q = _qid(r)
        classes.setdefault(q, set()).add(_qid(r, "cls"))
        note(q, "wikidata_p131", _point(r), "wikidata_p625")
    n_typed = len(cand_origin)

    by_title: dict[str, dict[str, str]] = {}
    geo_coords: dict[str, dict[str, tuple[float, float]]] = {}
    for lang in ("ru", "en"):
        geo = geosearch(net, lang)
        cats = category_titles(net, lang)
        titles = sorted(set(geo) | cats)
        qmap = title_qids(net, lang, titles)
        by_title[lang] = qmap
        cc = article_coords(net, lang, sorted(cats - set(geo)))
        for t, q in qmap.items():
            if t in geo:
                note(q, f"wikipedia_{lang}_geosearch", (geo[t]["lat"], geo[t]["lon"]), "wikipedia_coordinates")
            if t in cats:
                note(q, f"wikipedia_{lang}_category", cc.get(t), "wikipedia_coordinates")
        print(f"[wiki_places] {lang}: geosearch={len(geo)} category_pages={len(cats)} with_qid={len(qmap)}",
              file=sys.stderr)

    unclassified = sorted(q for q in cand_origin if q not in classes)
    for batch in we.batched(unclassified, 40):
        rows, fetched = we.sparql(net, q_classify(batch))
        snapshot_ts = max(snapshot_ts, fetched)
        for r in rows:
            q = _qid(r)
            classes.setdefault(q, set()).add(_qid(r, "cls"))
            if pt := _point(r):
                coords[q] = {"lat": pt[0], "lon": pt[1], "source": "wikidata_p625"}

    classified = {q: pick_category(c) for q, c in classes.items() if q in cand_origin and pick_category(c)}
    entities = we.fetch_entities(net, sorted(classified))
    ents = {q: {k: v for k, v in entities[q].items() if k != "id"} | {"qid": q} for q in sorted(classified)
            if q in entities}
    we.fetch_extracts(net, ents)

    places, dropped = [], {"no_coordinates": [], "outside_astana": [], "no_label": [], "organisation": []}
    n_nominatim = 0
    for q, ent in ents.items():
        labels = ent["labels"]
        name = labels.get("ru") or labels.get("en") or labels.get("kk")
        if not name:
            dropped["no_label"].append(q)
            continue
        if NOT_A_VISITOR_PLACE.search(name):
            dropped["organisation"].append({"qid": q, "name": name})
            continue
        names = list(dict.fromkeys(labels.get(lang) for lang in ("ru", "kk", "en") if labels.get(lang)))
        pos = coords.get(q)
        confidence = None
        if pos is None:
            hit = nominatim(net, names, districts)
            n_nominatim += 1
            if hit is None:
                dropped["no_coordinates"].append({"qid": q, "name": name})
                continue
            pos = {"lat": hit[0][0], "lon": hit[0][1], "source": "nominatim"}
            confidence = hit[1]
        if not inside((pos["lat"], pos["lon"]), districts):
            dropped["outside_astana"].append({"qid": q, "name": name})
            continue
        places.append({
            "qid": q, "name": name, "names": {f"name:{l}": labels[l] for l in ("ru", "kk", "en") if l in labels},
            "lat": round(pos["lat"], 7), "lon": round(pos["lon"], 7), "coord_source": pos["source"],
            "geocode_confidence": confidence, "category": classified[q],
            "classes": sorted(classes[q] & set(CLASS_MAP)), "found_via": sorted(cand_origin[q]),
            "descriptions": ent["descriptions"], "sitelinks": ent["sitelinks"], "wikipedia": ent.get("wikipedia", {}),
        })
    places.sort(key=lambda p: p["qid"])
    snapshot = datetime.fromtimestamp(snapshot_ts, timezone.utc).date().isoformat()
    by_cat: dict[str, int] = {}
    for p in places:
        by_cat[p["category"]] = by_cat.get(p["category"], 0) + 1
    return {
        "meta": {
            "snapshot_date": snapshot,
            "licenses": {"wikidata": we.LICENSES["wikidata"], "wikipedia": we.LICENSES["wikipedia"],
                         "nominatim": LICENSE_NOMINATIM},
            "class_map": CLASS_MAP, "categories": CATEGORIES, "geo_radius_m": GEO_RADIUS_M,
            "counts": {
                "candidates": len(cand_origin), "from_wikidata_typed_query": n_typed,
                "classified": len(classified), "places": len(places), "per_category": dict(sorted(by_cat.items())),
                "nominatim_lookups": n_nominatim,
                "nominatim_accepted": sum(1 for p in places if p["coord_source"] == "nominatim"),
                "dropped": {k: len(v) for k, v in dropped.items()},
            },
            "dropped": dropped,
            "hours": "Wikidata: 0 Astana items with P3025/P8626 (SPARQL count), nothing collected",
        },
        "places": places,
    }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DEFAULT_OUT))
    args = parser.parse_args(argv)
    net = default_net()
    try:
        result = collect(net, load_districts())
    except NetError as exc:
        raise SystemExit(f"[wiki_places] network failure: {exc}")
    write_json(Path(args.out), result)
    net.log_summary("wiki_places")
    print(json.dumps(result["meta"]["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
