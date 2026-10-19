"""The fact sheet of one candidate for the generation model: compact, but every concrete thing the data hold about the
place — its own human-written description (Wikipedia, Wikivoyage, the official site, OSM), the cuisine, the features
the tags state (seats outside, Wi-Fi, a playground, lit paths …), the street, the verified hours and walking minutes,
the people's marks. Code writes the labels in the answer language. `concrete(c, lang)` is the same sheet as short
phrases: a reason of the model must use at least one of them (walks.specific)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta

from .claims import unbacked_kinds
from .hours import to_local_naive
from .i18n import Entry, category_name, pick
from .i18n_cuisine import cuisine_label
from .models import Candidate, Recommendation, WeatherInfo
from .specific import opening_ok, states_status, uses_fact, vague_conditions
from .status import status_text

MAX_ABOUT_CHARS = (
    280  # the description sent to the model: enough for one concrete fact, short for speed
)
PRIVATE_REASONS = frozenset({"visited", "liked_category"})  # the profile's: never leave the machine
# (tag, value, label): the features a tag states, in kk / ru / en
_FEATURES: tuple[tuple[str, str, Entry], ...] = (
    ("outdoor_seating", "yes", ("сыртта отыратын орындар", "столики на улице", "outdoor seating")),
    ("internet_access", "wlan", ("Wi-Fi", "Wi-Fi", "Wi-Fi")),
    ("internet_access", "yes", ("интернет", "интернет", "internet access")),
    ("takeaway", "yes", ("алып кетуге болады", "можно взять с собой", "takeaway")),
    ("smoking", "no", ("темекі шегуге болмайды", "не курят", "no smoking")),
    ("wheelchair", "yes", ("баспалдақсыз кіреберіс", "вход без ступенек", "step-free entrance")),
    ("fee", "no", ("кіру тегін", "вход свободный", "free entry")),
    ("lit", "yes", ("кешке жарықтандырылған", "вечером освещено", "lit in the evening")),
    ("leisure", "playground", ("балалар алаңы", "детская площадка", "a playground")),
    ("leisure", "garden", ("бақ", "сад", "a garden")),
    ("leisure", "park", ("қалалық саябақ", "городской парк", "a city park")),
    ("leisure", "sports_centre", ("спорт орталығы", "спортивный центр", "a sports centre")),
    ("historic", "memorial", ("мемориал", "мемориал", "a memorial")),
    ("historic", "monument", ("ескерткіш", "памятник", "a monument")),
    ("tourism", "artwork", ("арт-нысан", "арт-объект", "an artwork")),
    ("tourism", "attraction", ("туристік орын", "туристическое место", "a tourist attraction")),
    ("amenity", "fountain", ("субұрқақ", "фонтан", "a fountain")),
    ("place", "square", ("алаң", "площадь", "a square")),
    ("indoor", "area", ("ғимарат ішінде", "в помещении", "indoors")),
    ("tourism", "viewpoint", ("шолу алаңы", "смотровая площадка", "a viewpoint")),
    ("diet:halal", "yes", ("халал", "халяль", "halal")),
    (
        "diet:vegetarian",
        "yes",
        ("вегетариандық тағамдар", "вегетарианские блюда", "vegetarian dishes"),
    ),
)
_OVERTURE: dict[str, Entry] = {
    "karaoke_venue": ("караоке", "караоке", "karaoke"),
    "music_venue": ("тірі музыка", "живая музыка", "live music"),
    "lounge": ("лаунж", "лаунж", "lounge"),
    "coffee_shop": ("кофехана", "кофейня", "coffee shop"),
    "bakery": ("наубайхана", "пекарня", "bakery"),
    "art_gallery": ("сурет галереясы", "арт-галерея", "art gallery"),
    "pub": ("паб", "паб", "pub"),
    "hookah_bar": ("кальян", "кальянная", "hookah"),
    "dessert_shop": ("тәттілер", "десерты", "desserts"),
    "tea_room": ("шайхана", "чайная", "tea room"),
    "sports_bar": ("спорт-бар", "спорт-бар", "sports bar"),
    "night_club": ("түнгі клуб", "ночной клуб", "night club"),
    "steakhouse": ("стейк-хаус", "стейк-хаус", "steakhouse"),
    "sushi_restaurant": ("суши", "суши", "sushi"),
    "pizza_restaurant": ("пицца", "пицца", "pizza"),
    "burger_restaurant": ("бургерлер", "бургеры", "burgers"),
    "asian_restaurant": ("азиялық тағам", "азиатская кухня", "Asian food"),
    "italian_restaurant": ("итальян тағамы", "итальянская кухня", "Italian food"),
    "shopping_mall": ("сауда орталығы", "торговый центр", "shopping mall"),
    "public_fountain": ("субұрқақ", "фонтан", "a fountain"),
    "park": ("саябақ", "парк", "a park"),
    "historic_site": ("тарихи орын", "историческое место", "a historic site"),
    "monument": ("ескерткіш", "памятник", "a monument"),
    "mosque": ("мешіт", "мечеть", "a mosque"),
    "irish_pub": ("ирланд пабы", "ирландский паб", "an Irish pub"),
    "cocktail_bar": ("коктейль-бар", "коктейль-бар", "a cocktail bar"),
    "beer_bar": ("сыра бары", "пивной бар", "a beer bar"),
    "wine_bar": ("шарап бары", "винный бар", "a wine bar"),
    "amusement_park": ("аттракциондар паркі", "парк аттракционов", "an amusement park"),
}
# a tag that only says the kind again («a viewpoint» of a viewpoint) is no fact about the place
_KIND_TAGS = {
    "viewpoint": ("tourism", "viewpoint"),
    "kids_playground": ("leisure", "playground"),
    "sport": ("leisure", "sports_centre"),
    "attraction_landmark": ("tourism", "attraction"),
}
_KIND_OVERTURE = {"cafe": ("coffee_shop",), "mall": ("shopping_mall",)}
_ADDRESS_NOISE = re.compile(
    r"\b(?:Астана|Astana|Нур-Султан|Nur-Sultan|Казахстан|Kazakhstan|Қазақстан)\b,?\s*", re.I
)
# what a card does not show of an address: the postcode, the city word, the district (said from the map), «дом» / «үй»,
# a unit code («B2.4»)
_ADDRESS_PARTS = (
    re.compile(r"(?<!\d)\d{6}(?!\d),?\s*"),
    _ADDRESS_NOISE,
    re.compile(r"(?<!\w)(?:г\.|город|қ\.|қаласы)(?!\w),?\s*", re.I),
    re.compile(r"(?<!\w)(?:район\s+[\w-]+|[\w-]+\s+ауданы|[\w-]+\s+district)(?!\w),?\s*", re.I),
    re.compile(r",\s*[A-Za-zА-Яа-я]\d+(?:\.\d+)+(?!\w)"),
    re.compile(r"(?<!\w)(?:дом|үй)(?!\w)\s*", re.I),
)
_YEAR = re.compile(r"^(1[6-9]\d\d|20\d\d)")
_OPENED: Entry = ("{y} жылы ашылған", "открыт в {y} году", "opened in {y}")


_CYRILLIC = re.compile(r"[А-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ]")
_NATIVE = re.compile(
    r"\s*\([^()]*[А-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ][^()]*\)"
)  # «(Kazakh: Нұр-Астана мешіті)»


def _in_script(text: str, lang: str) -> bool:
    """A source the model may lean on for an answer in `lang`: it quotes it as is, so the script must be the answer's."""
    return bool(_CYRILLIC.search(text)) == (lang != "en")


def about(c: Candidate, lang: str) -> str:
    """The place's own human-written description in the answer's script, best source first, cut at a sentence end
    near MAX_ABOUT_CHARS; '' when no source is written in it."""
    p = c.poi
    wiki = p.wikipedia.get(lang) or {} if p.wikipedia else {}
    own = p.description if p.description_source in {"osm", "wikipedia"} else ""
    sources = (wiki.get("extract"), p.description_voyage, p.description_official, own)
    sources = [_NATIVE.sub("", t) if t and lang == "en" else t for t in sources]
    text = next((t for t in sources if t and _in_script(t, lang)), "")
    text = " ".join(text.split())
    if len(text) <= MAX_ABOUT_CHARS:
        return text
    cut = text[:MAX_ABOUT_CHARS]
    end = max(cut.rfind(". "), cut.rfind("! "), cut.rfind("? "))
    return cut[: end + 1] if end > MAX_ABOUT_CHARS // 3 else cut.rstrip() + "…"


def features(c: Candidate, lang: str) -> list[str]:
    """What the tags and the record's own fields state about the place, as short phrases in the answer language."""
    p = c.poi
    tags = p.tag_dict()
    tags.setdefault("outdoor_seating", p.outdoor_seating or "")
    tags.setdefault("internet_access", p.internet_access or "")
    tags.setdefault("wheelchair", p.wheelchair or "")
    out = [
        pick(label, lang)
        for key, value, label in _FEATURES
        if tags.get(key) == value
        and _KIND_TAGS.get(p.category) != (key, value)  # not the kind said again
    ]
    if (kind := tags.get("overture_category", "")) in _OVERTURE and kind not in _KIND_OVERTURE.get(
        p.category, ()
    ):
        out.append(pick(_OVERTURE[kind], lang))
    if year := _YEAR.match(tags.get("start_date", "") or tags.get("opening_date", "")):
        out.append(pick(_OPENED, lang).format(y=year.group(1)))
    if p.price_text:
        out.append(p.price_text[:80])
    return list(dict.fromkeys(out))


def clean_address(addr: str | None) -> str:
    """The address as a card shows it: the street and the number («Мәңгілік Ел даңғылы, 55»), without the postcode,
    the country and the city, the district (the card says it from the map), «дом» / «үй» and a unit code («B2.4»)."""
    text = addr or ""
    for rx in _ADDRESS_PARTS:
        text = rx.sub("", text)
    text = re.sub(r"\s{2,}", " ", re.sub(r"(?:\s*,)+\s*", ", ", text))
    return re.sub(r"^[^\w«\"]+", "", text).strip(" ,;")


def street(c: Candidate) -> str:
    """The address as a card shows it (`clean_address`), '' when there is none."""
    return clean_address(c.poi.address)


def sheet(c: Candidate, lang: str, when: datetime | None = None) -> dict:
    """The candidate as the model needs it: every usable fact, nothing it must not write (coordinates, raw ids of other
    sources, a description the app derived from the record's own fields). The status comes ready from code (walks.status)
    and is the only one the model may repeat: the raw schedule is not sent, so no status is derived from it."""
    p = c.poi
    cuisine = cuisine_label(p.tag_dict().get("cuisine", ""), lang)
    text = about(c, lang)
    feats = features(c, lang)
    where = street(c)
    return {
        "poi_id": p.id,
        "name": p.name_for(lang),
        **({"generic_name": True} if p.name_generated else {}),
        "kind": category_name(p.category, lang),
        "walk_min": c.walk_min,
        "hours_state": c.hours_state,
        **({"status": card_status(c, when, lang)} if when is not None else {}),
        **({"opening_hours_source": p.hours_source()} if p.opening_hours else {}),
        **({"hours_issue": c.hours_issue} if c.hours_issue else {}),
        **({"about": text} if text else {}),
        **({"cuisine": cuisine} if cuisine else {}),
        **({"features": feats} if feats else {}),
        **({"street": where} if where else {}),
        **(
            {"description_official": p.description_official[:MAX_ABOUT_CHARS]}
            if p.description_official
            else {}
        ),
        "match": [r for r in c.reasons if r not in PRIVATE_REASONS],
        **({"people": c.people.model_dump(exclude_defaults=True)} if c.people else {}),
    }


def card_status(c: Candidate, when: datetime | None, lang: str) -> str:
    """The status line the card of `c` shows on arrival («Открыто до 22:00»); '' without a moment."""
    if when is None:
        return ""
    return status_text(
        c.poi, c.hours_state, to_local_naive(when) + timedelta(minutes=c.travel_min), lang
    )


_PEOPLE_WORDS: dict[str, Entry] = {  # what people's marks say, in words a reason uses
    "socket": ("розетка", "розетки", "power sockets"),
    "quiet": ("тыныш", "тихое спокойное", "quiet calm"),
    "noisy": ("шулы", "шумное", "noisy lively"),
}


def concrete(c: Candidate, lang: str) -> list[str]:
    """The concrete facts of the sheet a reason may use: description, cuisine, features, people's marks. The name, the
    kind, the status, the walking minutes and the address are not facts about the place: a reason made of them reads
    like a log («Это кафе расположено на улице Туркестан 34А»)."""
    p = c.poi
    ev = c.people
    marks = [
        pick(words, lang)
        for key, words in _PEOPLE_WORDS.items()
        if ev is not None and getattr(ev, key, 0) > 0
    ]
    out = [
        about(c, lang),
        cuisine_label(p.tag_dict().get("cuisine", ""), lang),
        *features(c, lang),
        *marks,
    ]
    return [x for x in out if x.strip()]


def allowed_numbers(c: Candidate) -> frozenset[str]:
    """The numbers a sentence of the model may state about `c`: its walking minutes and the times of its hours."""
    hours = (
        re.findall(r"\d{1,2}:\d{2}", c.poi.opening_hours or "")
        if c.hours_state != "unknown"
        else []
    )
    return frozenset({str(c.walk_min), *hours, *(h.lstrip("0") for h in hours)})


def vague_ids(recs: list[Recommendation], candidates: list[Candidate], lang: str) -> list[str]:
    """The model's cards whose text uses no concrete fact of the place. A filler phrase next to a fact does not make a
    card vague («Отлично подходит для ужина: кавказская кухня»); a bare address does («расположено на улице …»)."""
    by_id = {c.poi.id: c for c in candidates}
    out = []
    for r in recs:
        c = by_id.get(r.poi.id)
        if c is None or r.text_source != "llm":
            continue
        if not uses_fact(f"{r.why} {r.what_to_do}", concrete(c, lang), c.poi.name):
            out.append(r.poi.id)
    return out


def checked_opening(
    text: str,
    recs: list[Recommendation],
    candidates: list[Candidate],
    weather: WeatherInfo | None,
    lang: str,
    when: datetime | None = None,
) -> str:
    """The model's opening of the reply when code can stand behind it: it names the first card (by the name the answer
    shows), states only numbers of the payload (the temperature, the shown places' minutes and hours), a status only in
    the words of code (walks.status) and no place the answer does not show; else ''."""
    text = " ".join((text or "").split())
    if not text or not recs:
        return ""
    shown = {r.poi.id for r in recs}
    by_id = {c.poi.id: c for c in candidates}
    allowed: set[str] = set()
    statuses = []
    for r in recs:
        if (c := by_id.get(r.poi.id)) is not None:
            allowed |= allowed_numbers(c)
            statuses.append(card_status(c, when, lang))
    if weather is not None:
        allowed |= {
            str(abs(round(v))) for v in (weather.temperature_c, weather.apparent_c) if v is not None
        }
    others = [
        c.poi.name_for(lang)
        for c in candidates
        if c.poi.id not in shown and not c.poi.name_generated
    ]
    if recs[0].poi.name_for(lang).lower() not in text.lower() or not opening_ok(
        text, lang, allowed, others
    ):
        return ""
    if states_status(text) and not any(st and st.lower() in text.lower() for st in statuses):
        return ""  # «работает до 05:00», «сейчас открыто»: a status is said only as the card's own line
    if vague_conditions(text):
        return ""  # «в условиях плохого воздуха и холода подойдёт…»: the conditions are said with their numbers
    first = by_id.get(recs[0].poi.id)
    if first is not None and unbacked_kinds(
        text, first
    ):  # «круглосуточно», «халяль»: only what its record backs
        return ""
    return text if text[-1] in ".!?" else text + "."
