"""Words for OpenStreetMap `cuisine=` values in Kazakh / Russian / English (an unknown value is not shown)."""

from __future__ import annotations

from .i18n import Entry, pick

CUISINE: dict[str, Entry] = {
    "coffee_shop": ("кофе", "кофе", "coffee"),
    "burger": ("бургер", "бургеры", "burgers"),
    "chicken": ("тауық", "курица", "chicken"),
    "pizza": ("пицца", "пицца", "pizza"),
    "regional": ("жергілікті", "местная", "regional"),
    "local": ("жергілікті", "местная", "local"),
    "breakfast": ("таңғы ас", "завтраки", "breakfast"),
    "italian": ("итальян", "итальянская", "Italian"),
    "chinese": ("қытай", "китайская", "Chinese"),
    "russian": ("орыс", "русская", "Russian"),
    "oriental": ("шығыс", "восточная", "oriental"),
    "asian": ("азиялық", "азиатская", "Asian"),
    "european": ("еуропалық", "европейская", "European"),
    "japanese": ("жапон", "японская", "Japanese"),
    "sushi": ("суши", "суши", "sushi"),
    "cake": ("торттар", "торты", "cakes"),
    "sandwich": ("сэндвич", "сэндвичи", "sandwiches"),
    "international": ("халықаралық", "интернациональная", "international"),
    "kebab": ("кебаб", "кебаб", "kebab"),
    "georgian": ("грузин", "грузинская", "Georgian"),
    "steak_house": ("стейк", "стейки", "steaks"),
    "korean": ("корей", "корейская", "Korean"),
    "french": ("француз", "французская", "French"),
    "turkish": ("түрік", "турецкая", "Turkish"),
    "barbecue": ("барбекю", "барбекю", "barbecue"),
    "pasta": ("паста", "паста", "pasta"),
    "tea": ("шай", "чай", "tea"),
    "seafood": ("теңіз өнімдері", "морепродукты", "seafood"),
    "pastry": ("тоқаш-тәттілер", "выпечка", "pastries"),
}


def cuisine_label(osm_value: str, lang: str | None) -> str:
    """«coffee_shop;burger» -> «кофе, бургеры» (the values this table knows, nothing else)."""
    names = [pick(CUISINE[v], lang) for v in dict.fromkeys(osm_value.split(";")) if v in CUISINE]
    return ", ".join(names[:2])
