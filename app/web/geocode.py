"""The address search of «Где вы?»: `GET /api/geocode?q=&lang=` -> up to five points inside Astana.

Three sources, all local files (no network, nothing leaves the server, the query is never logged or kept):
  * houses and streets from OpenStreetMap (`data/gazetteer/astana_addresses.json`, collect/osm_addresses.py, ODbL);
  * street spellings of the state gazetteer (`data/gazetteer/astana_streets.json`, names only): they widen what a
    street answers to, they carry no positions;
  * the names of our own places (`data/poi.enriched.json`).

A query is folded to one skeleton before it is compared (Russian, Kazakh and Latin spellings of one name meet: «Мәңгілік»,
«Мангилик», «Mangilik»), street-type words (улица, көшесі, проспект, avenue ...) are dropped, and a house number may stand
before or after the street («Кенесары 40», «Кенесары, 40», «40 Кенесары», «Мәңгілік Ел 55/22»). A typo costs a few
points, not the answer. Ranking: an exact house, then a street, then a place."""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from functools import lru_cache
from pathlib import Path

from rapidfuzz import fuzz, process

from walks.districts import District, district_of, load_districts
from walks.i18n import norm
from walks.models import poi_path

ROOT = Path(__file__).resolve().parents[2]
GAZETTEER = ROOT / "data" / "gazetteer"
ADDRESSES = GAZETTEER / "astana_addresses.json"
STREETS = GAZETTEER / "astana_streets.json"
DISTRICTS = ROOT / "data" / "districts.geojson"
LIMIT = 5
QUERY_MAX = 100
FUZZY_MIN = 80  # a typo must keep at least this similarity (0-100)
KIND_BONUS = {"house": 20, "street": 10}  # a house beats a street beats a place of the same match
BIG_STREET = (
    20  # houses a street needs for the full bonus: a lane of two houses is not «the» street
)
NEAR_M = 120  # a point this close to a house is «at» it (reverse)
CLOSE = 25  # a hit this far below the best one is noise
TYPO_MIN_HOUSES = 5  # a street of a house or two is found by its name, never by a near miss (OSM has typos of its own)
SHOWN = {
    "cafe": -8,
    "restaurant": -8,
    "fast_food": -8,
    "bar_nightlife": -8,
}  # a cafe is rarely «where I am»
SKIP_CATEGORIES = frozenset({"kids_playground", "other"})

# words that say «this is a street» (raw spellings, before the fold): never part of what is compared
STREET_TYPES = frozenset(
    [
        "улица",
        "ул",
        "көше",
        "көшесі",
        "кошеси",
        "проспект",
        "просп",
        "пр",
        "пр-т",
        "даңғыл",
        "даңғылы",
        "дангылы",
        "дангилы",
        "avenue",
        "ave",
        "street",
        "st",
        "str",
        "переулок",
        "пер",
        "бульвар",
        "бул",
        "б-р",
        "шоссе",
        "тракт",
        "площадь",
        "пл",
        "набережная",
        "наб",
        "тупик",
        "микрорайон",
        "мкр",
        "шағын",
        "аудан",
        "ауданы",
        "район",
        "алаңы",
        "lane",
        "road",
        "rd",
        "boulevard",
        "blvd",
    ]
)
HOUSE_WORDS = frozenset({"д", "дом", "уй", "үй", "house", "no", "n"})
NUMBER = re.compile(r"^\d+[a-zа-яәіңғүұқөһ]?(?:[/\-]\d+[a-zа-я]?)*$")

_LAT_DIGRAPHS = (
    ("sh", "ш"), ("ch", "ч"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"), ("ya", "я"), ("yu", "ю"),
    ("yo", "е"), ("ye", "е"), ("ph", "ф"), ("ay", "аи"), ("ey", "еи"), ("oy", "ои"), ("uy", "уи"),
)  # fmt: skip
_LAT = str.maketrans(
    {
        **dict(
            zip(
                "abcdefghijklmnopqrstuvwyzäöüıñğşç",
                "абкдефгхижклмнопкрстуввизаоуингшч",
                strict=True,
            )
        ),
        "x": "кс",
    }
)
_CYR = str.maketrans(
    {"ё": "е", "э": "е", "й": "и", "ы": "и", "і": "и", "ә": "а", "ө": "о", "ү": "у", "ұ": "у", "қ": "к",
     "ң": "н", "ғ": "г", "һ": "х", "щ": "ш", "ъ": "", "ь": "", "ц": "с"}
)  # fmt: skip
_LOOKALIKE = str.maketrans(
    "abcekmhoptx", "авсекмнорте"
)  # a Latin letter typed for a Cyrillic one in a house number
_KK_LETTERS = re.compile("[әіңғүұқөһӘІҢҒҮҰҚӨҺ]")
_KK_WORDS = re.compile(r"көше|даңғыл|шағын|ауданы", re.IGNORECASE)
_CYRILLIC = re.compile("[а-яёәіңғүұқөһ]", re.IGNORECASE)
_WORDS = re.compile(r"[^\w/\-]+")


def fold(text: str) -> str:
    """One skeleton for Russian, Kazakh and Latin spellings of a name; street-type words are gone."""
    words = [
        w for w in _WORDS.sub(" ", text.casefold()).split() if w.strip("-") not in STREET_TYPES
    ]
    out = []
    for word in words:
        if not _CYRILLIC.search(word):
            for lat, cyr in _LAT_DIGRAPHS:
                word = word.replace(lat, cyr)
            word = word.translate(_LAT)
        out.append(word.translate(_CYR))
    return " ".join(w for w in out if w)


def number_key(text: str) -> str:
    return text.casefold().replace(" ", "").translate(_LOOKALIKE).replace("ё", "е")


def script_of(name: str) -> str:
    """The language a spelling of OSM is in: kk (its letters / its type words), ru (other Cyrillic), en (Latin)."""
    if _KK_LETTERS.search(name) or _KK_WORDS.search(name):
        return "kk"
    return "ru" if _CYRILLIC.search(name) else "en"


def pick_name(names: dict[str, str], lang: str) -> str:
    """The spelling of a name in the language of the page, else the nearest one."""
    order = {"kk": ("kk", "ru", "en"), "ru": ("ru", "kk", "en"), "en": ("en", "ru", "kk")}[lang]
    return next(names[k] for k in order if k in names)


# ---------------------------------------------------------------- the index


@dataclass(frozen=True)
class Entry:
    kind: str  # street | place
    names: dict[str, str]  # lang -> spelling
    keys: tuple[str, ...]  # folded spellings the query is compared with
    lat: float
    lon: float
    weight: int = 0


@dataclass
class Index:
    streets: list[Entry] = field(default_factory=list)
    places: list[Entry] = field(default_factory=list)
    houses: dict[int, dict[str, tuple[str, float, float]]] = field(default_factory=dict)
    street_keys: list[str] = field(
        default_factory=list
    )  # flat: folded key -> owner in street_owner
    street_owner: list[int] = field(default_factory=list)
    place_keys: list[str] = field(default_factory=list)
    place_owner: list[int] = field(default_factory=list)
    points: list[tuple[float, float, int, str]] = field(
        default_factory=list
    )  # every house: lat, lon, street, number


def _read(path: Path) -> dict | list | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def _gazetteer_names() -> dict[str, list[str]]:
    """Folded spelling -> the other spellings of the state gazetteer for it (aliases of old and short forms)."""
    data = _read(STREETS)
    extra: dict[str, list[str]] = {}
    for item in (data or {}).get("items", []) if isinstance(data, dict) else []:
        spellings = [item.get("name") or "", *item.get("aliases", [])]
        keys = [fold(s) for s in spellings if s]
        for key in keys:
            extra.setdefault(key, []).extend(s for s in spellings if s)
    return extra


def _near(a: dict, b: dict, km: float = 4.0) -> bool:
    return ((a["lat"] - b["lat"]) * 111) ** 2 + ((a["lon"] - b["lon"]) * 69) ** 2 < km * km


def _add_streets(index: Index) -> None:
    """One entry per street: the spellings OSM has for it (a name can be there twice, as a short road with one house or
    a typo, near the real street: those join it), its position, its houses. An `addr:street` that is a venue («ТРЦ …,
    проспект …») is no street."""
    data = _read(ADDRESSES)
    if not isinstance(data, dict):
        return
    aliases = _gazetteer_names()
    groups: list[dict] = []
    by_key: dict[str, list[int]] = {}
    group_of: dict[int, int] = {}
    for st in sorted(data.get("streets", []), key=lambda s: -s["houses"]):
        names = [n for n in st["names"] if "," not in n]
        keys = {k for n in names if (k := fold(n))}
        if not keys:
            continue
        at = next((g for k in keys for g in by_key.get(k, ()) if _near(groups[g], st)), None)
        if at is None:
            at = len(groups)
            groups.append(
                {"names": [], "keys": set(), "lat": st["lat"], "lon": st["lon"], "houses": 0}
            )
        home = groups[at]
        home["names"] += [n for n in names if n not in home["names"]]
        home["houses"] += st["houses"]
        for k in keys - home["keys"]:
            home["keys"].add(k)
            by_key.setdefault(k, []).append(at)
        group_of[st["id"]] = at
    for g in groups:
        spelled = {}
        for name in g["names"]:
            spelled.setdefault(script_of(name), name)
        keys = set(g["keys"])
        for key in g["keys"]:
            keys |= {k for a in aliases.get(key, ()) if (k := fold(a))}
        index.streets.append(
            Entry("street", spelled, tuple(sorted(keys)), g["lat"], g["lon"], weight=g["houses"])
        )
    for sid, number, lat, lon in data.get("houses", []):
        if sid in group_of:
            known = index.houses.setdefault(group_of[sid], {})
            if number_key(number) not in known:
                known[number_key(number)] = (number, lat, lon)
                index.points.append((lat, lon, group_of[sid], number))


def _add_places(index: Index) -> None:
    data = _read(poi_path())
    if not isinstance(data, list):
        return
    seen: set[tuple[str, int, int]] = set()
    for p in data:
        if p.get("name_generated") or p.get("category") in SKIP_CATEGORIES or "," in p["name"]:
            continue
        names = p.get("names") or {}
        spelled = {
            key[-2:]: names[key] for key in ("name:kk", "name:ru", "name:en") if names.get(key)
        }
        for value in (*names.values(), p["name"]):
            spelled.setdefault(script_of(value), value)
        keys = tuple(dict.fromkeys(k for v in (*names.values(), p["name"]) if (k := fold(v))))
        mark = (keys[0] if keys else "", round(p["lat"] * 1000), round(p["lon"] * 1000))
        if not keys or mark in seen:
            continue
        seen.add(mark)
        fame = min(10, int((p.get("popularity_pageviews") or 0) ** 0.5 // 8))
        index.places.append(
            Entry(
                "place",
                spelled,
                keys,
                p["lat"],
                p["lon"],
                weight=SHOWN.get(p.get("category", ""), 0) + fame,
            )
        )


def _flatten(entries: list[Entry], keys: list[str], owner: list[int]) -> None:
    for i, entry in enumerate(entries):
        for key in entry.keys:
            keys.append(key)
            owner.append(i)


@lru_cache(maxsize=1)
def index() -> Index:
    built = Index()
    _add_streets(built)
    _add_places(built)
    _flatten(built.streets, built.street_keys, built.street_owner)
    _flatten(built.places, built.place_keys, built.place_owner)
    return built


# ---------------------------------------------------------------- matching


def text_score(query: str, keys: list[str], owner: list[int]) -> dict[int, float]:
    """Entry -> best similarity (0-100) of the folded query to any of its keys; entries below the bar are absent."""
    words = query.split()
    out: dict[int, float] = {}
    for i, key in enumerate(keys):
        if key == query:
            score = 100.0
        elif len(query) >= 2 and key.startswith(query):
            score = 92.0 - min(8, (len(key) - len(query)) / 3)
        elif (len(words) > 1 or len(query) >= 3) and all(
            any(k.startswith(w) for k in key.split()) for w in words
        ):
            score = 86.0 - min(6, (len(key) - len(query)) / 6)
        else:
            continue
        j = owner[i]
        if score > out.get(j, 0):
            out[j] = score
    return out


def typo_score(
    query: str, keys: list[str], owner: list[int], known: dict[int, float]
) -> dict[int, float]:
    """The same for what the prefix rules missed: a spelling mistake, swapped words."""
    if len(query) < 4:
        return {}
    out: dict[int, float] = {}
    for scorer in (fuzz.ratio, fuzz.token_sort_ratio):
        for _, score, i in process.extract(
            query, keys, scorer=scorer, score_cutoff=FUZZY_MIN, limit=40
        ):
            j = owner[i]
            if j not in known and score * 0.96 > out.get(j, 0):
                out[j] = score * 0.96
    return out


def parse(q: str) -> list[tuple[str, str | None]]:
    """The readings of a query: [(street or place words, house number or None)], most specific first."""
    text = q.casefold().replace("№", " ").replace(",", " ").replace(";", " ")
    tokens = [t.strip(".") for t in text.split()]
    tokens = [t for t in tokens if t and t not in HOUSE_WORDS]
    readings: list[tuple[str, str | None]] = []
    if len(tokens) >= 2 and NUMBER.match(tokens[-1]):
        readings.append((" ".join(tokens[:-1]), tokens[-1]))
    elif len(tokens) >= 2 and NUMBER.match(tokens[0]):
        readings.append((" ".join(tokens[1:]), tokens[0]))
    if tokens:
        readings.append((" ".join(tokens), None))
    return readings


def _district_names() -> dict[str, dict[str, str]]:
    data = _read(DISTRICTS)
    out: dict[str, dict[str, str]] = {}
    for f in (data or {}).get("features", []) if isinstance(data, dict) else []:
        p = f.get("properties") or {}
        ru = str(p.get("name:ru") or p.get("name") or "").removeprefix("район ").strip()
        kk = str(p.get("name:kk") or "").removesuffix(" ауданы").strip()
        en = str(p.get("name:en") or "").removesuffix(" district").removesuffix(" audany").strip()
        if ru:
            out[ru] = {"ru": ru, "kk": kk or ru, "en": en or ru}
    return out


@lru_cache(maxsize=1)
def _districts() -> tuple[tuple[District, ...], dict[str, dict[str, str]]]:
    return load_districts(DISTRICTS), _district_names()


def district(lat: float, lon: float, lang: str) -> str | None:
    polygons, names = _districts()
    ru = district_of(lat, lon, polygons)
    return names.get(ru or "", {}).get(lang, ru) if ru else None


def _houses_near(index_: Index, owner: int, number: str) -> list[tuple[str, float, float]]:
    """The house of that number, else the houses whose number begins with its digits («55/22» -> «55а», «55/1»):
    what the data has, shown with its own number."""
    houses = index_.houses.get(owner, {})
    key = number_key(number)
    if key in houses:
        return [houses[key]]
    for stem in dict.fromkeys((key, re.match(r"\d+", key).group())):  # type: ignore[union-attr]
        near = [
            h
            for k, h in houses.items()
            if k.startswith(stem) and not k[len(stem) : len(stem) + 1].isdigit()
        ]
        if near:
            return sorted(near, key=lambda h: len(h[0]))[:2]
    return []


def _candidates(ix: Index, folded: str, number: str | None, lang: str) -> list[tuple[float, dict]]:
    found: list[tuple[float, dict]] = []
    streets = text_score(folded, ix.street_keys, ix.street_owner)
    typos = typo_score(folded, ix.street_keys, ix.street_owner, streets)
    streets |= {i: s for i, s in typos.items() if ix.streets[i].weight >= TYPO_MIN_HOUSES}
    for i, score in streets.items():
        e = ix.streets[i]
        label = pick_name(e.names, lang)
        if number is not None:
            for raw, lat, lon in _houses_near(ix, i, number):
                found.append(
                    (score + KIND_BONUS["house"], _hit("house", f"{label}, {raw}", lat, lon))
                )
        bonus = (
            KIND_BONUS["street"] if e.weight >= BIG_STREET else 4
        )  # a lane of two houses is not «the» street
        found.append((score + bonus, _hit("street", label, e.lat, e.lon)))
    if number is None:
        places = text_score(folded, ix.place_keys, ix.place_owner)
        places |= typo_score(folded, ix.place_keys, ix.place_owner, places)
        for i, score in places.items():
            e = ix.places[i]
            found.append((score + e.weight, _hit("place", pick_name(e.names, lang), e.lat, e.lon)))
    return found


def _km(a: dict, b: dict) -> float:
    return (((a["lat"] - b["lat"]) * 111) ** 2 + ((a["lon"] - b["lon"]) * 69) ** 2) ** 0.5


def reverse(lat: float, lon: float, lang: str | None = None) -> list[dict]:
    """The house under a point (within NEAR_M metres), as a one-element list; nothing when no house is that close."""
    lang = norm(lang)
    ix = index()
    best, best_m = None, NEAR_M
    for h_lat, h_lon, street, number in ix.points:
        m = (((h_lat - lat) * 111_000) ** 2 + ((h_lon - lon) * 69_000) ** 2) ** 0.5
        if m < best_m:
            best, best_m = (h_lat, h_lon, street, number), m
    if best is None:
        return []
    h_lat, h_lon, street, number = best
    label = f"{pick_name(ix.streets[street].names, lang)}, {number}"
    return [{**_hit("house", label, h_lat, h_lon), "district": district(h_lat, h_lon, lang)}]


def search(q: str, lang: str | None = None) -> list[dict]:
    lang = norm(lang)
    q = " ".join(q.split())[:QUERY_MAX]
    if not q:
        return []
    ix = index()
    found: list[tuple[float, dict]] = []
    for text, number in parse(q):
        folded = fold(text)
        if folded and not (folded.replace(" ", "").isdigit() and number is None):
            found += _candidates(ix, folded, number, lang)
    found.sort(key=lambda f: -f[0])
    out: list[dict] = []
    for score, hit in found:
        if score < found[0][0] - CLOSE:
            break
        # the same name twice a few hundred metres apart (a chain's branches, a stop and its landmark) is one answer
        if any(o["label"].casefold() == hit["label"].casefold() and _km(o, hit) < 1.0 for o in out):
            continue
        out.append({**hit, "district": district(hit["lat"], hit["lon"], lang)})
        if len(out) == LIMIT:
            break
    return out


def _hit(kind: str, label: str, lat: float, lon: float) -> dict:
    return {"label": label, "kind": kind, "lat": round(lat, 5), "lon": round(lon, 5)}


class _NoQuery(logging.Filter):
    """uvicorn's access line carries the whole URL; for the address search that would be what a person typed."""

    def filter(self, record: logging.LogRecord) -> bool:
        args = record.args
        if isinstance(args, tuple) and len(args) >= 3 and str(args[2]).startswith("/api/geocode"):
            record.args = (*args[:2], "/api/geocode", *args[3:])
        return True


logging.getLogger("uvicorn.access").addFilter(_NoQuery())
