"""Name normalisation and similarity shared by Wikidata matching and the OSM<->Overture merge.

Scores are transliteration-insensitive: Cyrillic (ru/kk) names are romanised and reduced to a rough
phonetic skeleton, so «Байтерек», «Baiterek» and «Bayterek» compare as equal.
"""

from __future__ import annotations

import re
import unicodedata

from rapidfuzz import fuzz

_RU = {
    "а": "a", "б": "b", "в": "v", "г": "g", "д": "d", "е": "e", "ё": "e", "ж": "zh", "з": "z", "и": "i",
    "й": "i", "к": "k", "л": "l", "м": "m", "н": "n", "о": "o", "п": "p", "р": "r", "с": "s", "т": "t",
    "у": "u", "ф": "f", "х": "kh", "ц": "ts", "ч": "ch", "ш": "sh", "щ": "sh", "ъ": "", "ы": "y", "ь": "",
    "э": "e", "ю": "yu", "я": "ya",
    # Kazakh
    "ә": "a", "ғ": "g", "қ": "k", "ң": "n", "ө": "o", "ұ": "u", "ү": "u", "і": "i", "һ": "h",
}

# Words that carry the venue type, not the identity ("Кафе Керуен" == "Керуен").
_GENERIC = {
    "cafe", "kafe", "restoran", "restaurant", "bar", "pub", "park", "skver", "sad", "coffee", "kofe",
    "kofeina", "kofeinia", "club", "klub", "muzei", "museum", "teatr", "theatre", "theater", "kinoteatr",
    "cinema", "tts", "trts", "trk", "mall", "torgovyi", "torgovii", "centr", "tsentr", "center", "centre",
    "stolovaia", "stolovaya", "pitstseria", "pizzeria", "bistro", "fast", "food", "ulitsa", "ul",
    "prospekt", "pr", "the",
}

_NON_WORD = re.compile(r"[^0-9a-z]+")


def translit(text: str) -> str:
    out = []
    for ch in text.casefold():
        out.append(_RU.get(ch, ch))
    return "".join(out)


def skeleton(text: str) -> str:
    """Phonetic skeleton: casefolded, romanised, y/j/i merged, c/q/x folded, doubles collapsed."""
    if not text:
        return ""
    text = unicodedata.normalize("NFKD", text)
    text = "".join(c for c in text if not unicodedata.combining(c))
    s = translit(text)
    s = _NON_WORD.sub(" ", s)
    tokens = [t for t in s.split() if t not in _GENERIC]
    s = " ".join(tokens) if tokens else " ".join(s.split())
    for a, b in (("shch", "sh"), ("kh", "h"), ("ck", "k"), ("ph", "f"), ("ya", "ia"), ("yu", "iu"),
                 ("ye", "ie"), ("yo", "io"), ("y", "i"), ("j", "i"), ("w", "v"), ("q", "k"), ("c", "k"),
                 ("x", "ks"), ("oo", "u"), ("ou", "u"), ("ee", "i")):
        s = s.replace(a, b)
    s = re.sub(r"(.)\1+", r"\1", s)
    return s.strip()


def name_score(a_names: list[str], b_names: list[str]) -> float:
    """Best 0..100 similarity over all name pairs (skeleton ratio / token-sort ratio, no subset bonus)."""
    best = 0.0
    sa = {skeleton(n) for n in a_names if n}
    sb = {skeleton(n) for n in b_names if n}
    for x in sa:
        if not x:
            continue
        for y in sb:
            if not y:
                continue
            best = max(best, fuzz.ratio(x, y), fuzz.token_sort_ratio(x, y))
            if best >= 100:
                return 100.0
    return float(best)


# Cyrillic (ru + kk) -> Latin, one-way, for comparing names only. Same table and rules as `name_key` in
# app/walks/retrieve.py (the app clusters same-chain points by this key), so a merge duplicate here is a
# duplicate card there. Keep the two in sync.
_KEY_TRANSLIT = {
    **dict(zip(
        "абвгдезийклмнопрстуфхцчшщыэёжюяқәғіңөұүһ",
        ["a", "b", "v", "g", "d", "e", "z", "i", "i", "k", "l", "m", "n", "o", "p", "r", "s", "t", "u", "f", "h",
         "ts", "ch", "sh", "sh", "i", "e", "e", "zh", "iu", "ia", "k", "a", "g", "i", "n", "o", "u", "u", "h"],
        strict=True,
    )),
    "ъ": "",
    "ь": "",
}


def name_key(name: str) -> str:
    """Comparable form of a place name: casefolded, punctuation dropped, Cyrillic romanised, Latin spelling
    variants folded, so 'Burger King', «Бургер Кинг» and 'BURGER-KING' coincide."""
    s = "".join(_KEY_TRANSLIT.get(ch, ch) for ch in name.casefold() if ch.isalnum())
    s = re.sub(r"c(?!h)", "k", s.replace("ck", "k").replace("kh", "h"))
    s = s.replace("q", "k").replace("w", "v").replace("x", "ks").replace("y", "i")
    return re.sub(r"([^aeiou\d])\1+", r"\1", s)


def is_generic_name(name: str) -> bool:
    """True when every word only names the venue type ('Кафе', 'Coffee', 'Парк'): says nothing about identity."""
    words = [w for w in _NON_WORD.sub(" ", translit(name)).split() if w]
    return all(w in _GENERIC for w in words)
