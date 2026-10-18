"""The five case scenarios, rule-based parser + template text, on the real data/poi.json."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.models import DEFAULT_POI_PATH, load_pois
from walks.pipeline import recommend
from walks.presets import PRESETS, SCENARIOS
from walks.radius import (
    STROLL_TRAVEL_SHARE,
    TRAVEL_SHARE,
    haversine_m,
    is_stroll,
    kids_walk_radius_m,
    reachable_radius_m,
)

DAY = datetime(2026, 10, 14, 14, 0)  # a Wednesday afternoon, Astana local time
NIGHT = datetime(2026, 10, 14, 23, 0)


@pytest.fixture(scope="module")
def pois():
    return load_pois(DEFAULT_POI_PATH)


def run(pois, scenario, when=None):
    lat, lon = PRESETS[scenario.preset]
    if when is None:
        when = datetime.combine(DAY.date(), scenario.at) if scenario.at else DAY
    return recommend(scenario.text, lat, lon, when, use_llm=False, pois=pois), lat, lon


@pytest.mark.parametrize("scenario", SCENARIOS, ids=[s.label for s in SCENARIOS])
def test_scenario_basics(pois, scenario):
    res, lat, lon = run(pois, scenario)
    assert res.intent.parser == "rules"
    assert res.generation == "template"
    assert res.recs, "no recommendations"
    assert 1 <= len(res.recs) <= 3
    intent = res.intent.intent
    share = STROLL_TRAVEL_SHARE if is_stroll(intent) else TRAVEL_SHARE  # a stroll may walk further
    base = reachable_radius_m(intent.time_budget_min, intent.mode, share=share)
    if intent.with_kids and intent.mode == "walk":
        base = min(base, kids_walk_radius_m())  # a child's walk is capped at 15 minutes one way
    radius = res.retrieval.filters.radius_effective_m
    assert radius == round(base * res.retrieval.filters.radius_factor)
    for r in res.recs:
        assert (
            haversine_m(lat, lon, r.poi.lat, r.poi.lon) <= radius + 120
        )  # +100 m location rounding
        assert r.distance_m <= radius
        assert r.hours_state != "closed"
        assert r.why
        assert r.what_to_do
        assert not r.generated_idea  # template text is built from data only
    assert res.route is not None


def test_scenario_kids(pois):
    scenario = SCENARIOS[2]
    res, _, _ = run(pois, scenario)
    assert res.intent.intent.with_kids
    assert any(r.poi.category in {"kids_playground", "museum_gallery"} for r in res.recs)
    assert all(
        r.poi.category in {"kids_playground", "museum_gallery", "entertainment"} for r in res.recs
    )


def test_scenario_quiet_cafe(pois):
    res, _, _ = run(pois, SCENARIOS[1])
    i = res.intent.intent
    assert i.quiet
    assert i.needs_wifi_socket
    assert any(r.poi.category in {"cafe", "coworking_library"} for r in res.recs)


def test_scenario_tourist_reserves_flight_time(pois):
    res, _, _ = run(pois, SCENARIOS[3])
    assert res.intent.intent.time_budget_min == 60  # 120 min minus 60 min airport reserve


def test_scenario_night_23(pois):
    scenario = SCENARIOS[4]
    assert scenario.at is not None
    assert scenario.at.hour == 23
    res, _, _ = run(pois, scenario, NIGHT)
    assert res.intent.intent.night
    assert res.retrieval.filters.night_mode
    assert res.recs
    for r in res.recs:
        assert r.hours_state in {"open", "unknown"}
    for c in res.retrieval.candidates:
        assert c.hours_state != "closed"


def test_cold_weather_real_data(pois):
    from walks.weather import OUTDOOR_CATEGORIES, manual_weather

    lat, lon = PRESETS["Байтерек"]  # parks and playgrounds dominate here
    cold = manual_weather(-30)
    res = recommend(
        "С ребёнком: площадка или интерактивный музей",
        lat,
        lon,
        DAY,
        use_llm=False,
        pois=pois,
        weather=cold,
    )
    assert res.retrieval.filters.weather_adapted
    assert res.retrieval.filters.radius_effective_m <= 600
    assert res.retrieval.candidates
    assert res.retrieval.candidates[0].poi.category not in OUTDOOR_CATEGORIES
    assert res.recs[0].poi.category not in OUTDOOR_CATEGORIES
    for r in res.recs:
        assert r.distance_m <= 600


def test_transit_stations_never_recommended_real_data(pois):
    from walks.weather import make_weather

    stations = {p.id for p in pois if p.category == "transit_station"}
    assert len(stations) >= 20  # the LRT stations are in the dataset
    texts = [s.text for s in SCENARIOS] + ["LRT станция рядом", "вокзал", "транспорт на 3 часа"]
    for name, (lat, lon) in PRESETS.items():
        for text in texts:
            for weather in (None, make_weather(10, 10, pm25=5)):
                res = recommend(text, lat, lon, DAY, use_llm=False, pois=pois, weather=weather)
                assert not stations & {c.poi.id for c in res.retrieval.candidates}, (name, text)
                assert not stations & {r.poi.id for r in res.recs}, (name, text)


def test_lrt_hint_real_data(pois):
    res = recommend(
        "музей или смотровая на 3 часа на транспорте",
        *PRESETS["Mega Silk Way"],
        DAY,
        use_llm=False,
        pois=pois,
    )
    hints = [r.lrt_hint for r in res.recs if r.lrt_hint]
    for h in hints:
        assert h.startswith("LRT: ")
        assert "→" in h
        assert h.endswith("(проверьте расписание)")
    assert res.lrt_note
