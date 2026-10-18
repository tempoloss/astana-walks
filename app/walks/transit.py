"""LRT hint: transit stations are never recommended as places, but they are used to suggest a ride when the user
stands near an LRT station and a recommendation is far away yet close to another station.

The hint carries only station names from OpenStreetMap and a reminder to check the timetable: no times, no prices,
no claim that the line is running."""

from __future__ import annotations

from .i18n import t
from .models import POI, Recommendation
from .radius import haversine_m

TRANSIT_CATEGORY = "transit_station"
STATION_RADIUS_M = 600  # station within this distance of the user / of the recommendation
MIN_RIDE_DISTANCE_M = 1500  # hint only for recommendations farther than this


def is_lrt(poi: POI) -> bool:
    td = poi.tag_dict()
    return poi.category == TRANSIT_CATEGORY and (
        td.get("station") == "light_rail" or td.get("light_rail") == "yes"
    )


def station_name(poi: POI, lang: str | None = "ru") -> str:
    return poi.names.get(f"name:{lang}") or poi.names.get("name:ru") or poi.name


def _nearest(stations: list[POI], lat: float, lon: float) -> tuple[POI, float] | None:
    best = min(
        ((s, haversine_m(lat, lon, s.lat, s.lon)) for s in stations),
        key=lambda t: t[1],
        default=None,
    )
    return best if best is not None and best[1] <= STATION_RADIUS_M else None


def attach_lrt_hints(
    pois: list[POI],
    lat: float,
    lon: float,
    recs: list[Recommendation],
    mode: str,
    lang: str | None = "ru",
) -> str:
    """Set `rec.lrt_hint` where it applies; return a short explanation for the data panel."""
    if mode == "car":
        return t("lrt_car", lang)
    stations = [p for p in pois if is_lrt(p)]
    if not stations:
        return t("lrt_none", lang)
    here = _nearest(stations, lat, lon)
    if here is None:
        return t("lrt_far", lang, m=STATION_RADIUS_M)
    attached = 0
    for r in recs:
        if r.distance_m <= MIN_RIDE_DISTANCE_M:
            continue
        there = _nearest(stations, r.poi.lat, r.poi.lon)
        if (
            there is None
            or there[0].id == here[0].id
            or station_name(there[0]) == station_name(here[0])
        ):
            continue
        r.lrt_hint = t(
            "lrt_hint", lang, a=station_name(here[0], lang), b=station_name(there[0], lang)
        )
        attached += 1
    return t("lrt_near", lang, name=station_name(here[0], lang), m=round(here[1]), n=attached)
