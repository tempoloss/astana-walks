"""The place to eat a request puts first when the data hold no prices: «подешевле» — fast food and a canteen (столовая,
асхана) before a café, a café before a restaurant; a named fast-food dish («шаурму или бургер») — fast food and a
kebab / burger kitchen before a café that serves coffee. Pure rules of the ranking (walks.retrieve)."""

from __future__ import annotations

import re

from .models import POI, Intent

CHEAPER_KINDS = frozenset({"fast_food", "cafe"})
CHEAPER_BONUS = 1.0
CHEAPEST_BONUS = 2.0  # fast food and a canteen before a café: «подешевле» is not «кофейня»
_CANTEEN = re.compile(r"столов|асхана|canteen|cafeteria", re.I)
QUICK_CUISINES = frozenset(
    {"burger", "kebab", "shawarma", "doner", "hot_dog", "sandwich", "chicken", "pizza"}
)
QUICK_BONUS = 2.5  # «шаурму или бургер»: fast food and a kebab / burger kitchen before a café


def price_bonus(poi: POI, reasons: list[str]) -> float:
    """«Подешевле» or a price cap: a free place first, a paid one later; with no fee tag the kind of place is the only
    signal (a snack bar costs less than a café, a café less than a restaurant)."""
    fee = poi.tag_dict().get("fee")
    if fee == "no":
        reasons.append("free")
        return 1.0
    if fee == "yes":
        return -1.0
    cat = poi.category
    if cat == "fast_food" or (cat in CHEAPER_KINDS and _CANTEEN.search(poi.name)):
        return CHEAPEST_BONUS
    if cat in CHEAPER_KINDS:
        return CHEAPER_BONUS
    return -1.5 if cat == "restaurant" else 0.0


def quick_bonus(poi: POI, intent: Intent) -> float:
    """The person named a fast-food dish first: fast food or a kebab / burger kitchen leads."""
    if intent.wished[:1] != ["fast_food"]:
        return 0.0
    cuisines = set(poi.tag_dict().get("cuisine", "").split(";"))
    return QUICK_BONUS if poi.category == "fast_food" or cuisines & QUICK_CUISINES else 0.0
