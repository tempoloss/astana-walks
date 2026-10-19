"""Round 2 of the human testers (rules only, no key): «на бегу» is on the go, sockets / a kids' room / «is it worth it»
asked of a place, saved places in questions, the kids words inside a new request, «if it is not cold», museums at a
named time. Behaviour, not wording: topics, ids, categories, moments."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_strings import s
from walks.dialog_types import DialogState, ShownPlace
from walks.followup import parse_follow_up
from walks.models import POI, Bookmark, Intent
from walks.walking import offline_router
from walks.weather import make_weather

EXPO = (51.0890, 71.4160)
SATURDAY = datetime(2026, 10, 17, 15, 0)
ENV = TurnEnv(when=SATURDAY, use_llm=False, router=offline_router())
BAITEREK = "way/230401645"
HOTEL = Bookmark(name="my hotel", kind="other", lat=51.1283, lon=71.4305)
HOME = Bookmark(name="Дом", kind="home", lat=51.10, lon=71.45)


def dialogue(lang: str, *messages: str, env: TurnEnv = ENV):
    state, outs = new_state(*EXPO, lang), []
    for m in messages:
        out = take_turn(state, m, env)
        state = out.state
        outs.append(out)
    return outs, state


def showing(poi: POI, lang: str = "ru") -> tuple[DialogState, TurnEnv]:
    state = new_state(*EXPO, lang).model_copy(
        update={"shown": [ShownPlace(id=poi.id, name=poi.name, kind="кафе", minutes=3)]}
    )
    return state, TurnEnv(when=SATURDAY, use_llm=False, router=offline_router(), pois=[poi])


def cafe(**fields) -> POI:
    return POI(id="t/1", name="Test Cafe", lat=51.0895, lon=71.4165, category="cafe", **fields)


# ------------------------------------------------------------------ 1. «на бегу»


@pytest.mark.parametrize(
    "text", ["где шаурму взять или бургер, на бегу", "бургер на бегу", "grab a burger on the go"]
)
def test_on_the_go_is_fast_food_never_sport_or_a_park(text):
    _, state = dialogue("ru", text)
    categories = state.conversation.intent.categories
    assert "fast_food" in categories
    assert not {"sport", "park_garden"} & set(categories)


def test_running_is_still_sport():
    _, state = dialogue("ru", "хочу побегать")
    assert "sport" in state.conversation.intent.categories


# ------------------------------------------------------------------ 2. questions about the shown place


def test_sockets_are_answered_from_the_record_never_a_search():
    state, env = showing(cafe(tags=["amenity=cafe", "socket:schuko=4"]))
    out = take_turn(state, "а тут розетки есть?", env)
    (a,) = out.turn.answers
    assert out.turn.kind == "place_answer"
    assert out.result is None
    assert a.topic == "socket"
    assert a.known


def test_sockets_missing_from_the_record_say_so_and_wifi_has_its_own_answer():
    state, env = showing(
        cafe(tags=["amenity=cafe", "internet_access=wlan"], internet_access="wlan")
    )
    out = take_turn(state, "а тут розетки есть?", env)
    (a,) = out.turn.answers
    assert a.topic == "socket"
    assert not a.known
    assert out.state.shown == state.shown
    out = take_turn(state, "а тут вайфай есть?", env)
    (w,) = out.turn.answers
    assert w.topic == "wifi"
    assert w.known


def test_a_kids_room_question_names_the_place_and_is_about_it():
    outs, _ = dialogue("kk", "ТД Эверестте балаларға арналған ойын бөлмесі бар ма")
    (a,) = outs[0].turn.answers
    assert outs[0].turn.kind == "place_answer"
    assert a.topic == "kids_room"
    assert outs[0].turn.places[0].name == "ТД Эверест"


def test_a_kids_room_the_record_marks_is_yes():
    state, env = showing(cafe(tags=["amenity=cafe", "for_kids=yes"]))
    out = take_turn(state, "есть детская комната?", env)
    (a,) = out.turn.answers
    assert a.topic == "kids_room"
    assert a.known


def test_is_it_worth_going_up_is_the_hours_and_the_entry_of_that_place():
    outs, _ = dialogue("en", "is it worth going up baiterek at night or in the morning")
    out = outs[0]
    (a,) = out.turn.answers
    assert out.turn.kind == "place_answer"
    assert out.result is None
    assert a.topic == "visit"
    assert out.turn.places[0].id == BAITEREK
    assert "2500" in a.text
    assert "21:00" in a.text


# ------------------------------------------------------------------ 3. saved places in questions


@pytest.mark.parametrize(
    ("text", "bookmark"),
    [
        ("how long to walk back to my hotel", HOTEL),
        ("how long does it take to walk to the hotel", HOTEL),
        ("сколько идти до дома", HOME),
    ],
)
def test_the_way_to_a_saved_place_is_minutes_from_the_person(text, bookmark):
    env = TurnEnv(when=SATURDAY, use_llm=False, router=offline_router(), bookmarks=[HOTEL, HOME])
    outs, _ = dialogue("en" if "walk" in text else "ru", "кофе рядом", text, env=env)
    out = outs[1]
    (a,) = out.turn.answers
    assert out.turn.kind == "place_answer"
    assert out.result is None
    assert a.topic == "route"
    assert a.name == bookmark.name
    assert a.known
    assert [p.id for p in out.turn.places] == [
        p.id for p in outs[0].turn.places
    ]  # the map keeps them


def test_any_bookmark_name_is_the_way_along_which_a_search_runs():
    env = TurnEnv(when=SATURDAY, use_llm=False, router=offline_router(), bookmarks=[HOTEL])
    outs, _ = dialogue("en", "something nice to see on my way back to the hotel", env=env)
    out = outs[0]
    assert out.turn.kind == "places"
    assert out.turn.places
    assert "hotel" in out.turn.reply
    assert out.result.on_the_way == "my hotel"
    assert {"attraction_landmark", "viewpoint"} & set(out.result.intent.intent.categories)


# ------------------------------------------------------------------ 4. kids words, «if it is not cold»


def test_kids_words_with_their_own_kind_start_a_new_search():
    _, state = dialogue("kk", "кафе жақын жерде", "балам жақын жерде ойнайтын жер керек")
    intent = state.conversation.intent
    assert "kids_playground" in intent.categories
    assert intent.with_kids


def test_a_cafe_that_asks_for_a_kids_menu_is_a_new_request():
    outs, state = dialogue("kk", "кафе жақын жерде", "балалар мәзірі бар кафе бар ма")
    assert outs[1].turn.kind == "places"
    assert "cafe" in state.conversation.intent.categories
    assert not outs[1].turn.reply.startswith("Баламен")


def test_a_weather_question_with_kids_in_it_is_a_weather_answer():
    outs, _ = dialogue(
        "kk", "кафе жақын жерде", "ауа райы қандай, балаларды жылы киіндіру керек пе"
    )
    out = outs[1]
    assert out.turn.kind == "place_answer"
    assert out.turn.answers[0].topic == "weather"
    assert [p.id for p in out.turn.places] == [p.id for p in outs[0].turn.places]


def test_where_to_play_indoors_after_a_search_is_a_request_of_its_own():
    _, state = dialogue("ru", "кафе рядом", "где поиграть детям в помещении")
    assert "kids_playground" in state.conversation.intent.categories


@pytest.mark.parametrize("text", ["с ребёнком", "а если с детьми", "баламен", "with a kid"])
def test_a_bare_kids_message_is_still_the_refinement(text):
    prev = Intent(categories=["cafe"])
    fu = parse_follow_up(text, prev)
    assert fu is not None
    assert fu.with_kids == "yes"


@pytest.mark.parametrize(
    "text",
    ["балам жақын жерде", "где поиграть детям в помещении", "как одеть детей в такую погоду"],
)
def test_kids_words_with_more_in_them_are_not_the_refinement(text):
    assert parse_follow_up(text, Intent(categories=["cafe"])) is None


def _weather_env(feels: float) -> TurnEnv:
    w = make_weather(feels, feels, 4.0, 0.0, source="metar", observed_at="2026-10-17T14:50+05:00")
    return TurnEnv(when=SATURDAY, use_llm=False, router=offline_router(), weather=w)


def test_if_it_is_not_cold_says_it_is_not_cold_and_picks_the_street():
    outs, state = dialogue(
        "kk", "суық емес болса саябаққа барайық, балаларға ойнайтын жер", env=_weather_env(14.0)
    )
    out = outs[0]
    assert "+14" in out.turn.reply
    assert "park_garden" in state.conversation.intent.categories
    assert any(p.category == "park_garden" for p in out.turn.places)


def test_if_it_is_not_cold_says_it_is_cold_and_picks_indoors():
    outs, state = dialogue("ru", "если не холодно, хочу в парк", env=_weather_env(-8.0))
    out = outs[0]
    assert "−8" in out.turn.reply
    assert "холодно" in out.turn.reply
    assert "park_garden" not in state.conversation.intent.categories
    assert (
        out.turn.places[0].category != "park_garden"
    )  # indoor first; the nearest park only as the option
    parks = [p for p in out.turn.places if p.category == "park_garden"]
    assert all(s("note_fresh_air", "ru") in p.note for p in parks)


def test_if_it_is_not_cold_without_a_temperature_says_so():
    env = TurnEnv(when=SATURDAY, use_llm=False, router=offline_router(), weather=make_weather())
    outs, _ = dialogue("ru", "если не холодно, хочу в парк", env=env)
    assert "в данных нет" in outs[0].turn.reply
    assert outs[0].turn.places


# ------------------------------------------------------------------ 5. museums at a named time


def test_museums_for_tomorrow_morning_are_museums_for_that_morning():
    outs, state = dialogue(
        "en", "i want a cafe nearby", "what about tomorrow morning, which museums are open"
    )
    out = outs[1]
    assert out.result.when == datetime(2026, 10, 18, 9, 0)
    assert state.conversation.intent.categories == ["museum_gallery"]
    assert out.turn.places[0].category == "museum_gallery"
    assert out.turn.reply.startswith("Tomorrow in the morning, 09:00.")
