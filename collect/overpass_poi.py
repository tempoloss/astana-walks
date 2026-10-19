"""Collect Astana POIs from OpenStreetMap via Overpass and normalize them.

Usage: uv run python -m collect.overpass_poi [--out data/poi.osm.json]
Writes <out> (POI list) and <out stem>_stats.json next to it. Never touches data/poi.json.
All HTTP goes through collect.net (UA, rate limits, retries, on-disk cache, failover).
"""

from __future__ import annotations

import argparse
import json
import math
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

try:
    from collect.net import Net, NetError, default_net
except ImportError:  # run as a plain script: python collect/overpass_poi.py
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from collect.net import Net, NetError, default_net

ENDPOINTS = [
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
    "https://maps.mail.ru/osm/tools/overpass/api/interpreter",  # public mirror listed on the OSM wiki; last resort
]
TIMEOUT = 180
DEFAULT_OUT = "data/poi.osm.json"

AREA_NAME = "Астана"
# Sanity bbox for the Astana admin area (its real bbox is ~50.86..51.35 / 71.22..71.79;
# the bbox centre must lie in 51.0-51.3 / 71.2-71.7) and for the collected POIs.
LAT_RANGE = (50.8, 51.4)
LON_RANGE = (71.1, 71.9)
CENTER_LAT_RANGE = (51.0, 51.3)
CENTER_LON_RANGE = (71.2, 71.7)

SELECTORS = {
    "amenity": [
        "cafe", "restaurant", "fast_food", "bar", "pub", "nightclub", "cinema", "theatre",
        "arts_centre", "library", "coworking_space", "ice_cream", "museum", "place_of_worship",
    ],
    "tourism": [
        "museum", "gallery", "attraction", "viewpoint", "artwork", "theme_park", "zoo", "aquarium",
    ],
    "leisure": [
        "park", "garden", "playground", "water_park", "amusement_arcade", "sports_centre",
        "escape_game", "bowling_alley", "trampoline_park", "ice_rink", "swimming_pool",
    ],
    "shop": ["mall"],
}

# Extra Overpass requests, one small query per selector (kept apart from the first request so its cached response,
# and every record built from it, stays byte-identical; small queries survive a busy server). Tags that the first
# selector set missed. Live counts inside the Astana area, 2026-10-17: leisure=indoor_play 1, amenity=planetarium 0,
# man_made=tower+tower:type=observation 0, tourism=viewpoint 1 (unnamed, already in the first set), shop=books 7,
# club=* 6, amenity=events_venue 1, amenity=fountain 129 (5 named), amenity=community_centre 15,
# leisure=miniature_golf / adult_gaming_centre / trampoline_park 0. EXTRA_NAME_FILTER keeps out what is not a place to
# visit (congress halls, book shops without a cafe in the name). Practical layers (round 10, nodes+ways, see
# recon/round10/practical_layers_count.jsonl): amenity=pharmacy 191, shop=supermarket 165, convenience 462,
# greengrocer 20, butcher 9 (shop=kiosk is left out: anonymous, so it would be dropped anyway; shop=bakery 20 stays
# with the cafe vocabulary of the app, so it is not collected as grocery). Money (one category `money`, the card
# name / SUBTYPE tells the three apart; same file): amenity=atm 309, bank 165, bureau_de_change 14. Lodging:
# tourism=hotel|hostel|guest_house (135 = 97 nodes + 22 ways + 16 relations, SOURCES 24.1).
EXTRA_SELECTORS = [
    '["leisure"="indoor_play"]',
    '["playground"="indoor"]',
    '["amenity"="planetarium"]',
    '["amenity"="events_venue"]',
    '["amenity"="fountain"]',
    '["amenity"="pharmacy"]',
    '["shop"~"^(supermarket|convenience|greengrocer|butcher)$"]',
    '["amenity"="toilets"]',
    '["amenity"~"^(atm|bank|bureau_de_change)$"]',
    '["tourism"~"^(hotel|hostel|guest_house)$"]',
    '["amenity"="community_centre"]',
    '["club"]',
    '["shop"="books"]',
    '["man_made"="tower"]["tower:type"~"observation|viewing"]',
    '["shop"="pawnbroker"]',  # 32 ломбарда Астаны (раунд 25): деньги без налички - pawn; name-regex дублирует нетегированные
    '["amenity"~"^(dentist|clinic)$"]',  # клиники и стоматологии (раунд 26): census 2026-10-19 - dentist 49, clinic 91
    '["healthcare"~"^(dentist|clinic|doctor|centre|laboratory)$"]',  # то же по тегу healthcare (в т.ч. кабинеты врача)
    '["amenity"="post_office"]',  # почтовые отделения (раунд 26): census 2026-10-19 - post_office 50/50 named
]
EXTRA_NAME_FILTER = {
    ("amenity", "community_centre"): re.compile(r"дворец|сарай|мәдениет|культур|палас|palace|cultur", re.I),
    ("shop", "books"): re.compile(r"coffee|кофе|cafe|кафе", re.I),
    # members-only gyms and boxing clubs are not a place to visit; ski bases, rinks, riding and rowing clubs are
    ("club", "sport"): re.compile(r"лыж|\bski\b|каток|\bskat|\bice\b|конн|\bhorse|яхт|\byacht|гребн|\browing", re.I),
    # a pawnshop without a name cannot be told apart from the bank/ATM cards of the same category, and the
    # generated "Банкомат" would lie about it: keep only named ones (the 32 of round 25 all carry names)
    ("shop", "pawnbroker"): re.compile(r".+", re.S),
}

# Railway / LRT / train stations (kept for routing, not for recommendations).
TRANSIT_SELECTORS = [
    '["railway"~"^(station|halt)$"]',
    '["public_transport"="station"]["train"="yes"]',
    '["public_transport"="station"]["light_rail"="yes"]',
    '["public_transport"="station"]["station"~"^(light_rail|light_train|train)$"]',
]

# First matching rule wins (order = priority).
CATEGORY_RULES: list[tuple[str, str, str]] = [
    ("leisure", "playground", "kids_playground"),
    ("tourism", "viewpoint", "viewpoint"),
    ("tourism", "museum", "museum_gallery"),
    ("amenity", "museum", "museum_gallery"),
    ("tourism", "gallery", "museum_gallery"),
    ("amenity", "cinema", "culture_theatre_cinema"),
    ("amenity", "theatre", "culture_theatre_cinema"),
    ("amenity", "arts_centre", "culture_theatre_cinema"),
    ("amenity", "library", "coworking_library"),
    ("amenity", "coworking_space", "coworking_library"),
    ("office", "coworking", "coworking_library"),
    ("amenity", "nightclub", "bar_nightlife"),
    ("amenity", "bar", "bar_nightlife"),
    ("amenity", "pub", "bar_nightlife"),
    ("amenity", "restaurant", "restaurant"),
    ("amenity", "fast_food", "fast_food"),
    ("amenity", "cafe", "cafe"),
    ("amenity", "ice_cream", "cafe"),
    ("shop", "mall", "mall"),
    ("tourism", "theme_park", "entertainment"),
    ("tourism", "zoo", "entertainment"),
    ("tourism", "aquarium", "entertainment"),
    ("leisure", "water_park", "entertainment"),
    ("leisure", "amusement_arcade", "entertainment"),
    ("leisure", "escape_game", "entertainment"),
    ("leisure", "bowling_alley", "entertainment"),
    ("leisure", "trampoline_park", "entertainment"),
    ("leisure", "sports_centre", "sport"),
    ("leisure", "park", "park_garden"),
    ("leisure", "garden", "park_garden"),
    ("tourism", "attraction", "attraction_landmark"),
    ("tourism", "artwork", "attraction_landmark"),
    ("historic", "*", "attraction_landmark"),
    ("amenity", "place_of_worship", "attraction_landmark"),
    ("leisure", "ice_rink", "sport"),
    ("leisure", "swimming_pool", "sport"),
    ("railway", "station", "transit_station"),
    ("railway", "halt", "transit_station"),
    ("public_transport", "station", "transit_station"),
    # EXTRA_SELECTORS only (appended so no record of the first request can change its category)
    ("leisure", "indoor_play", "entertainment"),
    ("playground", "indoor", "entertainment"),
    ("amenity", "planetarium", "museum_gallery"),
    ("amenity", "events_venue", "culture_theatre_cinema"),
    ("amenity", "community_centre", "culture_theatre_cinema"),
    ("amenity", "fountain", "attraction_landmark"),
    ("amenity", "toilets", "public_toilet"),
    ("amenity", "atm", "money"),
    ("amenity", "bank", "money"),
    ("amenity", "bureau_de_change", "money"),
    ("shop", "pawnbroker", "money"),  # 32 ломбарда (раунд 25): деньги без налички; card name says which subtype
    # клиники и стоматологии (раунд 26): именованный слой — безымянные (GENERATED_NAMES нет) normalizer выбрасывает
    ("amenity", "dentist", "clinic"),
    ("amenity", "clinic", "clinic"),
    ("healthcare", "dentist", "clinic"),
    ("healthcare", "clinic", "clinic"),
    ("healthcare", "doctor", "clinic"),
    ("healthcare", "centre", "clinic"),  # медцентр по тегу healthcare; спорт-«центр» ловит leisure=*, а не healthcare
    ("healthcare", "laboratory", "clinic"),
    ("amenity", "post_office", "post"),  # почтовые отделения (раунд 26): census 50/50 named, безымянных нет
    ("tourism", "hotel", "lodging"),
    ("tourism", "hostel", "lodging"),
    ("tourism", "guest_house", "lodging"),
    ("amenity", "pharmacy", "pharmacy"),
    ("shop", "supermarket", "grocery"),
    ("shop", "convenience", "grocery"),
    ("shop", "greengrocer", "grocery"),
    ("shop", "butcher", "grocery"),
    ("club", "sport", "sport"),
    ("shop", "books", "cafe"),
    ("man_made", "tower", "viewpoint"),
]

CATEGORIES = [
    "cafe", "restaurant", "fast_food", "bar_nightlife", "museum_gallery", "attraction_landmark",
    "viewpoint", "park_garden", "kids_playground", "entertainment", "mall", "public_toilet", "pharmacy", "grocery",
    "culture_theatre_cinema", "coworking_library", "sport", "transit_station", "money", "lodging", "clinic", "post", "other",
]

# Unnamed items kept with a generated name (category -> base name).
GENERATED_NAMES = {
    "kids_playground": "Детская площадка",
    "viewpoint": "Смотровая площадка",
    "park_garden": "Парк / сквер",
    "public_toilet": "Туалет",
    "money": "Банкомат",  # unnamed ATMs are most of the 309; the card then reads «Банкомат (улица)»
}

# `leisure=playground` + `indoor=yes` (8 records in Astana, all inside buildings) is an indoor play area: the app treats
# `kids_playground` as outdoor and drops it in frost / smog, exactly when a child needs an indoor place.
INDOOR_PLAYGROUND_NAME = "Детская площадка в помещении"

KEPT_TAG_KEYS = (
    "amenity", "tourism", "leisure", "shop", "historic", "office", "cuisine", "outdoor_seating",
    "internet_access", "wheelchair", "opening_hours", "website", "phone", "artwork_type",
    "museum", "attraction", "sport", "fee", "power_supply", "socket", "smoking", "takeaway",
    "delivery", "operator", "brand", "payment:cards", "min_age", "max_age", "access", "surface", "indoor", "outdoor",
    "religion", "denomination", "railway", "public_transport", "station", "train", "light_rail", "network",
    "wikidata", "wikipedia", "name:kk", "name:en", "brand:wikidata",
)

# Tag keys kept only for EXTRA_SELECTORS records (adding them to KEPT_TAG_KEYS would rewrite existing records).
EXTRA_KEPT_TAG_KEYS = ("club", "playground", "tower:type", "man_made", "building")

DEDUP_RADIUS_M = 50.0


def build_query(area_id: int) -> str:
    parts = []
    for key, values in SELECTORS.items():
        regex = "|".join(values)
        parts.append(f'  nwr(area.a)["{key}"~"^({regex})$"];')
    parts.append('  nwr(area.a)["historic"];')
    parts.append('  nwr(area.a)["office"="coworking"];')
    parts.extend(f"  nwr(area.a){sel};" for sel in TRANSIT_SELECTORS)
    body = "\n".join(parts)
    return (
        f"[out:json][timeout:{TIMEOUT}];\n"
        f"area({area_id})->.a;\n(\n{body}\n);\nout center tags;\n"
    )


def build_extra_queries(area_id: int) -> list[str]:
    return [f"[out:json][timeout:120];\narea({area_id})->.a;\nnwr(area.a){sel};\nout center tags;\n"
            for sel in EXTRA_SELECTORS]


def build_area_query() -> str:
    return (
        f"[out:json][timeout:60];\n"
        f'rel["boundary"="administrative"]["name"="{AREA_NAME}"];\n'
        f"out tags bb;\n"
    )


def overpass(net: Net, query: str) -> tuple[dict, float]:
    """POST a query via the polite layer; an answer cached under any endpoint wins (no request while a mirror is
    down), otherwise fall over to the next mirror only if the previous one fails outright.

    Returns (json, fetched_at epoch seconds) — fetched_at is the cache time, so reruns are identical.
    """
    for url in ENDPOINTS:
        if (hit := net.cached("POST", url, data={"data": query})) is not None:
            try:
                return hit.json(), hit.fetched_at
            except ValueError:
                pass
    last_error: Exception | None = None
    for url in ENDPOINTS:
        try:
            resp = net.post(url, data={"data": query}, timeout=TIMEOUT)
            return resp.json(), resp.fetched_at
        except (NetError, ValueError) as exc:  # NetError after retries; ValueError: HTML/XML with HTTP 200
            last_error = exc
            print(f"[overpass] {url}: {exc!r}", file=sys.stderr)
    raise RuntimeError(f"Overpass failed on all endpoints: {last_error!r}")


def resolve_area(net: Net) -> tuple[int, dict]:
    """Find the Astana admin relation; verify its bbox; return (area id, bounds)."""
    data, _ = overpass(net, build_area_query())
    candidates = []
    for el in data.get("elements", []):
        b = el.get("bounds")
        if el.get("type") != "relation" or not b:
            continue
        in_range = (
            LAT_RANGE[0] <= b["minlat"] and b["maxlat"] <= LAT_RANGE[1]
            and LON_RANGE[0] <= b["minlon"] and b["maxlon"] <= LON_RANGE[1]
        )
        center_ok = (
            CENTER_LAT_RANGE[0] <= (b["minlat"] + b["maxlat"]) / 2 <= CENTER_LAT_RANGE[1]
            and CENTER_LON_RANGE[0] <= (b["minlon"] + b["maxlon"]) / 2 <= CENTER_LON_RANGE[1]
        )
        if not (in_range and center_ok):
            continue
        level = int(el.get("tags", {}).get("admin_level", 99) or 99)
        candidates.append((level, el["id"], b))
    if not candidates:
        raise RuntimeError(
            f"No administrative relation '{AREA_NAME}' with bbox inside {LAT_RANGE}/{LON_RANGE}"
        )
    candidates.sort()
    _, rel_id, bounds = candidates[0]
    return 3_600_000_000 + rel_id, bounds


def match_rule(tags: dict) -> tuple[str, str | None, str | None]:
    """Return (category, matched key, matched actual value)."""
    if tags.get("leisure") == "playground" and tags.get("indoor") == "yes":
        return "entertainment", "leisure", "playground"
    for key, value, category in CATEGORY_RULES:
        if key in tags and (value == "*" or tags[key] == value):
            return category, key, tags[key]
    return "other", None, None


def classify(tags: dict) -> str:
    return match_rule(tags)[0]


def pick_name(tags: dict) -> tuple[str | None, dict]:
    names = {}
    for key in ("name:ru", "name", "name:kk", "name:en"):
        if tags.get(key):
            names[key] = tags[key].strip()
    name = next(iter(names.values()), None)
    return name, names


def build_address(tags: dict) -> str | None:
    street = tags.get("addr:street")
    house = tags.get("addr:housenumber")
    head = ", ".join(p for p in (street, house) if p)
    parts = [tags.get("addr:city"), head or None]
    if not street and tags.get("addr:place"):
        parts.insert(1, tags["addr:place"])
    text = ", ".join(p for p in parts if p)
    return text or None


def coords(el: dict) -> tuple[float, float] | None:
    if el["type"] == "node":
        return el.get("lat"), el.get("lon")
    c = el.get("center")
    return (c["lat"], c["lon"]) if c else None


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6_371_000 * math.asin(math.sqrt(a))


SUBTYPE_RU = {
    ("amenity", "cafe"): "Кафе",
    ("amenity", "restaurant"): "Ресторан",
    ("amenity", "fast_food"): "Заведение быстрого питания",
    ("amenity", "bar"): "Бар",
    ("amenity", "pub"): "Паб",
    ("amenity", "nightclub"): "Ночной клуб",
    ("amenity", "cinema"): "Кинотеатр",
    ("amenity", "theatre"): "Театр",
    ("amenity", "arts_centre"): "Центр искусств",
    ("amenity", "library"): "Библиотека",
    ("amenity", "coworking_space"): "Коворкинг",
    ("office", "coworking"): "Коворкинг",
    ("amenity", "ice_cream"): "Кафе-мороженое",
    ("tourism", "museum"): "Музей",
    ("tourism", "gallery"): "Галерея",
    ("tourism", "attraction"): "Достопримечательность",
    ("tourism", "viewpoint"): "Смотровая площадка",
    ("tourism", "artwork"): "Арт-объект",
    ("tourism", "theme_park"): "Парк развлечений",
    ("tourism", "zoo"): "Зоопарк",
    ("tourism", "aquarium"): "Аквариум",
    ("leisure", "park"): "Парк",
    ("leisure", "garden"): "Сад",
    ("leisure", "playground"): "Детская площадка",
    ("leisure", "water_park"): "Аквапарк",
    ("leisure", "amusement_arcade"): "Зал игровых автоматов",
    ("leisure", "sports_centre"): "Спортивный центр",
    ("leisure", "escape_game"): "Квест-комната",
    ("leisure", "bowling_alley"): "Боулинг",
    ("leisure", "trampoline_park"): "Батутный парк",
    ("shop", "mall"): "Торговый центр",
    ("amenity", "museum"): "Музей",
    ("amenity", "place_of_worship"): "Культовое здание",
    ("leisure", "ice_rink"): "Каток",
    ("leisure", "swimming_pool"): "Бассейн",
    ("railway", "station"): "Железнодорожная станция",
    ("railway", "halt"): "Железнодорожная остановка",
    ("public_transport", "station"): "Транспортная станция",
    ("leisure", "indoor_play"): "Детский игровой центр",
    ("playground", "indoor"): "Детский игровой центр",
    ("amenity", "planetarium"): "Планетарий",
    ("amenity", "events_venue"): "Площадка для мероприятий",
    ("amenity", "community_centre"): "Дворец / центр культуры",
    ("amenity", "fountain"): "Фонтан",
    ("amenity", "toilets"): "Публичный туалет",
    ("amenity", "atm"): "Банкомат",
    ("amenity", "bank"): "Отделение банка",
    ("amenity", "bureau_de_change"): "Обмен валют",
    ("tourism", "hotel"): "Гостиница",
    ("tourism", "hostel"): "Хостел",
    ("tourism", "guest_house"): "Гостевой дом",
    ("amenity", "pharmacy"): "Аптека",
    ("shop", "supermarket"): "Супермаркет",
    ("shop", "convenience"): "Магазин у дома",
    ("shop", "greengrocer"): "Овощной магазин",
    ("shop", "butcher"): "Мясной магазин",
    ("club", "sport"): "Спортивный клуб",
    ("shop", "books"): "Книжный магазин-кафе",
    ("man_made", "tower"): "Смотровая башня",
}

RELIGION_RU = {
    "muslim": "ислам", "christian": "христианство", "buddhist": "буддизм", "jewish": "иудаизм",
}

DENOMINATION_RU = {
    "orthodox": "православие", "russian_orthodox": "православие", "catholic": "католицизм",
    "roman_catholic": "католицизм", "protestant": "протестантизм", "sunni": "сунниты",
    "baptist": "баптисты", "lutheran": "лютеране", "evangelical": "евангелисты",
}

HISTORIC_RU = {
    "monument": "Памятник", "memorial": "Мемориал", "archaeological_site": "Археологический объект",
    "building": "Историческое здание", "castle": "Замок", "ruins": "Руины",
    "wayside_cross": "Придорожный крест", "wayside_shrine": "Придорожная святыня",
    "fort": "Крепость", "manor": "Усадьба", "tomb": "Захоронение", "city_gate": "Городские ворота",
    "battlefield": "Место сражения", "church": "Историческая церковь", "mosque": "Историческая мечеть",
    "yes": "Историческое место",
}

ARTWORK_RU = {
    "statue": "статуя", "sculpture": "скульптура", "mural": "мурал", "installation": "инсталляция",
    "bust": "бюст", "graffiti": "граффити", "mosaic": "мозаика", "relief": "рельеф",
    "architecture": "архитектурный объект", "stone": "каменная скульптура",
}

MUSEUM_RU = {
    "history": "исторический", "art": "художественный", "science": "научный", "technology": "технический",
    "local": "краеведческий", "natural": "естествознания", "military": "военный", "children": "детский",
    "aviation": "авиационный", "railway": "железнодорожный", "archaeological": "археологический",
}

CUISINE_RU = {
    "italian": "итальянская", "japanese": "японская", "sushi": "суши", "pizza": "пицца", "burger": "бургеры",
    "coffee_shop": "кофе", "kazakh": "казахская", "uzbek": "узбекская", "turkish": "турецкая",
    "georgian": "грузинская", "chinese": "китайская", "korean": "корейская", "asian": "азиатская",
    "russian": "русская", "european": "европейская", "steak_house": "стейки", "french": "французская",
    "indian": "индийская", "american": "американская", "mediterranean": "средиземноморская",
    "vietnamese": "вьетнамская", "thai": "тайская", "regional": "региональная", "international": "интернациональная",
    "kebab": "кебаб", "shawarma": "шаурма", "chicken": "курица", "seafood": "морепродукты",
    "bakery": "выпечка", "dessert": "десерты", "ice_cream": "мороженое", "tea": "чай", "coffee": "кофе",
    "sandwich": "сэндвичи", "donut": "пончики", "vegetarian": "вегетарианская", "vegan": "веганская",
    "uyghur": "уйгурская", "tatar": "татарская", "ukrainian": "украинская", "german": "немецкая",
    "mexican": "мексиканская", "arab": "арабская", "lebanese": "ливанская", "dumplings": "пельмени",
}

PLAYGROUND_RU = {
    "slide": "горки", "swing": "качели", "climbingframe": "лазалки", "sandpit": "песочница",
    "seesaw": "качалки", "springy": "качалки на пружине", "roundabout": "карусель",
    "balance_beam": "бревно для равновесия", "structure": "игровой комплекс", "zipwire": "тарзанка",
    "basketswing": "гнездо-качели", "climbingwall": "скалодром", "playhouse": "домик",
    "water": "водные элементы", "trampoline": "батут", "horizontal_bar": "турник",
}


def _is_true(v: str | None) -> bool:
    return v in ("yes", "wlan", "wifi", "wired", "terminal", "designated")


def derive_description(
    tags: dict, name: str, generated: bool, category: str, key: str | None, value: str | None
) -> str:
    """Build a 1-2 sentence Russian description from raw OSM tags (no invented facts)."""
    if category == "transit_station" and (
        tags.get("station") in ("light_rail", "light_train") or tags.get("light_rail") == "yes"
    ):
        kind = "Станция лёгкого рельсового транспорта (LRT)"
    elif category == "entertainment" and (key, value) == ("leisure", "playground"):
        kind = INDOOR_PLAYGROUND_NAME
    elif key == "historic":
        kind = HISTORIC_RU.get(value or "yes", "Историческое место")
    elif key:
        kind = SUBTYPE_RU.get((key, value), "Объект")
    else:
        kind = "Объект"

    first = kind if generated else f"{kind} «{name}»"
    details = []
    if key == "tourism" and value == "artwork" and tags.get("artwork_type") in ARTWORK_RU:
        details.append(ARTWORK_RU[tags["artwork_type"]])
    if value == "museum" and key in ("tourism", "amenity") and tags.get("museum") in MUSEUM_RU:
        details.append(f"{MUSEUM_RU[tags['museum']]} профиль")
    if key == "amenity" and value == "place_of_worship" and tags.get("religion"):
        religion = RELIGION_RU.get(tags["religion"], tags["religion"])
        denom = DENOMINATION_RU.get(tags.get("denomination", ""))
        details.append(f"{religion}, {denom}" if denom else religion)
    if key == "amenity" and tags.get("cuisine"):
        cuisines = [CUISINE_RU.get(c.strip(), c.strip().replace("_", " ")) for c in tags["cuisine"].split(";") if c.strip()]
        if cuisines:
            details.append("кухня: " + ", ".join(cuisines[:3]))
    if tags.get("operator") and tags["operator"] != name:
        details.append(f"оператор: {tags['operator']}")
    if details:
        first += " (" + "; ".join(details) + ")"
    addr = build_address(tags)
    first += f" по адресу {addr}." if addr else " в Астане."

    feats = []
    ia = tags.get("internet_access")
    if _is_true(ia):
        feats.append("есть Wi-Fi" if ia in ("wlan", "wifi", "yes") else "есть интернет")
    if tags.get("outdoor_seating") == "yes":
        feats.append("есть места на улице")
    wc = tags.get("wheelchair")
    if wc == "yes":
        feats.append("доступно для колясок")
    elif wc == "limited":
        feats.append("частично доступно для колясок")
    elif wc == "no":
        feats.append("не приспособлено для колясок")
    if category == "kids_playground":
        eq = [PLAYGROUND_RU[k.split(":", 1)[1]] for k in tags
              if k.startswith("playground:") and tags[k] == "yes" and k.split(":", 1)[1] in PLAYGROUND_RU]
        if eq:
            feats.append("оборудование: " + ", ".join(sorted(set(eq))))
        if tags.get("min_age") or tags.get("max_age"):
            lo, hi = tags.get("min_age"), tags.get("max_age")
            feats.append(f"возраст детей: {lo or '0'}–{hi}" if hi else f"возраст детей: от {lo}")
    if tags.get("fee") == "yes":
        feats.append("вход платный")
    elif tags.get("fee") == "no":
        feats.append("вход бесплатный")
    oh = tags.get("opening_hours")
    if oh == "24/7":
        feats.append("работает круглосуточно")
    elif oh:
        feats.append("часы работы: " + (oh if len(oh) <= 60 else "указаны на карте OSM"))

    if feats:
        second = feats[0][0].upper() + feats[0][1:]
        if len(feats) > 1:
            second += ", " + ", ".join(feats[1:])
        second += "."
    else:
        second = "Подробности (часы работы, контакты) в OpenStreetMap не указаны."
    return f"{first} {second}"


def normalize(el: dict, collected_at: str, extra: bool = False) -> dict | None:
    tags = el.get("tags") or {}
    pos = coords(el)
    if not pos or pos[0] is None:
        return None
    lat, lon = pos
    category, rule_key, rule_value = match_rule(tags)
    if extra and category == "other":
        return None
    name, names = pick_name(tags)
    if extra and (rx := EXTRA_NAME_FILTER.get((rule_key, rule_value))) and not (name and rx.search(name)):
        return None
    generated = False
    address = build_address(tags)
    if not name:
        base = GENERATED_NAMES.get(category) or (
            INDOOR_PLAYGROUND_NAME if (rule_key, rule_value, category) == ("leisure", "playground", "entertainment")
            else None)
        if not base:
            return None
        street = tags.get("addr:street")
        name = f"{base} ({street})" if street else base
        generated = True
    description = (tags.get("description:ru") or tags.get("description") or "").strip() or None
    if description:
        description_auto, description_source = description, "osm"
    else:
        description_auto = derive_description(tags, name, generated, category, rule_key, rule_value)
        description_source = "derived"
    return {
        "id": f"{el['type']}/{el['id']}",
        "name": name,
        "name_generated": generated,
        "names": names,
        "lat": round(lat, 7),
        "lon": round(lon, 7),
        "category": category,
        "tags": [f"{k}={tags[k]}" for k in KEPT_TAG_KEYS + (EXTRA_KEPT_TAG_KEYS if extra else ()) if k in tags],
        "opening_hours": tags.get("opening_hours"),
        "website": tags.get("website") or tags.get("contact:website") or tags.get("url"),
        "phone": tags.get("phone") or tags.get("contact:phone"),
        "address": address,
        "wheelchair": tags.get("wheelchair"),
        "internet_access": tags.get("internet_access"),
        "outdoor_seating": tags.get("outdoor_seating"),
        "description": description,
        "description_auto": description_auto,
        "description_source": description_source,
        "source": "osm",
        "collected_at": collected_at,
    }


def richness(poi: dict) -> int:
    fields = ("opening_hours", "website", "phone", "address", "wheelchair", "internet_access",
              "outdoor_seating", "description")
    bonus = 50 if any(t.startswith(("wikidata=", "wikipedia=")) for t in poi["tags"]) else 0
    return sum(1 for f in fields if poi[f]) * 100 + len(poi["tags"]) + len(poi["names"]) + bonus


STATION_DEDUP_RADIUS_M = 150.0


def station_key(poi: dict) -> tuple[str, str]:
    """(network, kind) of a transit station: the same physical stop is mapped as node and way."""
    tags = dict(t.partition("=")[::2] for t in poi["tags"])
    if tags.get("station") in ("light_rail", "light_train") or tags.get("light_rail") == "yes":
        kind = "light_rail"
    elif tags.get("train") == "yes" or tags.get("railway") in ("station", "halt"):
        kind = "train"
    else:
        kind = "other"
    return tags.get("network", ""), kind


def dedupe_stations(pois: list[dict]) -> list[dict]:
    """One record per (network, kind) station within STATION_DEDUP_RADIUS_M regardless of name.

    Clusters are seeded richest-first (so same-name duplicates resolve exactly as before). When the names in
    a cluster disagree (a typo in one of them), the way wins over the node, then the richer record.
    """
    clusters: dict[tuple[str, str], list[list[dict]]] = {}
    for poi in sorted(pois, key=lambda p: (-richness(p), p["id"])):
        groups = clusters.setdefault(station_key(poi), [])
        for cluster in groups:
            if any(haversine_m(poi["lat"], poi["lon"], o["lat"], o["lon"]) <= STATION_DEDUP_RADIUS_M for o in cluster):
                cluster.append(poi)
                break
        else:
            groups.append([poi])
    kept: list[dict] = []
    for groups in clusters.values():
        for cluster in groups:
            if len({p["name"].casefold() for p in cluster}) > 1:
                cluster = sorted(cluster, key=lambda p: (not p["id"].startswith("way/"), -richness(p), p["id"]))
            kept.append(cluster[0])
    return kept


def dedupe(pois: list[dict]) -> list[dict]:
    """Drop same-name POIs within DEDUP_RADIUS_M (richest wins); stations by network/kind + distance."""
    stations = dedupe_stations([p for p in pois if p["category"] == "transit_station"])
    rest = [p for p in pois if p["category"] != "transit_station"]
    by_name: dict[str, list[dict]] = {}
    kept: list[dict] = list(stations)
    for poi in sorted(rest, key=lambda p: (-richness(p), p["id"])):
        if poi["name_generated"]:
            kept.append(poi)
            continue
        key = poi["name"].casefold()
        group = by_name.setdefault(key, [])
        if any(haversine_m(poi["lat"], poi["lon"], o["lat"], o["lon"]) <= DEDUP_RADIUS_M for o in group):
            continue
        group.append(poi)
        kept.append(poi)
    return kept


def pct(part: int, whole: int) -> float:
    return round(100 * part / whole, 1) if whole else 0.0


def compute_stats(pois: list[dict]) -> dict:
    total = len(pois)
    per_cat = {c: [p for p in pois if p["category"] == c] for c in CATEGORIES}
    return {
        "total": total,
        "count_per_category": {c: len(v) for c, v in per_cat.items()},
        "pct_opening_hours_per_category": {
            c: pct(sum(1 for p in v if p["opening_hours"]), len(v)) for c, v in per_cat.items()
        },
        "pct_opening_hours_total": pct(sum(1 for p in pois if p["opening_hours"]), total),
        "pct_real_description": pct(sum(1 for p in pois if p["description_source"] == "osm"), total),
        "pct_derived_description": pct(sum(1 for p in pois if p["description_source"] == "derived"), total),
        "pct_real_description_per_category": {
            c: pct(sum(1 for p in v if p["description_source"] == "osm"), len(v)) for c, v in per_cat.items()
        },
        "pct_derived_description_per_category": {
            c: pct(sum(1 for p in v if p["description_source"] == "derived"), len(v)) for c, v in per_cat.items()
        },
        "count_without_any_description": sum(1 for p in pois if not p["description_auto"]),
        "pct_website": pct(sum(1 for p in pois if p["website"]), total),
        "count_wheelchair_tag": sum(1 for p in pois if p["wheelchair"]),
        "count_internet_access_tag": sum(1 for p in pois if p["internet_access"]),
        "count_outdoor_seating_tag": sum(1 for p in pois if p["outdoor_seating"]),
        "count_name_generated": sum(1 for p in pois if p["name_generated"]),
        "count_lrt_stations": len({p["id"] for p in per_cat["transit_station"]
                                   if station_key(p) == ("Tarlan Astana", "light_rail")}),
        "count_with_wikidata_tag": sum(1 for p in pois if any(t.startswith("wikidata=") for t in p["tags"])),
        "count_with_wikipedia_tag": sum(1 for p in pois if any(t.startswith("wikipedia=") for t in p["tags"])),
        "count_with_wikidata_or_wikipedia_tag": sum(
            1 for p in pois if any(t.startswith(("wikidata=", "wikipedia=")) for t in p["tags"])),
        "count_with_name_kk": sum(1 for p in pois if "name:kk" in p["names"]),
        "count_with_name_en": sum(1 for p in pois if "name:en" in p["names"]),
        "count_with_brand": sum(1 for p in pois if any(t.startswith("brand=") for t in p["tags"])),
        "count_with_brand_wikidata": sum(1 for p in pois if any(t.startswith("brand:wikidata=") for t in p["tags"])),
    }


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(obj, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    tmp.replace(path)


def add_extra(pois: list[dict], main_ids: set[str], data: dict, collected_at: str) -> list[dict]:
    """POIs of the EXTRA_SELECTORS request that the first request did not return: never overrides, never removes
    a first-request record (same-name neighbours within DEDUP_RADIUS_M lose against the existing one)."""
    raw = [p for el in data.get("elements", []) if f"{el['type']}/{el['id']}" not in main_ids
           and (p := normalize(el, collected_at, extra=True))]
    by_name: dict[str, list[dict]] = {}
    for p in pois:
        by_name.setdefault(p["name"].casefold(), []).append(p)
    out = []
    for p in dedupe(raw):
        if any(haversine_m(p["lat"], p["lon"], o["lat"], o["lon"]) <= DEDUP_RADIUS_M
               for o in by_name.get(p["name"].casefold(), ())):
            continue
        out.append(p)
    return out


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=DEFAULT_OUT, help=f"output POI file (default: {DEFAULT_OUT})")
    args = parser.parse_args(argv)
    out = Path(args.out)
    if out.name == "poi.json":
        raise SystemExit("refusing to overwrite data/poi.json (frozen app input); use another --out")

    net = default_net()
    area_id, bounds = resolve_area(net)
    print(f"[area] id={area_id} bbox={bounds}", file=sys.stderr)
    data, fetched_at = overpass(net, build_query(area_id))

    collected_at = datetime.fromtimestamp(fetched_at, timezone.utc).replace(microsecond=0).isoformat()
    raw = [p for el in data.get("elements", []) if (p := normalize(el, collected_at))]
    pois = dedupe(raw)
    extra_els: dict[str, dict] = {}
    extra_fetched = 0.0
    for query in build_extra_queries(area_id):
        part, stamp = overpass(net, query)
        extra_fetched = max(extra_fetched, stamp)
        extra_els.update({f"{el['type']}/{el['id']}": el for el in part.get("elements", [])})
    extra_at = datetime.fromtimestamp(extra_fetched, timezone.utc).replace(microsecond=0).isoformat()
    extra = add_extra(pois, {p["id"] for p in raw}, {"elements": list(extra_els.values())}, extra_at)
    print(f"[extra] elements={len(extra_els)} new_records={len(extra)}", file=sys.stderr)
    pois = sorted(pois + extra, key=lambda p: p["id"])

    lats = [p["lat"] for p in pois]
    lons = [p["lon"] for p in pois]
    if not pois or not (LAT_RANGE[0] <= min(lats) and max(lats) <= LAT_RANGE[1]
                        and LON_RANGE[0] <= min(lons) and max(lons) <= LON_RANGE[1]):
        raise RuntimeError("POI bbox outside expected Astana range; refusing to write output")

    stats = compute_stats(pois)
    write_json(out, pois)
    write_json(out.with_name(out.stem + "_stats.json"), stats)
    print(f"[done] elements={len(data.get('elements', []))} normalized={len(raw)} "
          f"after_dedup={len(pois)} -> {out}", file=sys.stderr)
    net.log_summary("osm")
    print(json.dumps({k: stats[k] for k in stats if k.startswith(("total", "count_with", "count_lrt"))},
                     ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
