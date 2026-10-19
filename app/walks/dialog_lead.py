"""The lead of an answer (`Turn.reply` of a search): one or two sentences in the order the owner asked for — the
conditions in Astana right now, what the person wants, the recommendation. Every fact in it (temperature, air, hours,
minutes, names) is inserted by code from a field of the data; the model supplies only the paraphrase of the wish
(`Result.lead_want`, checked in walks.generate), and the template composes that too when there is none."""

from __future__ import annotations

import re

from .attributes import local_food_signal
from .dialog_strings import s
from .dialog_types import Place
from .holidays import holiday_name as holiday_ru
from .hours import local_now, to_local_naive
from .i18n import category_name, holiday_name, plural_ru, t
from .i18n_gov import weekday_on
from .i18n_weather import tw
from .kids import kids_gap
from .lexicon import match
from .lexicon_concepts import CONCEPTS
from .models import Recommendation, Result, WeatherInfo
from .profile import Profile
from .shelter import LIT_NEAR
from .sun import is_dark
from .want import names_the_wish
from .weather import BAD_PM25, HEAVY_PRECIP_MM, warned
from .wishes import DAY_END, DAY_START, ERRANDS, errand, of_subkind, subkind_missing

_ERRAND_SUBKINDS = (
    "atm",
    "dentist",
    "kids_doctor",
)  # the errand records the lead names by what they are

_NIGHT_WORDS = re.compile(
    r"ночью|ночн|по ночам|түнде|түнгі|at night|tonight|overnight|late[- ]night", re.I
)

FEELS_GAP_C = 3  # «ощущается как» is said when it differs from the temperature by this much
TRACE_PRECIP_MM = 0.2  # less precipitation than this in the hour is not worth a word
_SKY = (
    "thunder",
    "freezing_rain",
    "blowing_snow",
    "rain",
    "snow",
    "fog",
    "wind",
)  # tokens of the station report
_MAX_WANT_KINDS = 2
MAX_CLAUSES = (
    2  # the conditions are one short clause: at most this many parts (a holiday comes on top)
)
OUTDOOR_KINDS = frozenset({"park_garden", "viewpoint", "attraction_landmark", "kids_playground"})
_BAR_CONCEPTS = frozenset(c.name for c in CONCEPTS if "bar_nightlife" in c.categories)


def signed(value: float) -> str:
    """+12, −5 (a real minus sign), 0."""
    n = round(value)
    return f"+{n}" if n > 0 else f"−{-n}" if n < 0 else "0"


def up(text: str) -> str:
    """The text with its first letter capital (a leading quote or dash stays)."""
    for i, ch in enumerate(text):
        if ch.isalpha():
            return text[:i] + ch.upper() + text[i + 1 :]
    return text


def lower_first(text: str) -> str:
    return text[:1].lower() + text[1:] if text[1:2].islower() else text


def _temperature(w: WeatherInfo, lang: str) -> str:
    if w.temperature_c is None:
        return ""
    out = s("ld_now", lang, t=signed(w.temperature_c))
    if w.apparent_c is not None and abs(w.apparent_c - w.temperature_c) >= FEELS_GAP_C:
        out += ", " + s("ld_feels", lang, f=signed(w.apparent_c))
    return out


def _sky(w: WeatherInfo, lang: str) -> str:
    seen = next((c for c in _SKY if c in w.conditions), None)
    if seen is not None:
        return tw(f"wx_c_{seen}", lang)
    mm = w.precipitation_mm or 0.0
    if mm >= HEAVY_PRECIP_MM:
        return t("wx_heavy", lang, p=f"{mm:.1f}")
    return s("ld_precip", lang) if mm >= TRACE_PRECIP_MM else ""


def _air(w: WeatherInfo, lang: str) -> str:
    if w.user_hint == "smog":
        return t("wx_hint_smog", lang)
    if "nmu" in w.conditions:
        return s("ld_nmu", lang)
    if w.pm25 is not None and w.pm25 > BAD_PM25:
        return s("ld_pm", lang, pm=f"{w.pm25:.0f}")
    return s("ld_haze", lang) if "smog" in w.conditions else ""


def conditions(
    res: Result, lang: str, *, show_temp: bool, later: bool = False
) -> tuple[list[str], bool]:
    """(the clauses about Astana now that matter for THIS request, whether any of them changes what is offered): the
    cold, the sky and the dark for a walk; the air (НМУ) only for a stated outdoor wish; the official notice for a walk
    or a drive; a holiday always (it moves the hours). At most MAX_CLAUSES of them: one short clause, not a weather
    report before every café. The temperature is said only for the real present (or a weather set by hand)."""
    w = res.weather
    local = to_local_naive(res.when)
    intent, f = res.intent.intent, res.retrieval.filters
    walk = (
        bool(set(intent.wished) & OUTDOOR_KINDS) or f.outdoor_request
    )  # a walk the person named, not a default
    clauses: list[str] = []
    drives = False
    if w is not None:
        drives = w.adverse or w.air_bad
        if w.user_hint and w.user_hint != "smog":
            clauses.append(t(f"wx_hint_{w.user_hint}", lang))  # the person's own words or setting
        sky = _sky(w, lang)
        if walk and show_temp and (temp := _temperature(w, lang)):
            clauses.append(temp)
        if walk and sky:
            clauses.append(sky)
        if f.outdoor_request and (air := _air(w, lang)):
            clauses.append(air)
        notice = any(x.kind == "storm" and x.active for x in w.warnings)
        if (walk or intent.mode == "car") and notice and not sky:
            # the official notice, by what it warns of («ожидается туман»), not as a «шторм»; a fog notice is said
            # as advice only: it is no harsh weather (kazhydromet.harsh_notice), so nothing moves indoors
            what = warned(w, lang)
            clauses.append(s("ld_storm_what", lang, what=what) if what else s("ld_storm", lang))
    if (
        walk and w is not None and is_dark(w, local)
    ):  # «стемнеет» for a later hour, «уже темно» for now
        clauses.append(
            s("ld_dark_later" if later else "ld_dark", lang)
        )  # `later`: an asked hour ahead
        drives = True
    clauses = clauses[:MAX_CLAUSES]
    if name := holiday_ru(
        local.date()
    ):  # the asked day's holiday, said as that day («в воскресенье»), never «сегодня»
        days = (local.date() - to_local_naive(local_now()).date()).days
        holiday = holiday_name(name, lang)
        if days <= 0:
            clauses.append(s("ld_holiday", lang, name=holiday))
        else:
            day = s("w_tomorrow", lang) if days == 1 else weekday_on(local.weekday(), lang)
            clauses.append(s("ld_holiday_on", lang, name=holiday, day=day))
    return clauses, drives


def honest_gaps(
    res: Result, recs: list[Recommendation], lang: str, *, now: bool
) -> tuple[str, str]:
    """(said before the answer, said after it): a kids' place asked for that the data has none of, Kazakh food no
    shown place is marked with; and (`now`), when every card's hours are unknown, one short clause after it that more
    places nearby are closed now («(ещё 2 места рядом сейчас закрыты)»): the cards keep their state, the closed ones are
    not offered."""
    intent, pois = res.intent.intent, [r.poi for r in recs]
    out = [s(f"kids_none_{gap}", lang)] if (gap := kids_gap(intent, pois)) else []
    if intent.local_food and not any(local_food_signal(p) for p in pois):
        out.append(s("local_food_none", lang))
    n = res.retrieval.filters.excluded_closed
    quiet = (
        bool(set(intent.wished) & OUTDOOR_KINDS) or errand(intent.wished or intent.categories)
    )  # a park keeps no hours; «ещё 5 мест закрыты» under a toilet or a pharmacy names nothing to go to
    if not (now and n and recs and not quiet and all(r.hours_state == "unknown" for r in recs)):
        return " ".join(out), ""
    one = n % 10 == 1 and n % 100 != 11
    words = {
        "ru": {
            "places": plural_ru(n, "место", "места", "мест"),
            "closed": "закрыто" if one else "закрыты",
        },
        "en": {"places": "place" if n == 1 else "places", "closed": "is" if n == 1 else "are"},
    }.get(lang, {})
    return " ".join(out), s("known_hours_closed", lang, n=n, **words)


def notice_matters(res: Result) -> bool:
    """Is the official weather notice worth its own line under this answer: a walk the person asked for (an outdoor kind
    they named) or a drive (walks.dialog); never under a café, a bar or a toilet found while it is in force."""
    intent = res.intent.intent
    return (
        bool(set(intent.wished) & OUTDOOR_KINDS)
        or res.retrieval.filters.outdoor_request
        or intent.mode == "car"
    )


def _walk_advice(res: Result, shown: set[str], lang: str) -> str:
    """The conditions never replace a walk the person asked for: they are said as advice. The air or the weather: keep
    it short; the dark: the places beside streets the data tag lit come first (said only when one of them is shown)."""
    parts: list[str] = []
    w = res.weather
    if w is not None and (w.adverse or w.air_bad):
        parts.append(s("ld_walk_short", lang))
    lit = any(LIT_NEAR in c.reasons for c in res.retrieval.candidates if c.poi.id in shown)
    if res.retrieval.filters.dark and lit:
        parts.append(s("ld_walk_lit", lang))
    return "; ".join(parts)


def _tail(res: Result, drives: bool, lang: str, shown: set[str]) -> str:
    """What the conditions did to the choice: indoor places first (a request with no stated wish), or, for the outdoor
    place the person asked for, only advice."""
    if not drives:
        return ""
    f = res.retrieval.filters
    if f.outdoor_request:
        return _walk_advice(res, shown, lang)
    substituted = any(r.padding == "substituted" for r in res.recs)
    return s("ld_indoor", lang) if f.excluded_outdoor or substituted else ""


def _kind_word(poi_kind: str, lang: str) -> str:
    return category_name(poi_kind, lang).split(" / ")[0]


def template_want(res: Result, lang: str) -> str:
    """What the request is about, in the person's own terms, when the model gave no usable paraphrase: «Вы ищете, где
    прогуляться» for a walk, «Вы ищете: кафе» for a kind. It never names what the system put in its place: a kind a
    mood, a default («куда сходить») or a back-fill added is not the person's word, so it is not said."""
    intent = res.intent.intent
    said = match(res.query)
    if intent.wished:
        if intent.pets and said.has("dog_walk"):
            return s("ld_want_dog", lang)
        if said.has("stroll"):
            return s("ld_want_stroll", lang)
    kinds = [c for c in intent.wished if c in intent.categories and c != "other"][:_MAX_WANT_KINDS]
    words = [
        _kind_word(c, lang) for c in kinds
    ]  # never the keywords: they are the lexicon's stems («необычн»)
    return s("ld_want", lang, what=", ".join(words)) if words else ""


def guard_clause(res: Result, lang: str) -> str:
    """A kind the person asked for that a safety rule left out, said in one sentence instead of being named as the
    wish: bars and alcohol for a minor, bars under «без алкоголя». Empty when nothing the person asked for was dropped."""
    if not _BAR_CONCEPTS & set(match(res.query).active):
        return ""
    if res.intent.intent.minor:
        return s("ld_guard_minor", lang)
    return s("ld_guard_no_alcohol", lang) if res.constraints.no_alcohol else ""


def _way(kind: str, name: str, lang: str) -> str:
    return s(f"ld_way_{kind}", lang, name=name)


def pick_clause(
    place: Place, lang: str, *, anchor: str = "", way: tuple[str, str] | None = None
) -> str:
    """«советую «X», 6 мин пешком, открыто до 02:00 — и как раз по пути домой»."""
    walk = place.walk.text + (" " + s("ld_from", lang, bm=anchor) if anchor else "")
    tail = ", " + lower_first(place.hours.text) if place.hours.text else ""
    if way is not None:
        tail += " — " + _way(*way, lang)
    return s("ld_pick", lang, name=place.name, walk=walk, tail=tail)


def conditions_line(res: Result, lang: str, *, show_temp: bool, later: bool = False) -> str:
    """The clauses about Astana now as one line (the weather, the air, the dark): what a dialogue says once."""
    return ", ".join(conditions(res, lang, show_temp=show_temp, later=later)[0])


def own_opening(res: Result, places: list[Place], anchor: str, way: tuple[str, str] | None) -> str:
    """The model's own opening when it can be the lead: it names the first card and the person's wish, and no bookmark
    («рядом с домом», «по пути») is in play (the model does not know them)."""
    text = res.lead_text
    if not text or anchor or way is not None or places[0].name.lower() not in text.lower():
        return ""
    return text if names_the_wish(text, res.intent.intent) else ""


def by_the_clock(text: str, res: Result) -> str:
    """The model's words, unless they say «ночью» while the asked time is day: «го пожрать, щас уже поздно» at 11:30
    is a meal now, and the lead then takes the template's words."""
    hour = to_local_naive(res.when).hour
    return "" if not text or (DAY_START <= hour < DAY_END and _NIGHT_WORDS.search(text)) else text


def errand_pick(
    res: Result,
    places: list[Place],
    lang: str,
    *,
    anchor: str = "",
    way: tuple[str, str] | None = None,
) -> str:
    """«Ближайшая аптека — «Улы Дала», 14 мин пешком, часы неизвестны»: an errand is said by what it is, never as «Вы
    ищете: аптека — советую …». A first card the data confirm open is «ближайшая открытая» (a nearer one may have
    unknown hours, wishes.errand_order); with none confirmed open the first card is the nearest. '' for any other
    request, a bookmark or a way in play (their own lead), or a first card of another kind."""
    intent, first = res.intent.intent, places[0]
    if not errand(intent.wished or intent.categories) or anchor or way is not None:
        return ""
    poi = next((r.poi for r in res.recs if r.poi.id == first.id), None)
    kind = next(  # «Ближайший банкомат», «Ближайшая стоматология»: what the record is, not only its category
        (k for k in _ERRAND_SUBKINDS if poi is not None and of_subkind(poi, k)), first.category
    )
    if first.category not in ERRANDS:
        return ""
    if rest := subkind_missing(intent, poi) if poi is not None else "":
        # «Стоматологий рядом нет — ближайшая: …» was said before: this card is the nearest of the rest, one lead
        what = s(f"ld_errand_rest_{rest}", lang)
    else:
        what = s(
            f"ld_errand_open_{kind}" if first.hours.state == "open" else f"ld_errand_{kind}", lang
        )
    tail = ", " + lower_first(first.hours.text) if first.hours.text else ""
    return s("ld_errand_pick", lang, what=what, name=first.name, walk=first.walk.text, tail=tail)


def lead(
    res: Result,
    places: list[Place],
    lang: str,
    *,
    show_temp: bool,
    anchor: str = "",
    way: tuple[str, str] | None = None,
    taken: str = "",
    told: str = "",
    later: bool = False,
) -> str:
    """The lead of a fresh search: the model's own opening when code can stand behind it; else conditions, what the
    person wants, the recommendation and how many more are below. The conditions are said once per dialogue (`told`:
    the line said before), not before every answer; (`taken`) once, what of the saved settings this answer used."""
    guard = guard_clause(res, lang)
    nearest = errand_pick(res, places, lang, anchor=anchor, way=way)
    if not nearest and (own := by_the_clock(own_opening(res, places, anchor, way), res)):
        text = f"{guard} {own}" if guard else own
        return f"{text} {taken}" if taken else text
    clauses, drives = conditions(res, lang, show_temp=show_temp, later=later)
    if ", ".join(clauses) == told:
        clauses = []  # said in this dialogue already: the answer goes straight to the places
    if clauses and (tail := _tail(res, drives, lang, {p.id for p in places})):
        clauses.append(tail)
    first = ", ".join(clauses)
    want = "" if guard or nearest else by_the_clock(res.lead_want, res) or template_want(res, lang)
    pick = nearest or pick_clause(places[0], lang, anchor=anchor, way=way)
    rest = len(places) - 1
    more = s("ld_more", lang, more=s(f"more_{rest}", lang)) if rest else ""
    second = (f"{up(want)} — {pick}" if want else up(pick)) + more + "."
    text = f"{up(first)}. {second}" if first else second
    text = f"{guard} {text}" if guard else text
    return f"{text} {taken}" if taken else text


def _marked(some: str, none: str, marked: int, checked: int, lang: str) -> str:
    """«отмечен у 2 из 14 мест рядом» or the honest «в данных ничего нет»: a count of the records, never a promise."""
    if marked:
        return s(some, lang, n=marked, m=checked)
    return s(none, lang)


def _kinds(kinds: list[str], lang: str) -> str:
    return ", ".join(_kind_word(c, lang) for c in kinds)


def taken_into_account(res: Result, profile: Profile | None, lang: str) -> str:
    """«Учтены ваши настройки: халяль (в данных отмечен у 1 из 24 мест рядом, их ставлю первыми), без алкоголя.» The
    saved settings that changed THIS answer, each said once, with the real count where the data are thin. A setting that
    did nothing here (halal for a walk, a pace for «ещё») is not mentioned: nothing is claimed that did not happen. An
    errand (a pharmacy, an ATM, a toilet) is the nearest place that works: a child, quiet, a budget, the cold or the
    words about oneself change nothing there, so only the step-free entrance, the pace and «не показывать» are said."""
    if profile is None or res.continued:
        return ""
    f = res.retrieval.filters
    chore = errand(res.intent.intent.wished or res.intent.intent.categories)
    applied = set(res.profile_applied) - (
        {"with_kids", "quiet", "budget", "cold_tolerance"} if chore else set()
    )
    shown = {r.poi.category for r in res.recs}
    items: list[str] = []
    if "with_kids" in applied:
        band = ", ".join(profile.kids_age_bands)
        items.append(s("pl_with_kids_age", lang, band=band) if band else s("pl_with_kids", lang))
    if "mobility" in applied:
        note = _marked(
            "pl_step_some", "pl_step_none", f.step_free_marked, f.step_free_checked, lang
        )
        items.append(
            f"{s('pl_mobility', lang)} — {note}" if f.step_free_checked else s("pl_mobility", lang)
        )
    if "quiet" in applied:
        items.append(s("pl_quiet", lang))
    if "budget" in applied:
        items.append(s("pl_budget_low", lang))
    if "halal" in applied and f.halal_checked and shown & {"restaurant", "cafe", "fast_food"}:
        note = _marked("pl_halal_some", "pl_halal_none", f.halal_marked, f.halal_checked, lang)
        items.append(f"{s('pl_halal', lang)} — {note}")
    if "no_alcohol" in applied:
        n = f.excluded_alcohol
        items.append(s("pl_no_alcohol_n", lang, n=n) if n else s("pl_no_alcohol", lang))
    if "walk_pace" in applied and profile.walk_pace != "normal":
        items.append(s(f"pl_pace_{profile.walk_pace}", lang))
    if "cold_tolerance" in applied:
        items.append(s(f"pl_cold_{profile.cold_tolerance}", lang))
    if res.constraints.avoid and f.excluded_avoid:
        items.append(s("pl_avoid", lang, kinds=_kinds(list(res.constraints.avoid), lang)))
    loved = [c for c in profile.liked if c in shown and not res.intent.intent.wished]
    if loved:
        items.append(s("pl_liked", lang, kinds=_kinds(loved, lang)))
    if profile.about and res.generation == "llm" and not chore:
        items.append(s("pl_about", lang))
    return s("pl_wrap", lang, items="; ".join(items)) if items else ""


def follow_up_lead(
    places: list[Place],
    change: str,
    lang: str,
    *,
    anchor: str = "",
    way: tuple[str, str] | None = None,
) -> str:
    """The lead of a change of the same request («Поближе: …»): only the new recommendation."""
    rest = len(places) - 1
    pick = pick_clause(places[0], lang, anchor=anchor, way=way)
    more = s("ld_more", lang, more=s(f"more_{rest}", lang)) if rest else ""
    return (f"{change}: {pick}" if change else up(pick)) + more + "."
