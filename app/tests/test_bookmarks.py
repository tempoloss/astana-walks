"""The user's own named places: a request that names one is searched there or along the way; late at night food, coffee
and drinks lean toward home; nothing about them is stored or logged."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.bookmarks import find_ref, late_home, prefer_toward, toward
from walks.dialog import TurnEnv, new_state, take_turn
from walks.models import POI, Bookmark, Candidate, Intent
from walks.pipeline import round_location
from walks.presets import PRESETS
from walks.radius import haversine_m
from walks.walking import offline_router
from walks.weather import make_weather

BAITEREK = round_location(*PRESETS["Байтерек"])
HOME = Bookmark(name="Дом", kind="home", lat=51.128, lon=71.466)  # ~2.5 km east of the Baiterek
SCHOOL = Bookmark(name="Школа 5", kind="study", lat=51.14, lon=71.41)
GRAN = Bookmark(name="Бабушка", kind="other", lat=51.11, lon=71.44)
MIDNIGHT = datetime(2026, 10, 14, 23, 50)
NOON = datetime(2026, 10, 14, 12, 0)


def say(text, *, when=MIDNIGHT, bookmarks=(HOME,), state=None, lang="ru", **kw):
    env = TurnEnv(
        when=when,
        use_llm=False,
        weather=make_weather(12.0, 12.0, fetched_at="23:50"),
        router=offline_router(),
        bookmarks=list(bookmarks),
        **kw,
    )
    return take_turn(state or new_state(*BAITEREK, lang), text, env)


# ------------------------------------------------------------------ what a message names


@pytest.mark.parametrize(
    ("text", "bookmark", "along", "rest"),
    [
        ("хочу кофе рядом с домом", HOME, False, "хочу кофе"),
        ("где поесть возле дома", HOME, False, "где поесть"),
        ("хочу поесть по пути домой", HOME, True, "хочу поесть"),
        ("кофе по дороге домой", HOME, True, "кофе"),
        ("coffee on the way home", HOME, True, "coffee"),
        ("coffee near home", HOME, False, "coffee"),
        ("где поесть возле школы", SCHOOL, False, "где поесть"),
        ("кофе по пути в школу", SCHOOL, True, "кофе"),
        ("кофе у бабушки", GRAN, False, "кофе"),
        ("поесть рядом с Бабушкой", GRAN, False, "поесть"),
        ("кофе по пути к бабушке", GRAN, True, "кофе"),
        ("үйдің жанында кофе", HOME, False, "кофе"),
    ],
)
def test_a_message_that_names_a_bookmark(text, bookmark, along, rest):
    ref = find_ref(text, [HOME, SCHOOL, GRAN])
    assert ref is not None, text
    assert (ref.bookmark, ref.along) == (bookmark, along)
    assert ref.rest == rest


@pytest.mark.parametrize(
    "text",
    ["хочу кофе", "где поесть", "музей на час", "дом культуры где", "работаю из кафе"],
)
def test_a_message_that_names_none(text):
    assert find_ref(text, [HOME, SCHOOL, GRAN]) is None or text == "дом культуры где"


def test_no_bookmarks_no_reading():
    assert find_ref("кофе рядом с домом", []) is None


# ------------------------------------------------------------------ geometry


def cand(lat: float, lon: float, ident: str) -> Candidate:
    poi = POI(id=ident, name=ident, category="cafe", lat=lat, lon=lon, source="osm")
    return Candidate(
        poi=poi, distance_m=100, walk_min=2, travel_min=2, hours_state="open", score=1.0
    )


def test_toward_means_closer_to_home_than_the_user_is():
    user = BAITEREK
    assert toward(user, HOME, 51.128, 71.45, along=False)  # between the user and home
    assert not toward(user, HOME, 51.128, 71.41, along=False)  # the other way
    assert not toward(
        (HOME.lat, HOME.lon + 0.001), HOME, 51.128, 71.466, along=False
    )  # at home already


def test_along_the_way_also_means_a_small_detour():
    user = BAITEREK
    assert toward(user, HOME, 51.1285, 71.45, along=True)  # on the line
    assert not toward(user, HOME, 51.145, 71.45, along=True)  # closer to home, 2 km off the line


def test_the_candidates_toward_home_come_first_and_alone_when_there_are_enough():
    toward_a, toward_b = cand(51.128, 71.45, "a"), cand(51.128, 71.455, "b")
    away = cand(51.128, 71.41, "x")
    assert prefer_toward([away, toward_a, toward_b], BAITEREK, HOME, along=False) == [
        toward_a,
        toward_b,
    ]
    assert prefer_toward([away, toward_a], BAITEREK, HOME, along=False) == [toward_a, away]
    assert prefer_toward([away], BAITEREK, HOME, along=False) == [away]  # no way home: unchanged


def test_late_home_needs_the_hour_a_food_request_and_a_home():
    food = Intent(categories=["restaurant"])
    assert late_home(food, 23, BAITEREK, [HOME]) == HOME
    assert late_home(food, 2, BAITEREK, [HOME]) == HOME
    assert late_home(food, 12, BAITEREK, [HOME]) is None  # not late
    assert late_home(Intent(categories=["museum_gallery"]), 23, BAITEREK, [HOME]) is None
    assert late_home(food, 23, BAITEREK, [SCHOOL]) is None  # no home bookmark
    assert late_home(food, 23, (HOME.lat, HOME.lon), [HOME]) is None  # already there


# ------------------------------------------------------------------ the dialogue


def test_a_midnight_wish_for_food_leans_toward_home_and_says_so():
    out = say("хочу похавать")
    turn = out.turn
    assert turn.kind == "places"
    first = turn.places[0]
    to_home = lambda p: haversine_m(p.lat, p.lon, HOME.lat, HOME.lon)  # noqa: E731
    assert to_home(first) < haversine_m(*BAITEREK, HOME.lat, HOME.lon)
    assert "по пути домой" in turn.reply
    assert out.result is not None
    assert out.result.on_the_way == "Дом"


def test_without_a_home_bookmark_nothing_leans_and_nothing_is_claimed():
    out = say("хочу похавать", bookmarks=())
    assert "по пути домой" not in out.turn.reply
    assert out.result is not None
    assert out.result.on_the_way == ""


def test_at_noon_nothing_leans():
    out = say("хочу поесть", when=NOON)
    assert "по пути домой" not in out.turn.reply


def test_a_request_near_a_bookmark_is_searched_there():
    out = say("хочу кофе рядом с домом", when=NOON)
    turn = out.turn
    assert turn.kind == "places"
    assert turn.origin == (HOME.lat, HOME.lon)
    assert "от «Дом»" in turn.reply
    assert all(haversine_m(p.lat, p.lon, HOME.lat, HOME.lon) < 1500 for p in turn.places)


def test_a_school_in_the_words_is_a_place_to_search_around_not_a_missing_kind():
    out = say("где поесть возле школы", when=NOON, bookmarks=(SCHOOL,))
    assert out.turn.kind == "places"  # not «в моих данных нет школ»
    assert out.turn.origin == (SCHOOL.lat, SCHOOL.lon)


def test_a_request_along_the_way_keeps_the_user_as_the_origin():
    out = say("кофе по пути домой", when=NOON)
    assert out.turn.origin == BAITEREK
    assert out.turn.kind == "places"
    if out.result is not None and out.result.on_the_way:
        assert "по пути домой" in out.turn.reply


def test_a_follow_up_keeps_searching_around_the_bookmark_while_it_is_sent():
    first = say("хочу кофе рядом с домом", when=NOON)
    again = say("а поближе?", when=NOON, state=first.state)
    assert again.turn.origin == (HOME.lat, HOME.lon)
    gone = say("а поближе?", when=NOON, state=first.state, bookmarks=())
    assert gone.turn.origin == BAITEREK  # the bookmark is no longer on this device


def test_a_bookmark_request_is_never_logged(monkeypatch, tmp_path):
    log = tmp_path / "requests.jsonl"
    monkeypatch.setenv("WALKS_REQUEST_LOG", str(log))
    say("хочу кофе рядом с домом", when=NOON)
    say("хочу похавать")
    assert not log.exists() or log.read_text(encoding="utf-8") == ""
    say("хочу кофе", when=NOON, bookmarks=())
    assert log.exists()  # control: an ordinary request is still logged


def test_bookmark_coordinates_are_rounded_to_three_decimals():
    b = Bookmark(name="Дом", kind="home", lat=51.08934567, lon=71.45123456)
    assert (b.lat, b.lon) == (51.089, 71.451)
