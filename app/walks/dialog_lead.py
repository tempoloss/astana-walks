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
from .models import Result, WeatherInfo
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
    if w is not None and is_dark(w, local):
        clauses.append(s("ld_dark", lang))
        drives = True
    if name := holiday_ru(local.date()):
        clauses.append(s("ld_holiday", lang, name=holiday_name(name, lang)))
    return clauses, drives


def _tail(res: Result, drives: bool, lang: str) -> str:
    """What the conditions did to the choice: indoor places first, or the outdoor place kept at the user's request."""
    if not drives:
        return ""
    f = res.retrieval.filters
    if f.outdoor_request:
        return s("ld_outdoor_kept", lang)
    substituted = any(r.padding == "substituted" for r in res.recs)
    return s("ld_indoor", lang) if f.excluded_outdoor or substituted else ""


def _kind_word(poi_kind: str, lang: str) -> str:
    return category_name(poi_kind, lang).split(" / ")[0]


def template_want(res: Result, lang: str) -> str:
    """What the request is about, from the intent, when the model gave no usable paraphrase: «Вы ищете: кафе»."""
    intent = res.intent.intent
    kinds = [c for c in intent.categories if c != "other"][:_MAX_WANT_KINDS]
    words = [_kind_word(c, lang) for c in kinds] or list(
        intent.free_text_keywords[:_MAX_WANT_KINDS]
    )
    return s("ld_want", lang, what=", ".join(words)) if words else ""


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
) -> str:
    """The lead of a fresh search: conditions, what the person wants, the recommendation, how many more are below."""
    clauses, drives = conditions(res, lang, show_temp=show_temp)
    if clauses and (tail := _tail(res, drives, lang)):
        clauses.append(tail)
    first = ", ".join(clauses)
    want = res.lead_want or template_want(res, lang)
    pick = pick_clause(places[0], lang, anchor=anchor, way=way)
    rest = len(places) - 1
    more = s("ld_more", lang, more=s(f"more_{rest}", lang)) if rest else ""
    second = (f"{up(want)} — {pick}" if want else up(pick)) + more + "."
    return f"{up(first)}. {second}" if first else second


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
