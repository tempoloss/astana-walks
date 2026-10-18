"""Every saved setting visibly changes the answer (the owner's rule): the same request with and without the setting
differs, and the lead says once what the setting did, with the real counts where the data are thin."""

from __future__ import annotations

from datetime import datetime
from typing import get_args

import pytest
from pydantic import ValidationError

from walks import generate as gen_mod
from walks import llm
from walks.dialog import TurnEnv, new_state, take_turn
from walks.intent import parse_rules
from walks.models import POI, Constraints
from walks.profile import Profile, ProfileBudget, suggest_chips
from walks.walking import offline_router
from walks.weather import manual_weather
from web.memory import CHOICES, ProfileForm

ORIGIN = (51.1283, 71.4305)
DEG_M = 111_320.0
NOON = datetime(2026, 10, 20, 13, 0)
EVENING = datetime(2026, 10, 20, 21, 0)
INDOOR = {"cafe", "restaurant", "museum_gallery", "mall", "culture_theatre_cinema", "entertainment"}


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
        _poi("park1", 90, "park_garden"),
        _poi("park2", 160, "park_garden"),
        _poi("fountain", 120, "attraction_landmark"),
        _poi("museum", 300, "museum_gallery"),
        _poi("cafe1", 200, "cafe"),
        _poi("cafe2", 260, "cafe"),
        _poi("cafe3", 330, "cafe"),
        _poi("cafe_far", 1400, "cafe"),
        _poi("mall1", 380, "mall"),
        _poi("bar1", 100, "bar_nightlife"),
        _poi("bar2", 140, "bar_nightlife"),
        _poi("club", 180, "entertainment"),
    ]


def _ask(text, profile=None, weather=None, pois=None, when=NOON):
    env = TurnEnv(
        when=when,
        weather=weather,
        use_llm=False,
        router=offline_router(),
        pois=pois if pois is not None else _city(),
        profile=profile,
    )
    return take_turn(new_state(*ORIGIN), text, env)


def _ids(out) -> list[str]:
    return [p.id for p in out.turn.places]


def test_a_slow_pace_shrinks_the_radius_and_says_so():
    plain, slow = _ask("кафе"), _ask("кафе", Profile(walk_pace="slow"))
    radius = slow.result.retrieval.filters.radius_declared_m
    assert radius < plain.result.retrieval.filters.radius_declared_m
    assert "неспешный шаг — радиус меньше" in slow.turn.reply
    assert "Учтены ваши настройки" not in plain.turn.reply
    fast = _ask("кафе", Profile(walk_pace="fast"))
    assert fast.result.retrieval.filters.radius_declared_m > radius
    assert "быстрый шаг — радиус больше" in fast.turn.reply


def test_feeling_the_cold_puts_indoor_places_first_in_a_chill():
    chill = manual_weather(-8.0)
    plain = _ask("куда сходить", weather=chill)
    cold = _ask("куда сходить", Profile(cold_tolerance="low"), weather=chill)
    assert _ids(plain) != _ids(cold)
    assert cold.turn.places[0].category in INDOOR
    assert "вы мёрзнете — в холод сначала помещения" in cold.turn.reply


def test_taking_the_cold_easily_keeps_the_outdoors_in_a_frost():
    frost = manual_weather(-20.0)
    plain = _ask("куда сходить", weather=frost)
    hardy = _ask("куда сходить", Profile(cold_tolerance="high"), weather=frost)
    assert _ids(plain) != _ids(hardy)
    assert "холод переносите легко" in hardy.turn.reply


def test_a_low_budget_says_so_on_the_lead_and_the_cards():
    plain, low = _ask("кафе"), _ask("кафе", Profile(budget="low"))
    assert "недорого" in low.turn.reply
    assert "недорого" not in plain.turn.reply
    assert any("дешевле" in p.note.lower() or "цен" in p.note.lower() for p in low.turn.places)


def test_a_quiet_setting_leaves_the_loud_kinds_out():
    plain = _ask("куда сходить вечером", when=EVENING)
    quiet = _ask("куда сходить вечером", Profile(quiet=True), when=EVENING)
    loud = {"bar_nightlife", "entertainment"}
    assert not {p.category for p in quiet.turn.places} & loud
    assert _ids(plain) != _ids(quiet)
    assert "тихие места" in quiet.turn.reply


def test_a_wheelchair_puts_the_tagged_place_first_and_counts_honestly():
    pois = [*_city(), _poi("ramp_cafe", 420, "cafe", tags=["wheelchair=yes"])]
    plain = _ask("кафе", pois=pois)
    wheel = _ask("кафе", Profile(mobility="wheelchair"), pois=pois)
    assert _ids(wheel)[0] == "ramp_cafe" != _ids(plain)[0]
    assert "вход без ступенек — в данных отмечен у 1 из" in wheel.turn.reply
    none = _ask(
        "кафе", Profile(mobility="stroller")
    )  # no record says step-free: said so, nothing promised
    assert "у этих мест в данных об этом ничего нет" in none.turn.reply


def test_the_saved_answer_language_answers_a_message_without_words():
    assert _ask("☕").turn.lang == "ru"
    assert _ask("☕", Profile(language="en")).turn.lang == "en"
    assert _ask("👍", Profile(language="kk")).turn.lang == "kk"


def test_the_about_text_reaches_the_model_and_the_lead_claims_it_only_then(monkeypatch):
    about = "не пью кофе, люблю тишину"
    seen: list[str] = []

    def fake_json(prompt, schema, **kw):
        seen.append(prompt)
        raise llm.LLMUnavailable("test: no answer")

    offline = _ask("кафе", Profile(about=about))
    assert (
        "ваш текст о себе" not in offline.turn.reply
    )  # nothing went to a model: nothing is claimed
    monkeypatch.setattr(gen_mod, "ai_off_reason", lambda use_llm: "")
    monkeypatch.setattr(gen_mod, "generate_json", fake_json)
    env = TurnEnv(
        when=NOON, use_llm=True, router=offline_router(), pois=_city(), profile=Profile(about=about)
    )
    take_turn(new_state(*ORIGIN), "кафе", env)
    assert any(about in p for p in seen)


def test_the_halal_chip_is_offered_in_every_language():
    for text in ("халяль кафе", "халал тағам", "halal food"):
        intent = parse_rules(text).intent
        assert intent.halal, text
        keys = [c.key for c in suggest_chips(intent, Constraints(), Profile(), text)]
        assert "halal" in keys, text


def test_a_budget_the_data_cannot_act_on_is_no_setting():
    assert get_args(ProfileBudget) == (
        "any",
        "low",
    )  # the data hold no prices: «средний / дороже» did nothing
    assert CHOICES["budget"] == ("any", "low")
    assert (
        Profile.model_validate({"budget": "high"}).budget == "any"
    )  # a profile saved before still loads
    with pytest.raises(ValidationError):
        ProfileForm(budget="medium")
    pricey = parse_rules("дорогой ресторан").intent
    assert not [
        c for c in suggest_chips(pricey, Constraints(), Profile()) if c.key.startswith("budget")
    ]


def test_halal_is_never_claimed_on_an_answer_of_bars():
    turn = _ask("хочу выпить", Profile(halal=True), when=EVENING).turn
    assert not {p.category for p in turn.places} & {"restaurant", "cafe", "fast_food"}
    assert "халяль" not in turn.reply
    food = _ask(
        "хочу поесть", Profile(halal=True), pois=[*_city(), _poi("rest1", 240, "restaurant")]
    )
    assert "халяль — у этих мест в данных о халяль ничего нет" in food.turn.reply


def test_a_word_for_a_family_does_not_lift_the_avoided_kind():
    pois = [*_city(), _poi("rest1", 240, "restaurant"), _poi("rest2", 280, "restaurant")]
    eat = _ask("хочу поесть", Profile(avoid=["cafe"]), pois=pois).turn
    assert eat.places
    assert "cafe" not in {p.category for p in eat.places}
    coffee = _ask(
        "хочу кофе", Profile(avoid=["cafe"]), pois=pois
    ).turn  # the kind named by its own word
    assert coffee.places[0].category == "cafe"
