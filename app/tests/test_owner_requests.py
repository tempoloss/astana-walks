"""The owner's plain requests: a refused kind is never shown («не хочу в кафе, хочу гулять»), the answer speaks the
language of the current message, and a toilet is searched for as a toilet, its absence said as the data's, not the
street's."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.dialog import TurnEnv, new_state, take_turn
from walks.intent import merge_intents, parse_rules
from walks.models import POI, Intent
from walks.profile import Profile
from walks.shelter import WALKING_KINDS
from walks.walking import offline_router

ORIGIN = (51.1283, 71.4305)
DEG_M = 111_320.0
NOON = datetime(2026, 10, 20, 13, 0)


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


def _city(*extra: POI) -> list[POI]:
    return [
        _poi("park1", 200, "park_garden"),
        _poi("park2", 350, "park_garden"),
        _poi("fountain", 300, "attraction_landmark"),
        _poi("cafe1", 80, "cafe"),
        _poi("cafe2", 120, "cafe"),
        _poi("rest1", 140, "restaurant"),
        _poi("mall1", 150, "mall"),
        *extra,
    ]


def _env(pois=None, profile=None) -> TurnEnv:
    return TurnEnv(
        when=NOON,
        use_llm=False,
        router=offline_router(),
        pois=pois if pois is not None else _city(),
        profile=profile,
    )


def _turns(*messages, pois=None, profile=None, lang="ru"):
    env = _env(pois, profile)
    state, out = new_state(*ORIGIN, lang), None
    for message in messages:
        out = take_turn(state, message, env)
        state = out.state
    assert out is not None
    return out.turn


# ---- 1. a refused kind is never shown -------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "не хочу в кафе, хочу гулять",
        "не надо заведений, просто погулять",
        "только не заведения, просто походить",
        "i don't want a cafe, i want a walk",
    ],
)
def test_a_refused_kind_gives_way_to_the_walk(text):
    intent = parse_rules(text).intent
    assert "cafe" not in intent.categories
    assert set(intent.wished) <= WALKING_KINDS
    assert intent.wished
    turn = _turns(text)
    assert turn.kind == "places"
    assert {p.category for p in turn.places} <= WALKING_KINDS
    assert "кафе" not in turn.reply.lower()
    assert "cafe" not in turn.reply.lower()


def test_the_negation_reaches_past_a_preposition_but_not_past_a_comma():
    assert "cafe" in parse_rules("не хочу в кафе, хочу гулять").intent.refused
    assert "bar_nightlife" in parse_rules("не надо идти в бар, хочу в парк").intent.refused
    again = parse_rules(
        "нет, хочу в кафе"
    ).intent  # «нет» answers the question, the clause after it is the wish
    assert again.categories == ["cafe"]
    assert not again.refused


def test_the_model_cannot_bring_a_refused_kind_back():
    text = "не хочу в кафе, хочу гулять"
    rules = parse_rules(text).intent
    llm = Intent(categories=["cafe", "park_garden"], language="ru")
    merged = merge_intents(rules, llm, text)
    assert "cafe" not in merged.categories
    assert merged.refused == rules.refused


def test_a_refused_kind_stays_out_of_every_backfill():
    # only cafés are near besides one park: the refused kind never fills the answer up
    pois = [_poi("park1", 200, "park_garden"), _poi("cafe1", 80, "cafe"), _poi("cafe2", 90, "cafe")]
    turn = _turns("не хочу в кафе, хочу гулять", pois=pois)
    assert [p.category for p in turn.places] == ["park_garden"]


# ---- 2. the language of the current message ---------------------------------------------------------------


def test_a_cyrillic_message_is_answered_in_russian_after_an_english_one():
    turn = _turns("еда", "ne to, drugoe", "ещё варианты")
    assert turn.lang == "ru"
    assert turn.kind in {
        "places",
        "none_found",
    }  # «ещё» keeps the kind: no more food places is said so


def test_the_dialogue_switches_language_with_the_person():
    assert _turns("coffee", "ещё").lang == "ru"
    assert _turns("кафе", "тағы басқа").lang == "kk"
    assert _turns("кафе", "something else please").lang == "en"


def test_a_short_word_of_both_languages_keeps_a_kazakh_dialogue():
    assert _turns("кофе ішкім келеді", "другое", lang="kk").lang == "kk"


@pytest.mark.parametrize("saved", ["kk", "en"])
def test_the_saved_answer_language_speaks_for_a_message_without_words(saved):
    turn = _turns("☕", profile=Profile(language=saved))
    assert turn.lang == saved
    assert _turns("☕").lang == "ru"


# ---- 3. toilets ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        ("туалет", "ru"),
        ("где туалет", "ru"),
        ("дәретхана", "kk"),
        ("әжетхана қайда", "kk"),
        ("toilet", "en"),
        ("restroom", "en"),
        ("public toilet", "en"),
    ],
)
def test_a_toilet_is_searched_for_as_a_toilet(text, lang):
    intent = parse_rules(text).intent
    assert intent.categories == ["public_toilet"]
    assert intent.wished == ["public_toilet"]
    turn = _turns(text)
    assert turn.kind == "none_found", (
        turn.reply
    )  # the data hold no toilet near: never a café in its place
    assert turn.lang == lang
    assert not turn.places


def test_no_toilet_near_is_said_as_the_data_s_absence():
    reply = _turns("где туалет").reply
    assert reply.startswith("В наших данных туалетов рядом нет")
    assert "ТРЦ" in reply
    assert "рядом нет туалетов" not in reply
    assert _turns("toilet").reply.startswith("Our data has no toilets nearby")
    assert _turns("дәретхана").reply.startswith("Біздің деректерде")


def test_a_toilet_in_the_data_is_shown_with_its_hours_unknown():
    toilet = _poi("wc1", 120, "public_toilet", name="Туалет", name_generated=True, hours=None)
    turn = _turns("где туалет", pois=_city(toilet))
    assert turn.kind == "places"
    assert [p.category for p in turn.places] == ["public_toilet"]
    card = turn.places[0]
    assert card.hours.state == "unknown"
    assert (
        "туалет рядом" not in card.note
    )  # the record IS the toilet: no «нет данных о туалете» on it


def test_a_toilet_next_to_a_kind_stays_a_wish_of_that_kind():
    intent = parse_rules("кафе с туалетом").intent
    assert intent.categories == ["cafe"]
    assert "туалет" in intent.free_text_keywords


# ---- the QA catalogue: what the person meant -----------------------------------------------------------------


def test_a_walk_right_now_is_a_walk_not_a_place_named_right():
    pois = _city(_poi("myata", 90, "cafe", name="Myata Right"))
    turn = _turns("Where can I walk right now?", pois=pois)
    assert turn.kind == "places"
    assert {p.category for p in turn.places} <= WALKING_KINDS


@pytest.mark.parametrize(
    "question", ["вход платный?", "билеты сколько стоят", "is there an entry fee?"]
)
def test_an_entry_fee_question_is_about_the_museum_in_view(question):
    pois = _city(_poi("museum", 150, "museum_gallery", name="Picture Day"))
    turn = _turns("музей", question, pois=pois)
    assert turn.kind == "place_answer", turn.reply
    assert turn.places[0].name == "Picture Day"


@pytest.mark.parametrize(
    ("text", "kind"),
    [("кофэ где", "cafe"), ("паггулять хачу", "park_garden"), ("где пошопиться", "mall")],
)
def test_common_misspellings_are_read(text, kind):
    assert kind in parse_rules(text).intent.categories
