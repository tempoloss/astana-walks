"""Reading one message of the dialogue (rules only, offline): tidy and translit a messy text, tell small talk
(thanks, goodbye, a greeting, «new search») from a request, and find a question about places already shown.

Everything is matched on whole words of the normalised text (walks.lexicon.normalize: lowercase, ё->е, kazakh
letters -> their russian look-alikes), never on fuzzy prefixes: a guard against flipped meanings («недолго» is not
«надолго», «открытый воздух» is not «открыто ли»). Typos and translit are repaired first, once, by `restore`.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from rapidfuzz import fuzz

from .dialog_types import Topic
from .intent import named_categories, parse_rules
from .lexicon import match, named_places, normalize, without_durations
from .models import Intent
from .names import name_key

Act = Literal["thanks", "bye", "decline", "greeting", "reset"]
MAX_QUESTION_WORDS = 10
NAME_TOKEN_RATIO = 80

_TOKEN = re.compile(r"[^\W_]+", re.UNICODE)
_REPEAT = re.compile(r"([^\W\d_])\1{2,}")
_LATIN_ONLY = re.compile(r"^[^а-яёәіңғүұқөһА-ЯЁӘІҢҒҮҰҚӨҺ]*$")


def tidy(text: str) -> str:
    """Whitespace collapsed, a letter stretched three times or more («спасибооо», «хочууу») back to one."""
    return _REPEAT.sub(r"\1", " ".join(text.split()))


def tokens(text: str) -> list[str]:
    return _TOKEN.findall(normalize(text))


# ------------------------------------------------------------------ translit

_DIGRAPHS = (
    ("shch", "щ"), ("sch", "щ"), ("sh", "ш"), ("ch", "ч"), ("zh", "ж"), ("kh", "х"), ("ts", "ц"),
    ("yo", "ё"), ("yu", "ю"), ("ya", "я"), ("ye", "е"), ("gh", "г"), ("ph", "ф"),
)  # fmt: skip
_LETTERS = dict(
    zip(
        "abcdefghijklmnopqrstuvwxyz",
        ["а", "б", "к", "д", "е", "ф", "г", "х", "и", "ж", "к", "л", "м", "н", "о", "п", "к", "р",
         "с", "т", "у", "в", "в", "кс", "ы", "з"],
        strict=True,
    )
)  # fmt: skip
_VOWELS = "aeiou"
_EN_WORDS = frozenset(
    [
        "the",
        "a",
        "an",
        "i",
        "me",
        "my",
        "near",
        "with",
        "for",
        "to",
        "where",
        "want",
        "looking",
        "need",
        "some",
        "is",
        "are",
        "in",
        "at",
        "of",
        "and",
        "place",
        "something",
        "anything",
        "open",
        "on",
        "what",
        "when",
        "can",
        "we",
        "you",
        "any",
        "nearby",
        "today",
        "tomorrow",
        "tonight",
        "please",
        "from",
        "do",
        "does",
        "there",
        "it",
        "how",
        "should",
        "am",
        "im",
        "bored",
        "hello",
        "hi",
        "hey",
        "thanks",
        "thank",
        "bye",
        "goodbye",
        "cafe",
        "coffee",
        "park",
        "museum",
    ]
)


def _translit_word(word: str) -> str:
    low = word.lower()
    out: list[str] = []
    i = 0
    while i < len(low):
        for src, dst in _DIGRAPHS:
            if low.startswith(src, i):
                out.append(dst)
                i += len(src)
                break
        else:
            ch = low[i]
            if ch == "y" and i > 0 and low[i - 1] in _VOWELS:
                out.append("й")
            else:
                out.append(_LETTERS.get(ch, ch))
            i += 1
    return "".join(out)


def _best_variant(word: str) -> str:
    """The cyrillic spelling of a latin word: the plain one, or with a soft sign when the word ends in a verb
    «-ат / -ет / -ит» («poest» -> «поесть»), whichever the lexicon knows."""
    plain = _translit_word(word)
    soft = plain + "ь" if len(plain) > 3 and plain[-1] == "т" and plain[-2] in "аеиоуыс" else ""
    if soft and match(soft).hits and not match(plain).hits:
        return soft
    return plain


def _hit_count(text: str) -> int:
    return len(match(text).hits)


def restore(text: str) -> str:
    """The text, with a transliterated one («gde poest», «kofe», «shashlyk») read as the cyrillic it stands for.
    Only a latin-only text that the lexicon does not read as english is touched, and only when the cyrillic
    reading is understood better than the latin one."""
    if not re.search(r"[A-Za-z]", text) or not _LATIN_ONLY.match(text):
        return text
    words = [w.lower() for w in re.findall(r"[A-Za-z]+", text)]
    if any(w in _EN_WORDS for w in words):
        return text

    cyr = re.sub(r"[A-Za-z]+", lambda m: _best_variant(m.group(0)), text)
    if (
        _hit_count(cyr) > _hit_count(text)
        or (_small_talk_words(cyr) and not _small_talk_words(text))
        or _FOLLOW_WORDS.search(normalize(cyr))
    ):
        return cyr
    return text


# ------------------------------------------------------------------ small talk

_THANKS_STEM = re.compile(r"^(?:спасиб|благодар|рахмет|thank|thx|мерси|сенкс|пасиб|алгыс)")
_THANKS_WORDS = frozenset({"ty", "cheers", "спс", "сенкью", "thanks", "рахмет"})
_BYE = (
    "пока", "до свидания", "досвидания", "до встречи", "всего доброго", "всего хорошего", "хорошего дня",
    "до завтра", "спокойной ночи", "удачи", "сау бол", "сау болыныз", "кездескенше", "bye", "bye bye",
    "goodbye", "see you", "see ya", "good night", "have a nice day", "пока пока",
)  # fmt: skip
_GREETING = (
    "привет", "приветик", "здравствуйте", "здравствуй", "здрасте", "добрый день", "добрый вечер",
    "доброе утро", "доброй ночи", "хай", "салам", "салем", "саламатсыз ба", "салеметсиз бе",
    "ассалаумагалейкум", "ассаламу алейкум", "hello", "hi", "hey", "good morning", "good afternoon",
    "good evening", "yo", "хелло", "как дела", "как жизнь", "how are you", "кал калай", "кандай жагдай",
)  # fmt: skip
_DECLINE = (
    "нет", "не надо", "не нужно", "не хочу", "отмена", "забей", "ничего не надо", "ничего не нужно",
    "no", "no thanks", "never mind", "nevermind", "cancel", "nope", "жок", "керек емес", "койыныз",
)  # fmt: skip
_RESET = (
    "новый поиск", "новый запрос", "искать заново", "начать заново", "начнем заново", "начать сначала",
    "давай сначала", "давай заново", "с начала", "сброс", "сбросить", "забудь все", "new search",
    "start over", "start again", "reset", "begin again", "жаңа іздеу", "жана сурау", "кайтадан",
    "басынан", "жанадан бастайык",
)  # fmt: skip
_RESET_ALONE = (
    "сначала",
    "заново",
    "снова",
    "again",
)  # one word: a reset only when it is the whole message
_POLITE = frozenset(
    [
        "поняла",
        "понял",
        "понятно",
        "ясно",
        "помогли",
        "помог",
        "помогла",
        "вот",
        "это",
        "тебе",
        "got",
        "it",
        "helped",
        "пожалуйста",
        "пжл",
        "плиз",
        "please",
        "pls",
        "большое",
        "огромное",
        "вам",
        "тебе",
        "вас",
        "за",
        "помощь",
        "все",
        "всё",
        "очень",
        "сізге",
        "көп",
        "зор",
        "a",
        "lot",
        "so",
        "much",
        "very",
        "you",
        "for",
        "the",
        "help",
        "your",
        "ok",
        "ок",
        "окей",
        "okay",
        "ладно",
        "хорошо",
        "отлично",
        "супер",
        "класс",
        "good",
        "great",
        "nice",
        "cool",
        "perfect",
        "бот",
        "анык",
        "anyk",
        "bot",
        "ну",
        "а",
        "и",
        "да",
        "же",
        "вот",
        "тогда",
        "уже",
        "тоже",
        "too",
        "also",
        "again",
    ]
)
_FILLERS = frozenset(
    [
        "ну",
        "а",
        "и",
        "пожалуйста",
        "пжл",
        "плиз",
        "please",
        "pls",
        "давай",
        "давайте",
        "можно",
        "если",
        "конечно",
        "вот",
        "тогда",
        "теперь",
        "так",
        "бы",
        "же",
        "ли",
        "мне",
        "нам",
        "короче",
        "значит",
        "слушай",
        "смотри",
    ]
)


def _phrases(items: tuple[str, ...]) -> list[tuple[str, ...]]:
    return sorted((tuple(tokens(p)) for p in items), key=len, reverse=True)


_PHRASES = {
    "bye": _phrases(_BYE),
    "greeting": _phrases(_GREETING),
    "decline": _phrases(_DECLINE),
    "reset": _phrases(_RESET),
}


def _strip_phrases(toks: list[str], phrases: list[tuple[str, ...]]) -> tuple[list[str], bool]:
    """`toks` without the phrases (longest first); whether any was found."""
    found = False
    out = list(toks)
    for ph in phrases:
        n = len(ph)
        i = 0
        while i + n <= len(out):
            if tuple(out[i : i + n]) == ph:
                del out[i : i + n]
                found = True
            else:
                i += 1
    return out, found


def _is_thanks_token(tok: str) -> bool:
    return bool(_THANKS_STEM.match(tok)) or tok in _THANKS_WORDS


def _small_talk_words(text: str) -> bool:
    return small_talk(text) is not None


def small_talk(text: str) -> Act | None:
    """The act of a message that is ONLY small talk (every word of it is), else None: «спасибо большое», «пока»,
    «привет», «не надо». A word of a request next to it («спасибо, а подешевле?») makes it not small talk."""
    toks = tokens(text)
    if not toks:
        return None
    for act in ("bye", "greeting", "decline"):
        rest, found = _strip_phrases(toks, _PHRASES[act])
        if found and all(t in _POLITE or _is_thanks_token(t) for t in rest):
            return act  # type: ignore[return-value]
    if any(_is_thanks_token(t) for t in toks) and all(
        _is_thanks_token(t) or t in _POLITE for t in toks
    ):
        return "thanks"
    return None


def reset_request(text: str) -> tuple[bool, str]:
    """(is it a «new search», the rest of the message after the phrase). «сначала» / «заново» count only alone."""
    toks = tokens(text)
    rest, found = _strip_phrases(toks, _PHRASES["reset"])
    if found:
        return True, " ".join(rest)
    if (
        toks
        and all(t in _RESET_ALONE or t in _POLITE for t in toks)
        and any(t in _RESET_ALONE for t in toks)
    ):
        return True, ""
    return False, text


def strip_fillers(text: str) -> str:
    """The text without words that carry no request («ну а можно пожалуйста»): a long voice-style follow-up then
    fits the parser's short-message limit. A word that changes the meaning («не», «ещё») is never dropped."""
    kept = [w for w in text.split() if normalize(w).strip(",.!?") not in _FILLERS]
    return " ".join(kept) or text


def actionable(intent: Intent) -> bool:
    """The rules found something to search for: a kind of place, a named place, a wish keyword."""
    return bool(
        intent.categories or intent.landmark_refs or intent.info_about or intent.free_text_keywords
    )


def has_signal(text: str) -> bool:
    return actionable(parse_rules(text).intent)


def strong_signal(text: str) -> bool:
    """A kind of place or a named place in the text (a wish keyword alone does not count)."""
    intent = parse_rules(text).intent
    return bool(intent.categories or intent.landmark_refs or intent.info_about)


_KK_SMALL = frozenset(
    [
        "рахмет",
        "сау",
        "салем",
        "саламатсыз",
        "салеметсиз",
        "кездескенше",
        "жок",
        "алгыс",
        "кайтадан",
        "жана",
    ]
)
_EN_SMALL = frozenset(
    [
        "thanks",
        "thank",
        "thx",
        "ty",
        "cheers",
        "bye",
        "goodbye",
        "hello",
        "hi",
        "hey",
        "yo",
        "nope",
        "cancel",
        "reset",
        "start",
        "over",
        "new",
        "search",
        "again",
        "morning",
        "evening",
        "afternoon",
        "night",
        "see",
        "ya",
        "nevermind",
        "never",
        "mind",
        "no",
        "good",
    ]
)
_CYRILLIC = re.compile(r"[а-яёәіңғүұқөһ]", re.I)
_RU_ONLY = re.compile(r"[ёъэщ]", re.I)  # letters a kazakh word of its own does not use («ещё»)


def detect(text: str, fallback: str) -> str:
    """ru / kk / en of a message; `fallback` (the dialogue's language) when the message says nothing about it
    («?», «ок», a number, gibberish)."""
    toks = tokens(text)
    if not toks:
        return fallback
    m = match(text)
    if m.language != "ru" or m.hits:
        return m.language
    if any(t in _KK_SMALL for t in toks):
        return "kk"
    if not _CYRILLIC.search(text):
        return "en" if any(t in _EN_SMALL or t in _EN_WORDS for t in toks) else fallback
    if fallback != "kk" or _RU_ONLY.search(text) or len(toks) > 2 or small_talk(text) is not None:
        return "ru"  # a Cyrillic message is never english: «ещё варианты» after «ne to, drugoe» is russian again
    return fallback  # «другое» in a kazakh dialogue: a short word of both languages keeps the dialogue's


# ------------------------------------------------------------------ questions about shown places


@dataclass(frozen=True)
class PlaceQuestion:
    topic: Topic
    ordinal: int | None = None  # 0-based index in the shown places
    plural: bool = False
    marked: bool = False  # the message points at «this place» («там», «оно», «есть ли», «?»)


_MARK = (
    r"\b(?:там|тут|оно|он|она|у них|здесь|есть ли|имеется|there|it|does|do they|is there|are there|"
    r"бар ма|бар ма екен|ол жерде|онда|сонда)\b|\?"
)
# (topic, regex, needs a marker of «this place» next to it)
_TOPICS: tuple[tuple[Topic, str, bool], ...] = (
    (
        "hours",
        r"\bоткрыт[оаы]?\b|\bзакрыт[оаы]?\b|\bработа(?:ет|ют)\b|\bчасы\b|\bдо скольки\b|\bво сколько (?:открыва|закрыва)\w*|"
        r"\bкогда (?:открыва|закрыва)\w*|\bчасы работы\b|\bрежим работы\b|\bвремя работы\b|\bграфик\b|\bкруглосуточн\w* ли\b|"
        r"\bли круглосуточ\w*|\bзайти внутрь\b|\bможно (?:ли )?внутрь\b|\bвнутрь\b|"
        r"\bашык\w*|\bжабык\w*|жумыс (?:истей|уакыт|кестес)|нешеге дейин|нешеде (?:ашыл|жабыл)|кашан (?:ашыл|жабыл)|"
        r"\bopen\b|\bopens\b|\bclosed?\b|\bclosing\b|\bopening hours\b|\bhours\b|\buntil when\b|\bwhat time\b|"
        r"\bgo in\b|\bget in\b|\bgo inside\b|\binside\b",
        False,
    ),
    (
        "address",
        r"\b(?:это|оно|он|она|там|тут)\s+где\b|\bгде\s+(?:это|оно|он|она|находится|расположен\w*)\b|\bадрес\w*|"
        r"\bна какой улице\b|\bкайда (?:орналаскан|екен)\b|\bмекенжай\w*|\bол кайда\b|\bбул кайда\b|\bкайда екен\b|"
        r"\bwhere is (?:it|this|that)\b|\bwhere'?s (?:it|that|this)\b|\baddress\b|\bwhere exactly\b|\bwhat street\b",
        False,
    ),
    (
        "route",
        r"\bкак (?:дойти|добраться|пройти|доехать|туда|к нему|к ней)\b|\bдалеко\b|\bсколько (?:идти|минут|ехать|до него|до нее)\b|"
        r"\bмаршрут\w*|\bпешком дойти\b|\bдалеко ли\b|\bкалай (?:бар|жет)\w*|\bалыс па\b|\bканша минут\b|\bкалай жетемин\b|"
        r"\bhow (?:do i |can i |to )?(?:get|go|walk|reach)\b|\bhow far\b|\bdirections\b|\bhow long (?:to|does it take)\b|\bwalk there\b|\bhow do i walk\b",
        False,
    ),
    (
        "phone",
        r"\bтелефон\w*|\bпозвонить\b|\bзвонить\b|\bсозвониться\b|\bphone\b|\bcall (?:them|it|there)\b|\bномер телефона\b",
        False,
    ),
    (
        "website",
        r"\bсайт\w*|\bwebsite\b|\bweb site\b|\bsite\b|\burl\b|\bссылк\w*|\bвебсайт\w*",
        False,
    ),
    (
        "toilet",
        r"\bтуалет\w*|\bуборн\w*|\bwc\b|\btoilets?\b|\brestrooms?\b|\bwashrooms?\b|\bдаретхана\b|\bажетхана\b",
        False,
    ),
    ("parking", r"\bпарковк\w*|\bстоянк\w*|\bparking\b|\bтурак\w*", False),
    (
        "price",
        r"\bсколько стоит\b|\bкакие цены\b|\bцены\b|\bцена\b|\bhow much\b|\bprices?\b|\bбагасы\b|\bкандай баг\w*|\bканша тур\w*|"
        r"\bвход\w* (?:платн|бесплатн)\w*|\b(?:платн|бесплатн)\w* вход\w*|\bбилет\w*|\bentry fee\b|\bentrance fee\b|"
        r"\badmission\b|\btickets?\b|\bкиру акылы\b|\bакылы ма\b",
        False,
    ),
    (
        "price",
        r"\bдорог(?:о|ой|ая|ие)\b|\bexpensive\b|\bкымбат\b",
        True,
    ),
    ("reserve", r"\bброн\w*|\bзабронировать\b|\breserv\w*|\bbook(?:ing)?\b|\bброндау\b", True),
    ("wifi", r"\bwifi\b|\bwi fi\b|\bвай ?фай\b|\bинтернет\w*|\binternet\b", True),
    (
        "wheelchair",
        r"\bколяск\w*|\bинвалид\w*|\bпандус\w*|\bwheelchair\b|\baccessib\w*|\bstep free\b|\bарба\w*",
        True,
    ),
    (
        "terrace",
        r"\bтеррас\w*|\bверанд\w*|\bна улице\b|\boutdoor\b|\bterrace\b|\bpatio\b|\bдалада\b",
        True,
    ),
    (
        "takeaway",
        r"\bс собой\b|\bнавынос\b|\btakeaway\b|\btake away\b|\bto go\b|\bалып кету\b",
        True,
    ),
    (
        "about",
        r"\bчто (?:там|это|за место)\b|\bрасскажи\w*|\bподробнее\b|\bчто за\b|\bо нем\b|\bпро (?:него|нее|это|оно)\b|"
        r"\btell me more\b|\bwhat is it\b|\bwhat'?s there\b|\bmore about\b|\bmore details\b|\bтолыгырак\b|\bол не\b",
        False,
    ),
)
_ORDINALS = (
    (0, r"\bперв\w+|\bfirst\b|\bбиринш\w*|\bномер (?:один|1)\b|\bnumber (?:one|1)\b"),
    (1, r"\bвтор\w+|\bsecond\b|\bекинш\w*|\bномер (?:два|2)\b|\bnumber (?:two|2)\b"),
    (2, r"\bтрет\w+|\bthird\b|\bушинш\w*|\bномер (?:три|3)\b|\bnumber (?:three|3)\b"),
)
_PLURAL = re.compile(
    r"\b(?:они|обе|оба|все они|все места|эти места|все варианты|all of them|both|they|all|екеуи|барлыгы|барлыгынан)\b"
)
_COMPILED = tuple((topic, re.compile(rx), marked) for topic, rx, marked in _TOPICS)
_ORD = tuple((i, re.compile(rx)) for i, rx in _ORDINALS)
_MARKER = re.compile(_MARK)
_FOCUS = re.compile(r"\b(?:оно|он|она|там|тут|это место|его|ее|it|there|ол|осы|this|that)\b")


def _topic(text: str, question_mark: bool = False) -> Topic | None:
    marked = question_mark or bool(_MARKER.search(text))
    for topic, rx, needs_marker in _COMPILED:
        if rx.search(text) and (marked or not needs_marker):
            return topic
    return None


def place_question(text: str, *, allow_kind: bool = False) -> PlaceQuestion | None:
    """The question about places the message asks, else None. Short messages only; a message that names a kind of
    place is a request, not a question («а там есть кафе» searches), unless `allow_kind` (a named place is the
    subject: «Национальный музей сейчас открыт?»)."""
    norm = " ".join(tokens(text))
    if not norm or len(norm.split()) > MAX_QUESTION_WORDS:
        return None
    norm = without_durations(
        norm
    )  # «2 hours before the flight» is a time budget, not the «hours» of a place
    if named_categories(text) and not allow_kind:
        return None
    ordinal = next((i for i, rx in _ORD if rx.search(norm)), None)
    asked = "?" in text
    topic = _topic(norm, asked)
    if topic is None and ordinal is None:
        return None
    return PlaceQuestion(
        topic=topic or "about",
        ordinal=ordinal,
        plural=bool(_PLURAL.search(norm)) and ordinal is None,
        marked=asked or bool(_MARKER.search(norm)),
    )


def refers_to_focus(text: str) -> bool:
    return bool(_FOCUS.search(" ".join(tokens(text))))


def mentioned(text: str, names: list[str]) -> int | None:
    """Index of the shown place whose name the message contains (a word of 4+ letters, spelling-tolerant)."""
    toks = [name_key(t) for t in tokens(text) if len(t) >= 4]
    best, best_score = None, 0.0
    for i, name in enumerate(names):
        for word in tokens(name):
            if len(word) < 4:
                continue
            key = name_key(word)
            for tok in toks:
                score = fuzz.ratio(tok, key)
                if score >= NAME_TOKEN_RATIO and score > best_score:
                    best, best_score = i, score
    return best


def named_place_refs(text: str) -> list[tuple[str, ...]]:
    """The well-known places the text names directly (dataset names), when they are the subject, not the location."""
    return [names for names, located in named_places(text) if not located]


# ------------------------------------------------------------------ what the data does not hold at all

_OUT_OF_DATA = {
    "pharmacy": r"\bаптек\w*|\bдарихана\w*|\bpharmac\w*|\bdrugstores?\b|\bchemist\b",
    "exchange": (
        r"\bобмен\w* валют\w*|\bобменник\w*|\bобменять\b|\bобмен денег\b|\bайырбастау\b|"
        r"\bcurrency exchange\b|\bexchange (?:money|currency)\b|\bmoney exchange\b"
    ),
    "bank": r"\bбанкомат\w*|\bбанк(?:а|у|е|и|ом|овск\w*)?\b|\batm\b|\bbank\b|\bcash machine\b",
    "gas": r"\bзаправк\w*|\bазс\b|\bgas station\b|\bpetrol\b|\bfuel\b",
    "school": r"\bшкол\w*|\bмектеп\w*|\bschools?\b",
    "dentist": r"\bстоматолог\w*|\bзубн\w+|\bдантист\w*|\bтис даригер\w*|\bdentists?\b|\bdental\b",
    "embassy": r"\bпосольств\w*|\bконсульств\w*|\bелшилик\w*|\bembass(?:y|ies)\b|\bconsulates?\b",
    "police": r"\bполици\w*|\bполиция\b|\bpolice\b",
    "clinic": r"\bбольниц\w*|\bполиклиник\w*|\bклиник\w*|\bврач\w*|\bhospital\b|\bclinic\b|\bdoctor\b|\bемхана\b",
}
_OUT_RX = {key: re.compile(rx) for key, rx in _OUT_OF_DATA.items()}


def out_of_data(text: str) -> str | None:
    """The kind of place the message asks for that the dataset does not hold at all (a pharmacy, a currency
    exchange, a bank, a petrol station, a clinic), else None. A message that also names a kind of place the data has
    («кафе рядом с аптекой») is a search, not this."""
    if named_categories(text):
        return None
    words = " ".join(tokens(text))
    if _LATIN_ONLY.match(text) and re.search(r"[A-Za-z]", text):
        words = f"{words} " + " ".join(_translit_word(w) for w in re.findall(r"[A-Za-z]+", text))
    return next((key for key, rx in _OUT_RX.items() if rx.search(words)), None)


_FOLLOW_WORDS = re.compile(
    r"\b(?:рядом|ближе|поближе|далеко|недалеко|дешевле|подешевле|другое|друг\w+|еще)\b"
)
