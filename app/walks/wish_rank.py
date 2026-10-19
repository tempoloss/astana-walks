"""Ranking rules of a stated wish that the record itself can confirm (walks.retrieve): Kazakh / national food, a museum
proper before a gallery or an exhibition organiser, a park or a boulevard first for a plain walk, a meal before a
coffee shop for «пожрать». Each adds to the score and names its reason; a place that does not confirm a food wish loses
a little. And the hours bonus when the data hold hours for few places: the nearer place wins."""

from __future__ import annotations

from .attributes import coffee_shop, event_organiser, local_food_signal, museum_proper
from .models import POI, Candidate, Intent
from .radius import FOOD_KINDS, INFO_ABOUT
from .shelter import LIT_NEAR, outdoor_wish
from .wishes import ERRANDS, errand, of_subkind, off_subkind, subkind_of

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
    «поближе»), an organiser of exhibitions (Астана-Экспо КС) for a museum wish, what the sub-kind asked keeps out
    (walks.wishes.off_subkind: a concert hall for a PS evening, a courier for a post office, a dentist for a sick
    child)."""
    if poi.category == "kids_playground":
        return not intent.with_kids and "kids_playground" not in intent.categories
    if off_subkind(poi, subkind_of(intent)):
        return True
    return (
        poi.category == "museum_gallery"
        and "museum_gallery" in intent.wished
        and event_organiser(poi)
    )


def wish_found(cands: list[Candidate], intent: Intent) -> bool:
    """Does the pool hold what the record must confirm of the wish (the search widens its radius until it does):
    Kazakh food, a museum proper for «музей?», a record of the sub-kind asked (a dentist, a children's clinic)."""
    if intent.local_food and not any("local_food" in c.reasons for c in cands):
        return False
    if intent.wished == ["museum_gallery"] and not any("museum" in c.reasons for c in cands):
        return False
    sub = subkind_of(intent)
    return not sub or any(of_subkind(c.poi, sub) for c in cands)


def errand_first(cands: list[Candidate], intent: Intent) -> Candidate | None:
    """An errand's first candidate (wishes.errand_order: the nearest the data confirm open, a cash machine for
    «банкомат»), and in a request that pairs an errand with another kind («почта и кафе») the best one of the errand
    kind: the answer shows it whatever the model or the score preferred (walks.generate.required_cards)."""
    kinds = set(intent.wished or intent.categories)
    if errand(list(kinds)):
        return cands[0] if cands else None
    return next((c for c in cands if c.poi.category in kinds & ERRANDS), None)


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


# «а рейтинг?»: there is no rating in the data, so where code picks the cards (walks.generate.template_recs), among
# places of one kind this close on foot the one the data know more of comes first; the answer says nothing about it
NEAR_EQUAL_MIN = 3
# the reasons a ranking rule gave a place for the person's own wish: a place without one never moves above it
_WISH_MARKS = frozenset(
    {"halal", "local_food", "museum", INFO_ABOUT, LIT_NEAR, "kids", "landmark_ref"}
) | {
    *("liked_category", "pets", "wifi", "socket", "quiet", "wheelchair", "open_at_night"),
    *("weather_indoor", "weather_outdoor"),
}


def evidence(c: Candidate) -> int:
    """How much the data know of a place: an article (Wikipedia / Wikivoyage), a website, people's marks (up to 3),
    known hours, a brand. A count of the record's facts, never a rating."""
    p, ev = c.poi, c.people
    marks = 0 if ev is None else ev.n_open + ev.n_closed + ev.socket + ev.wifi + ev.quiet + ev.noisy
    return (
        bool(p.wikipedia or p.description_voyage)
        + bool(p.website)
        + min(marks, 3)
        + (c.hours_state != "unknown")
        + bool(p.tag_dict().get("brand"))
    )


def _marks(c: Candidate) -> set[str]:
    return {r for r in c.reasons if r in _WISH_MARKS or r.startswith(("diet:", "keywords:"))}


def _better_known(a: Candidate, b: Candidate) -> bool:
    """Does `a` go before `b`, ranked just above it: one kind, within NEAR_EQUAL_MIN on foot, every wish mark of `b`
    on `a` too, and more evidence."""
    return (
        a.poi.category == b.poi.category
        and abs(a.walk_min - b.walk_min) <= NEAR_EQUAL_MIN
        and _marks(b) <= _marks(a)
        and evidence(a) > evidence(b)
    )


def evidence_first(cands: list[Candidate]) -> list[Candidate]:
    """The ranked candidates, a better known place moved above a neighbour it is about as near as (`_better_known`);
    the rank order holds otherwise. «Поближе» and errands keep the plain distance order (walks.wishes.errand_order)."""
    out = list(cands)
    for i in range(1, len(out)):
        j = i
        while j > 0 and _better_known(out[j], out[j - 1]):
            out[j - 1], out[j] = out[j], out[j - 1]
            j -= 1
    return out
