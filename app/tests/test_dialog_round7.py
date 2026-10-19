"""Round 6 of the human testers (rules only, no key): compound questions about the shown place answered in full
(price and closing time, kids room and closing time, hours + cash machine + 24/7), follow-ups about a shown bank
(changing dollars, a cash machine) that are place questions, a child as the reason for an errand, and the Kazakh
phrasing of the lead. Behaviour, not wording: topics, categories, flags."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_questions import place_question
from walks.dialog_strings import STRINGS
from walks.dialog_types import ShownPlace
from walks.intent import parse_rules
from walks.models import POI
from walks.walking import offline_router

EXPO = (51.0890, 71.4160)
MONDAY = datetime(2026, 10, 28, 12, 0)  # a Wednesday: no holiday


def _env(pois=None) -> TurnEnv:
    return TurnEnv(when=MONDAY, use_llm=False, router=offline_router(), pois=pois)


def _showing(poi: POI, lang: str = "ru"):
    return new_state(*EXPO, lang).model_copy(
        update={"shown": [ShownPlace(id=poi.id, name=poi.name, kind="x", minutes=3)]}
    )


def _poi(**fields) -> POI:
    base = {"id": "t/1", "name": "Test Place", "lat": 51.0895, "lon": 71.4165, "category": "cafe"}
    return POI(**{**base, **fields})


def _ask(poi: POI, text: str, lang: str = "ru"):
    return take_turn(_showing(poi, lang), text, _env([poi]))


# ------------------------------------------------------------------ 1. compound questions, every part


def test_price_and_closing_time_of_a_museum_are_both_answered():
    poi = _poi(
        category="museum_gallery",
        price_text="500 тг.",
        opening_hours="Tu-Su 10:00-18:00",
    )
    out = _ask(poi, "сколько стоит вход и до сколько работает?")
    assert [a.topic for a in out.turn.answers] == ["entry", "hours"]
    assert out.result is None
    assert "500" in out.turn.reply
    assert "18:00" in out.turn.reply


def test_kids_room_and_closing_time_in_kazakh_are_both_answered():
    poi = _poi(
        category="mall", opening_hours="Mo-Su 10:00-22:00", tags=["shop=mall", "for_kids=yes"]
    )
    out = _ask(poi, "мұнда балаларға арналған ойын бөлмесі бар ма және қашанға дейін ашық?", "kk")
    assert [a.topic for a in out.turn.answers] == ["kids_room", "hours"]
    assert out.turn.lang == "kk"
    assert "22:00" in out.turn.reply


def test_hours_a_cash_machine_and_the_clock_about_a_bank_are_one_place_question():
    poi = _poi(category="money", opening_hours="24/7", tags=["amenity=atm", "opening_hours=24/7"])
    out = _ask(poi, "а до скольки он работает и есть ли там банкомат круглосуточно")
    topics = [a.topic for a in out.turn.answers]
    assert topics == ["hours", "atm"]
    assert out.turn.kind == "place_answer"
    assert out.result is None
    assert "круглосуточно" in out.turn.reply
    assert out.turn.answers[1].known


def test_a_bank_without_the_cash_machine_tag_is_not_in_the_data():
    poi = _poi(category="money", opening_hours="Mo-Fr 09:00-18:00", tags=["amenity=bank"])
    out = _ask(poi, "а до скольки он работает и есть ли там банкомат")
    atm = out.turn.answers[1]
    assert atm.topic == "atm"
    assert not atm.known
    assert "в данных" in atm.text
    assert "18:00" in out.turn.reply


def test_a_clock_asked_of_a_cash_machine_that_is_not_24_7_says_no_with_the_hours():
    poi = _poi(category="money", opening_hours="Mo-Fr 09:00-18:00", tags=["amenity=atm"])
    out = _ask(poi, "банкомат там круглосуточно?")
    topics = [a.topic for a in out.turn.answers]
    assert topics == ["atm", "hours"]
    assert "не круглосуточно" in out.turn.answers[1].text
    assert "09:00" in out.turn.answers[1].text


@pytest.mark.parametrize(
    ("text", "topics"),
    [
        ("сколько стоит вход и до сколько работает?", ["entry", "closing"]),
        ("до сколько работает", ["closing"]),
        ("қашанға дейін ашық", ["closing"]),
        ("а до скольки он работает и есть ли розетки и вайфай", ["closing", "socket", "wifi"]),
        ("сколько стоит вход и есть ли там туалет", ["entry", "toilet"]),
        ("круглосуточно ли", ["hours"]),
        ("банкомат там круглосуточно?", ["atm", "round_clock"]),
    ],
)
def test_the_parts_of_a_message_in_the_order_they_are_said(text, topics):
    pq = place_question(text, allow_kind=True)
    assert [pq.topic, *pq.also] == topics


def test_a_search_for_a_cash_machine_is_not_a_question_about_a_place():
    assert place_question("где банкомат", allow_kind=True) is None
    assert place_question("банкомат рядом?", allow_kind=True) is None


# ------------------------------------------------------------------ 2. changing currency at a shown bank


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("меняют ли там доллары", "ru"),
        ("do they change dollars at halyk bank", "en"),
        ("доллар айырбастай ма", "kk"),
    ],
)
def test_changing_dollars_at_a_shown_bank_is_a_place_question_not_a_search(text, lang):
    poi = _poi(category="money", tags=["amenity=bank"])
    out = _ask(poi, text, lang)
    (answer,) = out.turn.answers
    assert out.turn.kind == "place_answer"
    assert out.result is None
    assert answer.topic == "exchange"
    assert not answer.known
    assert out.turn.lang == lang
    assert "You are looking for" not in out.turn.reply
    assert out.state.shown == _showing(poi, lang).shown


def test_changing_currency_is_yes_when_the_record_says_so():
    bureau = _poi(category="money", tags=["amenity=bureau_de_change"])
    assert _ask(bureau, "меняют ли там доллары").turn.answers[0].known
    dollars = _poi(category="money", tags=["amenity=bank", "currency:USD=yes"])
    out = _ask(dollars, "do they change dollars there", "en")
    assert out.turn.answers[0].known
    assert "USD" in out.turn.answers[0].text


def test_where_to_change_dollars_is_still_a_search():
    state = new_state(*EXPO, "ru")
    out = take_turn(state, "где обменять доллары", _env())
    assert out.turn.kind != "place_answer"


# ------------------------------------------------------------------ 3. a child as a reason


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("жақын жерде дәретхана бар ма, балам сұранып жатыр", "public_toilet"),
        ("аптека нужна, ребёнок заболел", "pharmacy"),
        ("где туалет, ребёнок хочет в туалет", "public_toilet"),
    ],
)
def test_a_child_in_an_errand_is_a_reason_not_a_wish_for_kids_places(text, kind):
    intent = parse_rules(text).intent
    assert intent.categories == [kind]
    assert not intent.with_kids
    assert "kids_playground" not in intent.categories
    outs = take_turn(new_state(*EXPO, "ru"), text, _env())
    assert all(p.category != "kids_playground" for p in outs.turn.places)


def test_a_child_with_a_wish_for_a_place_is_still_a_kids_request():
    intent = parse_rules("хочу с ребёнком погулять").intent
    assert intent.with_kids
    intent = parse_rules("балалармен қайда барсам болады").intent
    assert intent.with_kids
    assert "kids_playground" in intent.categories


# ------------------------------------------------------------------ 4. Kazakh phrasing


def test_the_kazakh_lead_does_not_say_the_places_or_echo_the_request():
    pick = STRINGS["ld_pick"][0]
    assert "жеріне" not in pick
    assert "барыңыз" not in pick  # no verb that governs a case: a quoted name is never declined
    assert "Сіз іздеп жатырсыз" not in STRINGS["ld_want"][0]
    outs = take_turn(new_state(*EXPO, "kk"), "кафе жақын жерде", _env())
    assert "жеріне барыңыз" not in outs.turn.reply
    assert "Сіз іздеп жатырсыз" not in outs.turn.reply
