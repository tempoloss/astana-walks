"""Radius honesty (declared vs searched radius, padding of every card) and the city layer: the three demand
indicators with k-anonymity, data quality, the exports and the «Для города» tab online and offline."""

from __future__ import annotations

import csv
import io
import json
from datetime import datetime
from pathlib import Path

import pytest

from walks import cli
from walks.demand import (
    OTHER,
    DemandRequest,
    aggregate_demand,
    demand_csv,
    demand_geojson,
    filter_requests,
    is_padded,
    load_requests,
    quality_cells,
    quality_csv,
    quality_geojson,
    request_from_record,
    worst_hours_categories,
)
from walks.models import POI, Constraints, Intent
from walks.pipeline import recommend
from walks.radius import STROLL_TRAVEL_SHARE, reachable_radius_m
from walks.reqlog import cell_bounds, grid_cell_id, record_for
from walks.retrieve import retrieve
from walks.walking import offline_router
from walks.weather import manual_weather

APP_DIR = Path(__file__).resolve().parents[1]
WED_NOON = datetime(2026, 10, 14, 12, 0)
ORIGIN = (51.0890, 71.4160)
DEG_M = 111_320.0
STROLL = Intent(time_budget_min=45, categories=["park_garden"])
BASE = reachable_radius_m(45, "walk", share=STROLL_TRAVEL_SHARE)


def _poi(poi_id: str, north_m: float, category: str, **kw) -> POI:
    return POI(
        id=poi_id,
        name=poi_id,
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        **kw,
    )


# ---- radius honesty ------------------------------------------------------------------------------


def test_exact_matches_inside_the_declared_radius_have_no_padding():
    res = retrieve([_poi("park", 300, "park_garden")], *ORIGIN, STROLL, WED_NOON)
    f = res.filters
    assert f.radius_declared_m == f.radius_effective_m == BASE
    assert not f.radius_widened
    assert [c.padding for c in res.candidates] == ["none"]
    assert "расширено" not in f.radius_text()


def test_widened_radius_is_reported_and_the_far_card_is_marked_expanded():
    pois = [_poi("far-park", BASE * 1.3, "park_garden")]
    res = retrieve(pois, *ORIGIN, STROLL, WED_NOON)
    f = res.filters
    assert f.radius_declared_m == BASE
    assert f.radius_effective_m == round(BASE * 1.3) > f.radius_declared_m
    assert f.radius_widened
    assert [c.padding for c in res.candidates] == ["expanded"]
    assert (
        f"{f.radius_declared_m} м по вашему времени; расширено до {f.radius_effective_m} м, "
        "т.к. рядом мало подходящего" in f.radius_text()
    )


def test_other_categories_are_marked_backfill():
    pois = [_poi("park", 300, "park_garden"), _poi("cafe", 40, "cafe")]
    res = retrieve(
        pois, *ORIGIN, Intent(time_budget_min=45, categories=["park_garden", "viewpoint"]), WED_NOON
    )
    assert res.filters.categories_relaxed
    assert {c.poi.id: c.padding for c in res.candidates} == {"park": "none", "cafe": "backfill"}


def test_pipeline_copies_padding_to_the_recommendations_and_the_log(tmp_path, monkeypatch):
    log = tmp_path / "requests.jsonl"
    monkeypatch.setenv("WALKS_REQUEST_LOG", str(log))
    pois = [_poi("far-park", BASE * 1.3, "park_garden")]
    res = recommend(
        "парк, прогулка 45 минут",
        *ORIGIN,
        WED_NOON,
        use_llm=False,
        pois=pois,
        router=offline_router(),
    )
    assert [r.padding for r in res.recs] == ["expanded"]
    row = json.loads(log.read_text(encoding="utf-8"))
    assert row["recs_by_padding"] == {"expanded": 1}
    assert row["radius_m"] == res.retrieval.filters.radius_declared_m
    assert row["radius_effective_m"] == res.retrieval.filters.radius_effective_m
    assert is_padded(row)
    assert row["requested_nearby"] == 0  # the only park is beyond the declared radius


def test_cli_header_names_both_radii_and_marks_the_card(tmp_path, monkeypatch, capsys):
    path = tmp_path / "poi.json"
    path.write_text(
        json.dumps([_poi("far-park", BASE * 1.3, "park_garden").model_dump(mode="json")]),
        encoding="utf-8",
    )
    monkeypatch.setenv("POI_PATH", str(path))
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    code = cli.main(
        ["--lat", str(ORIGIN[0]), "--lon", str(ORIGIN[1]), "--q", "парк, прогулка 45 минут", "--no-llm",
         "--weather", "off", "--time", "2026-10-14 12:00"]
    )  # fmt: skip
    out = capsys.readouterr().out
    assert code == 0
    assert "по вашему времени; расширено до" in out
    assert "[чуть дальше]" in out


# ---- demand: three separate indicators -----------------------------------------------------------


def _rec(
    *, cands, recs, nearby=None, confirmed=None, cats=("cafe",), cell="1_1", ts="2026-10-14T12:00"
) -> dict:
    rec = {
        "ts_hour": ts,
        "cell": cell,
        "categories": list(cats),
        "recs": sum(recs.values()),
        "candidates": sum(cands.values()),
        "candidates_by_padding": cands,
        "recs_by_padding": recs,
    }
    if nearby is not None:
        rec["requested_nearby"] = nearby
        rec["requested_nearby_with_hours"] = nearby if confirmed is None else confirmed
    return rec


def test_padded_is_a_fact_about_the_ranker_and_says_nothing_about_the_city():
    assert not is_padded(_rec(cands={"none": 3}, recs={"none": 2}))
    assert not is_padded(_rec(cands={"none": 1, "backfill": 4}, recs={"none": 1, "backfill": 2}))
    assert is_padded(_rec(cands={"expanded": 3}, recs={"expanded": 2}))  # found only after widening
    assert is_padded(_rec(cands={"backfill": 2}, recs={"backfill": 2}))  # only other categories
    assert is_padded(_rec(cands={}, recs={}))  # nothing at all
    assert is_padded(_rec(cands={"none": 2}, recs={}))  # candidates, but not one recommendation
    assert is_padded({"cell": "1_1", "ts_hour": "2026-10-14T12:00", "recs": 0})  # legacy record
    assert not is_padded({"cell": "1_1", "ts_hour": "2026-10-14T12:00", "recs": 2})


def test_a_weather_substitution_is_not_a_supply_shortage():
    frost = _rec(cands={"substituted": 3}, recs={"substituted": 2}, nearby=4, confirmed=4)
    assert not is_padded(frost)  # an indoor place in frost counts like "none" for the city layer
    assert not is_padded(_rec(cands={"none": 1, "substituted": 4}, recs={"substituted": 2}))
    assert is_padded(_rec(cands={"substituted": 3}, recs={}))  # nothing was recommended at all
    req = request_from_record(frost)
    assert (req.no_requested_category_nearby, req.hours_unknown_nearby, req.padded) == (
        False,
        False,
        False,
    )


def test_supply_facts_do_not_see_the_substitution():
    pois = [_poi("park", 100, "park_garden"), _poi("cafe", 200, "cafe")]
    res = retrieve(pois, *ORIGIN, STROLL, WED_NOON, weather=manual_weather(-25))
    assert [c.padding for c in res.candidates] == ["substituted"]  # the cafe stands in for the park
    assert res.filters.requested_nearby == 1  # the park is in the city: frost only hides it
    assert res.filters.requested_nearby_with_hours == 0


def test_the_three_indicators_are_independent_facts():
    # all closed now, so the ranker padded; but the places exist and their hours are known: not a gap of the city
    closed = _rec(cands={"backfill": 2}, recs={"backfill": 2}, nearby=3, confirmed=3)
    req = request_from_record(closed)
    assert (req.no_requested_category_nearby, req.hours_unknown_nearby, req.padded) == (
        False,
        False,
        True,
    )
    # nothing of the kind in the dataset inside the radius
    gap = request_from_record(_rec(cands={"backfill": 2}, recs={"backfill": 2}, nearby=0))
    assert (gap.no_requested_category_nearby, gap.hours_unknown_nearby, gap.padded) == (
        True,
        False,
        True,
    )
    # the kind exists, no confirmed hours anywhere: a data-quality finding
    blind = request_from_record(_rec(cands={"none": 2}, recs={"none": 2}, nearby=4, confirmed=0))
    assert (blind.no_requested_category_nearby, blind.hours_unknown_nearby, blind.padded) == (
        False,
        True,
        False,
    )
    # a record of the older log has no supply counts: nothing is claimed about the city
    old = request_from_record(_rec(cands={"expanded": 3}, recs={"expanded": 2}))
    assert (old.no_requested_category_nearby, old.hours_unknown_nearby, old.padded) == (
        False,
        False,
        True,
    )


def _requests(
    cell: str, n: int, no_cat: int = 0, cats=("cafe",), bucket="day", hours_unknown: int = 0
) -> list[DemandRequest]:
    return [
        DemandRequest(
            cell, bucket, tuple(cats), i < no_cat, no_cat <= i < no_cat + hours_unknown, i % 2 == 0
        )
        for i in range(n)
    ]


def test_aggregation_by_cell_category_and_time_of_day():
    reqs = (
        _requests("1_1", 6, no_cat=2, cats=("cafe", "park_garden"))
        + _requests("1_1", 5, no_cat=5, cats=("cafe",), bucket="night")
        + _requests("2_2", 5, cats=())
    )
    agg = aggregate_demand(reqs, k=5)
    got = {
        (r.cell, r.category, r.bucket): (r.requests, r.no_requested_category_nearby)
        for r in agg.shown
    }
    assert got == {
        ("1_1", "cafe", "day"): (6, 2),
        ("1_1", "park_garden", "day"): (6, 2),
        ("1_1", "cafe", "night"): (5, 5),
        ("2_2", "без категории", "day"): (5, 0),
    }
    assert agg.total_requests == 16
    assert agg.total_no_category == 7
    assert agg.total_padded == 9  # every second request of each group
    assert agg.total_hours_unknown == 0
    assert agg.rows[0].no_requested_category_nearby == 5  # the worst group first
    by_cell = aggregate_demand(reqs, k=5, by=("cell",))
    assert {r.cell: (r.requests, r.no_requested_category_nearby) for r in by_cell.shown} == {
        "1_1": (11, 7),
        "2_2": (5, 0),
    }


def test_the_map_indicator_is_not_the_padded_or_the_hours_indicator():
    reqs = _requests("1_1", 10, no_cat=2, hours_unknown=3)
    (row,) = aggregate_demand(reqs, k=5, by=("cell",)).shown
    assert (
        row.requests,
        row.no_requested_category_nearby,
        row.hours_unknown_nearby,
        row.padded,
    ) == (10, 2, 3, 5)
    assert row.no_category_share == pytest.approx(0.2)


def test_groups_below_k_are_merged_into_one_row_without_a_location():
    reqs = (
        _requests("1_1", 5, no_cat=1)
        + _requests("3_3", 4, no_cat=4)
        + _requests("4_4", 2, no_cat=1)
    )
    agg = aggregate_demand(reqs, k=5, by=("cell", "category"))
    assert [(r.cell, r.requests) for r in agg.shown] == [("1_1", 5)]
    assert all(r.requests >= 5 for r in agg.shown)
    (other,) = agg.merged
    assert (other.cell, other.category, other.requests, other.no_requested_category_nearby) == (
        OTHER,
        "cafe",
        6,
        5,
    )
    assert agg.cells_total == 3
    assert agg.cells_suppressed == 2
    assert agg.groups_suppressed == 2
    assert agg.requests_suppressed == 6
    assert sum(r.requests for r in agg.rows) == 11  # nothing is lost, only de-located
    assert aggregate_demand(reqs, k=2, by=("cell",)).cells_suppressed == 0  # k is configurable
    with pytest.raises(ValueError, match="cell"):
        aggregate_demand(reqs, by=("category",))


def test_a_cell_below_k_never_reaches_the_exports():
    reqs = _requests("1_1", 5, no_cat=2) + _requests("3_3", 3, no_cat=3)
    agg = aggregate_demand(reqs, k=5)
    rows = list(csv.DictReader(io.StringIO(demand_csv(agg.rows))))
    assert [r["cell"] for r in rows] == ["1_1", OTHER]
    assert rows[1]["lat"] == rows[1]["lon"] == ""  # no location for the merged row
    assert set(rows[0]) == {
        "cell", "lat", "lon", "category", "time_of_day", "requests",
        "no_requested_category_nearby", "hours_unknown_nearby", "padded", "no_category_share",
    }  # fmt: skip
    geo = demand_geojson(agg.rows)
    assert [f["properties"]["cell"] for f in geo["features"]] == ["1_1"]
    assert "3_3" not in json.dumps(geo) + demand_csv(agg.rows)


def test_filters_and_loading():
    reqs = _requests("1_1", 2, cats=("cafe", "park_garden")) + _requests(
        "1_1", 3, cats=(), bucket="night"
    )
    assert len(filter_requests(reqs, category="park_garden")) == 2
    assert len(filter_requests(reqs, category="без категории")) == 3
    assert len(filter_requests(reqs, bucket="night")) == 3


def test_load_requests_skips_damaged_lines(tmp_path):
    path = tmp_path / "r.jsonl"
    good = _rec(
        cands={"none": 1}, recs={"none": 1}, nearby=2, cats=("cafe",), ts="2026-10-14T23:00"
    )
    path.write_text(
        "\n".join(
            [json.dumps(good), "{broken", json.dumps({"cell": "x_y"}), json.dumps(["list"]), ""]
        ),
        encoding="utf-8",
    )
    (req,) = load_requests(path)
    assert (req.cell, req.bucket, req.categories, req.padded) == ("1_1", "night", ("cafe",), False)
    assert load_requests(tmp_path / "missing.jsonl") == []
    assert request_from_record({"cell": "1_1"}) is None


def test_cell_bounds_roundtrip():
    cell = grid_cell_id(*ORIGIN)
    s, w, n, e = cell_bounds(cell)
    assert s <= ORIGIN[0] < n
    assert w <= ORIGIN[1] < e
    assert grid_cell_id((s + n) / 2, (w + e) / 2) == cell


def _ask(pois: list[POI], text: str = "парк, прогулка 45 минут", **kw):
    return recommend(
        text, *ORIGIN, WED_NOON, use_llm=False, pois=pois, router=offline_router(), **kw
    )


def test_record_for_roundtrips_into_a_demand_request():
    res = _ask([_poi("far-park", BASE * 1.3, "park_garden")])
    req = request_from_record(record_for(res))
    assert req is not None
    assert req.cell == grid_cell_id(*ORIGIN)
    assert req.bucket == "day"
    assert req.padded
    assert (
        req.no_requested_category_nearby
    )  # the only park is beyond the declared radius: nothing nearby


def test_supply_counts_are_a_dataset_fact_not_a_ranker_fact():
    closed = _poi("closed-park", 300, "park_garden", opening_hours="Mo-Su 00:00-01:00")
    f = _ask([closed]).retrieval.filters
    assert (f.requested_nearby, f.requested_nearby_with_hours) == (
        1,
        1,
    )  # exists, hours known (closed now)
    assert request_from_record(record_for(_ask([closed]))).padded
    blind = _ask([_poi("blind-park", 300, "park_garden")])
    assert (
        blind.retrieval.filters.requested_nearby,
        blind.retrieval.filters.requested_nearby_with_hours,
    ) == (1, 0)
    req = request_from_record(record_for(blind))
    assert (req.no_requested_category_nearby, req.hours_unknown_nearby, req.padded) == (
        False,
        True,
        False,
    )
    other = _ask([_poi("cafe", 100, "cafe"), _poi("far-cafe", 3000, "cafe")])
    assert other.retrieval.filters.requested_nearby == 0  # the cafe is not a park
    assert request_from_record(record_for(other)).no_requested_category_nearby


def test_supply_ignores_weather_narrowing_and_other_exclusions():
    pois = [_poi("park", BASE * 0.9, "park_garden")]
    plain = retrieve(pois, *ORIGIN, STROLL, WED_NOON)
    narrowed = retrieve(pois, *ORIGIN, STROLL, WED_NOON, constraints=Constraints(radius_factor=0.5))
    assert narrowed.filters.radius_declared_m < plain.filters.radius_declared_m
    assert narrowed.filters.requested_nearby == plain.filters.requested_nearby == 1


# ---- data quality --------------------------------------------------------------------------------


def _quality_pois() -> list[POI]:
    return [
        _poi("a", 10, "cafe", opening_hours="24/7", description_source="osm"),
        _poi("b", 20, "cafe"),
        _poi("c", 30, "cafe", opening_hours="Mo-Su 09:00-18:00"),
        _poi("d", 40, "park_garden", description_source="wikipedia"),
        _poi("e", 50, "park_garden"),
        _poi("f", 60, "park_garden"),
        _poi("t", 70, "transit_station", opening_hours="24/7"),
        _poi("far", 5000, "cafe", opening_hours="24/7"),
    ]


def test_quality_cells_count_hours_descriptions_and_marks():
    cells = {c.cell: c for c in quality_cells(_quality_pois(), {"a", "d"})}
    home = cells[grid_cell_id(*ORIGIN)]
    assert (home.pois, home.with_hours, home.with_description, home.with_people) == (6, 2, 2, 2)
    assert home.share("hours") == pytest.approx(2 / 6)
    assert sum(c.pois for c in cells.values()) == 7  # the station is not counted
    rows = list(csv.DictReader(io.StringIO(quality_csv(cells.values()))))
    assert {r["cell"] for r in rows} == set(cells)
    assert quality_geojson(cells.values())["features"][0]["geometry"]["type"] == "Polygon"


def test_worst_hours_categories_are_sorted_and_need_enough_places():
    pois = _quality_pois()
    ranked = worst_hours_categories(pois, top=10, min_pois=3)
    assert [(r.category, r.pois, r.with_hours) for r in ranked] == [
        ("park_garden", 3, 0),
        ("cafe", 4, 3),
    ]
    assert worst_hours_categories(pois, top=1, min_pois=3)[0].category == "park_garden"
    assert [r.category for r in worst_hours_categories(pois, min_pois=4)] == ["cafe"]
