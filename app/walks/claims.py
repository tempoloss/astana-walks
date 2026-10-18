"""Attribute-backing check of the model's text: a sentence of the AI card that asserts an attribute of the place
(halal, step-free access, Wi-Fi, sockets, quiet, for children, prices, banquets, gaming machines, round-the-clock
hours) is kept only when a field of the record (its tags and typed attributes, or the anonymous marks of people)
backs it. Same authority as the poi_id check: an unbacked sentence is dropped, and the card says in its notes that the
data do not state it. A sentence that itself says the data do not state it is a label, not a claim, and stays.

The claim table is the one place that says which words are an assertion and which field backs it; the no-AI template
never writes an attribute without its field (walks.reasons), so it needs no such check."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .attributes import (
    diet_signal,
    halal_signal,
    has_socket,
    has_wifi,
    pets_signal,
    wheelchair_access,
)
from .hours import is_24_7
from .kids import kids_signal
from .models import Candidate
from .shelter import has_indoor_signal
from .weather import INDOOR_CATEGORIES

_SPLIT = re.compile(r"(?<=[.!?])\s+")
# a sentence that says the data do NOT state / confirm it: a label, not a claim (the eval's `_NOT_CONFIRMED` + more)
_LABEL = re.compile(
    r"не подтвержд|не указан|нет данных|в данных нет|неизвестн|не уточн"
    r"|not (?:stated|specified|confirmed|listed|verified)|no data|unknown|unverified|isn't (?:stated|listed)"
    r"|расталмаған|көрсетілмеген|белгісіз|деректер жоқ|нақтыланбаған",
    re.I,
)
_LATE_HOURS = re.compile(r"-\s*(?:2[2-9]|0[0-4]):\d\d|24/7")


@dataclass(frozen=True)
class Claim:
    kind: str
    words: re.Pattern[str]
    backed: Callable[[Candidate], bool]
    note: (
        str | None
    )  # i18n key of the «not in the data» note the card gets (None: the hours note already exists)


def _wheelchair_backed(c: Candidate) -> bool:
    return wheelchair_access(c.poi) in {"yes", "limited", "designated"}


def _wifi_backed(c: Candidate) -> bool:
    return has_wifi(c.poi) or bool(c.people and c.people.wifi)


def _socket_backed(c: Candidate) -> bool:
    return has_socket(c.poi) or bool(c.people and c.people.socket)


def _quiet_backed(c: Candidate) -> bool:
    return "quiet" in c.reasons or bool(c.people and c.people.noise == "quiet")


def _kids_backed(c: Candidate) -> bool:
    return c.poi.category == "kids_playground" or "kids" in c.reasons or kids_signal(c.poi)


def _free_backed(c: Candidate) -> bool:
    return c.poi.tag_dict().get("fee") == "no"


_GAMBLING_TAGS = frozenset(
    {"amenity=casino", "leisure=amusement_arcade", "shop=lottery", "shop=bookmaker"}
)


_VIEW_WORDS = re.compile(
    r"смотров|observation (?:deck|platform)|панорам|шолу алаң|viewing platform", re.I
)


def _view_backed(c: Candidate) -> bool:
    """An observation deck / climb is stated by the record: a viewpoint, a `tourism=viewpoint` tag, or the word in its
    human-written description (OSM, the place's own website) or Wikipedia text."""
    p = c.poi
    if p.category == "viewpoint" or "tourism=viewpoint" in p.tags:
        return True
    text = " ".join([p.real_text(), *(a.get("extract", "") for a in p.wikipedia.values())])
    return bool(_VIEW_WORDS.search(text))


def _gambling_backed(c: Candidate) -> bool:
    p = c.poi
    return bool(_GAMBLING_TAGS & set(p.tags)) or any(t.startswith("gambling") for t in p.tags)


def _round_clock_backed(c: Candidate) -> bool:
    return is_24_7(c.poi.opening_hours)


def _late_backed(c: Candidate) -> bool:
    return bool(_LATE_HOURS.search(c.poi.opening_hours or ""))


GROUP_MIN_CAPACITY = (
    12  # a place states room for a big party only by `capacity=N` with N this large
)


def _pets_backed(c: Candidate) -> bool:
    return pets_signal(c.poi)


def capacity_backed(c: Candidate) -> bool:
    cap = c.poi.tag_dict().get("capacity", "")
    return cap.isdigit() and int(cap) >= GROUP_MIN_CAPACITY


def _never(_: Candidate) -> bool:
    return False


_I = re.I
CLAIMS: tuple[Claim, ...] = (
    Claim(
        "halal",
        re.compile(r"halal|халал|халяль|حلال", _I),
        lambda c: halal_signal(c.poi),
        "note_halal",
    ),
    Claim(
        "vegetarian",
        re.compile(
            r"вегетариан|vegetarian|без мяса|meat-?free|vegetable-based|plant-based|растительн", _I
        ),
        lambda c: diet_signal(c.poi, "vegetarian"),
        "note_diet_vegetarian",
    ),
    Claim(
        "vegan",
        re.compile(r"\bвеган|\bvegan", _I),
        lambda c: diet_signal(c.poi, "vegan"),
        "note_diet_vegan",
    ),
    Claim(
        "gluten_free",
        re.compile(r"глютен|gluten|целиак|celiac|coeliac", _I),
        lambda c: diet_signal(c.poi, "gluten_free"),
        "note_diet_gluten_free",
    ),
    Claim(
        "kosher",
        re.compile(r"кошер|kosher|кашрут", _I),
        lambda c: diet_signal(c.poi, "kosher"),
        "note_diet_kosher",
    ),
    Claim(
        "open_early_late",
        re.compile(
            r"early[- ]morning|early in the morning|open (?:early|late)|late[- ]night|after midnight"
            r"|ранним утром|рано утром|на рассвете|поздно ночью|после полуночи|в ночное время|ночью работает"
            r"|таңертең ерте|түнде ашық",
            _I,
        ),
        lambda c: c.hours_state == "open",
        None,
    ),
    Claim(
        "viewpoint",
        re.compile(
            r"смотров|observation (?:deck|platform)|панорам|view of the (?:city|capital)|вид на (?:город|столиц)"
            r"|подняться на|подъём на|подняться наверх|go up to|up to the top|шолу алаң|жоғарғы бөлі|шығып",
            _I,
        ),
        lambda c: _view_backed(c),
        "note_view",
    ),
    Claim(
        "interior",
        re.compile(
            r"зайти внутрь|войти внутрь|попасть внутрь|walk inside|go inside|step inside|enter the (?:building|sphere)"
            r"|ішіне кіру",
            _I,
        ),
        lambda c: c.poi.category in INDOOR_CATEGORIES or has_indoor_signal(c.poi),
        None,
    ),
    Claim(
        "access",
        re.compile(
            r"коляск|инвалид|маломобильн|wheelchair|stroller|pushchair|\bpram\b|step-?free|ramp\b|пандус"
            r"|без ступен|без лестниц|ровн\w+ (?:дорожк|покрыти|тротуар|поверхност|асфальт)"
            r"|(?:flat|even|smooth|level) (?:paths?|walkways?|surfaces?)|(?<!easily )\baccessible\b"
            r"|доступн\w+ для (?:всех|людей|колясок|маломобильн|инвалид)|арба\b|арбамен|арбалы|мүгедек"
            r"|баспалдақсыз|тегіс (?:жол|төсем)",
            _I,
        ),
        _wheelchair_backed,
        "note_wheelchair",
    ),
    Claim(
        "wifi",
        re.compile(r"wi-?fi|вай-?фай|вайфай|wlan|\bинтернет|\binternet\b", _I),
        _wifi_backed,
        "note_wifi",
    ),
    Claim(
        "socket",
        re.compile(r"розетк|\bsockets?\b|\boutlets?\b|power (?:plugs?|points?|sockets?)", _I),
        _socket_backed,
        "note_wifi",
    ),
    Claim(
        "quiet",
        re.compile(
            r"\bтих(?:о|ое|ий|ая|ие|ую|им|ом|их)\b|тишин|\bquiet(?:ly)?\b|тыныш(?:\w*)?", _I
        ),
        _quiet_backed,
        "note_quiet",
    ),
    Claim(
        "kids",
        re.compile(
            r"для детей|детям|детск|с детьми|с ребёнк|с ребенк|семейн\w+ отдых|\bkids?\b|\bchild(?:ren)?\b"
            r"|family-friendly|балалар|баламен",
            _I,
        ),
        _kids_backed,
        "note_kids",
    ),
    Claim(
        "free",
        re.compile(
            r"бесплатн\w+ (?:вход|посещен|проход)|вход\w* (?:\w+ )?бесплатн|вход свободн"
            r"|free (?:entry|admission|of charge|to enter)|(?:entry|admission) is free"
            r"|ақысыз кіру|кіру ақысыз|тегін кіру",
            _I,
        ),
        _free_backed,
        "note_price",
    ),
    Claim(
        "price",
        re.compile(
            r"недорог|дешев|дёшев|бюджетн|доступн\w+ цен|низк\w+ цен|приемлем\w+ цен|\bдорог(?:о|ой|ая|ое|ие|ий)\b"
            r"|affordable|inexpensive|\bcheap\b|budget-friendly|(?:low|reasonable|moderate) prices?|expensive"
            r"|арзан|қымбат",
            _I,
        ),
        _never,
        "note_price",
    ),
    Claim(
        "booking",
        re.compile(
            r"банкет|banquet|корпоратив|свадьб|wedding|групп\w* гостей|group booking"
            r"|бронирован|забронир|dress ?code|дресс-?код",
            _I,
        ),
        _never,
        "note_booking",
    ),
    Claim(
        "pets",
        re.compile(
            r"с собак|собак\w* (?:можно|разрешен)|с питомц|с животн|питомц|pet[- ]friendly|dog[- ]friendly"
            r"|with (?:a |your )?(?:dog|pet)s?|\bdogs? (?:are )?(?:allowed|welcome)|bring (?:a |your )?dog"
            r"|итпен|жануар|үй жануар",
            _I,
        ),
        lambda c: _pets_backed(c),
        "note_pets",
    ),
    Claim(
        "group",
        re.compile(
            r"больш\w+ (?:компани|групп)|для (?:компани|групп)|компани\w+ из|групп\w+ (?:из )?\d+|\d+ человек"
            r"|large (?:group|part(?:y|ies))|big (?:group|part(?:y|ies))|group of \d|part(?:y|ies) of \d"
            r"|(?:for|suits|suitable for) (?:a )?groups?|whole (?:team|company)"
            r"|үлкен (?:топ|компания)|топқа|компанияға|\d+ адам",
            _I,
        ),
        capacity_backed,
        "note_group",
    ),
    Claim(
        "gambling",
        re.compile(
            r"игров\w+ автомат|slot machines?|\bslots\b|казино|casino|gambl|ставк|betting|лотере|lottery|букмекер|ойын автомат",
            _I,
        ),
        _gambling_backed,
        "note_gambling",
    ),
    Claim(
        "toilet",
        re.compile(
            r"туалет|уборн|санузел|\bwc\b|toilets?\b|restrooms?\b|washrooms?\b|дәретхана|даретхана|әжетхана",
            _I,
        ),
        lambda c: any(t.startswith("toilets") for t in c.poi.tags),
        "note_toilet",
    ),
    Claim(
        "round_clock",
        re.compile(
            r"круглосуточ|24/7|24 часа|24 hours|(?:round|around)[- ]the[- ]clock|тәулік бойы", _I
        ),
        _round_clock_backed,
        None,
    ),
    Claim(
        "late_hours",
        re.compile(
            r"до полуночи|допоздна|до поздней ночи|until midnight|open late|late[- ]night|түн ортасына дейін",
            _I,
        ),
        _late_backed,
        None,
    ),
)


def unbacked_kinds(sentence: str, c: Candidate) -> list[str]:
    """Kinds of the claims `sentence` makes that no field of the candidate backs (a label that says the data do not
    state it makes none)."""
    if _LABEL.search(sentence):
        return []
    return [k.kind for k in CLAIMS if k.words.search(sentence) and not k.backed(c)]


def strip_unbacked(text: str, c: Candidate) -> tuple[str, list[str]]:
    """`text` without the sentences that assert an attribute the record does not back, and the kinds of the removed
    claims (one entry per kind per removed sentence)."""
    kept: list[str] = []
    removed: list[str] = []
    for sentence in _SPLIT.split(text.strip()):
        if not sentence:
            continue
        kinds = unbacked_kinds(sentence, c)
        if kinds:
            removed.extend(kinds)
        else:
            kept.append(sentence)
    return " ".join(kept), removed


def note_keys(kinds: list[str]) -> list[str]:
    """The i18n keys of the «not stated in the data» notes for removed claims, each once, in order (a gluten claim also
    brings the advice to ask the staff)."""
    by_kind = {k.kind: k.note for k in CLAIMS}
    out: list[str] = []
    for kind in kinds:
        for key in (by_kind[kind], "note_gluten_medical" if kind == "gluten_free" else None):
            if key and key not in out:
                out.append(key)
    return out


# Wishes of a request that no field of any record can answer (the dataset has no toilets, changing tables or menus):
# the keyword that names one makes every card say so, instead of the wish being dropped without a word.
_UNSUPPORTED = (
    (
        re.compile(r"туалет|wc\b|restroom|toilet", re.I),
        ("дәретхана", "туалет рядом", "a toilet nearby"),
    ),
    (
        re.compile(r"пеленальн|changing table|baby[- ]?changing|нәресте", re.I),
        ("жаялық үстелі", "пеленальный столик", "a baby changing table"),
    ),
    (
        re.compile(r"детск\w+ меню|kids?'? menu|children'?s menu|балалар мәзірі", re.I),
        ("балалар мәзірі", "детское меню", "a kids menu"),
    ),
    (
        re.compile(r"комнат\w+ матери|mother'?s room|nursing room|feeding room", re.I),
        ("ана бөлмесі", "комната матери", "a mother-and-baby room"),
    ),
)


def unsupported_wishes(keywords: list[str], lang: str) -> list[str]:
    """What the keywords ask for that the data cannot tell (one entry per wish, in the answer language)."""
    from .i18n import LANGS

    text = " ".join(keywords)
    idx = LANGS.index(lang if lang in LANGS else "ru")
    return [label[idx] for rx, label in _UNSUPPORTED if rx.search(text)]
