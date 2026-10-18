"""Comparing place names: one comparable key per name (Cyrillic romanised, spelling variants folded), the chain test
(two branches of Starbucks) and the match against the canonical names the rule parser resolved from the user's words."""

from __future__ import annotations

import re

from rapidfuzz import fuzz

from .models import POI

NAME_RATIO_MIN = 85  # rapidfuzz ratio of two normalised names (0-100) that counts as the same chain

# Cyrillic (ru + kk) -> Latin, one-way: only for comparing names, never shown.
# fmt: off
_LATIN = (
    "a", "b", "v", "g", "d", "e", "z", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f",
    "h", "ts", "ch", "sh", "sh", "i", "e", "e", "zh", "iu", "ia", "k", "a", "g", "i", "n", "o", "u", "u", "h",
)
# fmt: on
_TRANSLIT = {
    **dict(zip("абвгдезийклмнопрстуфхцчшщыэёжюяқәғіңөұүһ", _LATIN, strict=True)),
    "ъ": "",
    "ь": "",
}


def name_key(name: str) -> str:
    """Comparable form of a place name: casefolded, quotes / spaces / punctuation dropped, Cyrillic romanised and
    the obvious Latin spelling variants folded, so 'Burger King', «Бургер Кинг» and 'BURGER-KING' coincide."""
    s = "".join(_TRANSLIT.get(ch, ch) for ch in name.casefold() if ch.isalnum())
    s = re.sub(r"c(?!h)", "k", s.replace("ck", "k").replace("kh", "h"))
    s = s.replace("q", "k").replace("w", "v").replace("x", "ks").replace("y", "i")
    return re.sub(r"([^aeiou\d])\1+", r"\1", s)


def name_keys(poi: POI) -> set[str]:
    if poi.name_generated:
        return set()  # a name made up from the category ("Кафе") says nothing about the chain
    keys = {name_key(n) for n in (poi.name, *poi.names.values())}
    return {k for k in keys if len(k) >= 3}


def best_ratio(a: set[str], b: set[str]) -> float:
    return max((fuzz.ratio(x, y) for x in a for y in b), default=0.0)


def same_chain(a: POI, b: POI) -> bool:
    """Two records of one category whose names are the same chain (two branches of Starbucks), wherever they are.
    An anonymous name says nothing about a chain."""
    keys_a, keys_b = name_keys(a), name_keys(b)
    return (
        a.category == b.category
        and bool(keys_a)
        and bool(keys_b)
        and best_ratio(keys_a, keys_b) >= NAME_RATIO_MIN
    )


_PREFIX_MIN = 5  # a name key this long that opens another one is the same brand («starbucks» / «starbucks kazakhstan»)


def same_brand(a: POI, b: POI) -> bool:
    """Looser than `same_chain`, for «show me something else»: the same brand tag, or one name that opens the
    other («Starbucks» / «Starbucks Казахстан»), in the same category. Never used for ranking or merging."""
    if a.category != b.category:
        return False
    if same_chain(a, b):
        return True
    brand_a, brand_b = a.tag_dict().get("brand", ""), b.tag_dict().get("brand", "")
    if brand_a and name_key(brand_a) == name_key(brand_b):
        return True
    return any(
        len(short) >= _PREFIX_MIN and long.startswith(short)
        for ka in name_keys(a)
        for kb in name_keys(b)
        for short, long in (sorted((ka, kb), key=len),)
    )


def names_place(poi: POI, refs: list[str]) -> bool:
    """`poi` is one of the places the user described or asked about, by the canonical names the rule parser resolved."""
    if not refs or poi.name_generated:
        return False
    keys = name_keys(poi)
    return any(
        (rk := name_key(r)) and any(rk == k or fuzz.ratio(rk, k) >= NAME_RATIO_MIN for k in keys)
        for r in refs
    )
