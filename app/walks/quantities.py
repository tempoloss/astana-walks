"""Numbers the user states about themselves: how many they are, how much they may spend, how old a child is.

Rule-parser helpers (walks.intent): `group_size` («нас 8», «8 адамбыз», «party of 8»), `price_cap_kzt` («до 3000 тг»,
«5 мыңға дейін», «under 5000 tenge»), `child_age` («a 5 year old», «ребёнку 4 года»). A bare number is none of them.
"""

from __future__ import annotations

import re

MIN_GROUP, MAX_GROUP = 2, 200
MIN_PRICE_KZT, MAX_PRICE_KZT = 100, 10_000_000
CHILD_MAX_AGE = 12  # up to here a stated age means «with a child»; teenagers are a different guard (walks.safety)

_WORDS = {
    "двое": 2, "трое": 3, "четверо": 4, "пятеро": 5, "шестеро": 6,
    "два": 2, "две": 2, "три": 3, "четыре": 4, "пять": 5, "шесть": 6, "семь": 7, "восемь": 8, "девять": 9,
    "десять": 10, "двенадцать": 12, "пятнадцать": 15, "двадцать": 20,
    "екі": 2, "үш": 3, "төрт": 4, "бес": 5, "алты": 6, "жеті": 7, "сегіз": 8, "тоғыз": 9, "он": 10, "жиырма": 20,
    "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "twelve": 12, "fifteen": 15, "twenty": 20,
}  # fmt: skip
_NUMBER = "|".join(sorted(_WORDS, key=len, reverse=True))
_N = rf"(\d{{1,3}}|{_NUMBER})"
_NOT_DURATION = r"(?!\s*(?:час|мин|ч\b|лет|год|min|hour|h\b))"
_GROUP = (
    re.compile(rf"\bнас\s+{_N}\b{_NOT_DURATION}", re.I),
    re.compile(rf"\b{_N}\s+(?:человек|чел\b|персон|взрослых|друзей|гостей|ребят)", re.I),
    re.compile(rf"\b(?:компани\w*|групп\w*)\s+(?:из\s+)?{_N}\b{_NOT_DURATION}", re.I),
    re.compile(rf"\b{_N}\s*(?:адам|кісі)", re.I),
    re.compile(rf"\b(?:party|group|table|booking|reservation|team)\s+(?:of|for)\s+{_N}\b", re.I),
    re.compile(rf"\b{_N}\s+(?:people|persons|guests|adults|friends)\b", re.I),
    re.compile(rf"\b{_N}\s+of\s+us\b", re.I),
    re.compile(r"\b(двое|трое|четверо|пятеро|шестеро)\b", re.I),
)  # fmt: skip

_AMOUNT = r"(\d{1,3}(?:[ \u00a0]\d{3})+|\d+(?:[.,]\d+)?)"
_CURRENCY = r"(?:тг\b|тенге\w*|теңге\w*|теңг\w*|тенг\w*|₸|kzt\b|tenge\b|tg\b)"
_CAP_WORD = re.compile(
    r"\b(?:до|не\s+больше|не\s+более|не\s+дороже|в\s+пределах|в\s+рамках|максимум|бюджет|"
    r"under|up\s+to|max(?:imum)?|within|below|around|budget|дейін|шейін|аспайтын)",
    re.I,
)
_MONEY = re.compile(
    rf"{_AMOUNT}(?:\s*(?P<k>тыс\w*|мың\w*|мын\w*|thousand|k|к)(?!\w))?(?:\s*(?P<cur>{_CURRENCY}))?",
    re.I,
)
_CAP_REACH = 30  # characters around a number of thousands in which a cap word must stand

_KID = r"(?:ребенку|ребёнку|сыну|дочке|дочери|малышу|мальчику|девочке|ребенка|ребёнка|сына|дочки)"
_AGE_CHILD = (
    re.compile(r"(?<![\d.,:])(\d{1,2})\s*-?\s*летн", re.I),
    re.compile(rf"(?<![\d.,:])(\d{{1,2}})\s*(?:лет|года|год)\s+{_KID}", re.I),
    re.compile(rf"{_KID}\s+(\d{{1,2}})\s*(?:лет|года|год)\b", re.I),
    re.compile(r"(?<![\d.,:])(\d{1,2})\s*жас", re.I),
    re.compile(r"(?<![\d.,:])(\d{1,2})[\s-]*(?:years?|yrs?)[\s-]*olds?\b", re.I),
    re.compile(r"\baged?\s+(\d{1,2})\b(?!\s*(?:min|hour|h\b|km|m\b))", re.I),
)


def _value(token: str) -> int | None:
    token = token.lower()
    return int(token) if token.isdigit() else _WORDS.get(token)


def group_size(text: str) -> int:
    """How many people the text says they are: «нас 8 человек», «сегіз адаммыз», «party of 8», «двое»; 0: not said."""
    t = text.lower()
    for rx in _GROUP:
        for m in rx.finditer(t):
            n = _value(m.group(1))
            if n is not None and MIN_GROUP <= n <= MAX_GROUP:
                return n
    return 0


def price_cap_kzt(text: str) -> int:
    """A spending cap in tenge the text states: «до 3000 тг», «не дороже 5000 тенге», «3000 теңгеге», «under 3000
    tenge», «5 мыңға дейін», «up to 5k tenge»; 0 when none. An amount counts with a currency, or as a number of
    thousands next to a cap word («5 тысяч» alone may be anything)."""
    t = text.lower()
    for m in _MONEY.finditer(t):
        if m.group("cur") is None and (
            m.group("k") is None
            or not _CAP_WORD.search(t[max(0, m.start() - _CAP_REACH) : m.end() + _CAP_REACH])
        ):
            continue
        value = float(re.sub(r"[ \u00a0]", "", m.group(1)).replace(",", ".")) * (
            1000 if m.group("k") else 1
        )
        if MIN_PRICE_KZT <= value <= MAX_PRICE_KZT:
            return int(value)
    return 0


def child_age(text: str) -> bool:
    """True when the text gives an age of 12 or less for someone («a 5 year old», «ребёнку 4 года», «5 жаста»)."""
    return any(
        int(m.group(1)) <= CHILD_MAX_AGE for rx in _AGE_CHILD for m in rx.finditer(text.lower())
    )
