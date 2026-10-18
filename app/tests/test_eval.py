"""The evaluation harness (app/eval): the case file is well-formed and covers every axis, and the verdict logic
flags exactly what it claims to flag."""

from __future__ import annotations

import json

import pytest

from eval import metrics, report
from eval.cases import AXES, load_cases
from eval.report import percentile, write_summaries
from walks.models import POI
from walks.presets import SCENARIOS

DEFAULT_WALK = 3


def _poi(
    pid: str, category: str = "cafe", hours: str | None = None, name: str = "Cafe X", **kw
) -> POI:
    return POI(
        id=pid,
        name=name,
        lat=51.1,
        lon=71.4,
        category=category,
        opening_hours=hours,
        description_auto="Кафе в Астане.",
        **kw,
    )


def _rec(
    poi: POI, state: str, notes: str = "", walk: int = DEFAULT_WALK, why: str = "Подходит."
) -> dict:
    return {
        "poi_id": poi.id,
        "name": poi.name,
        "category": poi.category,
        "hours_state": state,
        "walk_min": walk,
        "why": why,
        "what_to_do": "",
        "notes": notes,
    }


def _case(**expected) -> dict:
    return {
        "id": "t",
        "when": "2026-10-20T14:00",
        "weather_override": None,
        "air_override": None,
        "expected": {"budget_min": 60, **expected},
    }


def _judge(case: dict, pois: list[POI], recs: list[dict], route: dict | None = None) -> dict:
    return metrics.judge_case(case, recs, route, metrics.dataset_index(pois))


# ---------------------------------------------------------------- cases.json


def test_cases_cover_every_axis_value_and_the_brief():
    cases = load_cases()
    assert 35 <= len(cases) <= 50
    assert len({c["id"] for c in cases}) == len(cases)
    for axis, values in AXES.items():
        assert {c["axes"][axis] for c in cases} == set(values), axis
    tz = [c for c in cases if c.get("tz")]
    assert [c["query"] for c in tz] == [s.text for s in SCENARIOS]


def test_cases_have_the_documented_shape():
    for c in load_cases():
        assert {
            "id",
            "label",
            "origin",
            "when",
            "weather_override",
            "air_override",
            "query",
            "expected",
        } <= set(c)
        assert {"name", "lat", "lon"} == set(c["origin"])
        assert "notes" in c["expected"]
        assert isinstance(c["expected"]["must_flag_unknown_hours"], bool)


def test_expected_indoor_matches_the_injected_conditions():
    from eval.cases import indoor_required

    for c in load_cases():
        assert c["expected"]["indoor_preferred"] == indoor_required(c), c["id"]


# ---------------------------------------------------------------- verdicts


def test_hallucinated_id_is_counted_and_closed_place_is_a_violation():
    closed = _poi("a", hours="Mo-Su 20:00-23:00")
    recs = [_rec(closed, "open"), {**_rec(closed, "open"), "poi_id": "ghost"}]
    v = _judge(_case(), [closed], recs)
    assert v["hallucinated"] == ["ghost"]
    assert v["constraint_violations"] == {"a": [metrics.CLOSED_AT_ARRIVAL]}
    assert not v["all_ok"]
    assert not v["coverage_ok"]


def test_honesty_open_needs_hours_and_unknown_needs_a_label():
    no_hours = _poi("a")
    labeled = _poi("b")
    v = _judge(
        _case(),
        [no_hours, labeled],
        [
            _rec(no_hours, "open"),
            _rec(
                labeled,
                "unknown",
                notes="Часы работы в данных неизвестны — уточните перед выходом.",
            ),
        ],
    )
    assert v["honesty_violations"] == {
        "a": [metrics.OPEN_WITHOUT_HOURS, metrics.UNKNOWN_NOT_LABELED]
    }
    assert v["constraint_violations"] == {}


def test_unlabeled_unknown_and_open_claim_in_text():
    p = _poi("a")
    v = _judge(_case(), [p], [_rec(p, "unknown", why="Сейчас открыто и работает.")])
    assert v["honesty_violations"]["a"] == [metrics.UNKNOWN_NOT_LABELED, metrics.OPEN_CLAIM_IN_TEXT]


def test_open_air_is_not_an_open_claim():
    p = _poi("a")
    label = "Часы работы в данных неизвестны — уточните."
    note = f"Место на открытом воздухе. {label}"
    assert _judge(_case(), [p], [_rec(p, "unknown", notes=note)])["honesty_violations"] == {}


def test_holiday_downgrade_is_labeled_and_open_on_holiday_is_not_allowed():
    p = _poi("a", hours="Mo-Su 09:00-20:00")
    case = {**_case(), "when": "2026-10-26T14:00"}
    label = "Государственный праздник: часы работы могут отличаться, уточните."
    assert _judge(case, [p], [_rec(p, "unknown", notes=label)])["honesty_violations"] == {}
    assert (
        metrics.OPEN_ON_HOLIDAY
        in _judge(case, [p], [_rec(p, "open", notes=label)])["honesty_violations"]["a"]
    )


def test_a_round_the_clock_place_may_be_open_on_a_holiday_only_with_the_caveat():
    p = _poi("a", hours="24/7")
    case = {**_case(), "when": "2026-10-26T14:00"}
    label = "Государственный праздник: часы работы могут отличаться, уточните."
    assert _judge(case, [p], [_rec(p, "open", notes=label)])["honesty_violations"] == {}
    assert (
        metrics.OPEN_ON_HOLIDAY in _judge(case, [p], [_rec(p, "open")])["honesty_violations"]["a"]
    )


def test_category_walk_indoor_kids_and_step_free_rules():
    park = _poi("p", "park_garden", hours="24/7")
    bar = _poi("b", "bar_nightlife", hours="24/7", wheelchair="no")
    case = _case(
        allowed_categories=["cafe"],
        forbidden_categories=["bar_nightlife"],
        max_walk_min_one_way=5,
        indoor_preferred=True,
        kids_ok=True,
        step_free=True,
    )
    v = _judge(case, [park, bar], [_rec(park, "open", walk=9), _rec(bar, "open")])
    assert set(v["constraint_violations"]["p"]) == {
        metrics.CATEGORY_NOT_ALLOWED,
        metrics.WALK_TOO_LONG,
        metrics.OUTDOOR_IN_BAD_AIR_OR_COLD,
    }
    assert set(v["constraint_violations"]["b"]) == {
        metrics.CATEGORY_NOT_ALLOWED,
        metrics.CATEGORY_FORBIDDEN,
        metrics.KIDS_UNSUITABLE,
        metrics.NOT_STEP_FREE,
    }


def test_wifi_claim_needs_data_support_and_negative_label_is_not_a_claim():
    bare = _poi("a", hours="24/7")
    case = _case(needs_wifi_socket=True)
    ok = _rec(bare, "open", notes="Wi-Fi/розетки в данных не подтверждены.")
    assert _judge(case, [bare], [ok])["honesty_violations"] == {}
    claim = _rec(bare, "open", why="В кафе есть Wi-Fi и розетки.")
    assert _judge(case, [bare], [claim])["honesty_violations"] == {
        "a": [metrics.WIFI_CLAIM_UNSUPPORTED]
    }
    hedged = _rec(
        bare, "open", notes="Наличие Wi-Fi не подтверждено в данных, но типично для сети."
    )
    assert _judge(case, [bare], [hedged])["honesty_violations"] == {}
    with_wifi = _poi("w", hours="24/7", internet_access="wlan")
    assert (
        _judge(case, [with_wifi], [_rec(with_wifi, "open", why="Есть Wi-Fi.")])[
            "honesty_violations"
        ]
        == {}
    )


def test_same_chain_duplicates_and_over_budget():
    a = _poi("a", hours="24/7", name="Starbucks")
    b = _poi("b", hours="24/7", name="STARBUCKS")
    route = {"stops": ["a", "b"], "legs_min": [3, 2], "stay_min": [30, 30], "total_min": 70}
    v = _judge(_case(), [a, b], [_rec(a, "open"), _rec(b, "open")], route)
    assert v["duplicate_chains"] == [["a", "b"]]
    assert v["over_budget"]
    assert {metrics.DUPLICATE_CHAIN, metrics.OVER_BUDGET} <= set(v["violations"])


def test_route_closed_stops_are_informational():
    early = _poi("a", hours="Mo-Su 08:00-14:10")
    late = _poi("b", hours="Mo-Su 09:00-20:00", name="Sushi Bar")
    route = {"stops": ["a", "b"], "legs_min": [3, 5], "stay_min": [30, 30], "total_min": 80}
    v = _judge(
        _case(budget_min=120), [early, late], [_rec(early, "open"), _rec(late, "open")], route
    )
    assert v["route_closed_stops"] == []
    route["stops"] = ["b", "a"]
    v = _judge(
        _case(budget_min=120), [early, late], [_rec(early, "open"), _rec(late, "open")], route
    )
    assert v["route_closed_stops"] == ["a"]
    assert v["all_ok"]


def test_empty_answer_is_not_ok():
    v = _judge(_case(), [], [])
    assert v["violations"] == [metrics.NO_RECS]
    assert not v["coverage_ok"]


@pytest.mark.parametrize(
    ("values", "q", "expected"),
    [([], 90, None), ([5], 90, 5), (list(range(1, 11)), 90, 9), (list(range(1, 11)), 50, 5)],
)
def test_percentile_is_nearest_rank(values, q, expected):
    assert percentile([float(v) for v in values], q) == expected


def test_write_summaries_names_files_after_dotted_dataset(tmp_path, monkeypatch):
    case = load_cases()[0]
    poi = _poi("a", hours="24/7")
    rec = {**_rec(poi, "open"), "source": "osm"}
    run = {
        "case_id": case["id"],
        "dataset": "poi.enriched",
        "mode": "offline",
        "model_link": "template",
        "generation_note": "",
        "recs": [rec],
        "route": None,
        "timings": {"total": 3, "generation": 1},
        "verdict": {},  # recomputed on load
    }
    monkeypatch.setattr(report, "_index", lambda _dataset: metrics.dataset_index([poi]))
    (tmp_path / "runs_poi.enriched_offline.jsonl").write_text(
        json.dumps(run) + "\n", encoding="utf-8"
    )
    assert list(write_summaries(tmp_path)) == [("poi.enriched", "offline")]
    for suffix in ("json", "md"):
        assert (tmp_path / f"summary_poi.enriched_offline.{suffix}").is_file()
