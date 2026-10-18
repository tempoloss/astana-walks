"""Address normalisation shared by the matchers: Kazakh/Russian spelling variants fold to one key, so that
«ул. Мангилик ел, 30» (gov4c.kz), «Мәңгілік Ел даңғылы 30» (OSM) and «МАНГИЛИК ЕЛ» (OpenAddresses) agree.

The key is a matching device, never shown to a user. Street names are compared token-wise after the folding below
(case, Kazakh letters, type words, initials and a trailing inflection vowel dropped); a house number must match
exactly after `norm_house`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

_FOLD = str.maketrans({
    "ә": "а", "і": "и", "ү": "у", "ұ": "у", "қ": "к", "ғ": "г", "ң": "н", "ө": "о", "һ": "х",
    "ё": "е", "й": "и", "ы": "и", "э": "е", "ъ": "", "ь": "",
})
_LAT = str.maketrans("abcehkmoptxy", "авсенкмортху")  # Latin look-alikes -> Cyrillic (house letters, «А 82»)
_TYPE_WORDS = ({
    "ул", "улица", "көшесі", "кошеси", "көше", "пр", "проспект", "даңғылы", "дангилы", "даңғыл", "шоссе", "бульвар",
    "бул", "пер", "переулок", "мкр", "микрорайон", "тупик", "проезд", "площадь", "г", "город", "астана", "қаласы",
    "каласы", "к", "қ", "дом", "д", "им", "имени", "street", "avenue", "st", "ave", "str", "road", "жолы", "алаңы",
    "тасжолы", "трасса", "набережная", "наб", "ш",
})
TYPE_WORDS = frozenset(w.casefold().translate(_FOLD) for w in _TYPE_WORDS)
_TOKEN = re.compile(r"[a-zа-яәіңғүұқөһё]+|\d+", re.IGNORECASE)
_HOUSE = re.compile(r"(\d+)\s*([а-яa-z])?(?:\s*/\s*(\d+)\s*([а-яa-z])?)?", re.IGNORECASE)
_CITY = re.compile(r"^\s*(?:г\.?|қ\.?)?\s*(?:Астана|Astana|Нур-Султан|Нұр-Сұлтан)(?:\s+(?:қ\.|қаласы|город))?\s*,\s*",
                   re.IGNORECASE)


def fold(text: str) -> str:
    return text.casefold().translate(_FOLD)


def _stem(tok: str) -> str:
    return tok[:-1] if len(tok) > 4 and tok[-1] in "аяуеи" else tok


def street_key(text: str | None) -> str:
    """Folded, type-word-free, initial-free street key of a printed street name ('' when nothing is left)."""
    toks = [fold(raw) for raw in _TOKEN.findall(text or "")]
    toks = [t for t in toks if t not in TYPE_WORDS]
    # initials («К. Сатбаева», «Б. Момышулы»): a one-letter token followed by a longer word
    toks = [t for i, t in enumerate(toks) if not (len(t) == 1 and t.isalpha() and i + 1 < len(toks) and len(toks[i + 1]) > 2)]
    return " ".join(_stem(t) for t in toks)


def norm_house(text: str | None) -> str | None:
    """'14А' / '14a' -> '14а'; '16/1' -> '16/1'; None when no number is found."""
    m = _HOUSE.search(text or "")
    if not m:
        return None
    num, letter, num2, letter2 = m.groups()
    out = num + (letter.casefold().translate(_LAT) if letter else "")
    if num2:
        out += "/" + num2 + (letter2.casefold().translate(_LAT) if letter2 else "")
    return out


@dataclass(frozen=True)
class Address:
    raw: str
    street: str  # printed street part, type words kept
    house: str | None  # normalised
    key: str  # street_key(street)


_PAREN = re.compile(r"\([^)]*\)")
_BLOCK_TAIL = re.compile(r",?\s*блок\s*[«\"“]?\s*\w+\s*[»\"”]?\s*$", re.IGNORECASE)
_BUILDING = re.compile(r"\b(?:здание|зд\.?|дом|д\.)\s*(?=\d)", re.IGNORECASE)
_NUM = r"\d+\s*[а-яa-z]?(?:\s*/\s*\d+\s*[а-яa-z]?)?"


def make_address(street: str | None, house: str | None, raw: str = "") -> Address:
    street = " ".join((street or "").split())
    return Address(raw=raw or ", ".join(x for x in (street, house) if x), street=street, house=norm_house(house),
                   key=street_key(street))


def parse_address(raw: str | None) -> Address:
    """'ул. Мангилик ел, 30' -> street 'ул. Мангилик ел', house '30'. Text in brackets («здание вокзала…»), the
    «г. Астана,» prefix and a trailing 'блок «К»' are dropped; 'здание 8' reads as house 8; 'ул. А 82, блок «М»' has
    no house number (house None: «А 82» is the street)."""
    text = " ".join((raw or "").replace("\n", " ").split())
    body = _BUILDING.sub("", _CITY.sub("", _PAREN.sub("", text))).strip(" ,.")
    body = _BLOCK_TAIL.sub("", body).strip(" ,.")
    street, house = body, None
    head, sep, tail = body.rpartition(",")
    if sep and re.fullmatch(rf"\s*{_NUM}\s*", tail, re.IGNORECASE):
        street, house = head, norm_house(tail)
    else:  # «пр. Туран 48»: a trailing number without a comma, unless a single letter precedes it («А 82»)
        m = re.fullmatch(rf"(.*?\D)\s+({_NUM})", body, re.IGNORECASE)
        if m and len(m[1].strip(" .,").split()[-1]) > 1:
            street, house = m[1], norm_house(m[2])
    street = street.strip(" ,.")
    return Address(raw=text, street=street, house=house, key=street_key(street))


def same_street(a: str, b: str, threshold: float = 88.0) -> bool:
    """Street keys agree: equal, one's tokens inside the other's (with a shared word longer than 3 letters), or
    fuzzy-equal (Джангильдина / Жангильдин)."""
    if not a or not b:
        return False
    if a == b:
        return True
    ta, tb = set(a.split()), set(b.split())
    if (ta <= tb or tb <= ta) and any(len(t) > 3 for t in ta & tb):
        return True
    return fuzz.ratio(a, b) >= threshold


def same_address(a: Address, b: Address) -> bool:
    return a.house is not None and a.house == b.house and same_street(a.key, b.key)
