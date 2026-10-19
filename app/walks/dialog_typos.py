"""Typos in the words of a place kind («кофк», «кафэшка», «прак», «coffe»): a word that the lexicon does not read, one
edit (a letter changed, added, dropped or swapped) away from exactly one key place word, is read as that word. Only
words of 4+ letters (6+ in English, which is full of real words one edit apart), only against the curated key words
below (never against every stem: a short or ambiguous word is nobody's typo), never a word the lexicon already reads,
never a real word listed in `REAL_WORDS`. Rules only, offline."""

from __future__ import annotations

import re

from rapidfuzz.distance import OSA

from .lexicon import match

MIN_LETTERS = 4
MIN_LATIN_LETTERS = 5  # «cafe» / «cape» / «care» / «cake»: english is full of real words one edit apart; keys are 6+
_WORD = re.compile(r"[^\W\d_]+", re.UNICODE)
# the key words of the place kinds, in the forms a person writes them (nominative, the usual accusative, a plural, the
# cases that a real word of another meaning could be mistaken for a typo of)
KEYS = frozenset(
    [
        "кофе",
        "кофейня",
        "кофейню",
        "кофейни",
        "кофейне",
        "кафе",
        "кафешка",
        "кафешку",
        "кафешки",
        "кафешке",
        "кафешкой",
        "кафешек",
        "ресторан",
        "ресторана",
        "рестораны",
        "ресторане",
        "ресторану",
        "рестораном",
        "аптека",
        "аптеку",
        "аптеки",
        "аптеке",
        "аптекой",
        "парк",
        "парка",
        "парке",
        "парку",
        "парков",
        "музей",
        "музея",
        "музеи",
        "музее",
        "музею",
        "музеям",
        "магазин",
        "магазина",
        "магазины",
        "магазине",
        "магазину",
        "туалет",
        "туалета",
        "туалеты",
        "туалету",
        "туалете",
        "банкомат",
        "банкомата",
        "пицца",
        "пиццу",
        "пиццы",
        "пицце",
        "шаурма",
        "шаурму",
        "бургер",
        "бургеры",
        "столовая",
        "столовую",
        "гостиница",
        "гостиницу",
        "отель",
        "отеля",
        "отелю",
        "отеле",
        "отели",
        "отелей",
        "театр",
        "театра",
        "театре",
        "театру",
        "театры",
        "театров",
        "кинотеатр",
        "сквер",
        "сквера",
        "набережная",
        "набережную",
        "coffee",
        "restaurant",
        "pharmacy",
        "museum",
        "toilet",
        "restroom",
        "theatre",
        "supermarket",
        "burger",
        "shawarma",
    ]
)
# real words one edit away from a key word: never a typo of it («пара» is not «парк», «кофта» is not «кофе»)
REAL_WORDS = frozenset(
    [
        "пара",
        "пары",
        "паре",
        "парт",
        "паук",
        "парки",
        "парню",
        "кофта",
        "кофт",
        "кафель",
        "кафеля",
        "кофр",
        "кофра",
        "скверы",
        "скверу",
        "коте",
        "котё",
        "coffer",
        "coffers",
        "айтеке",
        "каде",
        "caffe",
        "piazza",
        "пица",
    ]
)


def _known(word: str) -> bool:
    return bool(match(word).hits)


def repair(word: str) -> str:
    """`word` as the key place word it is a typo of, else unchanged."""
    low = word.lower()
    if len(low) < (MIN_LATIN_LETTERS if low.isascii() else MIN_LETTERS):
        return word
    if low in KEYS or low in REAL_WORDS or _known(low):
        return word
    near = {
        k for k in KEYS if abs(len(k) - len(low)) <= 1 and OSA.distance(low, k, score_cutoff=1) <= 1
    }
    if len(near) != 1:
        return word
    (key,) = near
    if low[0] != key[0]:
        return word  # a typo keeps the first letter: «парк» is not «марк»
    return key.capitalize() if word[:1].isupper() else key


def repair_typos(text: str) -> str:
    """`text` with each typo of a key place word replaced by the word."""
    return _WORD.sub(lambda m: repair(m.group(0)), text)
