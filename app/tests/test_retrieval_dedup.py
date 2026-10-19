"""Retrieval: chain duplicates collapse into one card; categories whose minimum stay cannot fit are dropped."""

from __future__ import annotations

from datetime import datetime

import pytest
from rapidfuzz import fuzz

from walks.chains import CLUSTER_RADIUS_M
from walks.generate import generate
from walks.models import POI, Intent
from walks.names import NAME_RATIO_MIN, name_key
from walks.radius import haversine_m
from walks.retrieve import retrieve
from walks.stay import MIN_STAY_OVER_BUDGET

WED_NOON = datetime(2026, 10, 14, 12, 0)


@pytest.fixture(autouse=True)
def _reasons_not_checked_for_facts(monkeypatch):
    """These tests are about the chain, the cache and the claims: their fake reasons are not checked for a concrete
    fact of the place (tests/test_answer_quality.py checks that)."""
    import walks.generate as generation

    monkeypatch.setattr(generation, "vague_ids", lambda *a, **k: [])


ORIGIN = (51.0890, 71.4160)
DEG_M = 111_320.0  # metres per degree of latitude


def _poi(poi_id: str, name: str, north_m: float, category: str = "cafe", **kw) -> POI:
    return POI(
        id=poi_id,
        name=name,
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        **kw,
    )


def _ids(res) -> list[str]:
    return [c.poi.id for c in res.candidates]


# ---- name normalisation ----------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Blackбери", "Блэкбери"),
        ("Блэкбери", "BlackBerry"),
        ("Blackбери", "BlackBerry"),
        ("Пинта", "Pinta"),
        ("Coffee BOOM", "coffee boom"),
        ("«Бургер Кинг»", "Burger King"),
        ("Бургер-Кинг", "BURGER KING"),
        ("Қазақстан", "Kazakstan"),
    ],
)
def test_name_variants_reach_the_similarity_threshold(a, b):
    assert fuzz.ratio(name_key(a), name_key(b)) >= NAME_RATIO_MIN


@pytest.mark.parametrize(
    ("a", "b"),
    [("Pinta", "Park Pinta Plaza"), ("Cafe 1", "Cafe 2"), ("Starbucks", "Сладкоежка")],
)
def test_different_names_stay_apart(a, b):
    assert fuzz.ratio(name_key(a), name_key(b)) < NAME_RATIO_MIN


# ---- chain clusters --------------------------------------------------------------------------------


def _chain_fixture() -> list[POI]:
    # three branches within 100 m of each other, the nearest one 300 m from the user ...
    near = [
        _poi("node/1", "Blackбери", 300),
        _poi("node/2", "Блэкбери", 370),
        _poi("node/3", "BlackBerry", 400),
    ]
    # ... a fourth 400 m beyond the first (outside the cluster radius), plus unrelated places
    far = _poi("node/4", "BlackBerry", 700)
    other = _poi("node/5", "Совсем другое кафе", 500)
    same_name_other_category = _poi("node/6", "Blackбери", 310, category="restaurant")
    return [*near, far, other, same_name_other_category]


def test_chain_collapses_to_nearest_member_with_a_note():
    pois = _chain_fixture()
    intent = Intent(time_budget_min=120, categories=["cafe", "restaurant"])
    res = retrieve(pois, *ORIGIN, intent, WED_NOON)
    ids = _ids(res)
    assert "node/1" in ids  # the nearest member represents the cluster
    assert "node/2" not in ids
    assert "node/3" not in ids
    assert "node/4" in ids  # 400 m from the cluster: a different card
    assert "node/5" in ids
    assert "node/6" in ids  # same name but another category is not a duplicate
    by_id = {c.poi.id: c for c in res.candidates}
    assert by_id["node/1"].nearby_same == 2
    assert by_id["node/4"].nearby_same == 0
    assert res.filters.clustered_away == 2
    [log] = res.filters.merged
    assert log.kept_id == "node/1"
    assert len(log.merged) == 2
    assert "node/2" in log.merged[0] + log.merged[1]


def test_cluster_note_reaches_the_card():
    pois = _chain_fixture()
    intent = Intent(time_budget_min=120, categories=["cafe"])
    res = retrieve(pois, *ORIGIN, intent, WED_NOON)
    gen = generate(intent, *ORIGIN, res.candidates, WED_NOON, use_llm=False)
    card = next(r for r in gen.recs if r.poi.id == "node/1")
    assert "ещё 2 точки рядом" in card.notes


def test_no_two_members_of_a_cluster_in_recs_or_route():
    from walks.route import build_route

    pois = _chain_fixture()
    intent = Intent(time_budget_min=240, categories=["cafe"])
    res = retrieve(pois, *ORIGIN, intent, WED_NOON)
    gen = generate(intent, *ORIGIN, res.candidates, WED_NOON, use_llm=False)
    plan = build_route(*ORIGIN, gen.recs, "walk", 240)
    chain = {"node/1", "node/2", "node/3"}
    assert len(chain & {r.poi.id for r in gen.recs}) <= 1
    assert plan is not None
    assert len(chain & set(plan.stops)) <= 1


def test_cluster_members_must_be_within_the_radius_of_the_nearest():
    assert CLUSTER_RADIUS_M == 150
    pois = [_poi("node/1", "Pinta", 300), _poi("node/2", "Пинта", 300 + CLUSTER_RADIUS_M + 60)]
    res = retrieve(pois, *ORIGIN, Intent(time_budget_min=120, categories=["cafe"]), WED_NOON)
    assert sorted(_ids(res)) == ["node/1", "node/2"]
    first, second = pois
    assert haversine_m(first.lat, first.lon, second.lat, second.lon) > CLUSTER_RADIUS_M


def test_generated_names_are_never_clustered_as_a_chain_but_one_card_stands_for_them():
    pois = [
        _poi("node/1", "Кафе", 300, name_generated=True),
        _poi("node/2", "Кафе", 330, name_generated=True),
    ]
    res = retrieve(pois, *ORIGIN, Intent(time_budget_min=120, categories=["cafe"]), WED_NOON)
    assert _ids(res) == ["node/1"]  # two anonymous records of one kind are not two choices ...
    assert res.candidates[0].nearby_anon == 1  # ... the card says there is one more
    assert res.filters.clustered_away == 0  # and it is not a chain merge


# ---- minimum stay vs. the budget ---------------------------------------------------------------------


def _cinema_and_cafe() -> list[POI]:
    return [
        _poi("node/10", "Кинотеатр Мир", 300, category="culture_theatre_cinema"),
        _poi("node/11", "Кофейня", 350),
    ]


def test_cinema_is_excluded_at_a_90_minute_budget():
    intent = Intent(time_budget_min=90, categories=["culture_theatre_cinema", "cafe"])
    res = retrieve(_cinema_and_cafe(), *ORIGIN, intent, WED_NOON)
    assert _ids(res) == ["node/11"]
    assert res.filters.excluded_min_stay == 1


def test_cinema_stays_when_the_budget_allows_it():
    intent = Intent(time_budget_min=240, categories=["culture_theatre_cinema", "cafe"])
    res = retrieve(_cinema_and_cafe(), *ORIGIN, intent, WED_NOON)
    assert "node/10" in _ids(res)
    assert res.filters.excluded_min_stay == 0
    assert all(MIN_STAY_OVER_BUDGET not in c.reasons for c in res.candidates)


def test_cinema_kept_with_a_note_when_it_is_the_only_candidate():
    pois = [_cinema_and_cafe()[0]]
    intent = Intent(time_budget_min=90, time_stated=True, categories=["culture_theatre_cinema"])
    res = retrieve(pois, *ORIGIN, intent, WED_NOON)
    [cand] = res.candidates
    assert cand.poi.id == "node/10"
    assert MIN_STAY_OVER_BUDGET in cand.reasons
    assert res.filters.excluded_min_stay == 0
    gen = generate(intent, *ORIGIN, res.candidates, WED_NOON, use_llm=False)
    assert "обычно здесь нужно от 120 мин" in gen.recs[0].why


def test_note_in_why_also_for_llm_text(monkeypatch):
    from walks import generate as gen_mod
    from walks import llm
    from walks.llm_output import LLMOutput, LLMRec
    from walks.models import LLMStep

    pois = [_cinema_and_cafe()[0]]
    intent = Intent(time_budget_min=90, time_stated=True, categories=["culture_theatre_cinema"])
    res = retrieve(pois, *ORIGIN, intent, WED_NOON)
    out = LLMOutput(
        recommendations=[
            LLMRec(
                poi_id="node/10",
                why="Хороший выбор.",
                time_on_site_min=120,
                what_to_do="Сходите.",
                confidence="medium",
                generated_idea=False,
            )
        ]
    )
    monkeypatch.setattr(llm, "llm_available", lambda: True)
    monkeypatch.setattr(
        gen_mod,
        "generate_json",
        lambda *a, **k: llm.LLMCall(out, LLMStep(chain=["m"], model="m")),
    )
    gen = generate(intent, *ORIGIN, res.candidates, WED_NOON)
    assert gen.mode == "llm"
    assert gen.recs[0].why.startswith("Хороший выбор.")
    assert "обычно здесь нужно от 120 мин" in gen.recs[0].why
