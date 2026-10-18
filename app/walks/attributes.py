"""What a record says about a place, as ranking signals: free-text keywords, Wi-Fi, sockets, alcohol, wheelchair."""

from __future__ import annotations

import re

from .models import POI


def _haystack(poi: POI) -> tuple[str, str]:
    """(names, everything else) lowercased."""
    names = " ".join([poi.name, *poi.names.values()]).lower()
    rest = " ".join(
        filter(
            None,
            [poi.description, poi.description_official, poi.description_auto, " ".join(poi.tags)],
        )
    ).lower()
    return names, rest


def _kw_regex(kw: str) -> re.Pattern[str]:
    return re.compile(rf"(?<![\w]){re.escape(kw.lower().strip())}", re.U)


def keyword_score(poi: POI, keywords: list[str]) -> tuple[float, list[str]]:
    names, rest = _haystack(poi)
    score, hits = 0.0, []
    for kw in keywords:
        if not kw.strip():
            continue
        rx = _kw_regex(kw)
        if rx.search(names):
            score += 2.0
            hits.append(kw)
        elif rx.search(rest):
            score += 1.0
            hits.append(kw)
    return min(score, 6.0), hits


def has_wifi(poi: POI) -> bool:
    v = (poi.internet_access or poi.tag_dict().get("internet_access") or "").lower()
    return v in {"wlan", "yes", "wifi", "wi-fi", "terminal"}


def has_socket(poi: POI) -> bool:
    td = poi.tag_dict()
    if td.get("power_supply", "").lower() in {"yes", "true"}:
        return True
    return any(k.startswith("socket") and v not in {"no", "0", ""} for k, v in td.items())


def crowd_bonus(marks: int) -> float:
    """Wi-Fi / sockets known only from people's marks: a bit less than the OSM tag, more with more marks."""
    return 1.5 + 0.5 * min(marks - 1, 2)


_ALCOHOL_TAGS = frozenset(
    {"alcohol=yes", "amenity=bar", "amenity=pub", "amenity=nightclub", "amenity=biergarten"}
    | {
        f"overture_category={c}"
        for c in (
            "bar",
            "pub",
            "irish_pub",
            "beer_bar",
            "gastropub",
            "brewery",
            "lounge",
            "cocktail_bar",
            "sports_bar",
            "hotel_bar",
            "dance_club",
            "bar_and_grill_restaurant",
        )
    }
)


def serves_alcohol(poi: POI) -> bool:
    """«А без алкоголя»: bars / nightlife by category, or a tag that says alcohol is served."""
    return poi.category == "bar_nightlife" or any(t in _ALCOHOL_TAGS for t in poi.tags)


def wheelchair_access(poi: POI) -> str | None:
    v = (poi.wheelchair or poi.tag_dict().get("wheelchair") or "").lower()
    return v or None


_HALAL_NAME = re.compile(r"halal|халал|халяль|حلال", re.I)
_HALAL_TAGS = frozenset(
    {
        "diet:halal=yes",
        "diet:halal=only",
        "halal=yes",
        "overture_category=halal_restaurant",
        "overture_category=halal_food",
    }
)


def halal_signal(poi: POI) -> bool:
    """The record itself says halal: a `diet:halal=yes|only` / `halal=yes` tag, Overture's halal restaurant class, or
    the word in a name or a human-written description. A cuisine («плов»), a kebab, a website domain or a guess is not
    a signal."""
    if _HALAL_TAGS & set(poi.tags):
        return True
    text = " ".join([poi.name, *poi.names.values(), poi.real_text()])
    return bool(_HALAL_NAME.search(text))


# ---------------------------------------------------------------- diets: vegetarian, vegan, gluten-free, kosher

DIETS = ("vegetarian", "vegan", "gluten_free", "kosher")
# tag values of OSM `diet:*=yes|only` and Overture classes; vegan food is vegetarian too
_DIET_TAGS: dict[str, frozenset[str]] = {
    "vegetarian": frozenset(
        {
            "diet:vegetarian=yes",
            "diet:vegetarian=only",
            "diet:vegan=yes",
            "diet:vegan=only",
            "overture_category=vegetarian_restaurant",
            "overture_category=vegan_restaurant",
        }
    ),
    "vegan": frozenset({"diet:vegan=yes", "diet:vegan=only", "overture_category=vegan_restaurant"}),
    "gluten_free": frozenset({"diet:gluten_free=yes", "diet:gluten_free=only"}),
    "kosher": frozenset(
        {"diet:kosher=yes", "diet:kosher=only", "overture_category=kosher_restaurant"}
    ),
}
_DIET_WORDS: dict[str, re.Pattern[str]] = {
    "vegetarian": re.compile(r"вегетариан|vegetarian|без мяса|meat-?free", re.I),
    "vegan": re.compile(r"\bвеган|\bvegan", re.I),
    "gluten_free": re.compile(r"глютен|gluten|целиак|celiac|coeliac", re.I),
    "kosher": re.compile(r"кошер|kosher|кашрут", re.I),
}
_MEAT_CUISINES = frozenset({"steak_house", "barbecue", "kebab"})
_MEAT_NAME = re.compile(
    r"meat|мясн|стейк|steak|шашлы|shashl[iy]k|барбекю|bbq|\bgrill\b|гриль|кебаб|kebab|\bkal'?bi\b",
    re.I,
)


def diet_signal(poi: POI, diet: str) -> bool:
    """The record itself marks the diet: a `diet:<x>=yes|only` tag or an Overture class of it. Nothing else counts:
    not a cuisine, not a menu guess (a steak house does not become gluten-free for a coeliac)."""
    return bool(_DIET_TAGS[diet] & set(poi.tags))


def meat_place(poi: POI) -> bool:
    """A meat-centred place (steak house, barbecue, kebab, «meat house»): the wrong answer to a vegetarian request."""
    cuisines = set(poi.tag_dict().get("cuisine", "").split(";"))
    if cuisines & _MEAT_CUISINES:
        return True
    return bool(_MEAT_NAME.search(" ".join([poi.name, *poi.names.values()])))


def requested_diets(intent) -> list[str]:
    """The diets a request names: the rule parser's `Intent.diets` plus the diet words among the keywords (the model
    may only add keywords). «vegetarian, vegan» together asks for the looser one."""
    found = list(getattr(intent, "diets", []) or [])
    text = " ".join(intent.free_text_keywords)
    for diet, rx in _DIET_WORDS.items():
        if diet not in found and rx.search(text):
            found.append(diet)
    if "vegan" in found and "vegetarian" in found:
        found.remove("vegan")
    return found


PETS_TAGS = frozenset(
    {"dog=yes", "dog=leashed", "dog=outside", "dog=designated", "dogs=yes", "pets=yes", "pet=yes"}
)


def pets_signal(poi: POI) -> bool:
    """The record says animals are welcome: a `dog=*` / `pets=yes` tag. A terrace (`outdoor_seating`) does not."""
    return bool(PETS_TAGS & set(poi.tags))
