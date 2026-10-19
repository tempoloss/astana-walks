"""A reason of the model must say something about THIS place: at least one concrete fact of its sheet (walks.facts), and
none of the filler that fits any place («удобно расположено», «в уютной обстановке», «отлично подходит для», «Закажите
горячие блюда», «Ещё одно кафе»). The opening of the reply may use only the numbers of the payload, name no place the
answer does not show, and is written in the answer language. Pure text checks: no data, no model."""

from __future__ import annotations

import re

GENERIC = re.compile(
    r"удобно расположен|удобн\w* расположени|в уютной обстановке|уютн\w* (?:атмосфер|обстановк|мест|уголок)|"
    r"(?:отлично|идеально|прекрасно|хорошо) подходит|подойд[её]т для|"
    r"закажите (?:любим|горяч|традиционн|вкусн|освежающ|что-нибудь)\w*|попробуйте (?:традиционн|вкусн|местн|блюда)\w*|"
    r"ещ[её] одн\w* (?:\w+ )?(?:кафе|бар|ресторан|место|парк|заведени)|пройдитесь по аллеям|"
    r"насладит\w* (?:атмосфер|прогулк|отдых)|приятн\w* атмосфер|"
    r"conveniently located|\bcos?zy\b|\bwelcoming\b|(?:perfect|great|ideal) (?:for|spot|place|choice)|"
    r"\bуютн\w*|\bжайлы\b|"
    r"another (?:\w+ )?(?:cafe|café|bar|restaurant|place|park|spot)|enjoy the atmosphere|"
    r"order (?:your favou?rite|hot|traditional|a refreshing)|"
    r"ыңғайлы орналасқан|жайлы атмосфера|өте қолайлы|тамаша орын|тағы бір (?:\w+ )?(?:кафе|бар|мейрамхана|орын)|"
    # selection notes and category echoes that read like a log («относится к категории баров», «designated as a viewpoint»)
    r"относится к категори|подходит под категори|как вы просили|совпадает с|ближайш\w+ по прямой|единственн\w+ мест|"
    r"designated as|as requested|falls into the category|fits the category|matches|the nearest in a straight line|"
    r"санатына жатады|сіз сұрағандай|түзу сызық бойынша",
    re.I,
)
# a status or an hour: said only in the words of code (walks.status). «открыт в 1988 году», «открытая терраса», «an open
# kitchen», «жабық ойын алаңы» (an indoor playground) are no status
_STATUS = re.compile(
    r"\b(?:открыт|закрыт)[аоы]?\b(?!\s+в\s+\d{4})|\b(?:открыва|закрыва)ет\w*|\b(?:откро|закро)ется|"
    r"\bработа\w* (?:до|с|круглосуточ|ночью|допоздна)|круглосуточ|"
    r"\b(?:opens|closes|closing|closed)\b|\bopen\b(?!-air)(?=\s+(?:now|until|till|at|from|daily|today|tonight|late|"
    r"24|round|around|all|every|on|\d))|\b(?:is|are|it's|stays?|still|currently|now)\s+open\b|\buntil\s+(?:late|"
    r"midnight|\d)|24/7|around the clock|"
    r"\bашылады\b|\bжабылады\b|(?:қазір|дейін|бүгін|әлі|түнде)\s+(?:ашық|жабық)\b|тәулік бойы|дейін жұмыс|"
    r"\d{1,2}:\d{2}",
    re.I,
)
_HOUR = re.compile(r"\d{1,2}:\d{2}")
# the conditions in words («в условиях плохого воздуха и холода», «despite the cold»): said only with their numbers
_CONDITIONS = re.compile(
    r"погод|холод|мороз|воздух|смог|туман|непогод|осадк|\bcold\b|frost|\bair\b|smog|\bfog\b|weather|"
    r"ауа райы|суық|аяз|тұман",
    re.I,
)


def vague_conditions(text: str) -> bool:
    """The text speaks of the weather or the air without a single number (a template, not a fact)."""
    return bool(_CONDITIONS.search(text)) and not re.search(r"\d", text)


def states_status(text: str) -> bool:
    return bool(_STATUS.search(text))


_OTHER_DAY = re.compile(r"следующ|завтра|next day|tomorrow|келесі|ертең", re.I)


def _same_hours(sentence: str, status: str) -> bool:
    """The sentence names hours, only those of the card's own status line, and that line names no other day
    («работает до 22:00» next to «Открыто до 22:00»; never next to «Открыто до 05:00 следующего дня»)."""
    said = {h.lstrip("0") for h in _HOUR.findall(sentence)}
    own = {h.lstrip("0") for h in _HOUR.findall(status)}
    return bool(said) and said <= own and not _OTHER_DAY.search(status)


def keep_status(text: str, status: str) -> str:
    """`text` without the sentences that state a status or an hour differing from the card's own `status` line."""
    own = norm(status)
    return " ".join(
        p
        for p in _sentences(text)
        if not states_status(p) or (own and (own in norm(p) or _same_hours(p, status)))
    ).strip()


_WORD = re.compile(r"[^\W\d_]{4,}", re.U)
_NUM = re.compile(r"\d{1,2}:\d{2}|\d+")
_STOP = frozenset(
    [
        "астана",
        "astana",
        "казахстан",
        "kazakhstan",
        "улица",
        "улице",
        "улицу",
        "улицы",
        "улицей",
        "street",
        "проспект",
        "проспекте",
        "проспекта",
        "проспекту",
        "avenue",
        "көше",
        "көшесі",
        "көшесінде",
        "даңғылы",
        "даңғылында",
        "расположено",
        "расположен",
        "расположена",
        "located",
        "кафе",
        "cafe",
        "ресторан",
        "restaurant",
        "парк",
        "park",
        "место",
        "place",
        "город",
        "city",
        "центр",
        "centre",
        "center",
        "здесь",
        "here",
        "очень",
        "very",
        "часы",
        "hours",
    ]
)
STEM = 5  # letters of a word that make it «the same word» across endings («террасой» / «терраса»)


def norm(text: str) -> str:
    return text.lower().replace("ё", "е")


def is_generic(text: str) -> bool:
    return bool(GENERIC.search(norm(text)))


def _stems(text: str, skip: set[str]) -> set[str]:
    return {w[:STEM] for w in _WORD.findall(norm(text)) if w not in _STOP and w[:STEM] not in skip}


def uses_fact(text: str, facts: list[str], name: str) -> bool:
    """Does `text` use at least one of `facts` (a word of it, an hour of the record, the walking minutes)? Words of the
    place's own name do not count: the name is not a fact about the place."""
    said = norm(text)
    words = {w[:STEM] for w in _WORD.findall(said)}
    skip = _stems(name, set())
    for fact in facts:
        hours = re.findall(r"\d{1,2}:\d{2}", fact)
        if hours:
            if any(h in said or h.lstrip("0") in said for h in hours):
                return True
            if any(h in {"00:00", "24:00"} for h in hours) and re.search(
                r"полуноч|midnight|түн ортас", said
            ):
                return True
            continue
        if fact.strip().isdigit():
            if re.search(rf"\b{fact.strip()}\s*(?:мин|min|минут)", said):
                return True
            continue
        if _stems(fact, skip) & words:
            return True
    return False


def _sentences(text: str) -> list[str]:
    return [p for p in re.split(r"(?<=[.!?])\s+", (text or "").strip()) if p]


# an interest of the person the model infers («fits your interest in museums»): code knows what was asked, the model
# does not tell the person what they like
_INTEREST = re.compile(
    r"your interest|you(?:'re| are) interested|you (?:like|love|enjoy)\b|ваш\w* интерес|вас интерес|вам интересн|"
    r"вы любите|қызығушылығыңыз|сізді қызықтыр",
    re.I,
)


def without_interest(text: str) -> str:
    """A model's text without the sentences that tell the person what they like («This gallery fits your interest in
    museums»): the request says what was asked, and the model may not invent it. Every other sentence stays; a card
    with no fact of its place at all is rewritten as a whole (walks.facts.vague_ids)."""
    return " ".join(p for p in _sentences(text) if not _INTEREST.search(p))


def numbers_ok(text: str, allowed: set[str]) -> bool:
    """Every number of `text` is one the payload holds (a temperature, a walking time, an hour of a record)."""
    return all(n in allowed or n.lstrip("0") in allowed for n in _NUM.findall(text))


def in_script(text: str, lang: str) -> bool:
    latin = len(re.findall(r"[A-Za-z]", text))
    cyrillic = len(re.findall(r"[А-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ]", text))
    return cyrillic <= latin if lang == "en" else latin <= cyrillic


def opening_ok(text: str, lang: str, allowed: set[str], others: list[str]) -> bool:
    """A natural opening of the reply: short, in the answer language, no filler, only the payload's numbers, no name of
    a place the answer does not show (`others`)."""
    said = norm(text)
    return (
        0 < len(text) <= 360
        and len(re.findall(r"[.!?](?:\s|$)", text)) <= 3
        and in_script(text, lang)
        and not is_generic(text)
        and numbers_ok(text, allowed)
        and not any(len(n) >= 4 and norm(n) in said for n in others)
    )
