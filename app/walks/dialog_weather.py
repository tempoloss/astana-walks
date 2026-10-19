"""A question about the weather («какая погода», «а че там с погодой», «what's the weather tomorrow, what should I
wear», «ауа райы қандай», «что надеть»): answered from the data the service already holds, never by a search. For the
present: the airport observation with the MET Norway forecast beside it; for a later time (`AskedTime`): the MET Norway
series at that hour. The active Kazhydromet notice for Astana is said as it is, with its link. The places the person was
shown stay on the map (`WeatherAnswer.places`); nothing is searched, nothing is cleared."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from . import metno
from .dialog_extras import weather_notice
from .dialog_lead import signed
from .dialog_nlu import tokens
from .dialog_place import place_from_poi
from .dialog_strings import s
from .dialog_types import DialogState, Notice, Place, PlaceAnswer, Source, Walk
from .dialog_when import AskedTime, indoors
from .hours import TZ, to_local_naive
from .i18n_weather import tw
from .intent import parse_rules
from .lexicon import match
from .models import POI, WeatherInfo, WeatherWarning
from .outing import is_outing
from .weather import attribution, make_weather

MAX_WORDS = 14
FORECAST_REACH = timedelta(
    hours=3
)  # the series is hourly for days, then every six hours: the nearest entry
NEAR_NOW = timedelta(minutes=90)  # a time this close to the present is the present
FEELS_GAP_C = 3
RAIN_MM = 0.1
WEATHER_CONCEPTS = frozenset(  # the weather's own words are the question, never a wish for a place
    {"shelter_from_weather", "kids", "kids_specific", "wx_cold", "wx_heat", "wx_rain", "wx_smog"}
)
COMPARE_SAME_C = 1.0  # a forecast this close to the present is «about the same»
# «будет теплее?», «жылырақ па», «will it be warmer»: the weather asked about against the present
_COMPARE_WORDS = (
    r"\b(?:тепле[ея]|холодне[ея]|потепле\w*|похолода\w*|теплой|холодной)\b|"
    r"\bжылыра[кқ]\b|\bсуыгыра[кқ]\b|\b(?:warmer|colder|cooler|hotter)\b"
)
_COMPARE = re.compile(_COMPARE_WORDS)
# words of a weather question, on the text as `tokens` reads it (lower case, kk letters as their ru look-alikes)
_ASKS = re.compile(
    r"\bпогод\w*|\bпрогноз\w*|\bтемператур\w*|\bградус\w*|\bчто (?:мне )?(?:надеть|одеть)\b|\bво что (?:мне )?одеть\w*|"
    r"\bкак (?:мне )?одеть\w*|\bчто (?:мне )?(?:надо )?надеть\b|\bзонт\w*|\bхолодно ли\b|\bтепло ли\b|"
    r"\bбудет ли (?:дождь|снег)\b|\b(?:дождь|снег) будет\b|\bна улице (?:(?:щас|сейчас|сегодня|завтра|вечером|утром) )*(?:холодно|тепло|жарко|мороз|дожд|снег|ветрен|скользко)\w*|"
    r"\bне (?:холодно|жарко) ли\b|\bwill it be (?:cold|warm|hot|rainy|snowy)\b|\bis it (?:cold|warm|hot) outside\b|\bсуык па\b|\bыстык па\b|"
    r"\bкиинд\w*|\bауа ра[йи]ы\b|\bауара[йи]ы\b|\bжанбыр жауа\b|\bкар жауа\b|\bне киемин\b|\bне кию\b|\bкандай ауа\b|"
    r"\bweather\b|\bforecast\b|\btemperature\b|\bwhat (?:should i|to|do i) wear\b|\bwhat shall i wear\b|"
    r"\bwill it (?:rain|snow)\b|\bgoing to (?:rain|snow)\b|\bhow (?:cold|warm|hot)\b|\bis it (?:cold|warm|hot|raining|snowing)\b|"
    r"\bumbrella\b|\bwear\b|" + _COMPARE_WORDS
)
_WEAR = re.compile(
    r"\bчто (?:мне )?(?:надеть|одеть)\b|\bво что (?:мне )?одеть\w*|\bкак (?:мне )?одеть\w*|\bчто (?:мне )?(?:надо )?надеть\b|"
    r"\bне киемин\b|\bне кию\b|\bкиинд\w*|\bwhat (?:should i|to|do i|shall i) wear\b|\bwear\b|\bзонт\w*|\bumbrella\b|"
    r"\bмне идти\b|\bидти ли\b|\bстоит ли идти\b|\bshould i go\b"
)
# a message that asks WHERE to go or WHAT to do is a search for a place, whatever the weather is in it
_PLACE_ASK = re.compile(
    r"\bкуда\b|\bгде\b|\bчем заняться\b|\bчто делать\b|\bwhere\b|\bwhat to do\b|\bwhat can we do\b|\bқайда\b|\bкайда\b"
)


@dataclass
class WeatherAnswer:
    reply: str
    answers: list[PlaceAnswer]
    places: list[Place] = field(default_factory=list)
    notices: list[Notice] = field(default_factory=list)


def asks_weather(text: str) -> bool:
    """The message asks about the weather itself: a weather word in a short message that names no kind of place and
    does not ask where to go."""
    norm = " ".join(tokens(text))
    if (
        not norm
        or len(norm.split()) > MAX_WORDS
        or not _ASKS.search(norm)
        or _PLACE_ASK.search(norm)
    ):
        return False
    if is_outing(text):
        return False
    intent = parse_rules(text).intent
    # a wish of its own (a kind, a sight, a mood such as «турист») makes it a search; the weather's own words
    # («холодно», «теплее») and the child to dress are no wish for a place
    own = set(match(text).active) - WEATHER_CONCEPTS
    return not (intent.wished or own or intent.landmark_refs or intent.info_about)


def asks_clothes(text: str) -> bool:
    return bool(_WEAR.search(" ".join(tokens(text))))


# ------------------------------------------------------------------ the forecast of a later hour


@dataclass(frozen=True)
class Hourly:
    temperature_c: float
    apparent_c: float
    wind_kmh: float
    precipitation_mm: float
    cloud_pct: float | None
    symbol: str  # clear / partly / cloud / fog / rain / sleet / snow / thunder, or ''


def forecast_at(moment: datetime) -> Hourly | None:
    """The MET Norway entry nearest to the local time `moment`, from the series already in memory (the refresh
    thread of the server, or the first weather request, filled it); None when there is none that close."""
    entries = metno._state.entries  # the series lives there; reading it never calls the network
    if not entries:
        return None
    utc = to_local_naive(moment).replace(tzinfo=TZ).astimezone(UTC)
    entry = min(entries, key=lambda e: abs(e.time - utc))
    if abs(entry.time - utc) > FORECAST_REACH:
        return None
    fc = metno.pick([entry], entry.time)
    if fc is None:
        return None
    return Hourly(
        fc.temperature_c,
        fc.apparent_c,
        fc.wind_kmh,
        fc.precipitation_mm,
        fc.cloud_pct,
        metno.symbol_kind(entry.symbol),
    )


# ------------------------------------------------------------------ wording


def _capital(text: str) -> str:
    return text[:1].upper() + text[1:]


def _deg(value: float) -> str:
    return f"{signed(value)} °C"


def _temp(temperature: float, apparent: float | None, lang: str) -> str:
    out = _deg(temperature)
    if apparent is not None and abs(apparent - temperature) >= FEELS_GAP_C:
        out += ", " + s("wx_feels", lang, f=_deg(apparent))
    return out


def _sky(kind: str, cloud_pct: float | None, lang: str) -> str:
    """The sky in a word: the kind the series names, else what the cloud cover says."""
    if kind:
        return s(f"wx_k_{kind}", lang)
    if cloud_pct is None:
        return ""
    return s(
        "wx_k_clear" if cloud_pct < 25 else "wx_k_partly" if cloud_pct < 70 else "wx_k_cloud", lang
    )


def _wind(kmh: float | None, lang: str) -> str:
    return s("wx_wind", lang, v=round(kmh)) if kmh is not None else ""


def _rain(mm: float | None, lang: str) -> str:
    if mm is None:
        return ""
    return s("wx_rain_mm", lang, mm=f"{mm:.1f}") if mm >= RAIN_MM else s("wx_dry", lang)


def clothes(apparent: float, wet: bool, lang: str) -> str:
    """What to put on, by the temperature it feels like (a rule of thumb, said as one): a short phrase."""
    band = (
        "vcold"
        if apparent <= -25
        else "cold"
        if apparent <= -10
        else "chilly"
        if apparent <= 0
        else "cool"
        if apparent <= 10
        else "mild"
        if apparent <= 18
        else "warm"
        if apparent <= 26
        else "hot"
    )
    out = s(f"wx_wear_{band}", lang)
    return f"{out}; {s('wx_wear_wet', lang)}" if wet else out


def _now_clause(w: WeatherInfo, lang: str) -> tuple[str, float | None, bool]:
    """(the sentence about the present, the temperature it feels like, whether it is wet) from the observation and the
    forecast the conditions carry; '' when the service holds no temperature at all."""
    if w.temperature_c is None:
        return "", None, False
    kind = w.precip_now or ("fog" if "fog" in w.conditions else "")
    sky = _sky(kind, w.cloud_pct, lang)
    parts = [
        s("wx_now", lang, t=_temp(w.temperature_c, w.apparent_c, lang)),
        sky,
        _wind(w.wind_kmh, lang),
        _rain(w.precipitation_mm, lang),
    ]
    wet = bool(w.precip_now) or (w.precipitation_mm or 0.0) >= RAIN_MM
    return ", ".join(p for p in parts if p) + ".", w.apparent_c, wet


def _source(w: WeatherInfo | None, lang: str, *, forecast: bool) -> Source:
    if not forecast and w is not None and w.source == "metar" and w.observed_at:
        return Source(label=attribution(w, lang) or tw("fc_attr", lang), url=None)
    return Source(label=tw("fc_attr", lang), url=metno.URL.split("?")[0])


def compare_clause(then_c: float, now_c: float, lang: str) -> str:
    """The forecast's temperature against the present one, in the same degrees the answer shows: each side is rounded
    once (`_deg`) and the difference is of those two numbers, so «+4 … сейчас +1» is always «на 3 °C», in every language."""
    diff = round(then_c) - round(now_c)
    if abs(diff) < COMPARE_SAME_C:
        return s("wx_cmp_same", lang, a=_deg(now_c))
    return s("wx_cmp_warmer" if diff > 0 else "wx_cmp_colder", lang, d=abs(diff), a=_deg(now_c))


def _compare(text: str, weather: WeatherInfo, asked: AskedTime, lang: str) -> str:
    """«а завтра днём будет теплее?»: the forecast of that time against the present observation, in degrees; says so
    when either side is missing from the data."""
    if not _COMPARE.search(" ".join(tokens(text))):
        return ""
    hour = forecast_at(asked.moment)
    if hour is None:
        return ""
    if weather.temperature_c is None:
        return s("wx_cmp_unknown", lang)
    return compare_clause(hour.temperature_c, weather.temperature_c, lang)


def _later_clause(asked: AskedTime, hour: Hourly, lang: str) -> tuple[str, float, bool]:
    parts = [
        s(
            "wx_at",
            lang,
            when=_capital(asked.label(lang)),
            t=_temp(hour.temperature_c, hour.apparent_c, lang),
        ),
        _sky(hour.symbol, hour.cloud_pct, lang),
        _wind(hour.wind_kmh, lang),
        _rain(hour.precipitation_mm, lang),
    ]
    wet = hour.precipitation_mm >= RAIN_MM or hour.symbol in ("rain", "sleet", "snow", "thunder")
    return ", ".join(p for p in parts if p) + ".", hour.apparent_c, wet


# ------------------------------------------------------------------ the answer


def kept_places(
    state: DialogState, pois: list[POI] | None, when: datetime, mode: str, lang: str
) -> list[Place]:
    """The places the person was shown, as they were (the same ids, so the map keeps them): rebuilt from the dataset
    with the way the search measured."""
    by_id = {p.id: p for p in pois or []}
    out: list[Place] = []
    for i, sp in enumerate(state.shown):
        poi = by_id.get(sp.id)
        if poi is None:
            continue
        place = place_from_poi(
            poi, origin=(state.lat, state.lon), mode=mode, when=when, lang=lang, what=sp.what
        )
        place.walk = Walk(
            minutes=sp.minutes,
            distance_m=sp.distance_m,
            method="estimate",
            mode=sp.mode,
            text=s(f"walk_{sp.mode}", lang, n=sp.minutes),
        )
        place.primary = i == 0
        out.append(place)
    return out


def weather_answer(
    state: DialogState,
    text: str,
    lang: str,
    *,
    weather: WeatherInfo | None,
    asked: AskedTime | None,
    pois: list[POI] | None,
    when: datetime,
    mode: str = "walk",
) -> WeatherAnswer:
    """The reply to a question about the weather: the present, or the forecast of the asked time; clothes when asked."""
    later = asked is not None and asked.moment - asked.since > NEAR_NOW
    apparent: float | None = None
    wet = False
    if later and asked is not None:
        hour = forecast_at(asked.moment)
        if hour is None:
            body = s("wx_no_forecast", lang, when=asked.label(lang))
            source = None
        else:
            body, apparent, wet = _later_clause(asked, hour, lang)
            source = _source(weather, lang, forecast=True)
    else:
        body, apparent, wet = (
            _now_clause(weather, lang) if weather is not None else ("", None, False)
        )
        if not body:
            body = s("wx_no_data", lang)
        source = _source(weather, lang, forecast=False) if apparent is not None else None
    if (
        later
        and asked is not None
        and weather is not None
        and (cmp := _compare(text, weather, asked, lang))
    ):
        body = f"{body} {cmp}"
    if apparent is not None and asks_clothes(text):
        body = f"{body} {s('wx_wear', lang, what=clothes(apparent, wet, lang))}"
    answers = [
        PlaceAnswer(
            place_id="weather",
            name=s("wx_name", lang),
            topic="weather",
            text=body,
            known=apparent is not None,
            source=source,
        )
    ]
    notices: list[Notice] = []
    if (notice := weather_notice(weather, lang)) is not None:
        notices.append(notice)
        answers.append(
            PlaceAnswer(
                place_id="weather",
                name=s("wx_name", lang),
                topic="weather_notice",
                text=notice.text,
                source=notice.source,
            )
        )
    reply = " ".join(a.text for a in answers)
    return WeatherAnswer(
        reply=reply,
        answers=answers,
        places=kept_places(state, pois, when, mode, lang),
        notices=notices,
    )


COLD_C = 5.0  # the temperature it feels like at or under which the street is «cold»


def cold_verdict(
    weather: WeatherInfo | None, asked: AskedTime | None
) -> tuple[bool | None, str, float | None]:
    """(is it cold, the temperature in words, the temperature it feels like) at the asked time, from the data we hold:
    the present observation, or the MET Norway entry of that hour; (None, '', None) when there is none."""
    if asked is not None and asked.moment - asked.since > NEAR_NOW:
        hour = forecast_at(asked.moment)
        if hour is None:
            return None, "", None
        return hour.apparent_c <= COLD_C, _deg(hour.temperature_c), hour.apparent_c
    if weather is None or weather.temperature_c is None:
        return None, "", None
    feels = weather.apparent_c if weather.apparent_c is not None else weather.temperature_c
    return feels <= COLD_C, _deg(weather.temperature_c), feels


def condition(
    weather: WeatherInfo | None,
    asked: AskedTime | None,
    lang: str,
    rest: str,
    *,
    temp_said: bool = False,
) -> tuple[str, str]:
    """«суық емес болса саябаққа барайық»: (the sentence that says whether it is cold at the asked time, the request to
    search). Not cold: the street as asked; cold: the same request indoors; no temperature in the data: as asked, said.
    `temp_said`: the lead of the answer already gives the temperature, the sentence only says cold or not."""
    cold, temp, _ = cold_verdict(weather, asked)
    if cold is None:
        return s("cond_unknown", lang), rest
    if asked is not None and asked.moment - asked.since > NEAR_NOW:
        now = s("cond_at", lang, t=temp)  # the asked time, never «now»
    else:
        now = "" if temp_said else s("cond_now", lang, t=temp)
    text = f"{now}{s('cond_cold' if cold else 'cond_warm', lang)}"
    return text[:1].upper() + text[1:], indoors(rest, lang) if cold else rest


def _warning_at(w: WeatherWarning, moment: datetime) -> WeatherWarning:
    """The notice as it stands at `moment`: active when its own period covers that time."""
    try:
        start, end = datetime.fromisoformat(w.valid_from), datetime.fromisoformat(w.valid_to)
    except ValueError:
        return w.model_copy(update={"active": False})
    local = to_local_naive(moment).replace(tzinfo=start.tzinfo)
    return w.model_copy(update={"active": start <= local <= end})


def weather_at(weather: WeatherInfo | None, asked: AskedTime | None) -> WeatherInfo | None:
    """The conditions of a request for a LATER time («завтра днём»): the MET Norway entry of that hour in place of the
    present observation, and the notices that are in force then; the present weather is no answer for tomorrow. The
    weather as it is when no later time was asked, or when the series has no entry that close (then nothing is
    claimed: no temperature, no adverse verdict)."""
    if weather is None or asked is None or asked.moment - asked.since <= NEAR_NOW:
        return weather
    hour = forecast_at(asked.moment)
    warnings = [_warning_at(x, asked.moment) for x in weather.warnings]
    if hour is None:
        return make_weather(warnings=warnings, fetched_at=weather.fetched_at, source="met-no")
    return make_weather(
        hour.temperature_c,
        hour.apparent_c,
        hour.wind_kmh,
        hour.precipitation_mm,
        cloud_pct=hour.cloud_pct,
        forecast_used=True,
        fetched_at=weather.fetched_at,
        warnings=warnings,
    )
