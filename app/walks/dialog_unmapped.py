"""A kind of place the person names that our categories cannot represent (a PS / computer club, a hookah lounge, a
sauna or a bath, karaoke, billiards, bowling, a quest, a massage or a spa): said, not swapped. The search runs for the
closest represented kind with the kind's own words as keywords (so a record that carries the name, «Taktika ps5»,
rises first); when no place of the answer carries those words, the reply says that the data has none near and offers
the closest kind with that framing. Never random places passed off as the wish. Rules only, offline."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .dialog_strings import s
from .intent import named_categories, parse_rules
from .models import CATEGORIES, POI, Intent, IntentResult


@dataclass(frozen=True)
class Kind:
    key: str
    asked: re.Pattern[
        str
    ]  # the person's words (lower case, as written and as `tokens` writes them)
    name: re.Pattern[str]  # the words a record of that kind carries in its name or tags
    near: tuple[str, ...]  # the closest represented categories
    keywords: tuple[str, ...]  # what the ranking looks for in a name or a description
    sub: str = ""  # the records of `near` that answer it (walks.wishes.of_subkind): «play», never a concert hall


# a PS evening, bowling, a quest: the nearest by meaning are places to play (bowling, billiards, an arcade, an
# entertainment centre, a cinema), never a concert or a congress hall that shares the category
PLAY_NEAR = ("entertainment", "culture_theatre_cinema")


def _kind(
    key: str, asked: str, name: str, near: tuple[str, ...], keywords: tuple[str, ...], sub: str = ""
) -> Kind:
    return Kind(key, re.compile(asked, re.I), re.compile(name, re.I), near, keywords, sub)


KINDS = (
    _kind(
        "gaming",
        r"\bпск[аеуи]?\b|\bпс ?[3-5]\b|\bps ?[3-5]\b|\bplay ?station\b|\bплойк\w*|\bпл[еэ]й ?ст[еэ]йш[еэ]?н\w*|\bпс[- ]?клуб\w*|\bps[- ]?(?:клуб|club)\w*|"
        r"\bприставк\w*|\bxbox\b|\bикс ?бокс\w*|\bкибер ?клуб\w*|\bпс[- ]?(?:центр|зал)\w*|"
        r"\bкомп(?:ьютерн\w*)? ?клуб\w*|\bкомпклуб\w*|\bкомп ?клаб\w*|\bкиберспорт\w*|\bкибер ?(?:клуб|кафе)\w*|\bигров\w* клуб\w*|"
        r"\bгеймерск\w* клуб\w*|\bгейм ?клуб\w*|\bgaming (?:club|lounge|zone)\b|\bcyber ?(?:cafe|club)\b|\binternet cafe\b|\bкомпьютерн\w* зал\w*|"
        r"\bойын клуб\w*|\bкомпьютер клуб\w*",
        r"ps ?[3-5]|play ?station|gaming|cyber|геймер|компьютерн\w* клуб|game ?club|игров\w* клуб",
        PLAY_NEAR,
        ("ps5", "playstation", "cyber", "gaming", "игровой клуб", "боулинг", "бильярд"),
        "play",
    ),
    _kind(
        "hookah",
        r"\bкальян\w*|\bhookah\w*|\bshisha\b|\bкальянн\w*",
        r"hookah|кальян|shisha|lounge|лаунж",
        ("bar_nightlife",),
        ("кальян", "hookah", "lounge"),
    ),
    _kind(
        "sauna",
        r"\bсаун\w*|\bбан[яеиюь]\b|\bбанн\w*|\bхамам\w*|\bhammam\b|\bsauna\b|\bbath ?house\b|\bпарная\b|\bпарной\b|\bшомылу\b|\bсауна\w*",
        r"sauna|саун|баня|банн|hammam|хамам|bath",
        ("sport", "entertainment"),
        ("сауна", "баня", "sauna"),
    ),
    _kind(
        "karaoke",
        r"\bкараоке\w*|\bkaraoke\b",
        r"karaoke|караоке|karaoké",
        ("bar_nightlife", "entertainment"),
        ("караоке", "karaoke"),
    ),
    _kind(
        "billiards",
        r"\bбильярд\w*|\bbilliards?\b|\bснукер\w*|\bsnooker\b",
        r"billiard|бильярд|снукер|луза",
        ("entertainment", "bar_nightlife"),
        ("бильярд", "billiard"),
    ),
    _kind(
        "bowling",
        r"\bбоулинг\w*|\bbowling\b|\bбоулингк\w*",
        r"bowling|боулинг",
        PLAY_NEAR,
        ("боулинг", "bowling"),
        "play",
    ),
    _kind(
        "quest",
        r"\bквест\w*|\bescape ?room\b|\bquest\b|\bквест ?комнат\w*",
        r"quest|квест|escape",
        PLAY_NEAR,
        ("квест", "quest", "escape room"),
        "play",
    ),
    _kind(
        "sports_screen",  # «where to watch the champions league»: a bar with a screen, if the data says so
        r"\b(?:watch|see|catch|show(?:s|ing)?)\b.{0,30}\b(?:football|soccer|match|game|champions league|europa league|hockey|ufc|f1)\b|"
        r"\b(?:football|soccer|match|champions league|ufc)\b.{0,20}\b(?:on tv|screen|live|broadcast)\w*|"
        r"\b(?:посмотреть|смотреть|показыва\w*|транслир\w*|глянуть)\b.{0,30}\b(?:футбол\w*|матч\w*|лиг\w+ чемпионов|хоккей|ufc|формул\w*)\b|"
        r"\bспорт ?бар\w*|\bsports? ?bar\w*|\bфутбол\w* на (?:большом )?экране\b",
        r"sport|спорт|футбол|\btv\b|screen|экран",
        ("bar_nightlife",),
        ("спорт", "sport", "tv", "футбол"),
    ),
    _kind(
        "massage",
        r"\bмассаж\w*|\bspa\b|\bспа\b|\bмассажк\w*|\bmassage\b|\bспа ?салон\w*",
        r"massage|массаж|\bspa\b|\bспа\b",
        ("sport", "entertainment"),
        ("массаж", "spa", "massage"),
    ),
)


@dataclass(frozen=True)
class Gap:
    kind: Kind
    result: IntentResult  # what the search is made from (the closest represented kind and the kind's words)

    def line(self, lang: str) -> str:
        return s(f"unmapped_{self.kind.key}", lang)

    def found_in(self, pois: list[POI]) -> bool:
        """Does a place of the answer carry the kind's own words in its name or tags?"""
        return any(self.kind.name.search(f"{p.name} {' '.join(p.tags)}") for p in pois)


def say_gap(turn, result, gap: Gap, lang: str) -> None:
    """The reply of a search for an unmapped kind starts with «таких мест в данных нет» unless a place of the answer
    carries the kind's own words («Taktika ps5»). `turn` is the Turn, `result` the search's Result (or None)."""
    if turn.kind in ("places", "none_found") and not (
        result and gap.found_in([r.poi for r in result.recs])
    ):
        turn.reply = f"{gap.line(lang)} {turn.reply}"


def read_gap(text: str, when=None) -> Gap | None:
    """The unmapped kind the message names, with the intent to search for the closest represented one; None when the
    message names none, or names another kind of place beside it (then it is read as usual)."""
    low = text.lower()
    found = next(((k, m) for k in KINDS if (m := k.asked.search(low))), None)
    if found is None:
        return None
    kind, own = found
    own_words = " ".join(m.group(0) for m in kind.asked.finditer(low))
    if (
        kind.key == "gaming"
    ):  # «playstation club», «ПС клуб»: the «club» of a gaming club is no nightclub
        own_words += " " + " ".join(re.findall(r"\b(?:club|клуб\w*|клаб\w*)\b", low))
    named = (
        set(named_categories(text))
        - set(named_categories(own_words))
        - set(named_categories(own.group(0)))
    )
    if named - set(kind.near):
        return None  # «кальян и поесть»: a meal is asked too, the usual reading serves both
    rules = parse_rules(text, when)
    if rules.intent.refusal != "none":
        return None
    keywords = [
        *kind.keywords,
        *(k for k in rules.intent.free_text_keywords if k not in kind.keywords),
    ]
    intent: Intent = rules.intent.model_copy(
        update={
            "categories": list(kind.near),
            "wished": [],  # the person named none of them: «Вы ищете: развлечения, театр» is not their word
            "refused": [
                c for c in CATEGORIES if c not in kind.near and c != "other"
            ],  # no padding with random places
            "free_text_keywords": keywords[:8],
            "subkind": kind.sub,  # «пску»: places to play only, never a concert hall
        }
    )
    note = f"{kind.key}: такого вида места в данных нет → ближайшее {', '.join(kind.near)}"
    return Gap(kind, IntentResult(intent=intent, parser="rules", note=note))
