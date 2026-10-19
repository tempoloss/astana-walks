"""Symptoms of an illness in a request («ребёнок температурит», «балам ыстықтап жатыр», «қызуы көтерілді», «у ребёнка жар»,
«заболел», «кашель», «ауырып қалды», «fever»): a sick person is a reason to look for a clinic or a pharmacy, never a
report of the weather («ыстық» = «hot» in the weather, but «ыстықтап жатыр» = «has a fever») and never a question about it
(«температура» of the weather is not a temperature of a child). Rules only, offline; no import from walks: the module sits
under the lexicon and the intent parser, which both use it. Also here: the weather words that are a condition, not a
report."""

from __future__ import annotations

import re

_LOOKALIKE = str.maketrans(
    {
        "ё": "е", "ә": "а", "ғ": "г", "қ": "к", "ң": "н", "ө": "о", "ұ": "у", "ү": "у", "һ": "х", "і": "и",
    }
)  # fmt: skip
# on the text lower-cased with the kazakh letters read as their russian look-alikes
_SYMPTOM = re.compile(
    r"\bтемператур(?:ит|ю|им|ишь)\b|"
    r"\b(?:повысил\w*|поднял\w*|высок\w*|подскочил\w*|вырос\w*)\s+температур\w*|\bтемператур\w*\s+(?:поднял\w*|повысил\w*|высок\w*|подскочил\w*|вырос\w*|3[7-9]|4[01])\b|"
    r"\bтемператур\w*\s+(?:3[7-9]|4[01])\b|"
    r"\bжар\b|\bлихорад\w*|\bбредит\b|\bозноб\w*|"
    r"\bзаболе\w*|\bболит\b|\bболят\b|\bкашел\w*|\bкашля\w*|\bнасморк\w*|\bтошнит\b|\bрвот\w*|\bпростуд\w*|\bпростыл\w*|\bангин\w*|"
    r"\bотравил\w*|\bотравлен\w*|\bсыпь\b|\bаллерг\w*|\bушиб\w*|\bсломал\w*|\bвывихн\w*|\bпоре[зж]\w*|\bзадыха\w*|"
    r"\bыстыктап\b|\bыстыгы\s+котерил\w*|\bкызуы\b|\bкызу\s+котерил\w*|\bкызып\b|\bтемператур\w*\s+котерил\w*|\bтемпературасы\s+котерил\w*|"
    r"\bауырып\b|\bауыр(?:ады|ып\s+жатыр)\b|\bжотел\w*|\bжотелип\b|"
    r"\bhas a fever\b|\bhave a fever\b|\bfever\b|\bfeverish\b|\bhigh temperature\b|\bis sick\b|\bgot sick\b|\bfell ill\b|\bcough\w*\b|\bsore throat\b|"
    r"\bvomit\w*\b|\bhurts?\b|\bache\b|\bnausea\b|\bbroke (?:his|her|their|my) \w+\b"
)
_CHILD = re.compile(
    r"\bребен\w*|\bребят\w*|\bдет(?:и|ей|ям|ьми|ях)\b|\bдоч\w*|\bсын\w*|\bмалыш\w*|\bдитя\b|\bдитят\w*|"
    r"\bбалам\w*|\bбала\w*|\bулым\w*|\bкызым\w*|\bсаби\w*|\bчild\w*|\bkid\w*|\bson\b|\bdaughter\b|\bbaby\b|\btoddler\b"
)


def _fold(text: str) -> str:
    return text.lower().translate(_LOOKALIKE)


def has_symptom(text: str) -> bool:
    """The message says somebody is ill or hurt."""
    return _SYMPTOM.search(_fold(text)) is not None


def sick_who(text: str, *, child: bool = False) -> str:
    """«child» when a child is the sick one (`child`: the parser already read one), «adult» for another sick person,
    '' when nobody is ill."""
    if not has_symptom(text):
        return ""
    return "child" if child or _CHILD.search(_fold(text)) else "adult"


_CONDITION = re.compile(
    r"\b(?:если|когда|вдруг|егер|if|when|in case of)\s+(?:вдруг\s+|на улице\s+|будет\s+|пойд[её]т\s+|начн[её]тся\s+|it\s+)?"
    r"(?:дожд|снег|холодн|жарк|мороз|ливн|rain|snow|cold|hot|жаңбыр|жанбыр|қар|кар|суық|сууык|ыстық|ыстык)|"
    r"\bбудет ли\b|\b(?:дождь|снег)\s+будет\b|\bwill it (?:rain|snow|be (?:cold|hot|rainy))\b|\bhow (?:cold|hot)\b",
    re.IGNORECASE,
)  # «чем заняться, если дождь», «а завтра дождь будет?»: a condition or a question, not the person's report of the weather


def is_not_a_report(text: str) -> bool:
    """«если дождь», «а завтра дождь будет?»: a condition or a question about the weather, not the person's report of it
    (the weather hint of the parser comes from reports only)."""
    return _CONDITION.search(text) is not None
