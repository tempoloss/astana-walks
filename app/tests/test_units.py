"""Unit tests on the small fixture (no network, no real data needed)."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

import pytest

from walks import generate as gen_mod
from walks import llm, llm_providers
from walks.hours import hours_state
from walks.intent import parse_rules, parse_time_budget
from walks.llm_output import LLMOutput, LLMRec
from walks.models import Intent, LLMStep, load_pois
from walks.pipeline import recommend, round_location
from walks.presets import PRESETS
from walks.radius import reachable_radius_m
from walks.retrieve import retrieve
from walks.route import build_route

FIXTURE = Path(__file__).parent / "fixtures" / "poi_sample.json"


@pytest.fixture(autouse=True)
def _reasons_not_checked_for_facts(monkeypatch):
    """These tests are about the chain, the cache and the claims: their fake reasons are not checked for a concrete
    fact of the place (tests/test_answer_quality.py checks that)."""
    import walks.generate as generation

    monkeypatch.setattr(generation, "vague_ids", lambda *a, **k: [])


WED_NOON = datetime(2026, 10, 14, 12, 0)
WED_23 = datetime(2026, 10, 14, 23, 0)


@pytest.fixture(scope="module")
def pois():
    return load_pois(FIXTURE)


# ---- opening hours -------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("raw", "when", "expected"),
    [
        ("Mo-Fr 09:00-18:00; Sa 10:00-16:00", WED_NOON, "open"),
        ("Mo-Fr 09:00-18:00; Sa 10:00-16:00", WED_23, "closed"),
        ("Mo-Fr 09:00-18:00; Sa 10:00-16:00", datetime(2026, 10, 18, 12, 0), "closed"),  # Sunday
        ("24/7", WED_23, "open"),
        ("off", WED_NOON, "closed"),
        ("Mo-Su 10:00-02:00", datetime(2026, 10, 15, 1, 0), "open"),  # past midnight, Wed rule
        (None, WED_NOON, "unknown"),
        ("", WED_NOON, "unknown"),
        ("garbage hours", WED_NOON, "unknown"),
        ("sunrise-sunset", WED_NOON, "unknown"),
        ('Mo-Fr 09:00-18:00 || "by appointment"', WED_23, "unknown"),
    ],
)
def test_hours_state(raw, when, expected):
    assert hours_state(raw, when) == expected


# ---- intent --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("прогулка 30–60 мин", 45),
        ("на 1-2 часа", 90),
        ("2 часа до вылета", 120),
        ("полчаса", 30),
        ("1 час 30 минут", 90),
        ("I have 45 minutes", 45),
        ("two hours", 120),
        ("на час", 60),
        ("500 м от меня", None),
        ("чашка кофе", None),
    ],
)
def test_time_budget(text, minutes):
    assert parse_time_budget(text) == minutes


def test_rules_flags_and_language():
    i = parse_rules("Тихое место с кофе и розеткой, с коляской").intent
    assert i.quiet
    assert i.needs_wifi_socket
    assert i.accessibility
    assert "cafe" in i.categories
    assert i.language == "ru"
    e = parse_rules("a quiet cafe with wifi for 2 hours by car").intent
    assert e.language == "en"
    assert e.mode == "car"
    assert e.time_budget_min == 120
    assert e.quiet
    k = parse_rules("Маған жаяу серуендеуге тыныш жер керек").intent
    assert k.language == "kk"
    assert k.quiet
    assert k.mode == "walk"
    assert parse_rules("Турист, 2 часа до вылета").intent.time_budget_min == 60


@pytest.mark.parametrize(
    "text",
    [
        "интересное место на общественном транспорте на 3 часа",
        "a person who takes public transport for 2 hours",
        "подробные детали маршрута",
    ],
)
def test_rules_no_false_sport_or_kids(text):
    i = parse_rules(text).intent
    assert "sport" not in i.categories
    assert not i.with_kids


@pytest.mark.parametrize(
    "text", ["идём с детьми гулять", "with my kid", "для детей", "детская площадка", "сын и дочка"]
)
def test_rules_kids_still_detected(text):
    assert parse_rules(text).intent.with_kids


def test_rules_parser_labelled():
    res = parse_rules("кофе")
    assert res.parser == "rules"


# ---- retrieval -----------------------------------------------------------------------------------


def test_radius_scales_with_budget_and_mode():
    assert (
        reachable_radius_m(120, "walk")
        > reachable_radius_m(60, "walk")
        > reachable_radius_m(30, "walk")
    )
    assert (
        reachable_radius_m(60, "car")
        > reachable_radius_m(60, "transit")
        > reachable_radius_m(60, "walk")
    )


def test_closed_excluded_unknown_flagged(pois):
    lat, lon = PRESETS["Mega Silk Way"]
    intent = Intent(time_budget_min=120, categories=["cafe", "coworking_library", "restaurant"])
    res = retrieve(
        pois, lat, lon, intent, datetime(2026, 10, 14, 21, 0)
    )  # library (Mo-Fr 09-18) is closed
    states = {c.poi.id: c.hours_state for c in res.candidates}
    assert "node/15" not in states  # library: Mo-Fr 09-18 -> closed at 21:00
    assert states["node/17"] == "unknown"  # unparsable hours stay, flagged
    assert states["node/12"] == "open"
    assert res.filters.excluded_closed >= 1
    unknown = next(c for c in res.candidates if c.poi.id == "node/17")
    open_ = next(c for c in res.candidates if c.poi.id == "node/12")
    assert open_.score > unknown.score


def test_wheelchair_no_excluded(pois):
    lat, lon = 51.1190, 71.4450
    res = retrieve(
        pois,
        lat,
        lon,
        Intent(time_budget_min=60, accessibility=True, categories=["museum_gallery"]),
        WED_NOON,
    )
    assert all(c.poi.id != "node/50" for c in res.candidates)


# ---- privacy -------------------------------------------------------------------------------------


def test_location_rounded_everywhere(pois, monkeypatch):
    assert round_location(51.08903456, 71.41607789) == (51.089, 71.416)
    sent = {}

    def fake_generate_json(prompt, schema, **kw):
        sent["prompt"] = prompt
        raise llm.LLMUnavailable("test")

    monkeypatch.setattr(llm, "llm_available", lambda: True)
    monkeypatch.setattr(gen_mod, "generate_json", fake_generate_json)
    res = recommend("кофе", 51.08903456, 71.41607789, WED_NOON, use_llm=True, pois=pois)
    # the intent step has no key -> rules; the generation step reached the (fake) LLM
    assert (res.lat, res.lon) == (51.089, 71.416)
    assert "51.08903456" not in sent["prompt"]
    assert "71.41607789" not in sent["prompt"]
    assert '"lat"' not in sent["prompt"]  # no coordinate of the user goes to the model at all
    assert res.generation == "template"
    assert "test" in res.generation_note


# ---- generation / validation ---------------------------------------------------------------------


def _call(out: LLMOutput) -> llm.LLMCall:
    return llm.LLMCall(out, LLMStep(chain=["m"], model="m"))


def _llm_result(pois, monkeypatch, out: LLMOutput):
    monkeypatch.setattr(llm, "llm_available", lambda: True)
    monkeypatch.setattr(gen_mod, "generate_json", lambda *a, **k: _call(out))
    lat, lon = PRESETS["Mega Silk Way"]
    intent = Intent(time_budget_min=90, categories=["cafe", "park_garden"])
    cands = retrieve(pois, lat, lon, intent, WED_NOON).candidates
    return gen_mod.generate(intent, lat, lon, cands, WED_NOON), cands


def test_llm_output_validated(pois, monkeypatch):
    out = LLMOutput(
        recommendations=[
            LLMRec(
                poi_id="node/does-not-exist",
                why="Выдумка.",
                time_on_site_min=30,
                what_to_do="x",
                confidence="high",
                generated_idea=False,
            ),
            LLMRec(
                poi_id="node/12",
                why="Уютная кофейня. Всего 97 минут пешком. Сейчас открыто.",
                time_on_site_min=500,
                what_to_do="Выпейте кофе. Откроется в 07:13.",
                confidence="high",
                generated_idea=True,
                notes="Расстояние 120 м",
            ),
            LLMRec(
                poi_id="node/12",
                why="Дубликат.",
                time_on_site_min=30,
                what_to_do="x",
                confidence="high",
                generated_idea=False,
            ),
        ],
        route_order=["node/12", "node/ghost"],
    )
    g, cands = _llm_result(pois, monkeypatch, out)
    assert g.mode == "llm"
    assert [r.poi.id for r in g.recs] == ["node/12"]
    r = g.recs[0]
    c = next(c for c in cands if c.poi.id == "node/12")
    assert (r.distance_m, r.walk_min, r.hours_state) == (
        c.distance_m,
        c.walk_min,
        c.hours_state,
    )  # from code
    assert r.why.startswith("Уютная кофейня.")
    assert "минут" not in r.why  # 97 is not the walking time of the record: dropped
    assert (
        "Сейчас открыто" not in r.why
    )  # a status in the model's own words: the card's line says it (walks.status)
    assert r.what_to_do == "Выпейте кофе."
    assert "120" not in r.notes
    assert r.time_on_site_min <= 90  # clamped to the budget
    assert r.generated_idea
    assert r.text_source == "llm"
    assert g.route_order == ["node/12"]


def test_llm_all_invalid_ids_falls_back(pois, monkeypatch):
    out = LLMOutput(
        recommendations=[
            LLMRec(
                poi_id="nope",
                why="a",
                time_on_site_min=10,
                what_to_do="b",
                confidence="low",
                generated_idea=True,
            )
        ]
    )
    g, _ = _llm_result(pois, monkeypatch, out)
    assert g.mode == "template"
    assert g.recs
    assert all(r.text_source == "template" for r in g.recs)


def test_confidence_capped_by_data(pois, monkeypatch):
    out = LLMOutput(
        recommendations=[
            LLMRec(
                poi_id="node/17",
                why="Хорошо.",
                time_on_site_min=30,
                what_to_do="Еда.",
                confidence="high",
                generated_idea=False,
            )
        ]
    )
    monkeypatch.setattr(llm, "llm_available", lambda: True)
    monkeypatch.setattr(gen_mod, "generate_json", lambda *a, **k: _call(out))
    lat, lon = PRESETS["Mega Silk Way"]
    intent = Intent(time_budget_min=120, categories=["restaurant"])
    cands = retrieve(pois, lat, lon, intent, WED_NOON).candidates
    r = gen_mod.generate(intent, lat, lon, cands, WED_NOON).recs[0]
    assert r.hours_state == "unknown"
    assert r.confidence == "medium"


def test_no_key_uses_template(pois, monkeypatch):
    monkeypatch.setattr(llm_providers, "gemini_key", lambda: None)
    res = recommend("кофе рядом", *PRESETS["EXPO"], WED_NOON, pois=pois)
    assert res.intent.parser == "rules"
    assert res.generation == "template"
    assert res.recs


# ---- route ---------------------------------------------------------------------------------------


def _recs(pois, ids, stay=30):
    from walks.models import Recommendation

    by = {p.id: p for p in pois}
    return [
        Recommendation(
            poi=by[i],
            why="w",
            time_on_site_min=stay,
            what_to_do="x",
            confidence="high",
            generated_idea=False,
            distance_m=0,
            walk_min=0,
            travel_min=0,
            hours_state="unknown",
            hours_raw=None,
            text_source="template",
        )
        for i in ids
    ]


def test_route_nearest_neighbour_and_fit(pois):
    lat, lon = PRESETS["EXPO"]
    recs = _recs(pois, ["node/4", "node/52", "node/3"], stay=20)
    plan = build_route(lat, lon, recs, "walk", 120)
    assert plan
    assert plan.fits
    assert len(plan.stops) == 3
    assert not plan.dropped
    assert plan.total_min == plan.walk_min_total + plan.return_min + plan.on_site_min_total
    # first stop is the one nearest to the user
    from walks.radius import haversine_m

    nearest = min(recs, key=lambda r: haversine_m(lat, lon, r.poi.lat, r.poi.lon))
    assert plan.stops[0] == nearest.poi.id


def test_route_shrinks_then_drops(pois):
    lat, lon = PRESETS["EXPO"]
    recs = _recs(pois, ["node/4", "node/52", "node/3"], stay=60)
    shrunk = build_route(lat, lon, recs, "walk", 90)
    assert shrunk
    assert shrunk.fits
    assert shrunk.shrunk
    assert len(shrunk.stops) == 3
    assert all(s >= 10 for s in shrunk.stay_min)
    tight = build_route(lat, lon, recs, "walk", 40)
    assert tight
    assert tight.fits
    assert len(tight.stops) < 3
    assert tight.dropped
    assert build_route(lat, lon, [], "walk", 60) is None


def test_fixture_follows_contract():
    rows = json.loads(FIXTURE.read_text(encoding="utf-8"))
    for key in (
        "id",
        "name",
        "names",
        "lat",
        "lon",
        "category",
        "tags",
        "opening_hours",
        "description_auto",
        "description_source",
        "source",
        "collected_at",
    ):
        assert all(key in r for r in rows)


# ---- weather -------------------------------------------------------------------------------------


def test_weather_adverse_thresholds():
    from walks.weather import make_weather

    assert make_weather(-20, -15).adverse
    assert not make_weather(-10, -14.9).adverse
    assert make_weather(5, 3, precipitation_mm=3.0).adverse
    assert not make_weather(5, 3, precipitation_mm=1.0).adverse
    assert make_weather(5, 5, pm25=35.1).air_bad
    assert not make_weather(5, 5, pm25=35.0).air_bad
    assert not make_weather().indoor_preferred  # nothing known -> no adaptation


AIR_BODY = {"current": {"pm2_5": 80.2, "european_aqi": 120}}


def _fake_network(calls, met, *, air_ok=True):
    """MET Norway (the `met` MetServer) and the Open-Meteo air API; the station report and Kazhydromet are not
    reachable in this test."""
    import io
    import urllib.error

    def opener(req, timeout):
        url = req.full_url
        if "api.met.no" in url:
            calls.append(url)
            assert timeout == 4.0
            assert "astana-walks" in req.get_header("User-agent")
            return met(req, timeout)
        if "air-quality-api.open-meteo.com" not in url or not air_ok:
            raise urllib.error.URLError("offline")
        calls.append(url)
        assert "astana-walks" in req.get_header("User-agent")
        return io.BytesIO(json.dumps(AIR_BODY).encode())

    return opener


def _cold_met(met_server, **kwargs):
    from conftest import met_doc

    return met_server(met_doc("2026-10-14T07:00:00Z", -22.0, 80.0, 5.0, 0.0), **kwargs)


def test_weather_fetch_parses_forecast_and_caches_until_expires(met_server, monkeypatch):
    from walks import weather as wx

    monkeypatch.setenv("WALKS_AIR_DEMO", "1")
    calls: list[str] = []
    clock = [0.0]
    met = _cold_met(met_server, expires="Wed, 14 Oct 2026 07:05:00 GMT")
    opener = _fake_network(calls, met)
    w = wx.fetch_weather(opener=opener, clock=lambda: clock[0])
    assert w.adverse
    assert w.apparent_c == pytest.approx(-29.2, abs=0.05)
    assert w.wind_kmh == 18.0
    assert w.source == "met-no"
    assert w.forecast_used
    assert w.air_bad
    assert w.pm25 == 80.2
    assert w.aqi == 120
    assert len(calls) == 2
    assert any("air-quality-api.open-meteo.com" in c and "pm2_5,european_aqi" in c for c in calls)
    clock[0] = 299
    wx.fetch_weather(opener=opener, clock=lambda: clock[0])
    assert len(calls) == 2  # the forecast until its Expires (5 min), the air for 10 min
    clock[0] = 301
    wx.fetch_weather(opener=opener, clock=lambda: clock[0])
    assert len(calls) == 3  # only the forecast, revalidated
    clock[0] = 601
    wx.fetch_weather(opener=opener, clock=lambda: clock[0])
    assert len(calls) == 5


def test_weather_failures_are_independent_and_never_adapt(met_server, monkeypatch):
    import urllib.error

    from walks import weather as wx

    monkeypatch.setenv("WALKS_AIR_DEMO", "1")
    down = _cold_met(met_server, fail=urllib.error.URLError("offline"))
    w = wx.fetch_weather(opener=_fake_network([], down, air_ok=False))
    assert w.temperature_c is None
    assert w.pm25 is None
    assert not w.forecast_used
    assert not w.indoor_preferred
    wx.clear_cache()
    w = wx.fetch_weather(opener=_fake_network([], down))
    assert w.temperature_c is None
    assert w.air_bad
    assert w.indoor_preferred
    wx.clear_cache()
    w = wx.fetch_weather(opener=_fake_network([], _cold_met(met_server), air_ok=False))
    assert w.adverse
    assert w.pm25 is None
    assert not w.air_bad


def test_cold_weather_prefers_indoor(pois):
    from walks.weather import OUTDOOR_CATEGORIES, manual_weather

    lat, lon = PRESETS["EXPO"]
    intent = Intent(time_budget_min=120)
    cold = manual_weather(-30)
    calm = retrieve(pois, lat, lon, intent, WED_NOON)
    freezing = retrieve(pois, lat, lon, intent, WED_NOON, weather=cold)
    assert freezing.filters.weather_adapted
    assert not calm.filters.weather_adapted
    assert freezing.filters.radius_effective_m <= 600 < calm.filters.radius_effective_m
    assert freezing.candidates[0].poi.category not in OUTDOOR_CATEGORIES

    res = recommend(
        "площадка для ребёнка", lat, lon, WED_NOON, use_llm=False, pois=pois, weather=cold
    )
    assert res.recs
    assert res.recs[0].poi.category not in OUTDOOR_CATEGORIES
    assert "непогода" in res.recs[0].why
    outdoor = [r for r in res.recs if r.poi.category in OUTDOOR_CATEGORIES]
    assert all(r.time_on_site_min <= 20 and "оденьтесь" in r.notes for r in outdoor)


def test_unknown_weather_does_not_adapt(pois):
    lat, lon = PRESETS["EXPO"]
    res = recommend("кофе", lat, lon, WED_NOON, use_llm=False, pois=pois, weather=None)
    assert res.weather is None
    assert not res.retrieval.filters.weather_adapted


# ---- anonymised request log ----------------------------------------------------------------------


def test_request_log_is_anonymous(pois, tmp_path, monkeypatch):
    log = tmp_path / "requests.jsonl"
    monkeypatch.setenv("WALKS_REQUEST_LOG", str(log))
    text = "очень личный запрос про кофе"
    res = recommend(
        text, 51.08903456, 71.41607789, datetime(2026, 10, 14, 12, 34), use_llm=False, pois=pois
    )
    raw = log.read_text(encoding="utf-8")
    assert raw.count("\n") == 1
    row = json.loads(raw)
    assert set(row) == {
        "ts_hour",
        "cell",
        "mode",
        "time_budget_min",
        "categories",
        "flags",
        "radius_m",
        "radius_effective_m",
        "requested_nearby",
        "requested_nearby_with_hours",
        "candidates_by_padding",
        "recs_by_padding",
        "candidates",
        "recs",
        "hours_state_counts",
    }
    assert row["ts_hour"] == "2026-10-14T12:00"
    assert row["recs"] == len(res.recs)
    assert row["radius_m"] == res.retrieval.filters.radius_declared_m
    assert row["radius_effective_m"] == res.retrieval.filters.radius_effective_m
    for secret in (
        text,
        "кофе рядом",
        "51.089",
        "71.416",
        "51.08903456",
        "node/",
        res.recs[0].poi.name,
    ):
        assert secret not in raw
    from walks.reqlog import grid_cell_id

    assert row["cell"] == grid_cell_id(51.089, 71.416)
    assert grid_cell_id(51.0890, 71.4160) == grid_cell_id(51.0891, 71.4161)  # same 500 m cell
    assert grid_cell_id(51.0890, 71.4160) != grid_cell_id(51.1283, 71.4305)


def test_request_log_off_writes_nothing(pois, tmp_path):
    # conftest sets WALKS_REQUEST_LOG=off
    recommend("кофе", *PRESETS["EXPO"], WED_NOON, use_llm=False, pois=pois)
    assert not list(tmp_path.iterdir())
