"""A wish the person NAMES beats the system's defaults (shelter rule, darkness, time fit, padding, the late-home bias):
the conditions only order inside the kind and are said as advice. A profile's «не показывать» is a hard exclusion unless
the kind is named now. Settings that change the answer say once what they did, with honest counts."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from walks import city_layers
from walks.bookmarks import prefer_toward
from walks.dialog import TurnEnv, new_state, take_turn
from walks.intent import parse_rules
from walks.models import POI, Bookmark, Candidate, WeatherWarning
from walks.profile import Profile
from walks.shelter import outdoor_wish
from walks.stay import NAMED_OVER_BUDGET, fit_stay_budget
from walks.walking import offline_router
from walks.weather import make_weather

ORIGIN = (51.1283, 71.4305)
DEG_M = 111_320.0
EVENING = datetime(2026, 10, 20, 21, 42)
NMU = WeatherWarning(
    kind="nmu", title="НМУ", text="x", source_url="https://www.kazhydromet.kz/", active=True
)


def _poi(poi_id: str, north_m: float, category: str, **kw) -> POI:
    return POI(
        id=poi_id,
        name=poi_id,
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        opening_hours=kw.pop("hours", "24/7"),
        **kw,
    )


def _city() -> list[POI]:
    return [
        _poi("park1", 200, "park_garden"),
        _poi("park2", 350, "park_garden"),
        _poi("fountain", 300, "attraction_landmark"),
        _poi("cafe1", 80, "cafe"),
        _poi("cafe2", 120, "cafe"),
        _poi("mall1", 150, "mall"),
        _poi("bar1", 160, "bar_nightlife"),
    ]


def _nmu():
    return make_weather(8, 8, 0.0, 0.0, warnings=[NMU], source="met-no")


def _turns(*messages, weather=None, profile=None, when=EVENING):
    env = TurnEnv(
        when=when,
        weather=weather,
        use_llm=False,
        router=offline_router(),
        pois=_city(),
        profile=profile,
    )
    state, out = new_state(*ORIGIN), None
    for message in messages:
        out = take_turn(state, message, env)
        state = out.state
    assert out is not None
    return out


def test_the_words_name_a_wish_a_mood_does_not():
    assert outdoor_wish(parse_rules("Где прогуляться можно щас?").intent)
    assert outdoor_wish(parse_rules("хочу в парк").intent)
    assert "cafe" in parse_rules("хочу кофе").intent.wished
    assert parse_rules("куда сходить на 2 часа").intent.wished == []
    assert not outdoor_wish(parse_rules("куда сходить с ребёнком").intent)


@pytest.mark.parametrize("message", ["Где прогуляться можно щас?", "Я именно погулять хочу"])
def test_a_walk_under_the_nmu_after_dark_stays_outdoors_and_is_said_as_advice(message):
    out = _turns(message, weather=_nmu())
    assert out.turn.kind == "places"
    assert {p.category for p in out.turn.places} <= {"park_garden", "attraction_landmark"}
    assert (
        all(p.padding in ("none", "expanded") for p in out.turn.places)
        if hasattr(out.turn.places[0], "padding")
        else True
    )
    reply = out.turn.reply
    assert "Вы ищете, где прогуляться" in reply  # the person's own terms, never «уютное место»
    assert "в помещении" not in reply
    assert "гулять лучше недолго" in reply


def test_the_correction_after_a_walk_answer_is_still_a_walk():
    out = _turns("Где прогуляться можно щас?", "Я именно погулять хочу", weather=_nmu())
    assert {p.category for p in out.turn.places} <= {"park_garden", "attraction_landmark"}


def test_without_a_stated_wish_the_conditions_still_steer_indoors():
    out = _turns("куда сходить на 2 часа, холодно", weather=_nmu())
    assert {p.category for p in out.turn.places} <= {"cafe", "mall", "museum_gallery"}


def test_a_walk_is_never_padded_with_a_cafe(tmp_path):
    pois = [_poi("park1", 200, "park_garden"), _poi("cafe1", 80, "cafe"), _poi("cafe2", 90, "cafe")]
    env = TurnEnv(when=EVENING, weather=_nmu(), use_llm=False, router=offline_router(), pois=pois)
    out = take_turn(new_state(*ORIGIN), "хочу погулять", env)
    assert [p.id for p in out.turn.places] == ["park1"]


def test_a_lit_street_lifts_the_park_after_dark_and_the_lead_says_so(tmp_path, monkeypatch):
    way = {
        "id": 1,
        "lit": "yes",
        "geometry": [
            [ORIGIN[0] + 0.0035, ORIGIN[1] - 0.0005],
            [ORIGIN[0] + 0.0035, ORIGIN[1] + 0.0005],
        ],
    }
    (tmp_path / "lit.json").write_text(json.dumps([way]), encoding="utf-8")
    monkeypatch.setenv("WALKS_CITY_DIR", str(tmp_path))
    assert city_layers.lit_near(ORIGIN[0] + 0.0033, ORIGIN[1])
    assert not city_layers.lit_near(
        ORIGIN[0] + 0.0010, ORIGIN[1]
    )  # no tag is no verdict, never «dark»
    out = _turns("хочу погулять", weather=_nmu())
    assert out.turn.places[0].id == "park2"  # farther, but beside the lit street
    assert "освещённых улиц" in out.turn.reply


def test_the_late_home_bias_never_replaces_the_named_kind():
    home = Bookmark(name="Дом", kind="home", lat=ORIGIN[0] + 0.01, lon=ORIGIN[1])

    def cand(poi_id, north_m, cat):
        poi = _poi(poi_id, north_m, cat)
        return Candidate(
            poi=poi, distance_m=100, walk_min=2, travel_min=2, hours_state="open", score=1
        )

    bars_away = cand("bar_away", -300, "bar_nightlife")
    cafe_toward = cand("cafe_home", 600, "cafe")
    kept = prefer_toward(
        [bars_away, cafe_toward], ORIGIN, home, along=False, kinds=frozenset({"bar_nightlife"})
    )
    assert kept[0].poi.id == "bar_away"


def test_a_named_kind_is_kept_when_its_usual_stay_does_not_fit():
    cinema = Candidate(
        poi=_poi("c", 100, "culture_theatre_cinema"),
        distance_m=100,
        walk_min=2,
        travel_min=2,
        hours_state="open",
        score=1,
    )
    cafe = Candidate(
        poi=_poi("k", 100, "cafe"),
        distance_m=100,
        walk_min=2,
        travel_min=2,
        hours_state="open",
        score=1,
    )
    kept, _ = fit_stay_budget([cinema, cafe], 30, frozenset({"culture_theatre_cinema"}))
    assert {c.poi.id for c in kept} == {"c", "k"}
    assert NAMED_OVER_BUDGET in next(c for c in kept if c.poi.id == "c").reasons


def test_the_profile_avoid_is_a_hard_exclusion_unless_the_kind_is_named_now():
    profile = Profile(avoid=["bar_nightlife", "mall"])
    out = _turns("холодно, куда сходить", profile=profile)
    assert out.turn.places
    assert not {p.category for p in out.turn.places} & {"bar_nightlife", "mall"}
    named = _turns("хочу в бар", profile=profile)
    assert "bar_nightlife" in {p.category for p in named.turn.places}
    only_cafe = TurnEnv(
        when=EVENING,
        use_llm=False,
        router=offline_router(),
        pois=[_poi("cafe1", 100, "cafe")],
        profile=Profile(
            avoid=["cafe", "mall", "museum_gallery", "culture_theatre_cinema", "coworking_library"]
        ),
    )
    empty = take_turn(new_state(*ORIGIN), "холодно, куда сходить", only_cafe)
    assert empty.turn.kind == "none_found"  # the honest «ничего не нашлось», no bar brought back


def test_halal_is_ranked_with_the_flag_and_said_once_with_the_real_count():
    halal = _poi("h", 300, "cafe", tags=["diet:halal=yes"])
    plain = [_poi(f"p{i}", 100 + i * 10, "cafe") for i in range(5)]
    env = TurnEnv(
        when=datetime(2026, 10, 20, 13, 0),
        use_llm=False,
        router=offline_router(),
        pois=[halal, *plain],
        profile=Profile(halal=True),
    )
    out = take_turn(new_state(*ORIGIN), "хочу поесть", env)
    assert out.result is not None
    assert out.result.intent.intent.halal
    assert out.turn.places[0].id == "h"
    assert out.turn.reply.count("Учтены ваши настройки") == 1
    assert "отмечен у 1 из 6" in out.turn.reply
    assert all("Вы отмечали" not in p.why for p in out.turn.places)
    none = TurnEnv(
        when=datetime(2026, 10, 20, 13, 0),
        use_llm=False,
        router=offline_router(),
        pois=plain,
        profile=Profile(halal=True),
    )
    said = take_turn(new_state(*ORIGIN), "хочу поесть", none).turn.reply
    assert "в данных о халяль ничего нет" in said


def test_a_paraphrase_that_drifted_from_the_wish_is_not_used():
    from walks.want import names_the_wish

    walk = parse_rules("Где прогуляться можно щас?").intent
    assert names_the_wish("Вы ищете, где прогуляться", walk)
    assert names_the_wish("Вы ищете тихий парк", walk)
    assert not names_the_wish("Вы ищете уютное место для отдыха", walk)
    assert names_the_wish(
        "Вы ищете что-нибудь", parse_rules("куда сходить").intent
    )  # no stated wish


def test_the_storm_notice_says_the_city_once():
    from walks.dialog_extras import _storm_text

    warning = WeatherWarning(
        kind="storm",
        title="Штормовое предупреждение для Астаны",
        text="Астана: 19 октября ночью и утром ожидается туман.",
        source_url="https://www.kazhydromet.kz/ru/storm",
        active=True,
    )
    assert _storm_text(warning) == "19 октября ночью и утром ожидается туман"


def test_a_named_wish_is_never_read_as_a_follow_up_by_the_model(monkeypatch):
    """«Я именно погулять хочу» after a walk answer is a new request: the model's follow-up reading is not asked."""
    calls: list[str] = []

    def spy(text, prev, **kw):
        calls.append(text)
        return None, None

    monkeypatch.setattr("walks.pipeline.refine_with_llm", spy)
    out = _turns("Где прогуляться можно щас?", "Я именно погулять хочу", weather=_nmu())
    assert out.turn.kind == "places"
    assert calls == []


def test_a_kind_named_once_lifts_the_avoid_for_that_message_only():
    profile = Profile(avoid=["mall"])
    env = TurnEnv(
        when=EVENING, use_llm=False, router=offline_router(), pois=_city(), profile=profile
    )
    first = take_turn(new_state(*ORIGIN), "хочу в торговый центр", env)
    assert "mall" in {p.category for p in first.turn.places}  # named now: the avoid is lifted
    again = take_turn(first.state, "ещё", env)  # a vague follow-up of the same dialogue
    assert "mall" not in {p.category for p in again.turn.places}
