"""A reason of the model must say something about THIS place: at least one concrete fact of its sheet (walks.facts), and
none of the filler that fits any place («удобно расположено», «в уютной обстановке», «отлично подходит для», «Закажите
горячие блюда», «Ещё одно кафе»). The opening of the reply may use only the numbers of the payload, name no place the
answer does not show, and is written in the answer language. A sentence that states a distance, a time or «open now»
the record does not hold is dropped. Pure text checks: no data, no model."""

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


# a status line that names another day or the coming morning («до 05:00 утра», «until 5 am»): a bare «до 05:00» of
# the model next to it leaves the day out
_OTHER_DAY = re.compile(r"следующ|завтра|next day|tomorrow|келесі|ертең|утра|\bam\b|таңғы", re.I)


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


# the letters of both scripts on one key, so that «гриль» is the «Grill» of «ПИНТА Bar & Grill» and «кофе» its «Coffee»
_LATIN = str.maketrans(
    "абвгдезийклмнопрстуфхцыэәғқңөұүһіюяcw",
    "abvgdeziiklmnoprstufhcyeagknouuhiuakv",
    "ьъ",
) | str.maketrans({"ж": "zh", "ч": "ch", "ш": "sh", "щ": "sh"})


def _key(word: str) -> str:
    """A word's first sounds in Latin letters, doubled letters as one: «гриль» / «grill» -> «gril»."""
    return re.sub(r"(.)\1+", r"\1", norm(word).translate(_LATIN))[:4]


def uses_fact(text: str, facts: list[str], name: str) -> bool:
    """Does `text` use at least one of `facts` (a word of it, an hour of the record, the walking minutes)? Words of the
    place's own name do not count, in either script: the name is not a fact about the place («ПИНТА Bar & Grill, где
    гриль»)."""
    said = norm(text)
    named = {_key(w) for w in _WORD.findall(norm(name))}
    words = {w[:STEM] for w in _WORD.findall(said) if _key(w) not in named}
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
# a reason taken from the place's own name («где в названии указан гриль», «as its name says»): the name is no fact
_NAME_TALK = re.compile(
    r"названи|называет|\bin (?:its|the) name\b|\bits name\b|\bthe name (?:says|suggests|tells)|\bas the name\b|"
    r"атауы|атауын|деп аталат",
    re.I,
)


def without_filler(text: str) -> str:
    """A model's text without the sentences that tell the person what they like («This gallery fits your interest in
    museums») or that argue from the place's own name («где в названии указан гриль»): the request says what was
    asked, and the name is no fact. Every other sentence stays; a card with no fact of its place at all is rewritten
    as a whole, then is the template's (walks.facts.vague_ids)."""
    return " ".join(
        p for p in _sentences(text) if not (_INTEREST.search(p) or _NAME_TALK.search(p))
    )


def numbers_ok(text: str, allowed: set[str]) -> bool:
    """Every number of `text` is one the payload holds (a temperature, a walking time, an hour of a record)."""
    return all(n in allowed or n.lstrip("0") in allowed for n in _NUM.findall(text))


_NUMERIC_CLAIM = re.compile(
    r"\d+(?:[.,]\d+)?\s*(?:м|км|метр\w*|мин\w*|час\w*|ч|сағат\w*|сағ|шақырым\w*|m|km|meters?|metres?|min\w*|hours?|h)(?![\w])"
    r"|\d{1,2}:\d{2}",
    re.I,
)
OPEN_NOW = re.compile(
    r"(?:сейчас|now|қазір).{0,20}(?:открыт|работает|open|ашық)|(?:открыт\w*|работает|open|ашық).{0,20}(?:сейчас|now|қазір)",
    re.I,
)


def strip_unverified_claims(
    text: str, allowed: frozenset[str] = frozenset(), open_now: bool = False
) -> str:
    """Drop sentences that state distances / times / hours the record does not hold (`allowed`: the walking minutes and
    the times written in its hours) or «open now» of a place that is not open by its hours."""
    keep = [
        p
        for p in _sentences(text)
        if not (_NUMERIC_CLAIM.search(p) and not numbers_ok(p, set(allowed)))
        and not (OPEN_NOW.search(p) and not open_now)
    ]
    return " ".join(keep).strip()


def in_script(text: str, lang: str) -> bool:
    latin = len(re.findall(r"[A-Za-z]", text))
    cyrillic = len(re.findall(r"[А-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ]", text))
    return cyrillic <= latin if lang == "en" else latin <= cyrillic


def opening_ok(text: str, lang: str, allowed: set[str], others: list[str]) -> bool:
    """A natural opening of the reply: short, in the answer language, no filler (nor a reason taken from the name),
    only the payload's numbers, no name of a place the answer does not show (`others`)."""
    said = norm(text)
    return (
        0 < len(text) <= 360
        and len(re.findall(r"[.!?](?:\s|$)", text)) <= 3
        and in_script(text, lang)
        and not is_generic(text)
        and not _NAME_TALK.search(text)
        and numbers_ok(text, allowed)
        and not any(len(n) >= 4 and norm(n) in said for n in others)
    )
