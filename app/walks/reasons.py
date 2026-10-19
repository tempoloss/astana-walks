"""Why a place, in words the data can back: the sentences of the no-AI card (`why`, `what_to_do`) and the clauses that
code adds to an AI card (weather, marks of people, budget).

A reason is a FACT of a field, never a flourish: the wish of the request that the record answers (kids, quiet,
Wi-Fi, socket, step-free, a keyword), the marks of people, the weather / air / darkness that moved the place indoors,
the time window (the round trip and the stay of THIS place against the budget), the hours (24/7 or open at this time
by OSM), how it compares with the other candidates (nearest, the only one of its kind, the most-read Wikipedia
article) and attributes (tables outside, cuisine, Wi-Fi, wheelchair). Of those the two strongest stay in at most two
sentences. The numbers come from the final routing step: the pipeline calls `refresh_why` after it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .claims import strip_unbacked
from .districts import district_of
from .facts import features, street
from .i18n import (
    attr_label,
    district_name,
    marks,
    source_label,
    t,
    tip,
)
from .i18n_cuisine import cuisine_label
from .models import HOURS_SUFFIX, MUSEUM_REGISTER, Candidate, Intent, Recommendation, WeatherInfo
from .radius import INFO_ABOUT
from .shelter import AIR_OUTDOOR_KEPT, LIT_NEAR, WEATHER_OUTDOOR_KEPT
from .stay import MIN_STAY_OVER_BUDGET, NAMED_OVER_BUDGET, min_stay
from .weather import BAD_PM25, adverse_text, air_driver_text, air_text
from .wishes import ERRANDS

MAX_FACTS = 2  # sentences of a `why`
WIKI_SENTENCE_MAX = 220
# wishes of the request that a record answers: reason code -> i18n key of the clause
_FIT_REASONS = {
    "kids": "fit_kids",
    "halal": "fit_halal",
    "local_food": "fit_local_food",
    "quiet": "fit_quiet",
    "wifi": "fit_wifi",
    "socket": "fit_socket",
    "wheelchair": "fit_wheelchair",
    "free": "fit_free",
    "pets": "fit_pets",
    INFO_ABOUT: "fit_info",
}

# What the eval counts as an unconfirmed «open» claim (eval/metrics.py `_OPEN_CLAIM`; a test keeps them equal).
# «на открытом воздухе» is a different word and does not match.
_OPEN_CLAIM = re.compile(r"\bоткрыт[оаы]?\b|\bработает\b|\bopen now\b", re.I)
_OPEN_CLAIM_KK = re.compile(
    r"\bашық\b|\bжұмыс істейді\b", re.I
)  # the same for Kazakh text; the eval has no kk set
# Hours as derived by the collector into a description: «Работает круглосуточно», «часы работы: <OSM string>».
_DERIVED_24_7 = re.compile(r"\b[Рр]аботает круглосуточно")
_DERIVED_HOURS = re.compile(r"\b[Чч]асы работы:\s*([^.]+)")
# A sentence of a website's description that states hours: the hours of a card are its own fields, never a quote.
_HOURS_WORDS = re.compile(
    r"\d{1,2}[:.]\d{2}|круглосуточ|24/7|24 час|24 hours|режим работы|график работы|часы работы|opening hours"
    r"|working hours|ежедневно с\b|тәулік бойы|жұмыс уақыты|жұмыс кестесі",
    re.I,
)


def budget_phrase(c: Candidate, intent: Intent) -> str:
    """Why a place stayed in the list although its usual minimum stay exceeds the time left ('' otherwise, and '' when
    the person set no time: a default of 60 min is no limit of theirs to explain)."""
    if not intent.time_stated or (
        MIN_STAY_OVER_BUDGET not in c.reasons and NAMED_OVER_BUDGET not in c.reasons
    ):
        return ""
    return t("budget_over", intent.language, lo=min_stay(c.poi.category))


def honest_hours_text(text: str, c: Candidate, lang: str | None = "ru") -> str:
    """Text of a card whose hours are not confirmed (state != open): hours phrases that the collector wrote into
    a description are rewritten to «обычно: …; в праздник часы могут отличаться», and every sentence that is
    still an unconfirmed open-claim (the eval's `_OPEN_CLAIM`) is dropped. A confirmed «open» card is untouched."""
    if c.hours_state == "open" or not text:
        return text
    if c.poi.opening_hours:
        tail = t(
            "hours_tail_holiday"
            if c.hours_note.startswith("праздник")
            else "hours_tail_unconfirmed",
            lang,
        )

        def usual(m: re.Match[str], hours: str) -> str:
            word = t("hours_usual", lang)
            word = word if m.group(0)[0].isupper() else word.lower()
            return f"{word}: {hours}; {tail}"

        text = _DERIVED_24_7.sub(lambda m: usual(m, t("hours_247", lang)), text)
        text = _DERIVED_HOURS.sub(lambda m: usual(m, m.group(1).strip()), text)
    parts = re.split(r"(?<=[.!?])\s+", text.strip())
    claim = _OPEN_CLAIM_KK if lang == "kk" else _OPEN_CLAIM
    return " ".join(p for p in parts if p and not claim.search(p)).strip()


_OUTDOOR_ASKED = frozenset({"park_garden", "viewpoint", "kids_playground", "attraction_landmark"})


def weather_phrase(c: Candidate, intent: Intent, weather: WeatherInfo | None) -> str:
    """Short clause explaining a choice driven by weather, air or darkness ('' when none of them mattered): one clause,
    never one per condition, and none on a kind the person named (the weather did not choose it, the person did)."""
    if weather is None or c.poi.category in intent.wished:
        return ""
    lang = intent.language
    parts: list[str] = []
    if "weather_indoor" in c.reasons and weather.adverse:
        parts.append(t("wx_bad", lang, what=adverse_text(weather, lang)))
    if (
        "air_indoor" in c.reasons and weather.air_bad and not parts
    ):  # one «место в помещении» is enough
        parts.append(air_text(weather, lang))
    if (
        "dark_indoor" in c.reasons and not parts
    ):  # the weather / air clause already says «место в помещении»
        parts.append(t("wx_dark", lang))
    return "; ".join(parts)


def weather_notes(c: Candidate, weather: WeatherInfo | None, lang: str) -> list[str]:
    """The notes under an outdoor card that the weather, the air or the darkness call for, each with its real
    reason: an outdoor place shown in spite of them (the shelter rule found no indoor one) or kept because the
    request asked for the outdoors (the walk is better kept short)."""
    out: list[str] = []
    if weather is not None:
        kept: list[str] = []
        if WEATHER_OUTDOOR_KEPT in c.reasons and weather.adverse:
            kept.append(adverse_text(weather, lang))
        if AIR_OUTDOOR_KEPT in c.reasons and weather.air_bad:
            kept.append(air_driver_text(weather, lang))
        if kept:
            out.append(t("note_outdoor_kept", lang, reason=", ".join(kept)))
        if "weather_outdoor" in c.reasons and weather.adverse:
            key = "note_hint_outdoor" if weather.user_hint == "heat" else "note_weather_outdoor"
            out.append(t(key, lang, reason=adverse_text(weather, lang)))
        if "air_outdoor" in c.reasons and weather.air_bad:
            if weather.user_hint != "smog" and (weather.pm25 or 0) > BAD_PM25:
                out.append(t("note_air_outdoor", lang, pm=f"{weather.pm25:.0f}"))
            else:
                out.append(t("note_hint_outdoor", lang, reason=air_driver_text(weather, lang)))
    if "dark_outdoor" in c.reasons:
        out.append(t("note_dark_outdoor", lang))
    if LIT_NEAR in c.reasons:
        out.append(t("note_lit_near", lang))
    return out


def _marks(c: Candidate, lang: str, asked: bool) -> str:
    """What anonymous marks of people say about sockets / Wi-Fi / noise, with its source: the marks the request
    asked about (`asked`), else every mark the place has ('' when none)."""
    ev = c.people
    if ev is None:
        return ""
    items = [
        f"{attr_label(code, lang)} ({marks(n, lang)})"
        for code, n in (
            ("people_socket", ev.socket),
            ("people_wifi", ev.wifi),
            ("people_quiet", ev.quiet),
            ("people_noisy", ev.noisy),
        )
        if (code in c.reasons if asked else n > 0)
    ]
    return f"{source_label(ev.demo, lang)}: {', '.join(items)}" if items else ""


def people_phrase(c: Candidate, intent: Intent) -> str:
    """What anonymous marks of people say about the sockets / Wi-Fi / noise the request asked about ('' when none)."""
    return _marks(c, intent.language, asked=True)


# ---------------------------------------------------------------- the composer


@dataclass(frozen=True)
class Trip:
    """What one visit costs, from the routing step: minutes one way and minutes on site."""

    one_way_min: int
    stay_min: int


def _sentence(fragment: str) -> str:
    fragment = fragment.strip()
    if not fragment:
        return ""
    text = fragment[0].upper() + fragment[1:]
    return text if text.endswith((".", "!", "?")) else text + "."


def _lower_first(text: str) -> str:
    first = text.split(" ", 1)[0]
    return text[0].lower() + text[1:] if first[1:].islower() else text


def _wishes(c: Candidate, lang: str) -> list[str]:
    """The wishes of the request that the record answers (clauses)."""
    out = []
    for r in c.reasons:
        if r in _FIT_REASONS:
            out.append(t(_FIT_REASONS[r], lang))
        elif r.startswith("diet:"):
            out.append(t(f"fit_diet_{r.split(':', 1)[1]}", lang))
    return out


def _time_fact(c: Candidate, intent: Intent, trip: Trip) -> str:
    round_trip = 2 * trip.one_way_min
    if not intent.time_stated or round_trip + trip.stay_min > intent.time_budget_min:
        return ""  # «в ваши 90 мин»: only a time the person set
    return t(
        "fact_time",
        intent.language,
        budget=intent.time_budget_min,
        rt=round_trip,
        stay=trip.stay_min,
    )


def hours_state_text(state: str, source: str | None, lang: str | None = "ru") -> str:
    """The label of an hours state, naming the source of the hours when it says «open»:
    «открыто по данным OSM» / «открыто по данным официального сайта»."""
    if state == "open":
        return t(f"hours_state_open_{HOURS_SUFFIX.get(source or '', 'osm')}", lang)
    return t(f"hours_state_{state}", lang)


def _quotable(raw: str) -> str:
    """The website's own words for hours that name no days, without the verbs that read as a claim of «open» («Открыто
    с 10:00», «работает с 9 до 18»): the card quotes them next to an unknown state."""
    text = _OPEN_CLAIM_KK.sub("", _OPEN_CLAIM.sub("", raw))
    return re.sub(r"\s+", " ", text).strip(" ,;:-—") or raw


def hours_notes(c: Candidate, lang: str | None) -> list[str]:
    """What a card must say about its hours besides the state: OSM and the website differ (and, when they disagree
    right now, that the state is therefore unknown); the website names hours without days; hours unknown at all."""
    poi = c.poi
    if c.hours_issue in ("conflict", "split"):
        note = t(
            "note_hours_conflict", lang, osm=poi.opening_hours, site=poi.opening_hours_official
        )
        return [f"{note} {t('note_hours_split_tail', lang)}" if c.hours_issue == "split" else note]
    if c.hours_issue == "unqualified":
        key = (
            "note_hours_unqualified_register"
            if poi.hours_source() == MUSEUM_REGISTER
            else "note_hours_unqualified"
        )
        return [t(key, lang, raw=_quotable(poi.hours_unqualified or ""))]
    if c.hours_state == "unknown" and not c.hours_note:
        return [t("note_hours_unknown", lang)]
    return []


def _open_fact(c: Candidate, lang: str) -> str:
    if c.hours_state == "closed" and c.poi.opening_hours and INFO_ABOUT in c.reasons:
        return t("fact_closed_now", lang)  # the user asked about the place: «закрыто» is the answer
    return ""


def _comparison_facts(c: Candidate, peers: list[Candidate], lang: str) -> list[str]:
    """What the record says about how well known the place is (its Wikipedia article and its views), compared with
    the other selected candidates only."""
    views = c.poi.popularity_pageviews
    if views:
        rated = [p for p in peers if p.poi.popularity_pageviews]
        top = len(rated) >= 2 and max(p.poi.popularity_pageviews or 0 for p in rated) == views
        return [t("fact_wiki_top" if top else "fact_wiki", lang, n=views)]
    return [t("fact_wiki_plain", lang)] if c.poi.wikipedia else []


def facts(
    c: Candidate,
    intent: Intent,
    weather: WeatherInfo | None,
    peers: list[Candidate],
    trip: Trip,
) -> list[str]:
    """Every sentence the record's fields can back, the strongest first: the wishes the record confirms, people's
    marks, the record's own facts (cuisine, features, Wikipedia), the time window. Never a selection note («ближайшее
    из N подобранных», «категория — как вы просили», «совпадает с …») nor a status (the card's own line says it,
    walks.status); the conditions only on a card that stands in for the outdoor place asked for, where they are the
    reason (a café padding a short list of bars is there for the shortage, not for the fog)."""
    lang = intent.language
    out: list[str] = []
    if wishes := _wishes(c, lang):
        out.append(_sentence("; ".join(wishes)))
    if clause := people_phrase(c, intent):
        out.append(_sentence(clause))
    substitute = "off_category" in c.reasons and set(intent.categories) & _OUTDOOR_ASKED
    if substitute and (wx := weather_phrase(c, intent, weather)):
        out.append(_sentence(wx))
    if closed := _open_fact(c, lang):
        out.append(closed)  # the person asked about this very place: «сейчас закрыто» is the answer
    if own := _own_facts(c, lang):
        out.append(own)
    out += _comparison_facts(c, peers, lang)
    if time_fact := _time_fact(c, intent, trip):
        out.append(time_fact)
    return out


def _own_facts(c: Candidate, lang: str) -> str:
    """The record's own facts in one sentence: the cuisine and the features its tags state (walks.facts)."""
    cuisine = cuisine_label(c.poi.tag_dict().get("cuisine", ""), lang)
    line = t("fact_cuisine", lang, c=cuisine) if cuisine else ""
    price = (c.poi.price_text or "")[:80]
    parts = (
        [line.rstrip(".")] if line and _info(c, lang) != line else []
    )  # «what to do» may say it already
    parts += [f for f in features(c, lang) if f != price]  # the price has its own line on the card
    return _sentence("; ".join(parts)) if parts else ""


# a brand that already says it is a chain («Сеть ресторанов ПИНТА»): said as it is, never «Сеть «Сеть ресторанов …»»
_CHAIN_WORDS = re.compile(r"\bсет[ьи]\b|ресторанов|\bchain\b|желі", re.I)


def _brand_fact(c: Candidate, lang: str) -> str:
    brand = c.poi.tag_dict().get("brand", "").strip()
    if not brand:
        return ""
    return f"{brand}." if _CHAIN_WORDS.search(brand) else t("fact_brand", lang, brand=brand)


def _where_fact(c: Candidate, lang: str) -> str:
    """Where the place is, to find it: the street of its address and its district («на улице Туркестан, 34А, район
    Есиль»); an errand without an address: its district, to find it (a pharmacy card is more than «nothing more»);
    '' otherwise."""
    where = street(c)
    district = district_of(c.poi.lat, c.poi.lon)
    if not where:
        errand = c.poi.category in ERRANDS
        return (
            t("fact_district", lang, district=district_name(district, lang))
            if errand and district
            else ""
        )
    if not district:
        return t("fact_where", lang, where=where)
    return t("fact_where_district", lang, where=where, district=district_name(district, lang))


def _record_facts(c: Candidate, lang: str, bare: bool) -> list[str]:
    """What a record without a description still holds, in this order: its brand; for a card with no other fact
    (`bare`), where it is and what people's marks say."""
    out = [_brand_fact(c, lang)]
    if bare:
        out += [_where_fact(c, lang), _sentence(_marks(c, lang, asked=False))]
    return [x for x in out if x]


def _without_repeats(sentences: list[str]) -> list[str]:
    """The sentences of a `why` without a fragment (a clause between «;») that a sentence before already holds; a
    sentence left with nothing is dropped, one with nothing repeated stays as it is."""
    out: list[str] = []
    for sentence in sentences:
        said = " ".join(out).lower()
        parts = re.split(r";\s+", sentence.rstrip("."))
        new = [p for p in parts if p.strip().lower() not in said]
        if new == parts:
            out.append(sentence)
        elif new:
            out.append(_sentence("; ".join(new)))
    return out


def compose_why(
    c: Candidate,
    intent: Intent,
    weather: WeatherInfo | None,
    peers: list[Candidate],
    trip: Trip,
) -> str:
    """The `why` of a no-AI card: its two strongest facts (one, when the budget note has to be said); what the data
    says about the place (its article, site, guide, cuisine) first; a record without a description: its cuisine and
    features, its brand, where it is (street and district), people's marks; '' when the record holds nothing at all
    (the card then says so honestly), never a selection note."""
    lang = intent.language
    off = "off_category" in c.reasons
    budget = budget_phrase(c, intent)
    found = facts(c, intent, weather, peers, trip)
    if info := _info(
        c, lang, address=False
    ):  # «есть статья в Википедии» says less than the article's own words
        bare = set(_comparison_facts(c, peers, lang))
        found = [f for f in found if f not in bare and f != info]
        found = [*found[:1], info, *found[1:]] if found else [info]
    else:  # an off-kind card says what it is, never only where it is
        found += _record_facts(c, lang, bare=not found and not off)
    found = _without_repeats(
        found
    )  # «…; в OSM указан Wi-Fi. Wi-Fi.»: the feature said by a wish is said once
    keep = found[:1] if budget else found[:MAX_FACTS]
    if (
        not keep
    ):  # the record holds nothing else: said so, never «рядом с вами» (the walk line says how far)
        keep = [t("fit_none_off" if off else "why_none", lang)]
    elif off:
        keep[0] = t("fit_head_off", lang) + _lower_first(keep[0])
    return " ".join([*keep, budget] if budget else keep)


def refresh_why(
    recs: list[Recommendation],
    peers: list[Candidate],
    intent: Intent,
    weather: WeatherInfo | None,
) -> None:
    """After routing: the `why` of every no-AI card again, with the final walking times (an AI card keeps its text)."""
    by_id = {c.poi.id: c for c in peers}
    for r in recs:
        c = by_id.get(r.poi.id)
        if r.text_source == "template" and c is not None:
            one_way = r.walk_min if intent.mode == "walk" else r.travel_min
            r.why = compose_why(c, intent, weather, peers, Trip(one_way, r.time_on_site_min))


# spelling / language remarks of an article's first sentence («(по-русски: ошибочно — „Ханский шатёр“ …)», «(каз.
# Қазақстан Республикасының Тұңғыш Президентінің мұражайы)»): not what to do there, and not what the record is; the
# abbreviation «каз.» would also end the sentence there
_REMARK = re.compile(
    r"\s*\([^()]*(?:ошибочн|неправильн|по-русски|правильно|mistaken|sometimes called|\bказ\.|\bқаз\.|\bангл\.)[^()]*\)",
    re.I,
)
# the native names an English article puts in brackets («The Nur-Astana Mosque (Kazakh: Нұр-Астана мешіті; …)»)
_NATIVE = re.compile(r"\s*\([^()]*[А-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ][^()]*\)")
_CYR = re.compile(r"[А-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ]")


def _first_sentence(text: str) -> str:
    text = _REMARK.sub("", text.strip())
    m = re.match(r"(.{30,}?[.!?])(\s|$)", text, re.S)
    out = m.group(1) if m else text
    return out if len(out) <= WIKI_SENTENCE_MAX else out[: WIKI_SENTENCE_MAX - 1].rstrip() + "…"


def _official_info(c: Candidate, lang: str) -> str:
    """The website's own description of the place, quoted and attributed: no sentence that names hours (they are the
    card's own fields) or asserts an attribute no field of the record backs."""
    sentences = re.split(r"(?<=[.!?])\s+", (c.poi.description_official or "").strip())
    text = " ".join(s for s in sentences if s and not _HOURS_WORDS.search(s))
    text = honest_hours_text(strip_unbacked(text, c)[0], c, lang)
    if lang == "en" and _CYR.search(
        text
    ):  # the site speaks Russian: an English card does not quote it
        return ""
    return t("info_site", lang, text=_first_sentence(text)) if text else ""


def _voyage_info(c: Candidate, lang: str) -> str:
    """The Wikivoyage description of the place (collect/wikivoyage), quoted and attributed to the guide: third-party
    CC BY-SA text, never presented as our own. The text is used only when its edition is in the answer language
    (the ru edition for ru, en for en); same filtering as the website's text."""
    poi = c.poi
    if (
        poi.description_voyage
        and poi.field_sources.get("description_voyage", {}).get("lang") != lang
    ):
        return ""
    sentences = re.split(r"(?<=[.!?])\s+", (poi.description_voyage or "").strip())
    text = " ".join(s for s in sentences if s and not _HOURS_WORDS.search(s))
    text = honest_hours_text(strip_unbacked(text, c)[0], c, lang)
    return t("info_voyage", lang, text=_first_sentence(text)) if text else ""


def _info(c: Candidate, lang: str, *, address: bool = True) -> str:
    """What the data says about the place, in the answer language: the first sentence of its Wikipedia article, a
    human-written OSM description (Russian only: no other language is known), the description on the place's own
    website (quoted, attributed), the Wikivoyage guide (quoted, attributed, same language as the answer), else its
    cuisine, else (with `address`, for «что делать») its address. The collector's derived description is boilerplate
    («Кафе «X» в Астане»): it is not used."""
    poi = c.poi
    art = poi.wikipedia.get(lang) or {}
    if poi.description_source == "wikipedia" and art.get("extract"):
        return _first_sentence(_NATIVE.sub("", art["extract"]) if lang == "en" else art["extract"])
    if lang == "ru" and poi.description_source in ("wikipedia", "osm") and poi.description:
        return _first_sentence(honest_hours_text(poi.description, c, lang))
    if official := _official_info(c, lang):
        return official
    if voyage := _voyage_info(c, lang):
        return voyage
    if cuisine := cuisine_label(poi.tag_dict().get("cuisine", ""), lang):
        return t("fact_cuisine", lang, c=cuisine)
    return t("address", lang, a=a) if address and (a := street(c)) else ""


def template_what(c: Candidate, intent: Intent) -> str:
    """«Что делать» of a no-AI card: what the data says about the place, then the usual thing to do there."""
    return f"{_info(c, intent.language)} {tip(c.poi.category, intent.language)}".strip()
