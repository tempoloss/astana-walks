"""The lead never pretends: a kind a safety rule dropped is said in one sentence, not named as the wish; a bare «куда
сходить» gets an answer (the model's reading when one is available, else a default), never a dead-end question."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks import dialog
from walks.dialog import TurnEnv, new_state, take_turn
from walks.models import POI, IntentResult
from walks.outing import DEFAULT_KINDS, default_outing, is_outing
from walks.profile import Profile
from walks.walking import offline_router

ORIGIN = (51.1283, 71.4305)
DEG_M = 111_320.0
EVENING = datetime(2026, 10, 20, 19, 0)


def _poi(poi_id: str, north_m: float, category: str) -> POI:
    return POI(
        id=poi_id,
        name=poi_id,
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        opening_hours="24/7",
    )


def _city() -> list[POI]:
    return [
        _poi("bar1", 60, "bar_nightlife"),
        _poi("bar2", 90, "bar_nightlife"),
        _poi("cafe1", 120, "cafe"),
        _poi("rest1", 150, "restaurant"),
        _poi("mall1", 200, "mall"),
        _poi("park1", 220, "park_garden"),
        _poi("museum1", 260, "museum_gallery"),
        _poi("fountain", 240, "attraction_landmark"),
    ]


def _ask(text, profile=None, lang="ru"):
    env = TurnEnv(
        when=EVENING, use_llm=False, router=offline_router(), pois=_city(), profile=profile
    )
    return take_turn(new_state(*ORIGIN, lang), text, env).turn


@pytest.mark.parametrize(
    ("text", "lang", "opening"),
    [
        ("мне 15, где купить пиво", "ru", "Бары и алкоголь до 18 лет не предлагаю."),
        ("мне 16 лет хочу выпить", "ru", "Бары и алкоголь до 18 лет не предлагаю."),
        ("I'm 16, where can I get a beer", "en", "I don't suggest bars or alcohol under 18."),
    ],
)
def test_a_minor_asking_for_alcohol_hears_why_and_no_bar(text, lang, opening):
    turn = _ask(text, lang=lang)
    assert turn.kind == "places"
    assert "bar_nightlife" not in {p.category for p in turn.places}
    assert turn.reply.startswith(opening), turn.reply
    assert "Вы ищете" not in turn.reply
    assert "You are looking for" not in turn.reply


def test_no_alcohol_says_why_the_bar_is_not_there():
    turn = _ask("побухать", Profile(no_alcohol=True))
    assert "bar_nightlife" not in {p.category for p in turn.places}
    assert turn.reply.startswith("Бары не показываю: включено «без алкоголя».")
    assert "Вы ищете: бар" not in turn.reply
    plain = _ask("побухать")
    assert "Бары не показываю" not in plain.reply


@pytest.mark.parametrize(
    ("text", "lang"),
    [("куда сходить", "ru"), ("where should I go", "en"), ("қайда барсам болады", "kk")],
)
def test_a_bare_where_to_go_gets_a_default_answer_offline(text, lang):
    assert is_outing(text)
    turn = _ask(text)
    assert turn.kind == "places", turn.reply
    assert turn.lang == lang
    assert {p.category for p in turn.places} <= set(DEFAULT_KINDS)
    for said in ("Вы ищете", "You are looking for", "іздеп жатырсыз"):
        assert said not in turn.reply  # the person named no kind: none is put in their mouth


def test_the_default_keeps_what_the_words_did_say():
    reading = default_outing("куда сходить вечером на 2 часа", EVENING)
    assert reading is not None
    assert reading.intent.time_budget_min == 120
    assert reading.intent.wished == []
    assert default_outing("где поесть", EVENING) is None  # a named kind is a search of its own


def test_a_model_reading_beats_the_default(monkeypatch):
    seen = []

    def reading(env, text):
        seen.append(text)
        it = default_outing("куда сходить", EVENING)
        assert it is not None
        intent = it.intent.model_copy(update={"categories": ["museum_gallery"]})
        return IntentResult(intent=intent, parser="rules+llm"), dialog.Deadline()

    monkeypatch.setattr(dialog, "_model_reading", reading)
    turn = _ask("куда сходить")
    assert seen == ["куда сходить"]
    assert next(p.category for p in turn.places) == "museum_gallery"
