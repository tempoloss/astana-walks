"""A place as the dialogue shows it (`Place`, from a recommendation or straight from the dataset) and the answers to
questions about places already shown or named: hours with their source, address, minutes on foot, phone, website,
or honestly «в данных этого нет». Nothing here searches; every fact is a field of the record."""

from __future__ import annotations

from datetime import datetime, timedelta
from urllib.parse import urlsplit

from opening_hours import OpeningHours

from .dialog_strings import s
from .dialog_text import display_name, first_sentence, plain, sentences, short_what, short_why
from .dialog_types import (
    Hours,
    PeopleMarks,
    Place,
    PlaceAnswer,
    Price,
    ShownPlace,
    Source,
    Topic,
    Walk,
)
from .facts import clean_address
from .feedback import hours_label
from .hours import poi_hours, to_local_naive
from .i18n import category_name, source_label, t, tip
from .i18n_gov import gt
from .models import (
    MUSEUM_REGISTER,
    OFFICIAL_SITE,
    POI,
    STATE_REGISTRY,
    WIKIVOYAGE,
    PeopleEvidence,
    Recommendation,
)
from .radius import haversine_m, travel_minutes
from .status import TEXT_KEY, hours_facts, next_change
from .visit_hours import visit_note
from .walking import WalkingRouter

FAR_WALK_MIN = 25  # from here «как дойти» suggests a vehicle
_HOURS_WORDS = (
    "час", "hour", "сағат", "праздник", "holiday", "мереке", "osm", "сайт", "website",
    "откро", "закро", "ашыл", "жабыл", "opens", "closes",
    "безымян", "unnamed", "атауы жоқ",  # «и ещё 27 безымянных мест» is noise, not a caveat
)  # fmt: skip
_OSM = "osm"
_ATTR_TOPICS = {  # topic -> (what, POI field read as yes/no/limited, a sentence key of the question)
    "wifi": "w_wifi",
    "wheelchair": "w_wheelchair",
    "terrace": "w_terrace",
    "takeaway": "w_takeaway",
}
_NO_DATA = {
    "toilet": "w_toilet",
    "price": "w_price",
    "parking": "w_parking",
    "reserve": "w_reserve",
}


def lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text[1:2].islower() else text


def walk_text(minutes: int, mode: str, lang: str) -> str:
    return s(f"walk_{mode}", lang, n=minutes)


# ------------------------------------------------------------------ sources and hours


def source_of_hours(poi: POI, lang: str) -> Source | None:
    which = poi.hours_source()
    if which is None:
        return None
    if which == OFFICIAL_SITE:
        return Source(label=s("src_site", lang), url=poi.hours_source_url())
    if which == STATE_REGISTRY:
        return Source(label=gt("src_gov", lang), url=poi.hours_source_url())
    if which == MUSEUM_REGISTER:
        return Source(label=s("src_museum_register", lang), url=poi.hours_source_url())
    if which == WIKIVOYAGE:
        return Source(label=s("src_wikivoyage", lang), url=poi.hours_source_url())
    return Source(label=s("src_osm", lang), url=None)


def sources_of(poi: POI, lang: str) -> list[Source]:
    out: list[Source] = []
    for name in poi.sources or [poi.source]:
        if name == OFFICIAL_SITE:
            site = poi.official_description_credit(lang)
            out.append(
                Source(label=s("src_site", lang), url=(site[1] if site else None) or poi.website)
            )
        elif name == STATE_REGISTRY:
            out.append(registry_source(poi, lang))
        elif name == MUSEUM_REGISTER:
            out.append(Source(label=s("src_museum_register", lang), url=poi.hours_source_url()))
        elif name == WIKIVOYAGE:
            out.append(Source(label=s("src_wikivoyage", lang), url=poi.wikivoyage_url()))
        elif name == "overture":
            out.append(Source(label=s("src_overture", lang)))
        elif name == _OSM:
            out.append(Source(label=s("src_osm", lang)))
    wiki = poi.wikipedia_credit(lang)
    if wiki:
        out.append(Source(label=s("src_wikipedia", lang), url=wiki[1]))
    return out or [Source(label=s("src_osm", lang))]


def registry_source(poi: POI, lang: str) -> Source:
    """The state register a record's facts come from: the ЦОН page, or the sport register of data.egov.kz."""
    match = poi.state_registry_match or {}
    key = "src_gov" if match.get("kind") == "cson" else "src_gov_sport"
    return Source(label=gt(key, lang), url=match.get("url"))


def poi_kind(poi: POI, lang: str) -> str:
    """The kind of place in the user's words: a ЦОН is «ЦОН», not the dataset's catch-all category."""
    return (
        gt("gov_kind_cson", lang) if poi.is_state_service() else category_name(poi.category, lang)
    )


def _by(poi: POI, lang: str) -> str:
    which = poi.hours_source()
    if which == STATE_REGISTRY:
        return gt("by_gov", lang)
    if which == MUSEUM_REGISTER:
        return s("by_register", lang)
    return s("by_site" if which == OFFICIAL_SITE else "by_osm", lang)


def dist_text(meters: int, lang: str) -> str:
    """«340 м», «8,6 км» (the english «8.6 km»)."""
    unit_m, unit_km = ("m", "km") if lang == "en" else ("м", "км")
    if meters < 1000:
        return f"{meters} {unit_m}"
    km = f"{round(meters / 1000, 1):g}"
    return f"{km if lang == 'en' else km.replace('.', ',')} {unit_km}"


def _open_spans(raw: str | None, local: datetime) -> list[list[datetime]] | None:
    """The open spans of the day of `local`, touching ones merged; None without a (readable) schedule."""
    if not raw or not raw.strip():
        return None
    day = datetime.combine(local.date(), datetime.min.time())
    try:
        spans = [
            (a, b)
            for a, b, state, _ in OpeningHours(raw).intervals(day, day + timedelta(days=1))
            if str(state) == "open"
        ]
    except (ValueError, OverflowError, TypeError):
        return None
    merged: list[list[datetime]] = []
    for a, b in spans:
        if merged and merged[-1][1] == a:
            merged[-1][1] = b
        else:
            merged.append([a, b])
    return merged


def today_intervals(poi: POI, local: datetime) -> str:
    """The open hours of the day of `local` as «11:00–24:00» (several: «08:00–13:00, 14:00–22:00»); '' when the
    record has none, or the place is open the whole day."""
    merged = _open_spans(poi.opening_hours, local)
    if not merged or (len(merged) == 1 and merged[0][1] - merged[0][0] >= timedelta(days=1)):
        return ""
    end = datetime.combine(local.date(), datetime.min.time()) + timedelta(days=1)
    return ", ".join(f"{a:%H:%M}–{'24:00' if b >= end else f'{b:%H:%M}'}" for a, b in merged)


def today_spans(poi: POI, at: datetime) -> list[tuple[float, float]] | None:
    """The open spans of the arrival day in hours (what the card's day strip draws); None without a schedule."""
    local = to_local_naive(at)
    merged = _open_spans(poi.opening_hours, local)
    if merged is None:
        return None
    day = datetime.combine(local.date(), datetime.min.time())
    return [
        (round((a - day).total_seconds() / 3600, 2), round((b - day).total_seconds() / 3600, 2))
        for a, b in merged
    ]


def closes_soon(poi: POI, state: str, at: datetime) -> bool:
    """Open at `at` and the schedule's next change, a closing, is less than an hour away."""
    if state != "open":
        return False
    local = to_local_naive(at)
    nxt = next_change(poi, local)
    return nxt is not None and nxt - local <= timedelta(hours=1)


_ANSWER_KEY = {
    "247": "open_247",
    "until": "open_until",
    "open": "open",
    "opens": "closed_opens",
    "closed": "closed",
}


def hours_block(poi: POI, state: str, issue: str, holiday: str, at: datetime, lang: str) -> Hours:
    """The hours of a place in plain words, its source and the honest caveat (sources disagree, holiday, unknown)."""
    kind, when = hours_facts(poi, state, at, lang)
    text = s(TEXT_KEY[kind], lang, t=when)
    note = ""
    if issue == "conflict":
        note = s("h_note_conflict", lang)
    elif issue == "split":
        note = s("h_note_split", lang)
    elif issue == "unqualified":
        note = s("h_note_unqualified", lang)
    elif holiday.startswith("праздник"):
        note = s("h_note_holiday", lang)
    elif state == "unknown":
        note = s("h_note_unknown", lang)
    return Hours(
        state=state,  # type: ignore[arg-type]
        text=text,
        raw=poi.opening_hours or None,
        source=source_of_hours(poi, lang),
        issue=issue,  # type: ignore[arg-type]
        note=note,
        data_date=(poi.collected_at or "")[:10] or None,
        today=today_spans(poi, at) if state != "unknown" else None,
        soon=closes_soon(poi, state, at),
    )


# ------------------------------------------------------------------ the card


def _people(ev: PeopleEvidence | None, lang: str) -> PeopleMarks | None:
    if ev is None:
        return None
    label = hours_label(ev, lang)
    text = f"{label} ({source_label(ev.demo, lang)})" if label else ""
    return PeopleMarks(
        hours=ev.hours,
        n_open=ev.n_open,
        n_closed=ev.n_closed,
        last_date=ev.last_hours_date,
        confidence=ev.confidence,
        socket=ev.socket,
        wifi=ev.wifi,
        quiet=ev.quiet,
        noisy=ev.noisy,
        demo=ev.demo,
        text=text,
    )


def _note(r: Recommendation) -> str:
    """The first sentence of the card's notes that is not about hours (those are `hours.note`): an honest caveat
    about weather, an unverified wish, a place of another kind."""
    for sentence in sentences(plain(r.notes)):
        if not any(w in sentence.lower() for w in _HOURS_WORDS):
            return sentence
    return ""


def _caveat(padding: str, lang: str) -> str:
    if padding == "expanded":
        return s("caveat_expanded", lang)
    return s("caveat_other", lang) if padding in ("backfill", "substituted") else ""


def _unsaid(text: str, said: str) -> str:
    """`text` without the sentences the card's reason already says (a template reason may lead with the record's
    own description, which «что делать» starts with too)."""
    known = {x.strip(" .").lower() for x in sentences(plain(said))}
    return " ".join(x for x in sentences(plain(text)) if x.strip(" .").lower() not in known)


def place_from_rec(
    r: Recommendation, *, primary: bool, lang: str, when: datetime, mode: str
) -> Place:
    poi = r.poi
    kind = poi_kind(poi, lang)
    arrival = to_local_naive(when) + timedelta(minutes=r.travel_min)
    hours = hours_block(poi, r.hours_state, r.hours_issue, r.hours_note, arrival, lang)
    visit = visit_note(poi, when, r.travel_min, r.time_on_site_min, r.hours_state, lang)
    if visit and not hours.note:
        hours.note = visit
    why = short_why(r.why) or t("why_none", lang)  # a model card left with nothing: the honest line
    return Place(
        id=poi.id,
        name=display_name(poi.name_for(lang)),
        kind=kind,
        category=poi.category,
        lat=poi.lat,
        lon=poi.lon,
        primary=primary,
        why=why,
        what_to_do=short_what(_unsaid(r.what_to_do, why)) or tip(poi.category, lang),
        ai_idea=r.generated_idea,
        stay_min=r.time_on_site_min,
        address=clean_address(poi.address) or None,
        phone=poi.phone,
        website=poi.website,
        walk=Walk(
            minutes=r.travel_min,
            distance_m=r.distance_m,
            method=r.walk_method,
            mode=mode,  # type: ignore[arg-type]
            text=walk_text(r.travel_min, mode, lang),
        ),
        hours=hours,
        people=_people(r.people, lang),
        caveat=_caveat(r.padding, lang),
        note=_note(r),
        text_source=r.text_source,
        padding=r.padding,
        lrt_hint=r.lrt_hint,
        sources=sources_of(poi, lang),
        data_date=(poi.collected_at or "")[:10] or None,
        price=price_of(poi, lang),
    )


def place_from_poi(
    poi: POI,
    *,
    origin: tuple[float, float],
    mode: str,
    when: datetime,
    lang: str,
    what: str = "",
    router: WalkingRouter | None = None,
) -> Place:
    """A place straight from the dataset (a question about it, no search): the distance by the straight line, or,
    with a `router` and on foot, the street leg from the person to the place (the walking time code of the search)."""
    d = haversine_m(origin[0], origin[1], poi.lat, poi.lon)
    minutes, method = travel_minutes(d, mode), "estimate"
    if router is not None and mode == "walk":
        leg = router.leg(origin, (poi.lat, poi.lon))
        d, minutes, method = leg.distance_m, leg.minutes, leg.method
    arrival = to_local_naive(when) + timedelta(minutes=minutes)
    hrs = poi_hours(
        poi, arrival
    )  # the state and its change time of one moment: the arrival (walks.status)
    return Place(
        id=poi.id,
        name=display_name(poi.name_for(lang)),
        kind=poi_kind(poi, lang),
        category=poi.category,
        lat=poi.lat,
        lon=poi.lon,
        what_to_do=what,
        address=clean_address(poi.address) or None,
        phone=poi.phone,
        website=poi.website,
        walk=Walk(
            minutes=minutes,
            distance_m=round(d),
            method=method,  # type: ignore[arg-type]
            mode=mode,  # type: ignore[arg-type]
            text=walk_text(minutes, mode, lang),
        ),
        hours=hours_block(poi, hrs.state, hrs.issue, hrs.note, arrival, lang),
        sources=sources_of(poi, lang),
        data_date=(poi.collected_at or "")[:10] or None,
        price=price_of(poi, lang),
    )


def shown_of(place: Place) -> ShownPlace:
    return ShownPlace(
        id=place.id,
        name=place.name,
        kind=place.kind,
        what=place.what_to_do,
        distance_m=place.walk.distance_m,
        minutes=place.walk.minutes,
        mode=place.walk.mode,
    )


# ------------------------------------------------------------------ answers


def _hours_answer(place: Place, poi: POI, lang: str, at: datetime) -> PlaceAnswer:
    h = place.hours
    kind, when = hours_facts(poi, h.state, at, lang)
    src = _by(poi, lang)
    if (iv := today_intervals(poi, to_local_naive(at))) and h.state != "unknown":
        src = f"{s('today_hours', lang, iv=iv)}; {src}"
    name = place.name
    if kind == "unknown":
        contact = (
            s("a_contact_phone", lang, phone=poi.phone)
            if poi.phone
            else s("a_contact_site", lang, site=poi.website)
            if poi.website
            else ""
        )
        text = s("a_hours_unknown", lang, name=name, contact=contact)
        if poi.admin_hours:  # the register's office week: said as such, never as «open» / «closed»
            text = f"{text} {gt('gov_admin_answer', lang, hours=poi.admin_hours.get('raw'))}"
    else:
        text = s(f"a_hours_{_ANSWER_KEY[kind]}", lang, name=name, t=when, src=src)
    if h.note and (h.state != "unknown" or h.issue):
        text = f"{text} {h.note}"
    return PlaceAnswer(
        place_id=place.id,
        name=name,
        topic="hours",
        text=text.strip(),
        known=h.state != "unknown",
        source=h.source,
    )


def _attr_value(poi: POI, topic: str) -> str | None:
    if topic == "wifi":
        v = poi.internet_access
        return {"wlan": "yes", "yes": "yes", "no": "no"}.get(v or "")
    if topic == "wheelchair":
        return poi.wheelchair if poi.wheelchair in ("yes", "no", "limited") else None
    if topic == "terrace":
        return poi.outdoor_seating if poi.outdoor_seating in ("yes", "no") else None
    value = poi.tag_dict().get("takeaway", "")
    return value if value in ("yes", "no") else None


def _attr_answer(place: Place, poi: POI, topic: str, lang: str) -> PlaceAnswer:
    what = s(_ATTR_TOPICS[topic], lang)
    value = _attr_value(poi, topic)
    src = Source(label=s("src_osm", lang))
    if value is None:
        return PlaceAnswer(
            place_id=place.id,
            name=place.name,
            topic=topic,
            text=s("a_unknown", lang, name=place.name, what=what),
            known=False,
        )
    key = {"yes": "a_attr_yes", "no": "a_attr_no", "limited": "a_attr_limited"}[value]
    return PlaceAnswer(
        place_id=place.id,
        name=place.name,
        topic=topic,
        text=s(key, lang, name=place.name, what=what, src=s("by_osm", lang)),
        source=src,
    )


def _fact(place: Place, topic: str, text: str, known: bool = True) -> PlaceAnswer:
    return PlaceAnswer(place_id=place.id, name=place.name, topic=topic, text=text, known=known)


def price_source(poi: POI, lang: str) -> tuple[str, str, str | None, str | None]:
    """(whose price wording it is, «по данным …», the page, the day the fact was read): every source of `price_text` is named by what it is —
    the venue's site, the ministry's museum register, the Wikivoyage guide, the page of any other first-party layer —
    never as the raw key of `field_sources`, never as OpenStreetMap."""
    src = poi.field_sources.get("price_text") or {}
    host = urlsplit(src.get("url") or "").hostname or ""
    which = src.get("source") or ""
    label = {
        "official_site": s("src_site", lang),
        "museum_register": s("src_museum_register", lang),
        "state_registry": gt("src_gov", lang),
        WIKIVOYAGE: s("src_wikivoyage", lang),
    }.get(which) or (s("src_host", lang, host=host) if host else s("src_record", lang))
    by = {
        "official_site": s("by_site", lang),
        "museum_register": s("by_register", lang),
        "state_registry": gt("by_gov", lang),
    }.get(which) or (s("by_host", lang, host=host) if host else s("by_record", lang))
    return label, by, src.get("url"), src.get("snapshot_date") or None


def price_of(poi: POI, lang: str) -> Price | None:
    """The card's price line: the place's own wording and whose it is; None when the record has no price."""
    if not poi.price_text:
        return None
    label, _, url, date = price_source(poi, lang)
    return Price(text=poi.price_text, source=Source(label=label, url=url), date=date)


def _price_answer(place: Place, poi: POI, lang: str) -> PlaceAnswer:
    """The place's own price wording («вход — 1000 тг») with its source; the wording is never parsed into a number."""
    label, by, url, _ = price_source(poi, lang)
    return PlaceAnswer(
        place_id=place.id,
        name=place.name,
        topic="price",
        text=s("a_price", lang, name=place.name, price=poi.price_text, by=by),
        known=True,
        source=Source(label=label, url=url),
    )


def answer(topic: Topic, place: Place, poi: POI, lang: str, at: datetime) -> PlaceAnswer:
    """The answer to a question about one place, from its record only."""
    name, walk = place.name, place.walk.text
    if topic == "hours":
        return _hours_answer(place, poi, lang, at)
    if topic in _ATTR_TOPICS:
        return _attr_answer(place, poi, topic, lang)
    if topic in _NO_DATA:
        if topic == "price" and poi.price_text:
            return _price_answer(place, poi, lang)
        what = s(_NO_DATA[topic], lang)
        return _fact(place, topic, s("a_unknown", lang, name=name, what=what), known=False)
    if topic == "address":
        if poi.address:
            return _fact(
                place,
                topic,
                s("a_address", lang, name=name, address=clean_address(poi.address), walk=walk),
            )
        return _fact(place, topic, s("a_address_none", lang, name=name, walk=walk), known=False)
    if topic == "route":
        key = "a_route_far" if place.walk.minutes >= FAR_WALK_MIN else "a_route"
        return _fact(
            place,
            topic,
            s(key, lang, name=name, d=dist_text(place.walk.distance_m, lang), walk=walk),
        )
    if topic == "phone":
        if poi.phone:
            return _fact(place, topic, s("a_phone", lang, name=name, phone=poi.phone))
        return _fact(place, topic, s("a_phone_none", lang, name=name), known=False)
    if topic == "website":
        if poi.website:
            return _fact(place, topic, s("a_site", lang, name=name, site=poi.website))
        return _fact(place, topic, s("a_site_none", lang, name=name), known=False)
    hours = lower_first(place.hours.text)
    return _fact(
        place, "about", s("a_about", lang, name=name, kind=place.kind, walk=walk, hours=hours)
    )


def short_reply(answers: list[PlaceAnswer]) -> str:
    """The reply of an answer turn: the answers themselves, each one sentence (the first one of its text)."""
    several_places = (
        len({a.place_id for a in answers}) > 1
    )  # one place, several questions: each answer whole
    return " ".join(first_sentence(a.text) if several_places else a.text for a in answers)
