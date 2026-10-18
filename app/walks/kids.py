"""Places for children that the category alone does not name. A request «с ребёнком: площадка» is answered with
indoor kids places too (a play centre, a trampoline park, an indoor playground: `entertainment` in the data), and the
outdoor `kids_playground` stays for the weather that allows it (the shelter rule of retrieve removes it in frost / smog).

A place counts as a kids place only by a field: the tags `for_kids=yes` (the collector's kids signal), `leisure=indoor_play`,
`playground=indoor`, an indoor `leisure=playground`, a theme park / aquarium / zoo, or a kids word in a human-written
description. Without one it is an ordinary place of its category and is never called «подходит для детей».
"""

from __future__ import annotations

import re
from collections import Counter

from .i18n import norm, plural_ru
from .models import POI, Candidate, Intent, Padding

KIDS_TAGS = frozenset(
    {
        "for_kids=yes",
        "leisure=indoor_play",
        "playground=indoor",
        "tourism=theme_park",
        "tourism=aquarium",
        "tourism=zoo",
    }
)
_KIDS_WORDS = re.compile(r"дет|интерактив|kids|children|interactive", re.I)
# categories that can hold a kids place besides the playgrounds themselves
KIDS_HOST_CATEGORIES = frozenset({"entertainment", "museum_gallery"})


def kids_signal(poi: POI) -> bool:
    """The record itself says it is for children."""
    tags = set(poi.tags)
    if tags & KIDS_TAGS or ("leisure=playground" in tags and "indoor=yes" in tags):
        return True
    text = " ".join(filter(None, [poi.real_text(), poi.name]))
    return bool(_KIDS_WORDS.search(text))


def is_kids_place(poi: POI) -> bool:
    return poi.category == "kids_playground" or (
        poi.category in KIDS_HOST_CATEGORIES and kids_signal(poi)
    )


def is_member(poi: POI, member_cats: set[str], requested: list[str], intent: Intent) -> bool:
    """Is `poi` of a requested kind? Its category is one of them, or (a request with a child that wants playgrounds)
    it is an indoor kids place of another category."""
    if poi.category in member_cats:
        return True
    return (
        intent.with_kids
        and "kids_playground" in requested
        and poi.category == "entertainment"
        and kids_signal(poi)
    )


NAMED_DETOUR_MIN = (
    15  # a named place counts as an alternative to an anonymous one only within this walk
)


def is_near_named(c: Candidate) -> bool:
    return not c.poi.name_generated and c.travel_min <= NAMED_DETOUR_MIN


def allowed_unnamed(named_total: int, slots: int) -> int:
    """How many of `slots` cards may be anonymous OSM records («Детская площадка»): one when two named places
    exist; never all of them while a named one exists."""
    return max(1, slots - named_total)


def padding_of(
    c: Candidate,
    requested: list[str],
    member_cats: set[str],
    declared_m: int,
    intent: Intent,
    substitutes: frozenset[str] = frozenset(),
) -> Padding:
    """How the card relates to the request: another category than requested, added to fill up -> "backfill"; an
    indoor category (`substitutes`) offered instead of the requested outdoor one because of the weather ->
    "substituted"; a requested kind found beyond the declared radius -> "expanded"; otherwise "none". An indoor
    kids place of a kids request is a match (is_member), not a substitute."""
    if requested and not is_member(c.poi, member_cats, requested, intent):
        return "backfill"
    if c.poi.category in substitutes and not is_member(c.poi, set(requested), requested, intent):
        return "substituted"
    return "expanded" if c.distance_m > declared_m else "none"


def keep_named(cands: list[Candidate], top: list[Candidate], want: int = 3) -> list[Candidate]:
    """`top` (the first of the ranked `cands`) with at least `want` named places within a short walk, when there
    are that many: where anonymous OSM records (hundreds of «Детская площадка») would fill the whole list, the best
    named ones replace the lowest-ranked anonymous ones. Rank order is kept."""
    named = [c for c in top if is_near_named(c)]
    extra = [c for c in cands if is_near_named(c) and c not in top][: max(0, want - len(named))]
    kept = list(top)
    for add in extra:
        drop = next((i for i in range(len(kept) - 1, -1, -1) if kept[i].poi.name_generated), None)
        if drop is None:
            return top
        kept.pop(drop)
        kept.append(add)
    order = {c.poi.id: i for i, c in enumerate(cands)}
    return sorted(kept, key=lambda c: order[c.poi.id])


def collapse_anonymous(ranked: list[Candidate]) -> list[Candidate]:
    """One card per category for the anonymous OSM records («Детская площадка», «Кафе»): the best-ranked one stays and
    records how many more of its kind are nearby (`nearby_anon`), the rest are dropped. Two cards that cannot be told
    apart are not two choices. `ranked` is in rank order; named places are never touched."""
    extra: Counter[str] = Counter()
    seen: set[str] = set()
    kept: list[Candidate] = []
    for c in ranked:
        if c.poi.name_generated:
            if c.poi.category in seen:
                extra[c.poi.category] += 1
                continue
            seen.add(c.poi.category)
        kept.append(c)
    return [
        c.model_copy(update={"nearby_anon": extra[c.poi.category]})
        if c.poi.name_generated and extra[c.poi.category]
        else c
        for c in kept
    ]


def unnamed_more(n: int, lang: str | None) -> str:
    """«И ещё 3 безымянных места этого типа рядом.»: the other anonymous OSM records one card stands for."""
    lang = norm(lang)
    if lang == "ru":
        what = plural_ru(n, "безымянное место", "безымянных места", "безымянных мест")
        return f"И ещё {n} {what} этого типа рядом."
    if lang == "kk":
        return f"Жақын жерде мұндай атаусыз орын тағы {n}."
    return f"And {n} more unnamed place{'s' if n != 1 else ''} of this kind nearby."
