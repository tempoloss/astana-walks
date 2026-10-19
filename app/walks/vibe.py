"""«Поиск по вайбу»: how much a place answers a person's vibe, and the data that say so.

The facets of a place (walks.vibe_data) come from its record alone - kind and tags, the late hours of a bar or a
cinema, words of its human-written texts, an encyclopedia or travel-guide entry of a sight - computed once per record
object, never by a model, never per request; the marks of people («тихо» / «шумно», walks.feedback) are added at the
moment of the request. Every facet keeps the evidence that said it, so a card can say «Под ваш вайб: тихо (по отметкам
людей), природа (парк)» and never claims a facet the data do not hold.

A person's vibe is a weight 0..1 per facet (walks.profile). It re-ranks and never filters: `vibe_bonus` is the hook of
the ranking (walks.retrieve) and walks.vibe_order the one of the cards, both doing nothing with no vibe set, so an
answer without a vibe is exactly the answer it always was."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from .i18n import pick
from .models import POI, WIKIVOYAGE, Intent, PeopleEvidence
from .vibe_data import (
    ADULT_LIVELY_KINDS,
    ASKS_VIBE,
    BETTING_TAGS,
    BETTING_WORDS,
    CATEGORY_RULES,
    EXTROVERT,
    FACET_NAME,
    FACETS,
    INTROVERT,
    KIND_NAME,
    LATE_CATEGORIES,
    LATE_CLOSE_H,
    LATE_KINDS,
    LEAD,
    LEAD_NONE,
    LINE_HEAD,
    NIGHT_KINDS,
    NO_VIBE_TAGS,
    OPPOSITE,
    RESTAURANT_SUFFIX,
    SIGHT_CATEGORIES,
    SIGHT_KINDS,
    SIGHT_TAGS,
    SOURCE_NAME,
    TAG_RULES,
    TEXT_WORDS,
    UNSET,
    Rule,
)

VIBE_WEIGHT = 3.0  # score points of a perfect match at weight 1: as much as a kind the request names (walks.retrieve)
FOCUS = 3.0  # «под мой вайб»: the vibe IS the request, its match outweighs the hour's bonuses (a bar at night)
MAX_LINE_FACETS = 3  # a card names at most this many facets
TOP_WEIGHT = (
    0.5  # a facet weighs this much at least to be one the person «asks for» (the model's payload)
)
_SPAN = re.compile(r"(\d{1,2}):\d{2}\s*-\s*(\d{1,2}):\d{2}")
_MORNING_H = 6  # a span that ends before this hour, earlier than it starts, ends past midnight


@dataclass(frozen=True)
class Evidence:
    """One facet of a place and what said it: `kind:<kind>` (its tags or category), `late` / `allday` (its hours),
    `text` (a human-written description), `wiki` / `voyage` (an encyclopedia / travel-guide entry), `people` /
    `people_demo` (the marks of people; seeded sample marks)."""

    facet: str
    strength: float  # 1.0: the evidence says it plainly; 0.5: it leans that way
    source: str


# ---------------------------------------------------------------- the record


def _rules(poi: POI) -> list[Rule]:
    """The kinds the tags name (the telling one first), else the category's own; none for a kind that is nobody's
    vibe (a place of worship, a children's room)."""
    tags = set(poi.tags)
    found = [rule for tag, rule in TAG_RULES.items() if tag in tags]
    found += [
        CATEGORY_RULES["restaurant"]
        for tag in poi.tags
        if tag.startswith("overture_category=") and tag.endswith(RESTAURANT_SUFFIX)
    ]
    if not found and not tags & NO_VIBE_TAGS and poi.category in CATEGORY_RULES:
        found = [CATEGORY_RULES[poi.category]]
    first: dict[
        str, Rule
    ] = {}  # a kind named by two tags (amenity=bar, overture_category=bar) is one kind
    for kind, facets in found:
        first.setdefault(kind, (kind, facets))
    return list(first.values())


def _late(poi: POI, kinds: set[str]) -> Evidence | None:
    """Nightlife by the hours of a bar, a club, a place of entertainment or a cinema: open round the clock or past
    midnight (plainly), until 23:xx or midnight (leaning). A café or a restaurant open late is still a meal, a shop or a
    pharmacy open all night an errand."""
    hours = poi.opening_hours or ""
    if not hours or not (poi.category in LATE_CATEGORIES or kinds & LATE_KINDS):
        return None
    if "24/7" in hours:
        return Evidence("night", 1.0, "allday")
    best = 0.0
    for m in _SPAN.finditer(hours):
        start, end = int(m.group(1)), int(m.group(2))
        if 0 < end < min(start, _MORNING_H):
            best = 1.0
        elif end >= LATE_CLOSE_H or end == 0:
            best = max(best, 0.5)
    return Evidence("night", best, "late") if best else None


def _sight(poi: POI, kinds: set[str]) -> bool:
    """A museum, a gallery, a landmark, a theatre, a monument, a place of worship: a place an encyclopedia or a guide
    entry says something of (a mall, a shop, a café or a station with an article is none)."""
    return (
        poi.category in SIGHT_CATEGORIES
        or bool(kinds & SIGHT_KINDS)
        or not SIGHT_TAGS.isdisjoint(poi.tags)
    )


def _human_text(poi: POI) -> str:
    """The texts people wrote about the place (OSM, Wikipedia, its own site, Wikivoyage); never a description the app
    derived from the record's own fields."""
    extracts = [(article or {}).get("extract", "") for article in poi.wikipedia.values()]
    return " ".join(p for p in (poi.real_text(), poi.description_voyage or "", *extracts) if p)


def _from_record(poi: POI) -> tuple[Evidence, ...]:
    if _betting(poi):
        return ()
    rules = _rules(poi)
    kinds = {kind for kind, _ in rules}
    out = [
        Evidence(facet, strength, f"kind:{kind}")
        for kind, facets in rules
        for facet, strength in facets.items()
    ]
    if (late := _late(poi, kinds)) is not None:
        out.append(late)
    text = _human_text(poi)
    out += [
        Evidence(facet, 0.5, "text") for facet, rx in TEXT_WORDS.items() if text and rx.search(text)
    ]
    if _sight(poi, kinds):
        if poi.wikipedia:
            out.append(Evidence("culture", 0.5, "wiki"))
        if WIKIVOYAGE in poi.sources:
            out.append(Evidence("unusual", 0.5, "voyage"))
    return tuple(out)


_KNOWN: dict[int, tuple[POI, tuple[Evidence, ...]]] = {}


def place_evidence(poi: POI) -> tuple[Evidence, ...]:
    """What the record says, computed once per record object: the records are loaded once per process (walks.pipeline)
    and the entry holds its record, so an id is never reused for another one."""
    known = _KNOWN.get(id(poi))
    if known is not None and known[0] is poi:
        return known[1]
    found = _from_record(poi)
    _KNOWN[id(poi)] = (poi, found)
    return found


def _betting(poi: POI) -> bool:
    """A bookmaker, a lottery, a casino: by its tags, or by a name like «Спорт-бар "Финал", БК FairPlay» (a bar in the
    tags)."""
    names = [poi.name, *poi.names.values(), *(t for t in poi.tags if t.startswith("brand="))]
    return not BETTING_TAGS.isdisjoint(poi.tags) or bool(BETTING_WORDS.search(" ".join(names)))


def evidence_of(
    poi: POI, people: PeopleEvidence | None, *, day: bool = False, kids: bool = False
) -> list[Evidence]:
    """The record's evidence and, first, what the marks of people say now: a quiet or a noisy verdict (a mixed one
    says neither). A betting place has none. In the daytime (`day`) and with children the evening's evidence says
    nothing (a bar, a club, the night facet), and with children a mall is no lively place either."""
    if _betting(poi):
        return []
    marks = []
    if people is not None and people.noise in ("quiet", "noisy"):
        facet = "calm" if people.noise == "quiet" else "lively"
        marks.append(Evidence(facet, 1.0, "people_demo" if people.demo else "people"))
    found = [*marks, *place_evidence(poi)]
    if not (day or kids):
        return found
    off = ADULT_LIVELY_KINDS if kids else NIGHT_KINDS
    return [e for e in found if e.facet != "night" and e.source.removeprefix("kind:") not in off]


def strengths(evidence: list[Evidence] | tuple[Evidence, ...]) -> dict[str, float]:
    """facet -> the clearest evidence of it."""
    out: dict[str, float] = {}
    for e in evidence:
        out[e.facet] = max(out.get(e.facet, 0.0), e.strength)
    return out


# ---------------------------------------------------------------- the person


def ranked_facets(weights: Mapping[str, float]) -> list[str]:
    """The facets the person wants, the weightiest first (then in the order of FACETS)."""
    return sorted(
        (f for f, w in weights.items() if w > 0), key=lambda f: (-weights[f], FACETS.index(f))
    )


def top_facets(weights: Mapping[str, float]) -> list[str]:
    """The facets the person plainly asks for (the model is told these)."""
    return [f for f in ranked_facets(weights) if weights[f] >= TOP_WEIGHT]


def vibe_match(
    poi: POI,
    people: PeopleEvidence | None,
    weights: Mapping[str, float],
    *,
    day: bool = False,
    kids: bool = False,
) -> tuple[float, list[str]]:
    """(-1..1, the wanted facets the place has evidence for, the best match first). One wanted facet the data say
    plainly already matches well (a library for «тихо, книги, парки»), each further one adds half as much; the opposite
    pole counts against (a bar is a worse answer to «тихо» than a plain café is). `day`, `kids`: see `evidence_of`."""
    strongest = max(weights.values(), default=0.0)
    if strongest <= 0:
        return 0.0, []
    have = strengths(evidence_of(poi, people, day=day, kids=kids))
    gain = sum(w * have.get(f, 0.0) for f, w in weights.items())
    loss = sum(w * have.get(OPPOSITE[f], 0.0) for f, w in weights.items() if f in OPPOSITE)
    matched = sorted(
        (f for f in ranked_facets(weights) if have.get(f)),
        key=lambda f: (-weights[f] * have[f], FACETS.index(f)),
    )
    scale = strongest + (sum(weights.values()) - strongest) / 2
    return max(-1.0, min(1.0, (gain - loss) / scale)), matched


def vibe_bonus(
    poi: POI,
    people: PeopleEvidence | None,
    weights: Mapping[str, float],
    reasons: list[str],
    intent: Intent,
    night: bool,
) -> float:
    """The ranking's hook: score points for the person's vibe (±VIBE_WEIGHT × the strongest weight) and the reason
    `vibe:<facets>` the model sees, for a place of the kind the request names (a vibe re-ranks inside a wish, it never
    brings bars to «ПС клуб»); before the night (`night`: walks.retrieve.is_night) and with children the evening's
    evidence says nothing. An ordinary answer only lifts the places the data back, so a place without evidence is never
    moved over another one (walks.vibe_order); a «под мой вайб» search (`is_focused`) also ranks the opposite pole
    down (a mall for «не люблю толпы»). 0.0 and nothing added with no vibe set."""
    if not weights or (intent.wished and poi.category not in intent.wished):
        return 0.0
    match, matched = vibe_match(poi, people, weights, day=not night, kids=intent.with_kids)
    if matched:
        reasons.append("vibe:" + ",".join(matched))
    if not is_focused(weights):
        match = max(match, 0.0)
    return round(VIBE_WEIGHT * max(weights.values()) * match, 3)


def focused(weights: Mapping[str, float]) -> dict[str, float]:
    """The weights of one «под мой вайб» search: the stored ones (0..1) times FOCUS. Only the request's own copy of the
    profile carries them; the stored file never does."""
    return {f: w * FOCUS for f, w in weights.items()}


def is_focused(weights: Mapping[str, float]) -> bool:
    """The weights of a «под мой вайб» search (`focused`): a stored weight is at most 1 (walks.vibe_data.clean_weights)
    and one the person asks for at least TOP_WEIGHT, so FOCUS × TOP_WEIGHT > 1 marks the search's own copy."""
    return max(weights.values(), default=0.0) > 1.0


# ---------------------------------------------------------------- the words


def facet_name(facet: str, lang: str | None) -> str:
    return pick(FACET_NAME[facet], lang)


def facets_text(facets: list[str], lang: str | None) -> str:
    return ", ".join(facet_name(f, lang) for f in facets)


def _source_text(source: str, lang: str | None) -> str:
    kind = source.removeprefix("kind:")
    return pick(KIND_NAME[kind] if kind != source else SOURCE_NAME[source], lang)


def vibe_line(
    poi: POI,
    people: PeopleEvidence | None,
    weights: Mapping[str, float],
    lang: str | None,
    *,
    day: bool = False,
    kids: bool = False,
) -> str:
    """«Под ваш вайб: тихо (по отметкам людей), природа (парк)»: each wanted facet the place has evidence for, with the
    clearest evidence of it; '' when the data say none of them. `day`, `kids`: see `evidence_of`."""
    if not weights:
        return ""
    evidence = evidence_of(poi, people, day=day, kids=kids)
    items = []
    for facet in vibe_match(poi, people, weights, day=day, kids=kids)[1][:MAX_LINE_FACETS]:
        mine = [e for e in evidence if e.facet == facet]
        best = next(e for e in mine if e.strength == max(x.strength for x in mine))
        items.append(f"{facet_name(facet, lang)} ({_source_text(best.source, lang)})")
    return pick(LINE_HEAD, lang) + ", ".join(items) if items else ""


def lead_sentence(facets: list[str], lang: str | None) -> str:
    """«Под ваш вайб — тихо, природа.»: the facets the places shown have evidence for; or that the data near hold none."""
    return (
        pick(LEAD, lang).format(facets=facets_text(facets, lang))
        if facets
        else pick(LEAD_NONE, lang)
    )


def unset_sentence(lang: str | None) -> str:
    return pick(UNSET, lang)


def asks_vibe(text: str) -> bool:
    """«под мой вайб», «под моё настроение», «менің вайбыма», «my vibe»: the message asks for the stored vibe."""
    return bool(ASKS_VIBE.search(text))


def stated_vibe(text: str) -> dict[str, float]:
    """The vibe the words themselves state: an introvert asks for quiet, an extrovert for a lively place."""
    intro, extro = bool(INTROVERT.search(text)), bool(EXTROVERT.search(text))
    if intro == extro:
        return {}
    return {"calm": 1.0} if intro else {"lively": 1.0}


def with_stated(weights: Mapping[str, float], stated: Mapping[str, float]) -> dict[str, float]:
    """The stored vibe with the axis the message states put over its own (the other facets stay)."""
    if not stated:
        return dict(weights)
    return {**{f: w for f, w in weights.items() if f not in OPPOSITE}, **stated}
