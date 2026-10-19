"""Finding the place a message NAMES («какие часы у Хан Шатыра», «до скольки работает Керуен», «Starbucks открыт?»):
first the well-known places of the lexicon, then any record of the dataset whose distinctive name word the message
repeats (spelling-tolerant). The place is answered about wherever it is: its distance is a fact, not a filter."""

from __future__ import annotations

import re
from collections.abc import Sequence

from rapidfuzz import fuzz, process

from .dialog_nlu import named_place_refs, tokens
from .lexicon import match
from .models import POI
from .names import name_key
from .radius import haversine_m

TOKEN_RATIO = 88  # rapidfuzz ratio of a message word and a name word that counts as the same word
MIN_WORD = 4
LONG_WORD = 6  # letters of a name word from which an inflection («Дерева» / «Дерево») still counts as the same word
LONG_WORD_RATIO = 80
NAME_TIE_CHARS = (
    2  # a record whose name is this much longer than the shortest match is another place
)
TRANSIT = "transit_station"
# what a well-known name most likely means: the sight itself, not a restaurant that borrowed the name
_KIND_RANK = (
    "attraction_landmark", "museum_gallery", "mall", "culture_theatre_cinema", "viewpoint", "park_garden",
    "entertainment",
)  # fmt: skip
# words of a question about a place: never the name of one
_QUESTION_WORDS = frozenset(
    [
        "какие",
        "какой",
        "какая",
        "часы",
        "работы",
        "работает",
        "работают",
        "открыт",
        "открыто",
        "закрыт",
        "закрыто",
        "сейчас",
        "далеко",
        "идти",
        "дойти",
        "добраться",
        "можно",
        "внутрь",
        "адрес",
        "телефон",
        "номер",
        "сайт",
        "расскажи",
        "подробнее",
        "где",
        "находится",
        "скольки",
        "сколько",
        "когда",
        "время",
        "режим",
        "график",
        "этого",
        "этом",
        "место",
        "места",
        "про",
        "него",
        "нее",
        "это",
        "там",
        "тут",
        "есть",
        "ли",
        "open",
        "opens",
        "closed",
        "closing",
        "hours",
        "what",
        "time",
        "until",
        "when",
        "where",
        "address",
        "phone",
        "website",
        "tell",
        "more",
        "about",
        "inside",
        "far",
        "how",
        "long",
        "walk",
        "there",
        "this",
        "that",
        "place",
        "the",
        "right",  # «where can I walk right now?» is no question about «Myata Right»
        "here",
        "nearby",
        "around",
        "today",
        "tonight",
        "should",
        "could",
        "would",
        "please",
        "здесь",
        "рядом",
        "сегодня",
        "куда",
        "ашык",
        "жабык",
        "кашан",
        "кайда",
        "мекенжай",
        "сайт",
        "жумыс",
        "уакыты",
        "нешеге",
        "дейин",
        "бул",
        "кандай",
        "балаларга",
        "балалар",
        "арналган",
        "ойын",
        "болмеси",
        "болмесі",
        "детская",
        "детской",
        "комната",
        "комнате",
        "игровая",
        "playroom",
        "room",
        "kids",
        "children",
        "розетки",
        "розетка",
        "worth",
        "going",
        "morning",
        "night",
        "утром",
        "ночью",
        "стоит",
        "enter",
        "entry",
        "entrance",
        "admission",
        "free",
        "cost",
        "costs",
        "money",
        "ticket",
        "tickets",
        "serve",
        "serves",
        "menu",
        "cuisine",
        "kazakh",
        "walk",
        "long",
        "minutes",
        "tomorrow",
        "weather",
        "вход",
        "входа",
        "платный",
        "платно",
        "бесплатно",
        "платить",
        "меню",
        "кухня",
        "кухни",
        "подают",
        "готовят",
        "завтра",
        "погода",
        "погоды",
        "акылы",
        "тегин",
        "мазир",
        "ертен",
        "киру",
    ]
)
_CAPITALISED = re.compile(r"(?<![.!?]\s)(?<!^)\b[A-ZА-ЯЁӘІҢҒҮҰҚӨҺ][\wәіңғүұқөһ'’-]{2,}")
_cache: dict[tuple[int, int], tuple[dict[str, list[int]], list[str]]] = {}


def _distinctive(text: str) -> list[str]:
    """Words of the message that could be part of a name: 4+ letters, not a question word, not a place kind or a
    wish the lexicon knows («кафе», «кофе», «музей»)."""
    return [
        w
        for w in tokens(text)
        if len(w) >= MIN_WORD and w not in _QUESTION_WORDS and not match(w).hits
    ]


def _index(pois: Sequence[POI]) -> tuple[dict[str, list[int]], list[str]]:
    """name word key -> indexes of the records that carry it (a record's own words that are place kinds excluded; a
    ЦОН is no walking destination and is never found by the words of its name: it answers a state-service request)."""
    ident = (id(pois[0]), len(pois)) if pois else (0, 0)
    if ident in _cache:
        return _cache[ident]
    by_key: dict[str, list[int]] = {}
    for i, poi in enumerate(pois):
        if poi.category == TRANSIT or poi.name_generated or poi.is_state_service():
            continue
        for name in {poi.name, *poi.names.values()}:
            for word in tokens(name):
                if len(word) >= MIN_WORD and not match(word).hits:
                    by_key.setdefault(name_key(word), []).append(i)
    _cache.clear()
    _cache[ident] = (by_key, list(by_key))
    return _cache[ident]


def _by_words(text: str, pois: Sequence[POI]) -> list[POI]:
    """The records that carry EVERY distinctive word of the message (spelling-tolerant): «Хрустальный Дракон» is
    not the place called «Дракон»."""
    by_key, keys = _index(pois)
    words = _distinctive(text)
    covered: dict[int, set[str]] = {}
    for word in words:
        key = name_key(word)
        cutoff = (
            LONG_WORD_RATIO if len(key) >= LONG_WORD else TOKEN_RATIO
        )  # an ending is a one-letter difference
        found = process.extract(key, keys, scorer=fuzz.ratio, score_cutoff=cutoff, limit=5)
        for key, _, _ in found:
            for i in by_key[key]:
                covered.setdefault(i, set()).add(word)
    return [pois[i] for i, got in covered.items() if len(got) == len(words)]


def _by_lexicon(text: str, pois: Sequence[POI]) -> list[POI]:
    """The records of the well-known places the text names (the dataset name contains the lexicon's name)."""
    names = [n for refs in named_place_refs(text) for n in refs]
    keys = [k for n in names if len(k := name_key(n)) >= MIN_WORD]
    found = [
        p
        for p in pois
        if p.category != TRANSIT
        and not p.name_generated
        and not p.is_state_service()
        and any(k in name_key(p.name) for k in keys)
    ]
    rank = {c: i for i, c in enumerate(_KIND_RANK)}
    return sorted(found, key=lambda p: rank.get(p.category, len(rank)))


def find_named(text: str, pois: Sequence[POI], origin: tuple[float, float]) -> POI | None:
    """The record the message names, or None: of the best kind (for a well-known name) or the best matching word,
    the one with the shortest name, then the nearest."""
    found = _by_lexicon(text, pois) or _by_words(text, pois)
    if not found:
        return None
    rank = {c: i for i, c in enumerate(_KIND_RANK)}
    found = sorted(found, key=lambda p: rank.get(p.category, len(rank)))
    head = found[0]
    pool = [p for p in found if p.category == head.category]
    shortest = min(len(p.name) for p in pool)
    near = [p for p in pool if len(p.name) <= shortest + NAME_TIE_CHARS]
    return min(near, key=lambda p: haversine_m(*origin, p.lat, p.lon))


def spells_a_place(text: str) -> bool:
    """The question names something that is not a word the lexicon knows, in lower case too («какие часы у башни
    центральной площади»): two or more such words, or a capitalised one. A question with no such word («до скольки
    работает?») is about the place already in view, not about a name."""
    unknown = [
        w
        for w in tokens(text)
        if len(w) >= MIN_WORD and w not in _QUESTION_WORDS and not match(w).hits
    ]
    return len(unknown) >= 2 or unknown_name(text)


def unknown_name(text: str) -> bool:
    """The message spells a name (a capital letter inside the sentence) that is not a word the lexicon knows."""
    return any(
        len(w) >= MIN_WORD and w.lower() not in _QUESTION_WORDS and not match(w).hits
        for w in _CAPITALISED.findall(text)
    )
