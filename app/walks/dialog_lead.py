"""The lead of an answer (`Turn.reply` of a search): one or two sentences in the order the owner asked for — the
conditions in Astana right now, what the person wants, the recommendation. Every fact in it (temperature, air, hours,
minutes, names) is inserted by code from a field of the data; the model supplies only the paraphrase of the wish
(`Result.lead_want`, checked in walks.generate), and the template composes that too when there is none."""

from __future__ import annotations

from .dialog_strings import s
from .dialog_types import Place
from .holidays import holiday_name as holiday_ru
from .hours import to_local_naive
from .i18n import category_name, holiday_name, t
from .i18n_weather import tw
from .lexicon import match
from .lexicon_concepts import CONCEPTS
from .models import Result, WeatherInfo
from .profile import Profile
from .shelter import LIT_NEAR
from .sun import is_dark
from .weather import BAD_PM25, HEAVY_PRECIP_MM

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


def conditions(res: Result, lang: str, *, show_temp: bool) -> tuple[list[str], bool]:
    """(the clauses about Astana now, whether any of them changes what is offered: weather, air or darkness). The
    temperature is said only for the real present (or a weather the user set by hand), never for another hour."""
    w = res.weather
    local = to_local_naive(res.when)
    clauses: list[str] = []
    drives = False
    if w is not None:
        if w.user_hint and w.user_hint != "smog":
            clauses.append(t(f"wx_hint_{w.user_hint}", lang))
        if show_temp and (temp := _temperature(w, lang)):
            clauses.append(temp)
        if sky := _sky(w, lang):
            clauses.append(sky)
        if air := _air(w, lang):
            clauses.append(air)
        drives = w.adverse or w.air_bad
        if "storm_warning" in w.conditions and not sky:
            clauses.append(
                s("ld_storm", lang)
            )  # the official notice, said once; its own line keeps the link
    if w is not None and is_dark(w, local):
        clauses.append(s("ld_dark", lang))
        drives = True
    if name := holiday_ru(local.date()):
        clauses.append(s("ld_holiday", lang, name=holiday_name(name, lang)))
    return clauses, drives


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


def lead(
    res: Result,
    places: list[Place],
    lang: str,
    *,
    show_temp: bool,
    anchor: str = "",
    way: tuple[str, str] | None = None,
    taken: str = "",
) -> str:
    """The lead of a fresh search: conditions, what the person wants, the recommendation, how many more are below, and
    (`taken`) once, what of the person's saved settings this answer took into account."""
    clauses, drives = conditions(res, lang, show_temp=show_temp)
    if clauses and (tail := _tail(res, drives, lang, {p.id for p in places})):
        clauses.append(tail)
    first = ", ".join(clauses)
    guard = guard_clause(res, lang)
    want = "" if guard else res.lead_want or template_want(res, lang)
    pick = pick_clause(places[0], lang, anchor=anchor, way=way)
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
    did nothing here (halal for a walk, a pace for «ещё») is not mentioned: nothing is claimed that did not happen."""
    if profile is None or res.continued:
        return ""
    f = res.retrieval.filters
    applied = set(res.profile_applied)
    shown = {r.poi.category for r in res.recs}
    items: list[str] = []
    if "with_kids" in applied:
        band = profile.kids_age_band
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
    if profile.about and res.generation == "llm":
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
