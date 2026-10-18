"""Brevity of what the dialogue says: cutting a text at sentence boundaries (never inside a sentence) and plain
words instead of data jargon. The numbers and the sources of a card live in its structured fields, not in prose."""

from __future__ import annotations

import re

WHY_MAX_WORDS = 25
WHAT_MAX_WORDS = 30
_ABBREVIATIONS = frozenset(
    {"ул", "пр", "просп", "пер", "им", "г", "д", "стр", "тел", "корп", "ш", "мкр", "bld", "st", "ave", "no",
     "каз", "рус", "англ", "лат", "тыс", "млн", "см", "напр", "др", "т", "kaz", "rus", "eng"}
)  # fmt: skip
_BOUNDARY = re.compile(r"(?<=[.!?…])\s+(?=[«\"“(]?[A-ZА-ЯЁӘІҢҒҮҰҚӨҺ0-9])")
# sentences that carry numbers or machinery for the card, not a reason for a person: dropped from a short `why`
_JARGON = re.compile(r"уверенност|confidence|сенімділік|\bPOI\b|\bOverture\b", re.I)
_TIME_FACT = re.compile(
    r"укладывается в ваши \d+ мин|уақытыңызға сыяды|fits your \d+ min|fit your \d+ min", re.I
)
_OPEN_CLAIM = re.compile(r"открыт|\bopen\b|ашық|работает|жұмыс істейді", re.I)
_LABELLED = re.compile(
    r"^(?:Адрес|Address|Мекенжайы|Кухня|Cuisine|Асханасы|Тағам[^:]{0,12}):", re.I
)
_PLAIN = (
    (re.compile(r"\bOSM\b"), "OpenStreetMap"),
    (re.compile(r"\bPOI\b"), ""),
    (re.compile(r"в радиусе доступности"), "рядом"),
    (re.compile(r"қол жетімділік радиусындағы"), "жақын жердегі"),
    (re.compile(r"in range\b"), "nearby"),
)


def plain(text: str) -> str:
    """The text with the data's own acronyms replaced by the names a person knows («OSM» -> «OpenStreetMap»)."""
    for rx, repl in _PLAIN:
        text = rx.sub(repl, text)
    return re.sub(r"\s{2,}", " ", text).strip()


def sentences(text: str) -> list[str]:
    """Whole sentences of `text`; a full stop after an abbreviation («ул.», «пр.») or one letter does not end one."""
    out: list[str] = []
    for part in _BOUNDARY.split(text.strip()):
        part = part.strip()
        if not part:
            continue
        last = out[-1].rstrip(".").rsplit(" ", 1)[-1].lower() if out else ""
        open_bracket = bool(out) and out[-1].count("(") > out[-1].count(")")
        after_abbreviation = (
            bool(out) and out[-1].endswith(".") and (last in _ABBREVIATIONS or len(last) == 1)
        )
        if out and (after_abbreviation or open_bracket):
            out[-1] = f"{out[-1]} {part}"
        else:
            out.append(part)
    return out


def word_count(text: str) -> int:
    return len(text.split())


def _closed(sentence: str) -> str:
    return sentence if sentence.endswith((".", "!", "?", "…")) else sentence + "."


def _fit(candidates: list[str], max_words: int) -> list[str]:
    """The leading sentences that fit `max_words` together; when even the first does not, the shortest one."""
    kept: list[str] = []
    total = 0
    for sentence in candidates:
        n = word_count(sentence)
        if total + n > max_words:
            break
        kept.append(sentence)
        total += n
    if kept:
        return kept
    return [min(candidates, key=word_count)] if candidates else []


def short_why(text: str) -> str:
    """The reason of a card in at most ~25 words, whole sentences: the data-jargon and the time-arithmetic
    sentences go first (the card has those numbers as fields), and a second sentence that only repeats «open»;
    '' when nothing is left."""
    found = [_closed(x) for x in sentences(plain(text)) if x]
    useful = [x for x in found if not _JARGON.search(x) and not _TIME_FACT.search(x)]
    deduped: list[str] = []
    for sentence in useful:
        if _OPEN_CLAIM.search(sentence) and any(_OPEN_CLAIM.search(d) for d in deduped):
            continue
        deduped.append(sentence)
    return " ".join(_fit(deduped, WHY_MAX_WORDS))


def short_what(text: str) -> str:
    """What to do there, ONE sentence: the first one that is not a labelled data line («Адрес: …») and not too long
    (else the shortest); '' when nothing is left."""
    found = [_closed(x) for x in sentences(plain(text)) if x and not _LABELLED.match(x)]
    found = [x for x in found if not _JARGON.search(x)]
    short = [x for x in found if word_count(x) <= WHAT_MAX_WORDS]
    if short:
        return short[0]
    return min(found, key=word_count) if found else ""


def first_sentence(text: str) -> str:
    return next(iter(sentences(text)), "")


def display_name(name: str) -> str:
    """A place name as a person says it: «Coffee BOOM, Мәңгілік Ел даңғылы, 55» (a name some records carry with the
    street) is cut at the comma that opens the address (the one followed by a house number)."""
    head, sep, tail = name.partition(", ")
    return head if sep and any(ch.isdigit() for ch in tail) and head else name
