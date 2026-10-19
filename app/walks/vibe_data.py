"""The tables of «поиск по вайбу» (walks.vibe): the eight facets a person can ask for, in kk / ru / en; which tags and
kinds of a record say which facet, and how clearly; the words a card uses for the data behind a facet; the phrases
that ask for the stored vibe or state one («куда сходить интроверту»).

A facet is something the data can actually hold: the kind of place (OSM / Overture tags, the category), its hours
(open after midnight), the marks of people («тихо» / «шумно»), its human-written texts and whether an encyclopedia or a
travel guide has it. «Уютно» or «новое» are not facets: no field of a record says them. A strength is 1.0 when the
evidence says the facet plainly (a park is nature) and 0.5 when it only leans that way (a museum is usually quiet)."""

from __future__ import annotations

import re
from typing import Literal

from .i18n import Entry

Facet = Literal["calm", "lively", "nature", "culture", "food", "active", "night", "unusual"]
FACETS: tuple[Facet, ...] = (
    "calm",
    "lively",
    "nature",
    "culture",
    "food",
    "active",
    "night",
    "unusual",
)
# the introvert ↔ extrovert axis: wanting one pole is a reason to rank the other one lower
OPPOSITE: dict[str, str] = {"calm": "lively", "lively": "calm"}
FACET_NAME: dict[str, Entry] = {
    "calm": ("тыныш", "тихо", "quiet"),
    "lively": ("шулы", "шумно", "lively"),
    "nature": ("табиғат", "природа", "nature"),
    "culture": ("өнер мен тарих", "искусство и история", "art and history"),
    "food": ("тамақ пен кофе", "еда и кофе", "food and coffee"),
    "active": ("белсенді демалыс", "активный отдых", "active"),
    "night": ("түнгі өмір", "ночная жизнь", "nightlife"),
    "unusual": ("ерекше", "необычное", "unusual"),
}

# ---------------------------------------------------------------- what a record says

Rule = tuple[str, dict[str, float]]  # (kind, {facet: strength})
_PARK: Rule = ("park", {"nature": 1.0, "calm": 0.5})
_LIBRARY: Rule = ("library", {"calm": 1.0, "culture": 0.5})
_MUSEUM: Rule = ("museum", {"culture": 1.0, "calm": 0.5})
_GALLERY: Rule = ("gallery", {"culture": 1.0, "calm": 0.5})
_THEATRE: Rule = ("theatre", {"culture": 1.0})
_ARTS: Rule = ("arts_centre", {"culture": 1.0})
_CONCERT: Rule = ("concert_hall", {"culture": 1.0, "lively": 0.5})
_CINEMA: Rule = ("cinema", {"culture": 0.5})
_MONUMENT: Rule = ("monument", {"culture": 1.0})
_BAR: Rule = ("bar", {"night": 1.0, "lively": 1.0})
_PUB: Rule = ("pub", {"night": 1.0, "lively": 1.0})
_MALL: Rule = ("mall", {"lively": 1.0})
_COFFEE: Rule = ("coffee", {"food": 1.0})
_CAFE: Rule = ("cafe", {"food": 1.0})
_RESTAURANT: Rule = ("restaurant", {"food": 1.0})
_SPORTS: Rule = ("sports", {"active": 1.0})
_BOWLING: Rule = ("bowling", {"lively": 1.0, "active": 0.5})
_AMUSEMENT: Rule = ("amusement_park", {"lively": 1.0, "active": 0.5, "unusual": 0.5})
_ARCADE: Rule = ("arcade", {"lively": 1.0, "unusual": 0.5})
# "key=value" -> what the tag says. The order is the order a card names the kinds in: the telling one first («кофейня»
# before «кафе», «караоке» before «бар»).
TAG_RULES: dict[str, Rule] = {
    "leisure=escape_game": ("escape_room", {"unusual": 1.0}),
    "tourism=aquarium": ("aquarium", {"unusual": 1.0, "nature": 0.5}),
    "overture_category=science_museum": ("science_museum", {"culture": 1.0, "unusual": 1.0}),
    "overture_category=theme_restaurant": ("theme_restaurant", {"food": 1.0, "unusual": 1.0}),
    "tourism=theme_park": _AMUSEMENT,
    "overture_category=amusement_park": _AMUSEMENT,
    "leisure=amusement_arcade": _ARCADE,
    "overture_category=arcade": _ARCADE,
    "overture_category=wildlife_sanctuary": ("nature_area", {"nature": 1.0}),
    "leisure=park": _PARK,
    "overture_category=park": _PARK,
    "leisure=garden": ("garden", {"nature": 1.0, "calm": 0.5}),
    "tourism=viewpoint": ("viewpoint", {"nature": 0.5, "calm": 0.5}),
    "amenity=library": _LIBRARY,
    "overture_category=library": _LIBRARY,
    "tourism=museum": _MUSEUM,
    "overture_category=museum": _MUSEUM,
    "overture_category=history_museum": _MUSEUM,
    "tourism=gallery": _GALLERY,
    "overture_category=art_gallery": _GALLERY,
    "amenity=theatre": _THEATRE,
    "overture_category=theatre_venue": _THEATRE,
    "overture_category=music_venue": _CONCERT,
    "amenity=events_venue": _CONCERT,
    "overture_category=auditorium": _CONCERT,
    "amenity=arts_centre": _ARTS,
    "overture_category=cultural_center": _ARTS,
    "amenity=cinema": _CINEMA,
    "overture_category=movie_theater": _CINEMA,
    "historic=archaeological_site": ("archaeology", {"culture": 1.0, "unusual": 0.5}),
    "tourism=artwork": ("artwork", {"culture": 1.0, "unusual": 0.5}),
    "historic=memorial": _MONUMENT,
    "historic=monument": _MONUMENT,
    "overture_category=monument": _MONUMENT,
    "overture_category=historic_site": ("historic_site", {"culture": 1.0}),
    "amenity=nightclub": ("nightclub", {"night": 1.0, "lively": 1.0}),
    "overture_category=karaoke_venue": ("karaoke", {"night": 1.0, "lively": 1.0}),
    "overture_category=hookah_bar": ("hookah", {"night": 1.0, "lively": 0.5}),
    "overture_category=lounge": ("lounge", {"night": 1.0, "lively": 0.5}),
    "amenity=pub": _PUB,
    "overture_category=pub": _PUB,
    "overture_category=irish_pub": _PUB,
    "overture_category=gastropub": _PUB,
    "amenity=bar": _BAR,
    "overture_category=bar": _BAR,
    "overture_category=cocktail_bar": _BAR,
    "overture_category=beer_bar": _BAR,
    "overture_category=sports_bar": _BAR,
    "overture_category=brewery": _BAR,
    "shop=mall": _MALL,
    "overture_category=shopping_mall": _MALL,
    "overture_category=department_store": _MALL,
    "leisure=bowling_alley": _BOWLING,
    "overture_category=bowling_alley": _BOWLING,
    "leisure=ice_rink": ("ice_rink", {"active": 1.0}),
    "sport=ice_skating": ("ice_rink", {"active": 1.0}),
    "overture_category=swimming_pool": ("pool", {"active": 1.0}),
    "overture_category=stadium_arena": ("stadium", {"active": 1.0}),
    "leisure=sports_centre": _SPORTS,
    "overture_category=sport_or_fitness_facility": _SPORTS,
    "overture_category=tennis_court": _SPORTS,
    "overture_category=race_track": _SPORTS,
    "overture_category=hockey_field": _SPORTS,
    "cuisine=coffee_shop": _COFFEE,
    "overture_category=coffee_shop": _COFFEE,
    "overture_category=bakery": ("bakery", {"food": 1.0}),
    "amenity=cafe": _CAFE,
    "overture_category=cafe": _CAFE,
    "amenity=restaurant": _RESTAURANT,
    "overture_category=restaurant": _RESTAURANT,
}
RESTAURANT_SUFFIX = (
    "_restaurant"  # Overture's «asian_restaurant», «steakhouse_restaurant», …: a restaurant
)
# the kind of the category when no tag above says more; a tag below takes the category's default away
CATEGORY_RULES: dict[str, Rule] = {
    "park_garden": _PARK,
    "viewpoint": ("viewpoint", {"nature": 0.5, "calm": 0.5}),
    "museum_gallery": _MUSEUM,
    "culture_theatre_cinema": ("culture_venue", {"culture": 0.5}),
    "coworking_library": ("coworking", {"calm": 0.5}),
    "bar_nightlife": _BAR,
    "cafe": _CAFE,
    "restaurant": _RESTAURANT,
    "fast_food": ("fast_food", {"food": 0.5}),
    "sport": _SPORTS,
    "mall": _MALL,
    "entertainment": ("entertainment", {"lively": 0.5}),
}
NO_VIBE_TAGS = frozenset(
    {
        "amenity=place_of_worship",  # a mosque or a church is nobody's «vibe»
        "amenity=community_centre",
        "leisure=playground",  # a children's room is the children's
        "leisure=indoor_play",
    }
)
# the places whose late hours are a night out: a bar or a club, a place of entertainment, a cinema (its late show). A
# café, a restaurant or fast food open late is still a meal, a pharmacy or a shop open all night an errand.
LATE_CATEGORIES = frozenset({"bar_nightlife", "entertainment"})
LATE_KINDS = frozenset({"cinema"})
# the places an encyclopedia or a travel-guide entry is evidence for (art and history, something unusual): a museum, a
# gallery, a landmark, a theatre, a monument, a place of worship. An article on a mall, a shop, a café or a station
# says nothing of the kind.
SIGHT_CATEGORIES = frozenset({"museum_gallery", "attraction_landmark"})
SIGHT_KINDS = frozenset(
    {
        *("museum", "science_museum", "gallery", "theatre", "concert_hall", "arts_centre"),
        *("monument", "historic_site", "archaeology", "artwork"),
    }
)
SIGHT_TAGS = frozenset({"amenity=place_of_worship"})
# betting is never anyone's vibe: a bookmaker («Спорт-бар "Финал", БК FairPlay» is tagged a bar), a lottery, a casino
BETTING_TAGS = frozenset(
    {
        *("shop=bookmaker", "shop=lottery", "amenity=gambling", "amenity=casino"),
        "leisure=adult_gaming_centre",
    }
)
BETTING_WORDS = re.compile(
    r"\bБК\b|букмекер|bookmaker|\bbetting\b|казино|\bcasino\b|лига ставок|fair\s?play|fonbet|olimpbet"
    r"|1xbet|parimatch|melbet|tennisi",
    re.I,
)
# the kinds whose liveliness is the evening's: in the daytime and with children they say nothing of a vibe
NIGHT_KINDS = frozenset({"bar", "pub", "nightclub", "karaoke", "hookah", "lounge"})
# with children a mall is no lively place to go to (the family's liveliness: entertainment, an amusement park, a park)
ADULT_LIVELY_KINDS = NIGHT_KINDS | {"mall"}
LATE_CLOSE_H = 23  # a schedule that closes at 23:xx is late (0.5); past midnight or round the clock, plainly (1.0)
# words of the human-written texts (the place's own site, OSM, Wikipedia, Wikivoyage), never of a derived description
TEXT_WORDS: dict[str, re.Pattern[str]] = {
    "calm": re.compile(
        r"\b(?:тих\w*|спокойн\w*|уединен\w*|уединён\w*|умиротвор\w*|quiet|peaceful)\b", re.I
    ),
    "lively": re.compile(
        r"\b(?:шумн\w*|живая музыка|живой музык\w*|live music|вечеринк\w*|танцпол\w*|диджей\w*)\b",
        re.I,
    ),
    "unusual": re.compile(
        r"\b(?:необычн\w*|уникальн\w*|интерактивн\w*|unusual|unique|interactive)\b", re.I
    ),
}

# ---------------------------------------------------------------- the words of a card

KIND_NAME: dict[str, Entry] = {
    "park": ("саябақ", "парк", "park"),
    "garden": ("бақ", "сад", "garden"),
    "nature_area": ("табиғи аймақ", "природная зона", "nature area"),
    "viewpoint": ("шолу алаңы", "смотровая площадка", "viewpoint"),
    "library": ("кітапхана", "библиотека", "library"),
    "coworking": ("коворкинг", "коворкинг", "coworking"),
    "museum": ("мұражай", "музей", "museum"),
    "science_museum": ("ғылым мұражайы", "научный музей", "science museum"),
    "gallery": ("галерея", "галерея", "gallery"),
    "theatre": ("театр", "театр", "theatre"),
    "arts_centre": ("мәдениет орталығы", "культурный центр", "arts centre"),
    "concert_hall": ("концерт залы", "концертный зал", "concert hall"),
    "cinema": ("кинотеатр", "кинотеатр", "cinema"),
    "culture_venue": ("мәдени орын", "место культуры", "cultural venue"),
    "monument": ("ескерткіш", "памятник", "monument"),
    "historic_site": ("тарихи орын", "историческое место", "historic site"),
    "archaeology": ("археологиялық ескерткіш", "археологический памятник", "archaeological site"),
    "artwork": ("арт-нысан", "арт-объект", "artwork"),
    "bar": ("бар", "бар", "bar"),
    "pub": ("паб", "паб", "pub"),
    "nightclub": ("түнгі клуб", "ночной клуб", "nightclub"),
    "karaoke": ("караоке", "караоке", "karaoke"),
    "hookah": ("кальян бар", "кальянная", "hookah lounge"),
    "lounge": ("лаунж", "лаунж", "lounge"),
    "mall": ("сауда орталығы", "торговый центр", "mall"),
    "cafe": ("кафе", "кафе", "café"),
    "coffee": ("кофехана", "кофейня", "coffee shop"),
    "bakery": ("наубайхана", "пекарня", "bakery"),
    "restaurant": ("мейрамхана", "ресторан", "restaurant"),
    "theme_restaurant": ("тақырыптық мейрамхана", "тематический ресторан", "theme restaurant"),
    "fast_food": ("фастфуд", "фастфуд", "fast food"),
    "sports": ("спорт кешені", "спорткомплекс", "sports centre"),
    "ice_rink": ("мұз айдыны", "каток", "ice rink"),
    "pool": ("бассейн", "бассейн", "swimming pool"),
    "stadium": ("стадион", "стадион", "stadium"),
    "bowling": ("боулинг", "боулинг", "bowling"),
    "amusement_park": ("ойын-сауық паркі", "парк развлечений", "amusement park"),
    "escape_room": ("квест бөлмесі", "квест-комната", "escape room"),
    "aquarium": ("океанариум", "океанариум", "aquarium"),
    "arcade": ("ойын автоматтары", "игровые автоматы", "arcade"),
    "entertainment": ("ойын-сауық орны", "развлечения", "entertainment"),
}
SOURCE_NAME: dict[str, Entry] = {
    "people": ("адамдардың белгілері бойынша", "по отметкам людей", "by people's marks"),
    "people_demo": ("үлгі белгілер бойынша", "по примерным отметкам", "by sample marks"),
    "late": ("кеш жабылады, кесте бойынша", "допоздна, по часам работы", "open late, by its hours"),
    "allday": (
        "тәулік бойы, кесте бойынша",
        "круглосуточно, по часам работы",
        "round the clock, by its hours",
    ),
    "wiki": ("Уикипедияда мақаласы бар", "есть статья в Википедии", "has a Wikipedia article"),
    "voyage": (
        "Wikivoyage жолсілтемесінде бар",
        "есть в путеводителе Wikivoyage",
        "in the Wikivoyage guide",
    ),
    "text": ("сипаттамасы бойынша", "по описанию", "by its description"),
}
LINE_HEAD: Entry = ("Сіздің вайбыңызға: ", "Под ваш вайб: ", "Your vibe: ")
LEAD: Entry = (
    "Сіздің вайбыңызға сай — {facets}.",
    "Под ваш вайб — {facets}.",
    "For your vibe — {facets}.",
)
LEAD_NONE: Entry = (
    "Жақын маңдағы деректерде вайбыңыздың белгілері бар орын жоқ — төменде уақытқа сай орындар.",
    "В данных рядом нет мест с признаками вашего вайба — ниже то, что подходит по времени.",
    "The data near you hold no place with signs of your vibe — below is what fits the time.",
)
UNSET: Entry = (
    "Вайбыңызға сай іздеу үшін «Жад» ішіндегі «Менің вайбым» бөлімінде айтыңыз: интроверт пе, экстраверт пе және "
    "не ұнайды.",
    "Чтобы искать под ваш вайб, расскажите о нём в «Памяти» → «Мой вайб»: интроверт вы или экстраверт и что вам "
    "нравится.",
    "To search for your vibe, tell me about it in «Memory» → «My vibe»: introvert or extrovert, and what you like.",
)

# ---------------------------------------------------------------- the words of a request

# «под мой вайб», «под моё настроение», «менің вайбыма», «my vibe»: the stored vibe is asked for
ASKS_VIBE = re.compile(
    r"\b(?:под|по|для|в) (?:мой|моё|мое|мою|свой|своё|свое|моему|своему|моим|моём|моем) "
    r"(?:вайб\w*|настроени\w*)"
    r"|\bмо(?:й|его|ему|им|ём|ем) вайб\w*|\bменің (?:вайб\w*|көңіл-күй\w*)|\bвайбыма\b"
    r"|\b(?:my|our) (?:vibe|mood)\b",
    re.I,
)
INTROVERT = re.compile(r"\bинтроверт\w*|\bintrovert\w*", re.I)
EXTROVERT = re.compile(r"\bэкстр[ао]верт\w*|\bextr[ao]vert\w*", re.I)

VIBE_TEXT_MAX = 300  # characters of the person's own words about their vibe


def clean_weights(value: object) -> dict[str, float]:
    """A stored vibe as code uses it: known facets only, weights in (0, 1], in the order of FACETS."""
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for facet in FACETS:
        raw = value.get(facet)
        if isinstance(raw, int | float) and not isinstance(raw, bool) and raw > 0:
            out[facet] = round(min(float(raw), 1.0), 2)
    return out
