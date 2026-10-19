"""Answers about a shown or named place that the plain `dialog_place.answer` does not give: what the place serves (the
cuisine tag and the place's own description, or honestly nothing), what the entry costs (the museum register's or the
site's wording with its source and the day it was read), the hours of another day («а в воскресенье?»), and the way
from the person to a named place (the street walk when a router has it). Every sentence is a field of the record or
«в данных этого нет»; nothing is searched, nothing is guessed."""

from __future__ import annotations

from datetime import datetime

from .attributes import has_socket, local_food_signal
from .bookmarks import named_bookmark
from .dialog_lead import honest_gaps
from .dialog_place import _by, card_walk_text, dist_text, price_source, today_intervals
from .dialog_place import answer as place_answer
from .dialog_questions import place_question
from .dialog_strings import s
from .dialog_text import first_sentence
from .dialog_types import Place, PlaceAnswer, Source
from .dialog_when import AskedTime
from .hours import is_24_7, poi_hours, to_local_naive
from .i18n_cuisine import cuisine_label
from .i18n_gov import weekday_on
from .intent import parse_rules
from .kids import is_kids_place
from .lexicon import match
from .models import POI, Bookmark, Recommendation, Result
from .radius import haversine_m, travel_minutes
from .status import hours_facts, next_change
from .walking import WalkingRouter
from .wishes import FAR_WALK_MIN, of_subkind, subkind_missing

FOOD_KINDS = frozenset({"restaurant", "cafe", "fast_food", "bar_nightlife"})
LOCAL_CUISINES = frozenset(
    {"regional", "local", "central_asian"}
)  # local, and not necessarily Kazakh
MAX_DESCRIPTION_CHARS = 180
STREET = "valhalla"


def _date(iso: str | None) -> str:
    """«17.10.2026» of a «2026-10-17»; '' without one."""
    if not iso or len(iso) < 10:
        return ""
    return f"{iso[8:10]}.{iso[5:7]}.{iso[:4]}"


def _fact(
    place: Place, topic: str, text: str, *, known: bool = True, source: Source | None = None
) -> PlaceAnswer:
    return PlaceAnswer(
        place_id=place.id, name=place.name, topic=topic, text=text, known=known, source=source
    )


# ------------------------------------------------------------------ the entry fee


def _entry(place: Place, poi: POI, lang: str) -> PlaceAnswer:
    """What the entry costs: the place's own price wording (the museum register's, the site's) with whose it is and the
    day it was read; never a number of ours."""
    if not poi.price_text:
        what = s("w_entry", lang)
        return _fact(place, "entry", s("a_unknown", lang, name=place.name, what=what), known=False)
    label, by, url, date = price_source(poi, lang)
    day = _date(date)
    if day:
        text = s("a_price_on", lang, name=place.name, price=poi.price_text, by=by, date=day)
    else:
        text = s("a_price", lang, name=place.name, price=poi.price_text, by=by)
    return _fact(place, "entry", text, source=Source(label=label, url=url))


# ------------------------------------------------------------------ what the place serves


def _own_description(poi: POI, lang: str) -> tuple[str, Source | None]:
    """The first sentence of the place's own words about itself (its site, else Wikipedia, else its OpenStreetMap
    description) and where it comes from."""
    if poi.description_official:
        credit = poi.official_description_credit(lang)
        source = Source(label=credit[0], url=credit[1]) if credit else None
        text = poi.description_official
    elif poi.description and poi.description_source in {"osm", "wikipedia"}:
        credit = poi.wikipedia_credit(lang)
        source = (
            Source(label=credit[0], url=credit[1]) if credit else Source(label=s("src_osm", lang))
        )
        text = poi.description
    else:
        return "", None
    sentence = first_sentence(" ".join(text.split()))
    if len(sentence) > MAX_DESCRIPTION_CHARS:
        sentence = sentence[:MAX_DESCRIPTION_CHARS].rsplit(" ", 1)[0].rstrip(" ,;:") + "…"
    return sentence, source


def _is_kazakh(poi: POI, values: set[str]) -> bool | None:
    """Does the record say the cuisine is Kazakh: True by the tag, the name or the description, False when the tag
    names another cuisine, None when the record says nothing (or only «local»)."""
    if local_food_signal(poi):
        return True
    return False if values - LOCAL_CUISINES else None


def _menu(topic: str, place: Place, poi: POI, lang: str, *, tail: bool = True) -> PlaceAnswer:
    """«what do they serve», «is that Kazakh food», «есть детское меню»: the cuisine tag and the place's own words; the
    menu itself, and a kids' menu, are in no record, and the answer says so (with `tail` only: one line under several
    cards, not the same sentence on each)."""
    raw = poi.tag_dict().get("cuisine", "")
    values = {v.strip() for v in raw.split(";") if v.strip()}
    cuisine = cuisine_label(raw, lang) or ", ".join(sorted(values))
    sentence, site = _own_description(poi, lang)
    name, by = place.name, s("by_osm", lang)
    if poi.category not in FOOD_KINDS and not cuisine:
        text = s("a_menu_not_food", lang, name=name, kind=place.kind)
        return _fact(place, "menu", text, known=False)
    parts: list[str] = []
    if topic == "menu_kids":
        parts.append(s("a_menu_kids_none", lang, name=name))
    if topic == "menu_kazakh":
        verdict = _is_kazakh(poi, values)
        if verdict is True:
            parts.append(s("a_menu_kazakh_yes", lang, name=name, by=by))
        elif verdict is False:
            parts.append(s("a_menu_kazakh_no", lang, name=name, cuisine=cuisine, by=by))
        else:
            parts.append(s("a_menu_kazakh_unknown", lang, name=name))
    if cuisine and (topic != "menu_kazakh" or _is_kazakh(poi, values) is None):
        parts.append(s("a_menu_cuisine", lang, name=name, cuisine=cuisine, by=by))
    if sentence:
        parts.append(s("a_menu_site", lang, text=sentence))
    if topic == "menu" and not parts:
        parts.append(s("a_menu_none", lang, name=name))
    elif not sentence and topic != "menu_kids" and tail:
        parts.append(s("a_menu_dishes_none", lang))
    source = site or (Source(label=s("src_osm", lang)) if cuisine else None)
    return _fact(
        place, topic, " ".join(parts), known=topic != "menu_kids" and bool(parts), source=source
    )


# ------------------------------------------------------------------ the hours of another day


def _hours_on(place: Place, poi: POI, lang: str, at: datetime, asked: AskedTime) -> PlaceAnswer:
    """«а в воскресенье?», «завтра работает?»: the hours the record gives for THAT day (and moment, when a part of the
    day was said), with the source; honestly «часов нет» when the record has none."""
    h = place.hours
    if h.state == "unknown":
        return place_answer("hours", place, poi, lang, at)
    when = asked.label(lang) if asked.exact else asked.day_label(lang)
    kind, _ = hours_facts(poi, h.state, at, lang)
    src = _by(poi, lang)
    iv = today_intervals(poi, to_local_naive(at))
    fields = {"name": place.name, "when": when, "src": src, "iv": iv}
    if kind == "247":
        text = s("a_on_247", lang, **fields)
    elif h.state == "open":
        text = s("a_on_open_iv" if iv else "a_on_open", lang, **fields)
    else:
        text = s("a_on_closed_iv" if iv else "a_on_closed", lang, **fields)
    if h.note:
        text = f"{text} {h.note}"
    return _fact(place, "hours", text, source=h.source)


# ------------------------------------------------------------------ sockets, a kids' room, «is it worth it»

KIDS_WORDS = ("детск", "дети", "детей", "kids", "children", "балал", "ойын")


def _socket(place: Place, poi: POI, lang: str) -> PlaceAnswer:
    """Sockets as the record has them (the OpenStreetMap `socket:*` tags); Wi-Fi is its own question and its own answer."""
    name = place.name
    if has_socket(poi):
        src = Source(label=s("src_osm", lang))
        return _fact(
            place, "socket", s("a_socket_yes", lang, name=name, by=s("by_osm", lang)), source=src
        )
    text = s("a_unknown", lang, name=name, what=s("w_socket", lang))
    return _fact(place, "socket", text, known=False)


def _kids_room(place: Place, poi: POI, lang: str) -> PlaceAnswer:
    """A play room or a children's zone: the `for_kids` tag or the place's own words about it; else «в данных нет»."""
    name = place.name
    if poi.tag_dict().get("for_kids") == "yes":
        return _fact(
            place,
            "kids_room",
            s("a_kids_yes", lang, name=name, by=s("by_osm", lang)),
            source=Source(label=s("src_osm", lang)),
        )
    sentence, source = _own_description(poi, lang)
    if sentence and any(w in sentence.lower() for w in KIDS_WORDS):
        return _fact(place, "kids_room", s("a_menu_site", lang, text=sentence), source=source)
    return _fact(
        place,
        "kids_room",
        s("a_unknown", lang, name=name, what=s("w_kids_room", lang)),
        known=False,
    )


def _visit(place: Place, poi: POI, lang: str, at: datetime) -> PlaceAnswer:
    """«Is it worth going up, at night or in the morning»: what the data holds for the decision, its hours (with
    today's interval) and the entry price, each with its source; nothing about whether it is «worth it»."""
    hours = place_answer("hours", place, poi, lang, at)
    parts = [hours.text]
    source = hours.source
    if poi.price_text:
        entry = _entry(place, poi, lang)
        parts.append(entry.text)
        source = source or entry.source
    return _fact(
        place, "visit", " ".join(parts), known=hours.known or bool(poi.price_text), source=source
    )


# ------------------------------------------------------------------ a saved place


def _bookmark_route(
    bookmark: Bookmark,
    origin: tuple[float, float],
    router: WalkingRouter | None,
    mode: str,
    lang: str,
) -> PlaceAnswer:
    """«How long to walk back to my hotel»: minutes from the person to the bookmark the message names (any name, the
    street leg when the router has it); the bookmark lives in this request only and is never stored."""
    d = haversine_m(*origin, bookmark.lat, bookmark.lon)
    minutes, method = travel_minutes(d, mode), "straight"
    if router is not None and mode == "walk":
        leg = router.leg(origin, (bookmark.lat, bookmark.lon))
        d, minutes, method = leg.distance_m, leg.minutes, leg.method
    far = minutes >= FAR_WALK_MIN
    key = ("a_route_street" if method == "valhalla" else "a_route") + ("_far" if far else "")
    text = s(
        key,
        lang,
        name=bookmark.name,
        d=dist_text(round(d), lang),
        walk=s(f"walk_{mode}", lang, n=minutes),
    )
    return PlaceAnswer(
        place_id=f"bookmark:{bookmark.kind}",
        name=bookmark.name,
        topic="route",
        text=text,
        known=True,
    )


def bookmark_answer(
    text: str,
    bookmarks: list[Bookmark],
    origin: tuple[float, float],
    router: WalkingRouter | None,
    mode: str,
    lang: str,
) -> PlaceAnswer | None:
    """The way to the saved place the message names, when the message asks about a way; None otherwise."""
    pq = place_question(text, allow_kind=True) if bookmarks else None
    saved = named_bookmark(text, bookmarks) if pq is not None and pq.topic == "route" else None
    return _bookmark_route(saved, origin, router, mode, lang) if saved is not None else None


# ------------------------------------------------------------------ the way


def _route(place: Place, lang: str) -> PlaceAnswer:
    """Minutes and distance from the person to the place by the streets (the walking router had the leg)."""
    key = "a_route_street_far" if place.walk.minutes >= FAR_WALK_MIN else "a_route_street"
    text = s(
        key, lang, name=place.name, d=dist_text(place.walk.distance_m, lang), walk=place.walk.text
    )
    return _fact(place, "route", text)


def _closing(place: Place, poi: POI, lang: str, at: datetime) -> PlaceAnswer:
    """«до какого часа он работает»: open now - when it closes; closed now - the next opening and the closing after it
    (today or the day it opens), from the record's schedule and with the source the card names. Never «unknown» when
    the schedule is known."""
    h = place.hours
    local = to_local_naive(at)
    if h.state == "unknown" or poi_hours(poi, local).state == "unknown":
        return place_answer("hours", place, poi, lang, at)
    src, name = _by(poi, lang), place.name
    if is_24_7(poi.opening_hours):
        return _fact(place, "hours", s("a_close_247", lang, name=name, src=src), source=h.source)
    is_open = poi_hours(poi, local).state == "open"
    opens = local if is_open else next_change(poi, local)
    closes = next_change(poi, opens) if opens is not None else None
    if opens is None or closes is None:
        return place_answer("hours", place, poi, lang, at)
    if (
        is_open
    ):  # the plain hours answer already says «до 20:00» with today's interval and the source
        return place_answer("hours", place, poi, lang, at)
    days = (opens.date() - local.date()).days
    day = (
        s("w_today", lang)
        if days == 0
        else s("w_tomorrow", lang)
        if days == 1
        else weekday_on(opens.weekday(), lang)
    )
    text = s(
        "a_close_later",
        lang,
        name=name,
        day=day,
        a=f"{opens:%H:%M}",
        b=f"{closes:%H:%M}",
        src=src,
    )
    if h.note:
        text = f"{text} {h.note}"
    return _fact(place, "hours", text, source=h.source)


def _toilet(place: Place, poi: POI, lang: str) -> PlaceAnswer:
    """A toilet as the record's `toilets` tag has it (OpenStreetMap), else «в данных этого нет»."""
    value = poi.tag_dict().get("toilets", "")
    src = Source(label=s("src_osm", lang))
    if value in ("yes", "no"):
        key = "a_toilet_yes" if value == "yes" else "a_toilet_no"
        return _fact(
            place, "toilet", s(key, lang, name=place.name, by=s("by_osm", lang)), source=src
        )
    what = s("w_toilet", lang)
    return _fact(place, "toilet", s("a_unknown", lang, name=place.name, what=what), known=False)


_CURRENCIES = ("USD", "EUR", "RUB", "CNY", "KZT", "GBP")


def _atm(place: Place, poi: POI, lang: str) -> PlaceAnswer:
    """A cash machine: the record IS one (`amenity=atm`) or says it has one (`atm=yes`, OpenStreetMap), else «в данных
    этого нет»; never a guess from «bank»."""
    tags = poi.tag_dict()
    src = Source(label=s("src_osm", lang))
    if tags.get("amenity") == "atm" or tags.get("atm") == "yes":
        text = s("a_atm_yes", lang, name=place.name, by=s("by_osm", lang))
        return _fact(place, "atm", text, source=src)
    return _fact(place, "atm", s("a_atm_unknown", lang, name=place.name), known=False)


def _exchange(place: Place, poi: POI, lang: str) -> PlaceAnswer:
    """Changing currency: a `bureau_de_change`, a `currency:USD=yes` tag, an `exchange` tag; else the honest «в данных
    этого нет — уточните в отделении»."""
    tags = poi.tag_dict()
    src, by, name = Source(label=s("src_osm", lang)), s("by_osm", lang), place.name
    cur = [c for c in _CURRENCIES if tags.get(f"currency:{c}") == "yes"]
    if cur:
        text = s("a_exchange_currency", lang, name=name, cur=", ".join(cur), by=by)
        return _fact(place, "exchange", text, source=src)
    if tags.get("amenity") == "bureau_de_change" or tags.get("exchange") == "yes":
        return _fact(place, "exchange", s("a_exchange_yes", lang, name=name, by=by), source=src)
    return _fact(place, "exchange", s("a_exchange_unknown", lang, name=name), known=False)


def _round_clock(place: Place, poi: POI, lang: str, at: datetime) -> PlaceAnswer:
    """«Круглосуточно?»: yes when the record's schedule is 24/7, no with the day's interval when it is another
    schedule, else the plain hours answer (unknown stays unknown)."""
    h = place.hours
    if h.state == "unknown":
        return place_answer("hours", place, poi, lang, at)
    src, name = _by(poi, lang), place.name
    if is_24_7(poi.opening_hours):
        return _fact(place, "hours", s("a_round_yes", lang, name=name, src=src), source=h.source)
    iv = today_intervals(poi, to_local_naive(at))
    if not iv:
        return place_answer("hours", place, poi, lang, at)
    return _fact(place, "hours", s("a_round_no", lang, name=name, iv=iv, src=src), source=h.source)


def answer(
    topic: str,
    place: Place,
    poi: POI,
    lang: str,
    at: datetime,
    *,
    asked: AskedTime | None = None,
    last: bool = True,
) -> PlaceAnswer:
    """The answer to a question about one place, from its record only (`asked`: the day or time the person named;
    `last`: the last of several cards, where a line true of them all is said once)."""
    if topic == "entry":
        return _entry(place, poi, lang)
    if topic in ("menu", "menu_kids", "menu_kazakh"):
        return _menu(topic, place, poi, lang, tail=last)
    if topic == "atm":
        return _atm(place, poi, lang)
    if topic == "exchange":
        return _exchange(place, poi, lang)
    if topic == "round_clock":
        return _round_clock(place, poi, lang, at)
    if topic == "closing":
        return _closing(place, poi, lang, at)
    if topic == "toilet":
        return _toilet(place, poi, lang)
    if topic == "socket":
        return _socket(place, poi, lang)
    if topic == "kids_room":
        return _kids_room(place, poi, lang)
    if topic == "visit":
        return _visit(place, poi, lang, at)
    if topic == "hours" and asked is not None and asked.shifted:
        return _hours_on(place, poi, lang, at, asked)
    if topic == "route" and place.walk.method == STREET:
        return _route(place, lang)
    return place_answer(topic, place, poi, lang, at)  # type: ignore[arg-type]


# ------------------------------------------------------------------ what a request lacks


def subkind_gap(res: Result, recs: list[Recommendation], pois: list[POI], lang: str) -> str:
    """«Стоматологий рядом в данных нет — ближайшая: «EliteStom», пешком далеко: 1,6 км — лучше на транспорте.»: the
    kind inside a category the person asked for (a dentist among the clinics, a children's clinic, a cash machine
    among the banks) that the first card is not. The nearest one is a card of its own (walks.chains.far_subkind) and
    is said by the walk its card says: from FAR_WALK_MIN on foot a distance and the transport, never the minutes. One
    sentence: the first card has its own (walks.dialog_lead.errand_pick). '' when the first card is one."""
    if not recs or not (sub := subkind_missing(res.intent.intent, recs[0].poi)):
        return ""
    if card := next((r for r in recs if of_subkind(r.poi, sub)), None):
        walk = card_walk_text(card, res.intent.intent.mode, lang)
        return s(f"sub_far_{sub}", lang, name=card.poi.name_for(lang), walk=walk)
    far = [(haversine_m(res.lat, res.lon, p.lat, p.lon), p) for p in pois if of_subkind(p, sub)]
    if not far:
        return s(f"sub_none_{sub}", lang)
    meters, near = min(
        far, key=lambda x: x[0]
    )  # not a card (a follow-up's cards): said by its distance
    walk = s("walk_far", lang, d=dist_text(round(meters), lang))
    return s(f"sub_far_{sub}", lang, name=near.name_for(lang), walk=walk)


def all_gaps(
    res: Result, recs: list[Recommendation], pois: list[POI], lang: str, *, now: bool
) -> tuple[str, str]:
    """What the answer lacks, (said before it, said after it) as `dialog_lead.honest_gaps` gives them, plus a sub-kind
    no card is (`subkind_gap`), and, when the person's own words asked for a place for a child to play (not a child
    from the memory or the model, not «балалармен» next to a coffee), that the data holds no play place near when none
    of the places shown is one, said before: a café or a gallery is never passed off as «где поиграть». Asked indoors
    («в помещении»), the line is about indoor play places: an outdoor playground nearby is no «нет площадок»."""
    before, after = honest_gaps(res, recs, lang, now=now)
    before = " ".join(x for x in (before, subkind_gap(res, recs, pois, lang)) if x)
    asked = parse_rules(res.query).intent  # the words' own reading
    indoor = match(res.query).has("shelter_from_weather")  # «где поиграть детям в помещении»
    play = [
        r
        for r in recs
        if is_kids_place(r.poi) and not (indoor and r.poi.category == "kids_playground")
    ]
    if (
        asked.with_kids
        and "kids_playground" in asked.categories
        and (not asked.wished or "kids_playground" in asked.wished)
        and not play  # indoors: an outdoor playground shown is the alternative, not the indoor place asked
        and recs
        and not any(
            s(k, lang) in before for k in ("kids_none_entertainment", "kids_none_museum_gallery")
        )
    ):
        before = f"{before} {s('kids_none_indoor' if indoor else 'kids_none_place', lang)}".strip()
    return before, after
