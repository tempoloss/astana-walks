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
from .hours import is_24_7
from .i18n import (
    attr_label,
    category_name,
    marks,
    source_label,
    t,
    tip,
)
from .i18n_cuisine import cuisine_label
from .models import HOURS_SUFFIX, MUSEUM_REGISTER, Candidate, Intent, Recommendation, WeatherInfo
from .radius import INFO_ABOUT
from .shelter import AIR_OUTDOOR_KEPT, LIT_NEAR, OUTDOOR_EXCLUDED, WEATHER_OUTDOOR_KEPT
from .stay import MIN_STAY_OVER_BUDGET, NAMED_OVER_BUDGET, min_stay
from .weather import BAD_PM25, adverse_text, air_driver_text, air_text

MAX_FACTS = 2  # sentences of a `why`
WIKI_SENTENCE_MAX = 220
# wishes of the request that a record answers: reason code -> i18n key of the clause
_FIT_REASONS = {
    "kids": "fit_kids",
    "halal": "fit_halal",
    "quiet": "fit_quiet",
    "wifi": "fit_wifi",
    "socket": "fit_socket",
    "wheelchair": "fit_wheelchair",
    "free": "fit_free",
    "pets": "fit_pets",
    INFO_ABOUT: "fit_info",
    "open_at_night": "fit_night",
}
_UNIQUE_KINDS = frozenset(  # a category whose «only one among the selected» is worth saying
    {
        "museum_gallery",
        "attraction_landmark",
        "viewpoint",
        "park_garden",
        "kids_playground",
        "entertainment",
        "culture_theatre_cinema",
        "mall",
        "sport",
        "coworking_library",
    }
)

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
    """Why a place stayed in the list although its usual minimum stay exceeds the time left ('' otherwise)."""
    if MIN_STAY_OVER_BUDGET not in c.reasons and NAMED_OVER_BUDGET not in c.reasons:
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


def weather_phrase(c: Candidate, intent: Intent, weather: WeatherInfo | None) -> str:
    """Short clause explaining a choice driven by weather, air or darkness ('' when none of them mattered)."""
    if weather is None:
        return ""
    lang = intent.language
    parts: list[str] = []
    if "weather_indoor" in c.reasons and weather.adverse:
        parts.append(t("wx_bad", lang, what=adverse_text(weather, lang)))
    if "air_indoor" in c.reasons and weather.air_bad:
        parts.append(air_text(weather, lang))
    if (
        "dark_indoor" in c.reasons and not parts
    ):  # the weather / air clause already says «место в помещении»
        parts.append(t("wx_dark", lang))
    if OUTDOOR_EXCLUDED in c.reasons:
        parts.append(t("wx_outdoor_off", lang))
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


def people_phrase(c: Candidate, intent: Intent) -> str:
    """What anonymous marks of people say about sockets / Wi-Fi / noise, always with its source ('' when none)."""
    ev = c.people
    if ev is None:
        return ""
    lang = intent.language
    items = [
        f"{attr_label(code, lang)} ({marks(n, lang)})"
        for code, n in (
            ("people_socket", ev.socket),
            ("people_wifi", ev.wifi),
            ("people_quiet", ev.quiet),
            ("people_noisy", ev.noisy),
        )
        if code in c.reasons
    ]
    if not items:
        return ""
    return f"{source_label(ev.demo, lang)}: {', '.join(items)}"


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
            key = _FIT_REASONS[r]
            out.append(t(key + _by_site(c) if key == "fit_night" else key, lang))
        elif r.startswith("diet:"):
            out.append(t(f"fit_diet_{r.split(':', 1)[1]}", lang))
        elif r.startswith("keywords:"):
            kws = ", ".join(f"“{k}”" for k in r.split(":", 1)[1].split(","))
            out.append(t("fit_keywords", lang, kws=kws))
    return out


def _time_fact(c: Candidate, intent: Intent, trip: Trip) -> str:
    round_trip = 2 * trip.one_way_min
    if round_trip + trip.stay_min > intent.time_budget_min:
        return ""
    return t(
        "fact_time",
        intent.language,
        budget=intent.time_budget_min,
        rt=round_trip,
        stay=trip.stay_min,
    )


def _is_24_7(c: Candidate) -> bool:
    return is_24_7(c.poi.opening_hours)


def _by_site(c: Candidate) -> str:
    """Suffix of the i18n key of a sentence about the hours: the website's hours say so, OSM's are the default."""
    suffix = HOURS_SUFFIX.get(c.poi.hours_source() or "")
    return f"_{suffix}" if suffix else ""


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
    if c.hours_state != "open" or not c.poi.opening_hours:
        return ""
    return t(("fact_open_247" if _is_24_7(c) else "fact_open") + _by_site(c), lang)


def _comparison_facts(c: Candidate, peers: list[Candidate], lang: str) -> list[str]:
    """How the place compares with the other selected candidates (never with the whole city: that is not known)."""
    cat = category_name(c.poi.category, lang)
    same = [p for p in peers if p.poi.category == c.poi.category]
    out = []

    def nearest(group: list[Candidate]) -> bool:
        return min(group, key=lambda p: (p.distance_m, p.poi.id)).poi.id == c.poi.id

    open_same = [p for p in same if p.hours_state == "open"]
    if c.hours_state == "open" and len(open_same) >= 2 and nearest(open_same):
        out.append(t("fact_nearest_open" + _by_site(c), lang, n=len(same), cat=cat))
    elif len(same) >= 2 and nearest(same):
        out.append(t("fact_nearest", lang, n=len(same), cat=cat))
    elif len(peers) >= 3 and len(same) == 1 and c.poi.category in _UNIQUE_KINDS:
        out.append(t("fact_only", lang, cat=cat))
    views = c.poi.popularity_pageviews
    if views:
        rated = [p for p in peers if p.poi.popularity_pageviews]
        top = len(rated) >= 2 and max(p.poi.popularity_pageviews or 0 for p in rated) == views
        out.append(t("fact_wiki_top" if top else "fact_wiki", lang, n=views))
    elif c.poi.wikipedia:
        out.append(t("fact_wiki_plain", lang))
    return out


def _attributes(c: Candidate, weather: WeatherInfo | None, lang: str) -> str:
    poi, parts = c.poi, []
    outdoors_ok = (
        weather is None or not weather.indoor_preferred
    ) and "dark_outdoor" not in c.reasons
    if poi.outdoor_seating == "yes" and outdoors_ok:
        parts.append(t("fact_outdoor", lang).rstrip("."))
    if poi.internet_access in ("wlan", "yes") and "wifi" not in c.reasons:
        parts.append(t("fit_wifi", lang))
    if poi.wheelchair == "yes" and "wheelchair" not in c.reasons:
        parts.append(t("fit_wheelchair", lang))
    return _sentence("; ".join(parts))


def facts(
    c: Candidate,
    intent: Intent,
    weather: WeatherInfo | None,
    peers: list[Candidate],
    trip: Trip,
) -> list[str]:
    """Every sentence the record's fields can back, the strongest first."""
    lang = intent.language
    out: list[str] = []
    if wishes := _wishes(c, lang):
        out.append(_sentence("; ".join(wishes)))
    for clause in (people_phrase(c, intent), weather_phrase(c, intent, weather)):
        if clause:
            out.append(_sentence(clause))
    led = bool(
        out
    )  # a wish, marks or the weather already say why THIS place; the time window comes after
    time_fact = _time_fact(c, intent, trip)
    opened = _open_fact(c, lang)
    always = (
        bool(opened) and _is_24_7(c) and c.hours_state == "open"
    )  # 24/7 is worth more than the comparison
    if time_fact and not led:
        out.append(time_fact)
    if always:
        out.append(opened)
    out += _comparison_facts(c, peers, lang)
    if time_fact and led:
        out.append(time_fact)
    if opened and not always:
        out.append(opened)
    if attrs := _attributes(c, weather, lang):
        out.append(attrs)
    if "category" in c.reasons:
        out.append(_sentence(t("fit_category", lang, cat=category_name(c.poi.category, lang))))
    return out


def compose_why(
    c: Candidate,
    intent: Intent,
    weather: WeatherInfo | None,
    peers: list[Candidate],
    trip: Trip,
) -> str:
    """The `why` of a no-AI card: its two strongest facts (one, when the budget note has to be said)."""
    lang = intent.language
    off = "off_category" in c.reasons
    budget = budget_phrase(c, intent)
    found = facts(c, intent, weather, peers, trip)
    keep = found[:1] if budget else found[:MAX_FACTS]
    if not keep:
        keep = [t("fit_none_off" if off else "fit_none", lang)]
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


# spelling / language remarks of an article's first sentence («(по-русски: ошибочно — „Ханский шатёр“ …)»): not what to
# do there, and not what the record is
_REMARK = re.compile(
    r"\s*\([^()]*(?:ошибочн|неправильн|по-русски|правильно|mistaken|sometimes called)[^()]*\)", re.I
)


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


def _info(c: Candidate, lang: str) -> str:
    """What the data says about the place, in the answer language: the first sentence of its Wikipedia article, a
    human-written OSM description (Russian only: no other language is known), the description on the place's own
    website (quoted, attributed), the Wikivoyage guide (quoted, attributed, same language as the answer), else its
    cuisine, else its address. The collector's derived description is boilerplate («Кафе «X» в Астане»): it is not
    used."""
    poi = c.poi
    art = poi.wikipedia.get(lang) or {}
    if poi.description_source == "wikipedia" and art.get("extract"):
        return _first_sentence(art["extract"])
    if lang == "ru" and poi.description_source in ("wikipedia", "osm") and poi.description:
        return _first_sentence(honest_hours_text(poi.description, c, lang))
    if official := _official_info(c, lang):
        return official
    if voyage := _voyage_info(c, lang):
        return voyage
    if cuisine := cuisine_label(poi.tag_dict().get("cuisine", ""), lang):
        return t("fact_cuisine", lang, c=cuisine)
    return t("address", lang, a=poi.address) if poi.address else ""


def template_what(c: Candidate, intent: Intent) -> str:
    """«Что делать» of a no-AI card: what the data says about the place, then the usual thing to do there."""
    return f"{_info(c, intent.language)} {tip(c.poi.category, intent.language)}".strip()
