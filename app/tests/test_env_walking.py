"""Transit stations, LRT hints, sunset / air quality, holidays and real walking times (fixture data, no network)."""

from __future__ import annotations

import http.server
import io
import json
import threading
import urllib.error
from datetime import date, datetime, timedelta
from pathlib import Path

import pytest

from walks import walking
from walks.holidays import HOLIDAYS, holiday_name
from walks.hours import hours_check, hours_state
from walks.models import Intent, Recommendation, load_pois
from walks.pipeline import PUBLIC_ORIGINS, recommend
from walks.presets import PRESETS
from walks.retrieve import DARK_OUTDOOR_PENALTY, retrieve
from walks.sun import computed_sun_times, is_dark, sun_for
from walks.transit import attach_lrt_hints
from walks.walking import WalkingRouter, straight_leg
from walks.weather import OUTDOOR_CATEGORIES, make_weather, manual_weather

FIXTURE = Path(__file__).parent / "fixtures" / "poi_sample.json"
DAY = datetime(2026, 10, 14, 14, 0)  # Wednesday afternoon (sun is up until ~17:30)
EVENING = datetime(2026, 10, 14, 19, 0)  # after sunset (~17:30), cafes still open
CALM = make_weather(10, 10, pm25=5)  # nothing adverse; sun times come from the local calculation


@pytest.fixture(scope="module")
def pois():
    return load_pois(FIXTURE)


# ---- transit stations ----------------------------------------------------------------------------


def test_transit_station_never_recommended(pois):
    stations = {p.id for p in pois if p.category == "transit_station"}
    assert len(stations) == 3
    for name in ("Mega Silk Way", "Байтерек", "EXPO"):
        lat, lon = PRESETS[name]
        for intent in (
            Intent(time_budget_min=240),
            Intent(time_budget_min=240, categories=["cafe", "park_garden"]),
        ):
            res = retrieve(pois, lat, lon, intent, DAY)
            assert not stations & {c.poi.id for c in res.candidates}
            assert res.filters.in_radius > 0
    rec = recommend(
        "метро или вокзал рядом", *PRESETS["Mega Silk Way"], DAY, use_llm=False, pois=pois
    )
    assert not stations & {r.poi.id for r in rec.recs}


def _rec(pois, poi_id, distance_m) -> Recommendation:
    poi = next(p for p in pois if p.id == poi_id)
    return Recommendation(
        poi=poi,
        why="w",
        time_on_site_min=30,
        what_to_do="x",
        confidence="high",
        generated_idea=False,
        distance_m=distance_m,
        walk_min=1,
        travel_min=1,
        hours_state="unknown",
        hours_raw=None,
        text_source="template",
    )


def test_lrt_hint_when_user_and_far_rec_are_near_stations(pois):
    lat, lon = PRESETS["Mega Silk Way"]
    far, near = _rec(pois, "node/20", 4300), _rec(pois, "node/12", 200)
    note = attach_lrt_hints(pois, lat, lon, [far, near], "walk")
    assert far.lrt_hint == "LRT: Университет → Байтерек (проверьте расписание)"
    assert near.lrt_hint is None  # closer than 1.5 km: walking is enough
    assert "Университет" in note
    assert not any(ch.isdigit() for ch in far.lrt_hint)  # no times, no prices


def test_lrt_hint_absent_when_no_station_near_user_or_rec_or_in_car_mode(pois):
    far = _rec(pois, "node/20", 4300)
    attach_lrt_hints(pois, 51.0600, 71.4500, [far], "walk")  # > 600 m from any station
    assert far.lrt_hint is None
    far_no_station = _rec(pois, "node/40", 4300)  # airport: no LRT station in the fixture nearby
    attach_lrt_hints(pois, *PRESETS["Mega Silk Way"], [far_no_station], "walk")
    assert far_no_station.lrt_hint is None
    far2 = _rec(pois, "node/20", 4300)
    assert "на машине" in attach_lrt_hints(pois, *PRESETS["Mega Silk Way"], [far2], "car")
    assert far2.lrt_hint is None
    rail_only = [
        p for p in pois if p.id != "way/9001"
    ]  # without the LRT station only the rail station is left
    far3 = _rec(pois, "node/20", 4300)
    attach_lrt_hints(rail_only, *PRESETS["Mega Silk Way"], [far3], "walk")
    assert far3.lrt_hint is None  # a railway station is not an LRT station


# ---- sunset / darkness ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("d", "sunrise", "sunset"),
    [
        (
            date(2026, 10, 16),
            (6, 39),
            (17, 20),
        ),  # Open-Meteo daily values for 51.13, 71.43 (UTC+5), fetched 2026-10-16
        (date(2026, 10, 17), (6, 40), (17, 17)),
    ],
)
def test_computed_sun_times_match_open_meteo(d, sunrise, sunset):
    rise, sset = computed_sun_times(d)
    for got, want in ((rise, sunrise), (sset, sunset)):
        assert abs((got.hour * 60 + got.minute) - (want[0] * 60 + want[1])) <= 3


def test_sun_for_is_always_the_calculation():
    rise, sset, source = sun_for(date(2026, 10, 14))
    assert (rise, sset) == computed_sun_times(date(2026, 10, 14))
    assert source == "расчёт"


def test_is_dark_cases():
    w = make_weather(5, 5)
    rise, sset = computed_sun_times(date(2026, 10, 14))
    assert not is_dark(w, datetime(2026, 10, 14, 12, 0))
    assert is_dark(w, datetime.combine(date(2026, 10, 14), sset) + timedelta(minutes=1))
    assert is_dark(w, datetime.combine(date(2026, 10, 14), rise) - timedelta(minutes=1))
    assert not is_dark(None, datetime(2026, 10, 14, 23, 0))  # adaptation switched off
    assert is_dark(manual_weather(5, force_dark=True), datetime(2026, 10, 14, 12, 0))


def test_after_sunset_penalizes_outdoor_places(pois):
    lat, lon = PRESETS["EXPO"]
    intent = Intent(time_budget_min=120, categories=["park_garden", "viewpoint", "cafe"])
    by_id = lambda res: {c.poi.id: c for c in res.candidates}  # noqa: E731
    day = by_id(retrieve(pois, lat, lon, intent, DAY, weather=CALM))
    night = by_id(retrieve(pois, lat, lon, intent, EVENING, weather=CALM))
    night_off = by_id(
        retrieve(pois, lat, lon, intent, EVENING, weather=None)
    )  # adaptation switched off

    park = "node/5"  # 24/7 park: open at both times
    assert "dark_outdoor" not in day[park].reasons
    assert "dark_outdoor" in night[park].reasons
    assert "dark_outdoor" not in night_off[park].reasons
    assert night_off[park].score - night[park].score == pytest.approx(
        DARK_OUTDOOR_PENALTY, abs=1e-6
    )
    assert "dark_indoor" in night["node/3"].reasons
    assert "dark_outdoor" not in night["node/3"].reasons

    res = retrieve(pois, lat, lon, intent, EVENING, weather=CALM)
    assert res.filters.dark
    assert not retrieve(pois, lat, lon, intent, DAY, weather=CALM).filters.dark
    assert res.filters.sunset
    assert res.filters.sun_source == "расчёт"


def test_after_sunset_reason_is_said(pois):
    res = recommend(
        "парк или кафе на 2 часа", *PRESETS["EXPO"], EVENING, use_llm=False, pois=pois, weather=CALM
    )
    assert {r.poi.category for r in res.recs} & OUTDOOR_CATEGORIES
    assert {r.poi.category for r in res.recs} & {"cafe"}
    for r in res.recs:
        if r.poi.category in OUTDOOR_CATEGORIES:
            assert "После заката" in r.notes
        elif r.poi.category in {"cafe", "museum_gallery", "mall"}:
            assert (
                "после заката" not in r.why.lower()
            )  # the person named the café: the dark did not choose it


# ---- air quality ---------------------------------------------------------------------------------


def test_polluted_air_prefers_indoor_and_says_why(pois):
    lat, lon = PRESETS["EXPO"]
    smog = make_weather(10, 10, pm25=80)
    res = retrieve(pois, lat, lon, Intent(time_budget_min=120), DAY, weather=smog)
    assert res.filters.air_bad
    assert res.filters.weather_adapted
    assert res.candidates[0].poi.category not in OUTDOOR_CATEGORIES
    assert res.filters.radius_effective_m <= 600
    rec = recommend(
        "где переждать на 2 часа", lat, lon, DAY, use_llm=False, pois=pois, weather=smog
    )
    assert rec.recs[0].poi.category not in OUTDOOR_CATEGORIES
    assert rec.weather is not None
    assert rec.weather.air_bad
    assert "оздух загрязнён" not in rec.recs[0].why  # never repeated on every card
    assert all(
        "загрязнён" in r.notes and r.time_on_site_min <= 20
        for r in rec.recs
        if r.poi.category in OUTDOOR_CATEGORIES
    )


# ---- holidays ------------------------------------------------------------------------------------


def test_holiday_list_matches_official_sources():
    for d in (
        date(2026, 3, 9),
        date(2026, 3, 24),
        date(2026, 3, 25),
        date(2026, 5, 11),
        date(2026, 5, 27),
        date(2026, 10, 26),
        date(2026, 12, 16),
        date(2027, 3, 15),
        date(2027, 5, 3),
        date(2027, 5, 10),
    ):
        assert holiday_name(d), d
    for d in (date(2026, 8, 30), date(2027, 8, 30), date(2026, 12, 31), date(2026, 10, 16)):
        assert holiday_name(d) is None, (
            d
        )  # Constitution Day moved to 15 March by Law 306-VIII (11.06.2026)
    assert all(d.year in (2026, 2027) for d in HOLIDAYS)


def test_open_becomes_unknown_on_holiday_closed_stays_closed():
    raw = "Mo-Su 10:00-22:00"
    ordinary, holiday = (
        datetime(2026, 5, 12, 12, 0),
        datetime(2026, 5, 11, 12, 0),
    )  # Tue / transferred day off
    assert hours_check(raw, ordinary) == ("open", "")
    state, note = hours_check(raw, holiday)
    assert state == "unknown"
    assert note == "праздник: День Победы (перенос)"
    assert hours_state(raw, holiday) == "unknown"
    assert hours_state(raw, datetime(2026, 5, 11, 23, 30)) == "closed"
    # round the clock does not depend on the day: it stays open, with the holiday caveat in the note
    assert hours_check("24/7", datetime(2026, 5, 11, 3, 0)) == (
        "open",
        "праздник: День Победы (перенос)",
    )
    assert hours_state("Mo-Su 00:00-24:00", datetime(2026, 5, 11, 3, 0)) == "open"


def test_holiday_in_retrieval_and_recommendations(pois):
    lat, lon = PRESETS["EXPO"]
    holiday = datetime(2026, 10, 26, 12, 0)  # Monday, transferred Republic Day
    res = retrieve(pois, lat, lon, Intent(time_budget_min=120, categories=["cafe"]), holiday)
    assert res.filters.holiday == "День Республики Казахстан (перенос)"
    assert res.candidates
    assert all(c.hours_state != "open" for c in res.candidates)
    cafe = next(c for c in res.candidates if c.poi.id == "node/3")  # Mo-Su 08:00-22:00
    assert cafe.hours_state == "unknown"
    assert cafe.hours_note.startswith("праздник")
    rec = recommend("кофе", lat, lon, holiday, use_llm=False, pois=pois)
    shown = next(r for r in rec.recs if r.poi.id == "node/3")
    assert shown.hours_state == "unknown"
    assert "праздник" in shown.hours_note
    assert "Государственный праздник" in shown.notes
    ordinary = retrieve(
        pois,
        lat,
        lon,
        Intent(time_budget_min=120, categories=["cafe"]),
        datetime(2026, 10, 27, 12, 0),
    )
    assert ordinary.filters.holiday is None
    assert next(c for c in ordinary.candidates if c.poi.id == "node/3").hours_state == "open"


# ---- real walking times --------------------------------------------------------------------------


def _valhalla_opener(calls, *, meters_km=0.62, seconds=451):
    def opener(req, timeout):
        calls.append((req, timeout))
        return io.BytesIO(
            json.dumps({"trip": {"summary": {"length": meters_km, "time": seconds}}}).encode()
        )

    return opener


def _blocked(calls):
    def opener(req, timeout):
        calls.append(req)
        raise urllib.error.URLError("network blocked")

    return opener


def test_valhalla_leg_parsed_cached_and_polite(tmp_path):
    calls: list = []
    sleeps: list[float] = []
    clock = [100.0]
    router = WalkingRouter(
        tmp_path / "cache.json",
        opener=_valhalla_opener(calls),
        sleep=sleeps.append,
        clock=lambda: clock[0],
    )
    a, b, c = (51.0890, 71.4160), (51.0894, 71.4180), (51.0870, 71.4120)
    leg = router.leg(a, b, persist=True)
    assert (leg.distance_m, leg.minutes, leg.method, leg.from_cache) == (620, 8, "valhalla", False)
    req, timeout = calls[0]
    body = json.loads(req.data)
    assert timeout == 5.0
    assert body["costing"] == "pedestrian"
    assert len(body["locations"]) == 2
    assert req.full_url == "https://valhalla1.openstreetmap.de/route"
    assert "astana-walks" in req.get_header("User-agent")

    again = router.leg(a, b, persist=True)
    reverse = router.leg(
        b, a, persist=True
    )  # walking is close to symmetric: the reverse leg reuses the entry
    assert again.from_cache
    assert reverse.from_cache
    assert len(calls) == 1

    router.leg(a, c, persist=True)  # second network call right away -> the router waits ~1 s first
    assert len(calls) == 2
    assert sleeps
    assert sleeps[0] == pytest.approx(1.1)

    fresh = WalkingRouter(tmp_path / "cache.json", opener=_blocked([]), sleep=lambda s: None)
    assert fresh.leg(a, b).from_cache  # survives a restart: the demo needs no network
    stored = json.loads((tmp_path / "cache.json").read_text(encoding="utf-8"))
    assert set(stored) == {"51.0890,71.4160>51.0894,71.4180", "51.0890,71.4160>51.0870,71.4120"}


def test_walks_valhalla_url_points_the_router_to_one_s_own_instance(tmp_path, monkeypatch):
    own = "http://127.0.0.1:8002/route"
    monkeypatch.setenv("WALKS_VALHALLA_URL", f"  {own} ")
    calls: list = []
    sleeps: list[float] = []
    router = WalkingRouter(
        tmp_path / "cache.json", opener=_valhalla_opener(calls), sleep=sleeps.append
    )
    router.leg((51.0890, 71.4160), (51.0894, 71.4180))
    router.leg((51.0890, 71.4160), (51.0870, 71.4120))
    assert [req.full_url for req, _ in calls] == [own, own]
    assert not sleeps  # no politeness pause towards one's own server


def test_valhalla_url_default_and_explicit_argument_win(tmp_path, monkeypatch):
    monkeypatch.setenv("WALKS_VALHALLA_URL", "http://own.example/route")
    calls: list = []
    explicit = WalkingRouter(
        tmp_path / "c.json",
        opener=_valhalla_opener(calls),
        sleep=lambda s: None,
        url="http://explicit.example/route",
    )
    explicit.leg((51.0890, 71.4160), (51.0894, 71.4180))
    assert calls[0][0].full_url == "http://explicit.example/route"
    monkeypatch.delenv("WALKS_VALHALLA_URL")
    assert walking.valhalla_url() == walking.VALHALLA_URL
    monkeypatch.setenv("WALKS_VALHALLA_URL", "   ")
    assert walking.valhalla_url() == walking.VALHALLA_URL  # blank = unset


def test_user_origin_never_written_to_disk(tmp_path):
    router = WalkingRouter(
        tmp_path / "cache.json", opener=_valhalla_opener([]), sleep=lambda s: None
    )
    leg = router.leg((51.0951, 71.4101), (51.0894, 71.4180), persist=False)
    assert leg.method == "valhalla"
    assert not (tmp_path / "cache.json").exists()
    assert router.leg((51.0951, 71.4101), (51.0894, 71.4180)).from_cache  # still memoised in memory


def test_pipeline_persists_only_public_origins(pois, tmp_path):
    cache = tmp_path / "cache.json"
    router = WalkingRouter(cache, opener=_valhalla_opener([]), sleep=lambda s: None)
    assert (51.089, 71.416) in PUBLIC_ORIGINS
    recommend(
        "кофе", 51.0951, 71.4101, DAY, use_llm=False, pois=pois, router=router
    )  # a user's own point
    keys = list(json.loads(cache.read_text(encoding="utf-8"))) if cache.exists() else []
    assert not any(
        k.startswith("51.0951,71.4101") or ">51.0951,71.4101" in k for k in keys
    )  # only POI-POI legs
    router2 = WalkingRouter(cache, opener=_valhalla_opener([]), sleep=lambda s: None)
    recommend("кофе", *PRESETS["EXPO"], DAY, use_llm=False, pois=pois, router=router2)
    keys = json.loads(cache.read_text(encoding="utf-8"))
    assert any(k.startswith("51.0890,71.4160>") for k in keys)


def test_walking_fallback_is_labelled_when_network_blocked(pois):
    calls: list = []
    router = WalkingRouter(False, opener=_blocked(calls), sleep=lambda s: None)
    res = recommend("кофе", *PRESETS["EXPO"], DAY, use_llm=False, pois=pois, router=router)
    assert res.recs
    assert all(r.walk_method == "straight" for r in res.recs)
    assert res.route is not None
    assert res.route.method == "straight"
    assert set(res.route.legs_method) == {"straight"}
    assert res.walk_stats.get("straight", 0) >= 1
    assert "valhalla" not in res.walk_stats
    assert len(calls) == 1  # after the first failure the router stops trying for a minute
    r = res.recs[0]
    straight = straight_leg(PRESETS["EXPO"], (r.poi.lat, r.poi.lon))
    assert (r.distance_m, r.walk_min) == (
        straight.distance_m,
        straight.minutes,
    )  # straight line x 1.3 at 4.5 km/h


def test_valhalla_times_used_for_cards_and_route(pois):
    router = WalkingRouter(False, opener=_valhalla_opener([]), sleep=lambda s: None)
    res = recommend("кофе", *PRESETS["EXPO"], DAY, use_llm=False, pois=pois, router=router)
    assert all(
        r.walk_method == "valhalla" and (r.distance_m, r.walk_min) == (620, 8) for r in res.recs
    )
    assert res.route.method == "valhalla"
    assert set(res.route.legs_m) == {620}
    assert res.walk_stats["valhalla"] >= 1


def test_non_walk_modes_do_not_call_routing(pois):
    calls: list = []
    router = WalkingRouter(False, opener=_valhalla_opener(calls), sleep=lambda s: None)
    res = recommend(
        "кофе на машине", *PRESETS["EXPO"], DAY, use_llm=False, pois=pois, router=router
    )
    assert res.intent.intent.mode == "car"
    assert not calls
    assert all(r.walk_method == "estimate" for r in res.recs)
    assert res.route.method == "estimate"


# ---- the pinned demo router and one's own Valhalla ------------------------------------------------


def _shipped_leg_points() -> tuple[tuple[float, float], tuple[float, float]]:
    cached = json.loads(walking.SHIPPED_CACHE_PATH.read_text(encoding="utf-8"))
    a, _, b = next(iter(cached)).partition(">")
    pa, pb = (tuple(map(float, x.split(","))) for x in (a, b))
    return pa, pb  # type: ignore[return-value]


@pytest.fixture
def own_valhalla():
    """A tiny local Valhalla: answers every /route with 1.234 km, 900 s and records the request bodies."""
    bodies: list[dict] = []

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            bodies.append(json.loads(self.rfile.read(int(self.headers["Content-Length"]))))
            out = json.dumps(
                {"trip": {"summary": {"length": 1.234, "time": 900.0}, "legs": [{"shape": ""}]}}
            ).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(out)))
            self.end_headers()
            self.wfile.write(out)

        def log_message(self, *args):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{server.server_address[1]}/route", bodies
    server.shutdown()
    server.server_close()


@pytest.mark.parametrize("env", [None, walking.VALHALLA_URL])
def test_pinned_router_without_an_own_valhalla_never_touches_the_network(monkeypatch, env):
    """The demo default: a leg that is not in data/walk_cache.json is the straight line, whatever the env says
    about the public FOSSGIS server (it is never asked on the pinned path)."""
    if env:
        monkeypatch.setenv("WALKS_VALHALLA_URL", env)
    router = walking.shipped_router()
    assert not router.network
    assert not walking.own_router()
    hit = router.leg(*_shipped_leg_points())
    assert (hit.method, hit.from_cache) == ("valhalla", True)
    assert router.leg((51.0, 71.0), (51.5, 71.5)).method == "straight"
    assert router.network_calls == 0


def test_pinned_router_with_an_own_valhalla_asks_it_for_a_miss_and_persists_nothing(
    monkeypatch, own_valhalla
):
    url, bodies = own_valhalla
    monkeypatch.setenv("WALKS_VALHALLA_URL", url)
    before = walking.SHIPPED_CACHE_PATH.read_bytes()
    router = walking.shipped_router()
    assert router.network

    assert router.leg(
        *_shipped_leg_points()
    ).from_cache  # a recorded leg: the cache, not the server
    assert not bodies

    miss = router.leg((51.0, 71.0), (51.5, 71.5), persist=True)
    assert (miss.method, miss.distance_m, miss.minutes, miss.from_cache) == (
        "valhalla",
        1234,
        15,
        False,
    )
    assert len(bodies) == 1
    assert bodies[0]["costing"] == "pedestrian"
    assert router.leg((51.0, 71.0), (51.5, 71.5)).from_cache  # remembered in memory
    assert len(bodies) == 1
    assert walking.SHIPPED_CACHE_PATH.read_bytes() == before  # nothing written to the tracked cache


def test_read_only_router_never_writes_its_disk_cache(tmp_path):
    path = tmp_path / "cache.json"
    router = WalkingRouter(path, opener=_valhalla_opener([]), sleep=lambda s: None, read_only=True)
    a, b = (51.0890, 71.4160), (51.0894, 71.4180)
    assert router.leg(a, b, persist=True).method == "valhalla"
    assert router.leg(a, b, persist=True).from_cache  # memory
    assert not path.exists()


def test_the_memory_of_a_router_is_bounded(monkeypatch):
    monkeypatch.setattr(walking, "MAX_MEM_LEGS", 2)
    calls: list = []
    router = WalkingRouter(False, opener=_valhalla_opener(calls), sleep=lambda s: None)
    legs = [((51.0890, 71.4160), (51.0894 + i * 0.001, 71.4180)) for i in range(3)]
    for a, b in legs:
        router.leg(a, b)
    assert len(router._mem) == 2
    assert router.leg(*legs[2]).from_cache  # the newest stays
    router.leg(*legs[0])  # the oldest was dropped: asked again
    assert len(calls) == 4
