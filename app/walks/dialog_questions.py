"""Questions about places already shown or named («а там розетки есть», «how long to walk to Baiterek», «вход платный»):
which topic a message asks about (`PlaceQuestion`), which of the shown places it is about (`targets`), and the words
that make a message a question about a place rather than a request for one. Rules only, offline; the answers are
walks.dialog_place and walks.dialog_facts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Literal

from .dialog_nlu import KK_EXISTS, mentioned, tokens
from .dialog_types import DialogState, ShownPlace, Topic
from .intent import named_categories
from .lexicon import without_durations

MAX_QUESTION_WORDS = 10
LONG_QUESTION_WORDS = 16  # «how long does it take to walk from here to Baiterek»
QuestionTopic = (
    Topic
    | Literal[
        "entry",
        "menu",
        "menu_kids",
        "menu_kazakh",
        "socket",
        "kids_room",
        "visit",
        "closing",
        "atm",
        "exchange",
        "round_clock",
    ]
)
KIND_SAFE_TOPICS = frozenset(
    {"price", "entry", "menu", "menu_kids", "menu_kazakh", "kids_room", "visit", "atm", "exchange"}
)  # asked of a shown place even when the text names a kind («is that kazakh food?»)
_LONG_OK = re.compile(  # questions that run long: how far / how long, is it worth ...
    r"\bhow (?:long|many minutes|far)\b|\bсколько (?:минут|времени)\b|\bканша минут\b|\bworth\b|\bстоит ли\b"
)
_ROUTE_TIME = re.compile(
    r"\bhow (?:long|many minutes|far)\b|\bсколько (?:минут|времени)\b|\bканша минут\b"
)


@dataclass(frozen=True)
class PlaceQuestion:
    topic: Topic
    ordinal: int | None = None  # 0-based index in the shown places
    plural: bool = False
    marked: bool = False  # the message points at «this place» («там», «оно», «есть ли», «?»)
    also: tuple[str, ...] = ()  # the other topics the same message asks («… и есть ли там туалет»)

    @property
    def kind_safe(self) -> bool:
        """Asked of a shown place even when the text names a kind of place («а там есть банкомат круглосуточно»)."""
        return bool(KIND_SAFE_TOPICS & {self.topic, *self.also})


_MARK = (
    r"\b(?:там|тут|оно|он|она|у них|здесь|есть ли|имеется|there|it|does|do they|is there|are there|"
    r"ол жерде|онда|сонда|мунда|мында|бул жерде|осы жерде)\b|\bесть(?= и\b|$)|\?"
)
# (topic, regex, needs a marker of «this place» next to it)
_TOPICS: tuple[tuple[QuestionTopic, str, bool], ...] = (
    (
        "closing",  # before «hours»: «до какого часа он работает» asks for the closing time, not for open / closed
        r"\bдо какого (?:часа|времени)\b|\bдо скольки\b|\bдо сколько\b|\bдо которого часа\b|\bкашанга дейин\b|\bкашанга чейин\b|\bво сколько закрыва\w*|\bдо которого часа\b|\bкогда закрыва\w*|"
        r"\buntil (?:when|what time)\b|\bwhat time (?:does|do) (?:it|they|the \w+) (?:close|shut)\b|\bwhen (?:does|do) (?:it|they) close\b|"
        r"\btill what time\b|\bhow late\b|\bнешеге дейін\b|\bнешеде жабыл\w*|\bкашан жабыл\w*",
        False,
    ),
    (
        "exchange",  # a question FORM («меняют ли там доллары»): «где обменять доллары» is a search
        r"\bменя(?:ют|ет) ли\b|\bобменива(?:ют|ет) ли\b|\bменя(?:ют|ет) (?:там|тут)\b|\bможно (?:ли )?(?:там |тут )?(?:обменять|поменять)\b|"
        r"\bdo (?:they|you) (?:change|exchange|take|buy)\b|\bcan (?:i|you|we) (?:change|exchange)\b|\bwill they (?:change|exchange)\b|"
        r"\bайырбастай(?:ды)? ма\b|\bайырбастауга бола ма\b|\bайырбастап бере ме\b",
        False,
    ),
    (
        "atm",  # only about a place pointed at («есть ли там банкомат»); «где банкомат» is a search
        r"\bбанкомат\w*|\batms?\b|\bcash machines?\b|\bcash point\b",
        True,
    ),
    (
        "visit",  # «is it worth going up at night or in the morning»: the hours and the entry together
        r"\bстоит ли\b|\bстоит (?:туда|подниматься|идти|ехать|заходить|посещать|посетить)\b|\bworth (?:it|going|visiting|a visit|the|seeing)\b|"
        r"\bis it worth\b|\bтура ма\b|\bбаруга тура\b",
        False,
    ),
    (
        "kids_room",  # «ТД Эверестте балаларға арналған ойын бөлмесі бар ма»
        r"\bойын болмес\w*|\bдетск\w* (?:комнат|зон|уголок)\w*|\bигров\w* (?:комнат|зон)\w*|\bplay ?room\b|\bkids? (?:room|zone|corner)\b|"
        r"\bchildren'?s (?:room|corner|zone)\b|\bchild care\b|\bдетская комната\b",
        False,
    ),
    (
        "socket",
        r"\bрозетк\w*|\bsockets?\b|\boutlets?\b|\bзарядк\w*|\bcharg(?:er|ing)\b|\bplugs?\b|\bзарядтал\w*",
        True,
    ),
    (
        "entry",  # before «hours»: «does it cost money to go in» is about the fee, not about getting in
        r"\bвход\w* (?:платн|бесплатн|свободн)\w*|\b(?:платн|бесплатн)\w* (?:вход|ли)\b|\bвход\w* (?:стоит|цена)|"
        r"\bсколько стоит (?:вход|билет)\w*|\bстоимость (?:вход|билет)\w*|\bбилет\w*|\bплатно\b|\bбесплатно\b|\bплатный\b|\bплатн\w* ли\b|"
        r"\b(?:надо|нужно) (?:ли )?платить\b|\bплатить за вход\b|\bтегин (?:бе|ме|ба|ма)\b|\bкиру (?:акылы|багасы)\b|\bакылы ма\b|"
        r"\b(?:does it|do i|do we|do you|will it) (?:cost|have to pay|need to pay)\b|\bcosts? (?:money|anything)\b|\bis it free\b|"
        r"\bfree (?:to|entry|admission|of charge)\b|\bhow much (?:to|is) (?:go|get|enter|entry|admission|the (?:entry|ticket))\w*|"
        r"\bentry fee\b|\bentrance fee\b|\badmission\b|\btickets?\b|\b(?:have|need) to pay\b|\bpay to\b",
        False,
    ),
    (
        "menu_kids",
        r"\bдетск\w* меню\b|\bменю для дет\w*|\bkids? menu\b|\bchild(?:ren)?s? menu\b|\bбалалар мазир\w*|\bбалаларга арнал\w* мазир\w*",
        True,
    ),
    (
        "menu_kazakh",
        r"\bказахск\w* (?:кухн\w*|еда|блюд\w*)\b|\bнациональн\w* (?:кухн\w*|еда|блюд\w*)\b|\bkazakh (?:food|cuisine|dishes)\b|"
        r"\bnational (?:food|cuisine)\b|\bказак (?:асханасы|тагам\w*|тамагы)\b",
        True,
    ),
    (
        "menu",
        r"\bкакая (?:там |у них )?кухн\w*|\bкухн\w* (?:там|у них)\b|\bчто (?:у них |там )?(?:подают|готовят)\b|\bчто (?:там |у них )?можно (?:поесть|заказать|съесть)\b|"
        r"\bчем кормят\b|\bчто (?:там |у них )?в меню\b|\bменю\b|\bкакие блюда\b|\bwhat (?:do|does) (?:they|it|the place) (?:serve|cook|offer|have)\b|"
        r"\bwhat'?s (?:on )?the menu\b|\bmenu\b|\b(?:what|which|the) (?:kind of |type of )?cuisine\b|\bwhat kind of food\b|\bwhat can i (?:eat|order)\b|"
        r"\bмазир\w*|\bкандай (?:тамак|тагам|ас)\w*",
        True,
    ),
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
        "round_clock",  # after «hours»: «круглосуточно ли» alone is the hours answer, «банкомат круглосуточно» adds it
        r"\bкруглосуточн\w*|\b24 ?(?:/|на)? ?7\b|\baround the clock\b|\b24 hours\b|\bтаулик бои\b|\bтулик бои\b",
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
        r"\bсколько стоит\b|\bкакие цены\b|\bцены\b|\bцена\b|\bhow much\b|\bprices?\b|\bбагасы\b|\bкандай баг\w*|\bканша тур\w*",
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


_COVERS = {  # a topic that already answers another one asked in the same message
    "entry": {"price"},
    "menu_kids": {"menu"},
    "menu_kazakh": {"menu"},
    "closing": {"hours", "round_clock"},
    "visit": {"hours", "entry", "price"},
}


_ANCHORED = frozenset({"atm"})  # asked only of a place the message points at (not by the «?» alone)
_ANCHOR = re.compile(
    r"\b(?:там|тут|здесь|у них|они|оно|there|they|here|мунда|мында|онда|сонда|бул жерде|осы жерде|ол жерде)\b"
)


def _topics(text: str, question_mark: bool = False) -> list[str]:
    """Every topic the message asks, in the table's order, without the ones another already covers."""
    marked = question_mark or bool(_MARKER.search(text))
    pointed = bool(_ANCHOR.search(text))
    found = [
        t
        for t, rx, needs in _COMPILED
        if rx.search(text) and (marked or not needs) and (pointed or t not in _ANCHORED)
    ]
    covered = {c for t in found for c in _COVERS.get(t, ())}
    return list(dict.fromkeys(t for t in found if t not in covered))


_SEGMENTS = re.compile(
    r"\s+(?:и|а также|and|also|және|жане|а еще|а ещё|а еще)\s+|[,;]"
)  # `жане`: «және» as `tokens` writes it


def _asked_topics(text: str, question_mark: bool = False) -> list[str]:
    """The topic of the message (the first one the table finds in it) and, after it, the topics of its LATER parts
    («сколько стоит вход» и «есть ли там туалет»): one sentence that merely matches two words asks one thing."""
    if not _topics(text, question_mark):
        return []
    marked = question_mark or bool(_MARKER.search(text))
    pointed = bool(_ANCHOR.search(text))
    out: list[str] = []
    for part in _SEGMENTS.split(
        text
    ):  # the message's own order: the first topic of each part, in the order said
        found = [t for t in _topics(part, marked) if t not in _ANCHORED or pointed]
        if found:
            out.append(found[0])
            if found[0] not in ("hours", "closing") and "round_clock" in found[1:]:
                out.append("round_clock")  # «банкомат круглосуточно»: one part, two things
    covered = {c for t in out for c in _COVERS.get(t, ())}
    return (
        list(dict.fromkeys(t for t in out if t not in covered)) or _topics(text, question_mark)[:1]
    )


def _topic(text: str, question_mark: bool = False) -> Topic | None:
    topics = _topics(text, question_mark)
    return topics[0] if topics else None  # type: ignore[return-value]


def place_question(text: str, *, allow_kind: bool = False) -> PlaceQuestion | None:
    """The question about places the message asks, else None. Short messages only; a message that names a kind of
    place is a request, not a question («а там есть кафе» searches), unless `allow_kind` (a named place is the
    subject: «Национальный музей сейчас открыт?»). The kazakh «X бар ма» («is there X?») is a search for X, never a
    question about a shown place; how long a walk takes may be asked at some length."""
    norm = " ".join(tokens(text))
    limit = LONG_QUESTION_WORDS if _LONG_OK.search(norm) else MAX_QUESTION_WORDS
    if len(norm.split()) > limit and len(_topics(norm, "?" in text)) >= 2:
        limit = LONG_QUESTION_WORDS  # «а до скольки он работает и есть ли розетки и вайфай»: several parts, one message
    if not norm or len(norm.split()) > limit:
        return None
    norm = without_durations(
        norm
    )  # «2 hours before the flight» is a time budget, not the «hours» of a place
    if named_categories(text) and not allow_kind:
        return None
    ordinal = next((i for i, rx in _ORD if rx.search(norm)), None)
    exists = KK_EXISTS.search(norm) is not None
    asked = "?" in text and not exists
    topics = _asked_topics(norm, asked)
    topic = topics[0] if topics else None
    if topic is None and ordinal is None:
        return None
    return PlaceQuestion(
        topic=topic or "about",  # type: ignore[arg-type]
        also=tuple(topics[1:]),
        ordinal=ordinal,
        plural=bool(_PLURAL.search(norm)) and ordinal is None,
        marked=asked or bool(_MARKER.search(norm)),
    )


def asks_visit(text: str) -> bool:
    """«is it worth going up at night or in the morning»: the «night» and «morning» are what is asked about, not the time."""
    pq = place_question(text, allow_kind=True)
    return pq is not None and pq.topic == "visit"


def targets(state: DialogState, pq: PlaceQuestion, text: str) -> list[ShownPlace]:
    """The place(s) a question is about: by ordinal («второе»), by name, plural («они»), the place the last
    question was about, else the main one."""
    shown = state.shown
    if pq.ordinal is not None:
        return shown[pq.ordinal : pq.ordinal + 1]
    named = mentioned(text, [p.name for p in shown])
    if named is not None:
        return [shown[named]]
    if pq.plural and shown:
        return list(shown)
    if state.asked is not None and (state.focus_id == state.asked.id or not shown):
        return [state.asked]
    focus = next((p for p in shown if p.id == state.focus_id), None)
    return [focus or shown[0]] if shown else []


def refers_to_focus(text: str) -> bool:
    return bool(_FOCUS.search(" ".join(tokens(text))))
