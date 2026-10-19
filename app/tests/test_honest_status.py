"""Round 2 of the human testers: a status said only by code and only for one moment, never a feature or a way home the
record does not carry, chips that keep their word, conditions only when they matter, English names in English."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_place import place_from_poi
from walks.facts import checked_opening
from walks.generate import _clean, template_recs
from walks.intent import parse_rules
from walks.models import POI, Candidate
from walks.status import status_text
from walks.walking import offline_router
from walks.weather import make_weather

ORIGIN = (51.1283, 71.4305)
DEG_M = 111_320.0
BAITEREK = POI(
    id="baiterek",
    name="Байтерек",
    names={"name:en": "Baiterek"},
    lat=ORIGIN[0] + 400 / DEG_M,
    lon=ORIGIN[1],
    category="attraction_landmark",
    opening_hours="Mo-Su 10:00-21:00",
)
OVERNIGHT = POI(
    id="sultani",
    name="Sultani",
    lat=ORIGIN[0] + 300 / DEG_M,
    lon=ORIGIN[1],
    category="cafe",
    opening_hours="Mo-Su 00:00-05:00,08:00-24:00",
)


def _at(day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(2026, 10, day, hour, minute)


def _poi(poi_id: str, north_m: float, category: str, **kw) -> POI:
    return POI(
        id=poi_id,
        name=kw.pop("name", poi_id),
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        opening_hours=kw.pop("hours", "24/7"),
        **kw,
    )


# ---- 1. the status of one moment, in the words of code -----------------------------------------------------


def test_baiterek_at_night_is_closed_and_opens_at_ten():
    assert status_text(BAITEREK, "closed", _at(20, 3, 10), "en") == "Closed, opens at 10:00"
    assert (
        status_text(BAITEREK, "open", _at(20, 3, 10), "ru") == "Закрыто, откроется в 10:00"
    )  # a stale state


def test_a_card_describes_one_moment_even_when_the_question_names_the_morning():
    # «is it worth going up in the morning?» at 03:10, 70 min away: the card was «open» on arrival in the morning but
    # its change time came from the departure — «Open until 10:00». One moment now: the arrival.
    place = place_from_poi(BAITEREK, origin=ORIGIN, mode="walk", when=_at(20, 9, 0), lang="en")
    assert place.hours.text in {"Closed, opens at 10:00", "Open until 21:00"}
    assert place.hours.text != "Open until 10:00"
    night = place_from_poi(BAITEREK, origin=ORIGIN, mode="walk", when=_at(20, 3, 10), lang="en")
    assert night.hours.text == "Closed, opens at 10:00"


def test_an_overnight_close_is_said_with_its_day():
    assert status_text(OVERNIGHT, "open", _at(21, 13, 0), "ru") == "Открыто до 05:00 следующего дня"
    assert status_text(OVERNIGHT, "open", _at(21, 13, 0), "en") == "Open until 05:00 the next day"
    assert (
        status_text(OVERNIGHT, "open", _at(21, 23, 0), "ru") == "Открыто до 05:00"
    )  # tonight it is plain


def test_tomorrow_at_nine_is_answered_for_tomorrow_at_nine():
    env = TurnEnv(when=_at(20, 3, 10), use_llm=False, router=offline_router(), pois=[BAITEREK])
    out = take_turn(new_state(*ORIGIN, "en"), "is baiterek open tomorrow at 9:00", env).turn
    texts = [a.text for a in out.answers] + [p.hours.text for p in out.places]
    assert not any("until 10:00" in x for x in texts), texts


def test_the_model_may_not_write_a_status_of_its_own():
    c = Candidate(
        poi=OVERNIGHT, distance_m=300, walk_min=4, travel_min=4, hours_state="open", score=1.0
    )
    own = status_text(OVERNIGHT, "open", _at(21, 13, 4), "ru")
    kept = _clean(f"Блинчики и кофе. {own}.", c, "ru", [], own)
    assert own in kept
    dropped = _clean("Блинчики и кофе. Работает до 05:00. Сейчас открыто.", c, "ru", [], own)
    assert dropped == "Блинчики и кофе."


def test_an_opening_with_a_status_not_of_code_is_not_used():
    c = Candidate(
        poi=OVERNIGHT, distance_m=300, walk_min=4, travel_min=4, hours_state="open", score=1.0
    )
    recs = template_recs([c], parse_rules("поесть").intent, None)
    when = _at(21, 13, 0)
    assert (
        checked_opening("«Sultani» работает до 05:00, можно поесть.", recs, [c], None, "ru", when)
        == ""
    )
    good = "«Sultani» рядом — открыто до 05:00 следующего дня."
    assert checked_opening(good, recs, [c], None, "ru", when) == good


# ---- 2. no feature the record does not carry ----------------------------------------------------------------


def test_with_wifi_is_not_claimed_of_a_place_without_it():
    pois = [
        _poi("cafe1", 100, "cafe", name="DAMI CAFE"),
        _poi("cafe2", 200, "cafe", name="Discovery"),
    ]
    env = TurnEnv(when=_at(20, 13), use_llm=False, router=offline_router(), pois=pois)
    first = take_turn(new_state(*ORIGIN), "хочу кофе", env)
    out = take_turn(first.state, "а с wifi", env).turn
    assert "С Wi-Fi" not in out.reply
    assert out.reply.startswith("Wi-Fi в данных не отмечен")


def test_a_socket_question_is_about_the_place_in_view():
    pois = [_poi("cafe1", 100, "cafe", name="DAMI CAFE")]
    env = TurnEnv(when=_at(20, 13), use_llm=False, router=offline_router(), pois=pois)
    first = take_turn(new_state(*ORIGIN), "хочу кофе", env)
    out = take_turn(first.state, "а тут розетки есть?", env).turn
    assert out.kind == "place_answer", out.reply
    assert "DAMI CAFE" in out.reply


# ---- 4. chips keep their word -----------------------------------------------------------------------------------


def _bars() -> list[POI]:
    return [
        _poi("pub_near", 300, "bar_nightlife", name="Harat's"),
        _poi("pub2", 900, "bar_nightlife", name="Shashlyk Pub"),
        _poi("pub3", 950, "bar_nightlife", name="Kings Cross"),
        _poi("pub4", 1000, "bar_nightlife", name="The Pub"),
        _poi("pub5", 1050, "bar_nightlife", name="Brewery"),
        _poi("cafe1", 200, "cafe", name="TOTEM"),
        _poi("dine", 250, "restaurant", name="Cloud9 Dine and Bar"),
        _poi("rest", 280, "restaurant", name="Berezka"),
    ]


def _bar_env() -> TurnEnv:
    return TurnEnv(when=_at(20, 23), use_llm=False, router=offline_router(), pois=_bars())


def test_closer_never_gives_a_farther_place_than_the_nearest_shown():
    first = take_turn(new_state(*ORIGIN), "где побухать с друзьями", _bar_env())
    nearest = min(p.walk.distance_m for p in first.turn.places)
    out = take_turn(first.state, "поближе", _bar_env()).turn
    assert out.places[0].walk.distance_m <= nearest
    if out.places[0].walk.distance_m == nearest:
        assert out.reply.startswith("Ближе таких мест нет")


def test_other_places_keep_the_kind():
    first = take_turn(new_state(*ORIGIN), "где побухать с друзьями", _bar_env())
    out = take_turn(first.state, "другие места", _bar_env()).turn
    assert out.places
    assert {p.category for p in out.places} == {"bar_nightlife"}


def test_no_alcohol_leaves_out_a_place_whose_name_says_bar_and_says_so():
    first = take_turn(new_state(*ORIGIN), "где поужинать", _bar_env())
    out = take_turn(first.state, "без алкоголя", _bar_env()).turn
    assert "Cloud9 Dine and Bar" not in {p.name for p in out.places}
    assert out.reply.startswith("Без алкоголя — убрал бары и места с алкоголем")


# ---- 5. conditions only when they matter --------------------------------------------------------------------------


def test_a_cafe_answer_says_no_weather_and_a_walk_says_it_in_one_clause():
    from walks.models import WeatherWarning

    fog = WeatherWarning(
        kind="storm",
        title="Штормовое предупреждение",
        text="ожидается туман",
        source_url="https://www.kazhydromet.kz/",
        active=True,
    )
    wx = make_weather(1.0, -2.0, pm25=10.0, warnings=[fog], fetched_at="03:00")
    pois = [
        _poi("cafe1", 100, "cafe", name="Кофейня"),
        _poi("park1", 150, "park_garden", name="Сквер"),
    ]
    env = TurnEnv(when=None, weather=wx, use_llm=False, router=offline_router(), pois=pois)
    cafe = take_turn(new_state(*ORIGIN), "хочу кофе", env).turn
    assert "туман" not in cafe.reply
    assert "°C" not in cafe.reply
    assert not cafe.notices
    walk = take_turn(new_state(*ORIGIN), "погулять в парке", env).turn
    first = walk.reply.split(". ")[0]
    assert "туман" in first  # for a walk the notice matters
    assert len(first) <= 100, first  # one short clause, not a report


# ---- 6. English names in English -----------------------------------------------------------------------------------


def test_an_english_answer_shows_the_english_name():
    env = TurnEnv(when=_at(20, 13), use_llm=False, router=offline_router(), pois=[BAITEREK])
    out = take_turn(new_state(*ORIGIN, "en"), "landmarks nearby", env).turn
    assert out.places[0].name == "Baiterek"
    assert "Baiterek" in out.reply
    ru = take_turn(new_state(*ORIGIN), "достопримечательности рядом", env).turn
    assert ru.places[0].name == "Байтерек"


@pytest.mark.parametrize("lang", ["ru", "en"])
def test_name_for_falls_back_to_the_record_name(lang):
    assert _poi("x", 10, "cafe", name="Кафе Икс").name_for(lang) == "Кафе Икс"
