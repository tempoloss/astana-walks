"""Ranking rules of a stated wish that the record itself can confirm (walks.retrieve): Kazakh / national food, a museum
proper before a gallery or an exhibition organiser, a park or a boulevard first for a plain walk, a meal before a
coffee shop for «пожрать». Each adds to the score and names its reason; a place that does not confirm a food wish loses
a little. And the hours bonus when the data hold hours for few places: the nearer place wins."""

from __future__ import annotations

from .attributes import coffee_shop, event_organiser, local_food_signal, museum_proper
from .models import POI, Candidate, Intent
from .radius import FOOD_KINDS
from .shelter import LIT_NEAR, outdoor_wish

SIGHTS_WISH = frozenset(
    {"attraction_landmark", "museum_gallery"}
)  # «что посмотреть / what should I see»

LOCAL_FOOD_BONUS = 4.0  # a food place whose record says Kazakh / national food, when asked
MUSEUM_BONUS = 2.5  # «музей»: a museum the register or its tags name, before a gallery or an exhibition organiser
PARK_WALK_BONUS = 1.0  # «погулять»: a park or a boulevard to walk in before a monument to look at
COFFEE_FOR_FOOD_PENALTY = 2.5  # «пожрать», «шаурму»: a coffee shop never leads over a meal place
# the data hold hours for few places (most are «unknown»): «open» says more about the data than about the place, so its
# bonus and the unknown penalty shrink to a tie-break and the distance decides
RARE_UNKNOWN_LIFT = 0.7  # the daytime unknown penalty (1.0) becomes 0.3 ...
RARE_OPEN_CUT = 0.3  # ... and the open bonus (0.5) becomes 0.2


def wish_bonus(poi: POI, intent: Intent, reasons: list[str]) -> float:
    cat, wished = poi.category, set(intent.wished)
    s = 0.0
    if intent.local_food and cat in FOOD_KINDS:
        if local_food_signal(poi):
            s += LOCAL_FOOD_BONUS  # «бешбармак», «казахская кухня»: the record says it, it leads
            reasons.append("local_food")
        else:
            s -= 1.0
    if intent.eat and cat in FOOD_KINDS and coffee_shop(poi):
        s -= COFFEE_FOR_FOOD_PENALTY
    if cat == "museum_gallery" and "museum_gallery" in wished and museum_proper(poi):
        s += MUSEUM_BONUS
        reasons.append("museum")
    if cat == "park_garden" and {"park_garden", "attraction_landmark"} <= wished:
        s += PARK_WALK_BONUS
    return s


def seen_outside(poi: POI, intent: Intent) -> bool:
    """A famous sight asked to be seen (not a walk, which goes where it is open) stays when its doors are closed: at
    dawn Байтерек is seen from outside, and its card says «закрыто до 10:00»."""
    return (
        poi.category == "attraction_landmark"
        and set(intent.wished) >= SIGHTS_WISH
        and bool(poi.wikipedia)
    )


def not_for(poi: POI, intent: Intent) -> bool:
    """A place that is no answer to this person whatever its score: a playground for an adult (never a walk's
    «поближе»), an organiser of exhibitions (Астана-Экспо КС) for a museum wish."""
    if poi.category == "kids_playground":
        return not intent.with_kids and "kids_playground" not in intent.categories
    return (
        poi.category == "museum_gallery"
        and "museum_gallery" in intent.wished
        and event_organiser(poi)
    )


def evening_sight(cands: list[Candidate], intent: Intent) -> Candidate | None:
    """A walk after dark keeps the sight that is open and beside the light («огни», Байтерек until 21:00): the best
    such candidate, whatever the model preferred (walks.generate.required_cards)."""
    dark = {LIT_NEAR, "dark_outdoor"}
    sights = (
        c for c in cands if c.poi.category == "attraction_landmark" and c.hours_state == "open"
    )
    return (
        next((c for c in sights if dark & set(c.reasons)), None) if outdoor_wish(intent) else None
    )


def hours_rare(cands: list[Candidate], daytime: bool) -> list[Candidate]:
    """In the daytime, when the hours of most candidates are unknown, the open bonus and the unknown penalty shrink
    (a Coffee BOOM with hours a kilometre away does not beat a café without them next door); at night «unknown» is
    likely closed and stays a penalty."""
    if not daytime or sum(c.hours_state == "unknown" for c in cands) * 2 <= len(cands):
        return cands
    lift = {"unknown": RARE_UNKNOWN_LIFT, "open": -RARE_OPEN_CUT}
    return [c.model_copy(update={"score": c.score + lift.get(c.hours_state, 0.0)}) for c in cands]
