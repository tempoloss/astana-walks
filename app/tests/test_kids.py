"""A request with a child: indoor kids places count as playgrounds, a place is «for children» only by a field, and
anonymous OSM records («Детская площадка») never fill every card while named places exist."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.generate import pick_diverse
from walks.kids import allowed_unnamed, is_kids_place, is_member, is_near_named, kids_signal
from walks.models import DEFAULT_POI_PATH, POI, Candidate, Intent, load_pois
from walks.pipeline import recommend
from walks.presets import PRESETS
from walks.retrieve import retrieve
from walks.weather import manual_weather

NOON = datetime(2026, 10, 19, 14, 0)


@pytest.fixture(scope="module")
def pois():
    return load_pois(DEFAULT_POI_PATH)


def poi(pid="p", category="entertainment", name_generated=False, **kw) -> POI:
    return POI(
        id=pid,
        name=kw.pop("name", pid),
        lat=51.09,
        lon=71.41,
        category=category,
        name_generated=name_generated,
        **kw,
    )


def cand(p: POI, score=1.0) -> Candidate:
    return Candidate(
        poi=p, distance_m=100, walk_min=2, travel_min=2, hours_state="unknown", score=score
    )


def test_a_kids_place_is_one_by_a_field_only():
    assert kids_signal(poi(tags=["for_kids=yes"]))
    assert kids_signal(poi(tags=["leisure=indoor_play"]))
    assert kids_signal(poi(tags=["leisure=playground", "indoor=yes"]))
    assert kids_signal(poi(tags=["tourism=theme_park"]))
    assert not kids_signal(poi(tags=["leisure=bowling_alley"]))  # an ordinary entertainment place
    assert not kids_signal(poi(tags=["leisure=playground"]))  # outdoors
    assert kids_signal(poi(name="Детский клуб Планета"))
    assert is_kids_place(poi(category="kids_playground"))
    assert not is_kids_place(
        poi(category="cafe", tags=["for_kids=yes"])
    )  # only the host categories


def test_indoor_kids_places_are_members_of_a_playground_request_with_a_child():
    kids = Intent(with_kids=True, categories=["kids_playground", "museum_gallery"])
    plain = Intent(categories=["kids_playground"])
    play = poi(tags=["leisure=indoor_play"])
    bowling = poi(tags=["leisure=bowling_alley"])
    member = {"kids_playground", "museum_gallery"}
    assert is_member(play, member, kids.categories, kids)
    assert not is_member(bowling, member, kids.categories, kids)
    assert not is_member(
        play, {"kids_playground"}, plain.categories, plain
    )  # no child in the request


def test_the_unnamed_cap_is_one_when_two_named_places_exist():
    assert allowed_unnamed(named_total=5, slots=3) == 1
    assert allowed_unnamed(named_total=2, slots=3) == 1
    assert allowed_unnamed(named_total=1, slots=3) == 2
    assert allowed_unnamed(named_total=0, slots=3) == 3


def test_pick_diverse_takes_named_places_before_anonymous_ones():
    anon = [cand(poi(f"a{i}", "kids_playground", True), 5.0 - i * 0.01) for i in range(5)]
    named = [cand(poi("n1", "entertainment"), 3.0), cand(poi("n2", "museum_gallery"), 2.9)]
    picked = pick_diverse(sorted(anon + named, key=lambda c: -c.score))
    assert len(picked) == 3
    assert sum(1 for c in picked if c.poi.name_generated) == 1
    assert {"n1", "n2"} <= {c.poi.id for c in picked}


def test_never_two_anonymous_records_of_one_kind_even_when_nothing_else_exists():
    anon = [cand(poi(f"a{i}", "kids_playground", True), 5.0 - i * 0.01) for i in range(5)]
    picked = pick_diverse(
        sorted([*anon, cand(poi("n1", "entertainment"), 1.0)], key=lambda c: -c.score)
    )
    assert {c.poi.id for c in picked} == {"a0", "n1"}  # one anonymous playground, the named place
    assert [c.poi.id for c in pick_diverse(anon)] == ["a0"]  # one card, not three that look alike
    two_kinds = [*anon, cand(poi("c0", "cafe", True), 4.0), cand(poi("c1", "cafe", True), 3.9)]
    kinds = [c.poi.category for c in pick_diverse(sorted(two_kinds, key=lambda c: -c.score))]
    assert sorted(kinds) == ["cafe", "kids_playground"]  # one of each kind


@pytest.mark.parametrize("preset", ["EXPO", "Хан Шатыр", "Байтерек"])
def test_a_kids_request_shows_named_places_and_at_most_one_anonymous_playground(pois, preset):
    res = recommend(
        "С ребёнком: площадка или интерактивный музей",
        *PRESETS[preset],
        NOON,
        use_llm=False,
        pois=pois,
        weather=manual_weather(10.0, pm25=5.0),
    )
    assert (
        2 <= len(res.recs) <= 3
    )  # one card for all the anonymous playgrounds, not three that look alike
    near_named = sum(1 for c in res.retrieval.candidates if is_near_named(c))
    unnamed = [r for r in res.recs if r.poi.name_generated]
    assert len(unnamed) <= min(1, allowed_unnamed(near_named, 3))
    assert len({r.poi.category for r in unnamed}) == len(unnamed)
    assert any(r.poi.category in ("entertainment", "museum_gallery") for r in res.recs)


def test_an_indoor_kids_centre_enters_the_candidates_of_a_request_with_a_child(pois):
    res = retrieve(
        pois,
        *PRESETS["EXPO"],
        Intent(
            with_kids=True, categories=["kids_playground", "museum_gallery"], time_budget_min=120
        ),
        NOON,
    )
    kids_centres = [
        c for c in res.candidates if c.poi.category == "entertainment" and kids_signal(c.poi)
    ]
    assert kids_centres
    assert all(c.padding in ("none", "expanded") for c in kids_centres)  # a match, not a back-fill
    assert "kids" in kids_centres[0].reasons


def test_an_entertainment_place_without_a_kids_field_is_not_called_suitable_for_children(pois):
    res = recommend(
        "С ребёнком: площадка или интерактивный музей",
        *PRESETS["EXPO"],
        NOON,
        use_llm=False,
        pois=pois,
        weather=manual_weather(-28.0),
    )
    for r in res.recs:
        if r.poi.category == "entertainment" and not kids_signal(r.poi):
            assert "для детей" not in r.why


def test_in_frost_no_outdoor_playground_is_offered_when_an_indoor_place_exists(pois):
    res = recommend(
        "С ребёнком: площадка или интерактивный музей",
        *PRESETS["Хан Шатыр"],
        NOON,
        use_llm=False,
        pois=pois,
        weather=manual_weather(-28.0),
    )
    assert res.recs
    assert all(r.poi.category != "kids_playground" for r in res.recs)


# ------------------------------------------------------------------ a child's walking budget


def test_the_routed_detour_of_retrieve_is_the_one_of_the_walking_step():
    from walks.radius import ROUTED_DETOUR
    from walks.walking import FALLBACK_DETOUR

    assert ROUTED_DETOUR == FALLBACK_DETOUR


def test_a_request_with_a_child_never_offers_more_than_a_15_minute_walk_as_a_plain_match(pois):
    from walks.radius import KIDS_WALK_MAX_MIN, kids_walk_radius_m
    from walks.walking import offline_router

    assert kids_walk_radius_m() <= 870  # 15 min at 4.5 km/h over a 1.3 detour
    for preset in ("EXPO", "Хан Шатыр", "Байтерек", "Mega Silk Way", "Аэропорт"):
        for hour in (14, 19):
            res = recommend(
                "С ребёнком: площадка или интерактивный музей",
                *PRESETS[preset],
                datetime(2026, 10, 20, hour, 30),
                use_llm=False,
                pois=pois,
                router=offline_router(),
                weather=manual_weather(10.0, pm25=5.0),
            )
            f = res.retrieval.filters
            assert f.radius_declared_m <= kids_walk_radius_m()
            for r in res.recs:
                if r.padding == "none":
                    assert r.walk_min <= KIDS_WALK_MAX_MIN, (preset, hour, r.poi.name, r.walk_min)


def test_a_far_other_category_is_never_back_filled_beyond_the_declared_radius(pois):
    """Nothing of the requested kind is in reach (the airport): other categories fill up only inside the radius the
    time gives, never the 35-minute walk of the widened one."""
    res = recommend(
        "С ребёнком: площадка или интерактивный музей",
        *PRESETS["Аэропорт"],
        datetime(2026, 10, 20, 19, 30),
        use_llm=False,
        pois=pois,
        weather=manual_weather(10.0, pm25=5.0),
    )
    declared = res.retrieval.filters.radius_declared_m
    for c in res.retrieval.candidates:
        if c.padding == "backfill":
            assert c.distance_m <= declared, (c.poi.name, c.distance_m, declared)
