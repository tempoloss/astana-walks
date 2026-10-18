"""Wording of the measured-weather layer (walks.weather): the adverse conditions read from the airport observation or
from a Kazhydromet warning, the attribution line and the source details. An entry is a tuple (kk, ru, en) like
walks.i18n.STRINGS; this table has its own lookup `tw` so the shared table stays untouched. The Russian wording is the
one kept in `WeatherInfo.reason` / `air_reason`."""

from __future__ import annotations

from .i18n import LANGS, Entry, norm

WEATHER_STRINGS: dict[str, Entry] = {
    "wx_hot": (
        "ыстық: сезілуі {deg}°C",
        "жара: ощущается как {deg}°C",
        "heat: feels like {deg}°C",
    ),
    "wx_c_rain": ("жаңбыр", "дождь", "rain"),
    "wx_c_snow": ("қар", "снег", "snow"),
    "wx_c_blowing_snow": ("боран", "метель или позёмка", "blowing snow"),
    "wx_c_freezing_rain": ("мұздақ жаңбыр", "ледяной дождь", "freezing rain"),
    "wx_c_thunder": ("найзағай", "гроза", "thunderstorm"),
    "wx_c_fog": ("тұман", "туман", "fog"),
    "wx_c_wind": ("күшті жел", "сильный ветер", "strong wind"),
    "wx_c_storm_warning": (
        "Қазгидромет дауыл ескертуі",
        "штормовое предупреждение Казгидромета",
        "Kazhydromet storm warning",
    ),
    "wx_c_smog": (
        "метеостанция бақылауы бойынша түтін немесе тұмша",
        "дым или дымка по наблюдению метеостанции",
        "smoke or haze at the weather station",
    ),
    "wx_c_nmu": (
        "Қазгидромет деректері бойынша қолайсыз метеожағдайлар (НМУ)",
        "неблагоприятные метеоусловия (НМУ) по данным Казгидромета",
        "unfavourable weather conditions (NMU, smog alert) per Kazhydromet",
    ),
    "obs_attr": (
        "Қазгидромет бақылауы бойынша (METAR UACC), {time}",
        "по наблюдению Казгидромета (METAR UACC), {time}",
        "Kazhydromet observation (METAR UACC), {time}",
    ),
    "obs_stale": (
        "Қазгидромет бақылауы (METAR UACC, {time}) ескірген (3 сағаттан артық): MET Norway болжамы қолданылды",
        "наблюдение Казгидромета (METAR UACC, {time}) устарело (старше 3 ч): использован прогноз MET Norway",
        "Kazhydromet observation (METAR UACC, {time}) is stale (over 3 h): the MET Norway forecast is used",
    ),
    "fc_attr": (
        "болжам: MET Norway (CC BY 4.0)",
        "прогноз: MET Norway (CC BY 4.0)",
        "forecast: MET Norway (CC BY 4.0)",
    ),
    "air_attr": (
        "ауа сапасы: Open-Meteo (CC BY 4.0), тегін API тек демо / коммерциялық емес пайдалануға арналған",
        "качество воздуха: Open-Meteo (CC BY 4.0), бесплатный API — только для демо / некоммерческого использования",
        "air quality: Open-Meteo (CC BY 4.0), the free API is for demo / non-commercial use only",
    ),
    "obs_details": (
        "Астана әуежайының METAR бақылауын Қазгидромет ДМҰ айырбасы арқылы береді; NOAA/NWS "
        "(aviationweather.gov, IEM) арқылы алынады, қоғамдық меншік.",
        "METAR аэропорта Астаны (UACC) Казгидромет передаёт через обмен ВМО; получено через NOAA/NWS "
        "(aviationweather.gov, IEM), общественное достояние.",
        "The Astana airport METAR (UACC) is issued by Kazhydromet via the WMO exchange; retrieved through "
        "NOAA/NWS (aviationweather.gov, IEM), public domain.",
    ),
    "warn_source": (
        "Дереккөз: Қазгидромет, {url}",
        "Источник: Казгидромет, {url}",
        "Source: Kazhydromet, {url}",
    ),
}


def tw(key: str, lang: str | None, **fields: object) -> str:
    text = WEATHER_STRINGS[key][LANGS.index(norm(lang))]
    return text.format(**fields) if fields else text
