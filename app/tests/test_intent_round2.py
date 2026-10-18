"""Round-2 fuzz findings of the intent step: eating at night, stairs, kk words, diets, vague places, multi-step plans,
deadlines, shift work, wishes the data cannot answer, gibberish language."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks import intent as intent_mod
from walks import llm
from walks.intent import merge_intents, parse_rules, refine_prompt
from walks.lexicon import landmark_refs, match
from walks.models import Intent, LLMStep

AFTERNOON = datetime(2026, 10, 14, 14, 0)


def rules(text: str, when: datetime | None = None) -> Intent:
    return parse_rules(text, when).intent


# ---- eating at night keeps the eat categories ----------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "что открыто в 4 утра, хочешь есть, работаю в ночную смену",
        "ночью хочу поесть",
        "it is 4 am, i am hungry and need food, what is open at night",
        "түнде қарным ашты",
    ],
)
def test_night_plus_hunger_is_food(text):
    i = rules(text)
    assert {"restaurant", "cafe", "fast_food"} <= set(i.categories)
    assert i.night
    assert "attraction_landmark" not in i.categories


def test_night_alone_still_has_its_default_kinds():
    assert "bar_nightlife" in rules("что открыто ночью").categories


def test_a_night_shift_is_not_laptop_work():
    for text in [
        "работаю в ночную смену, где поесть",
        "после смены хочу кофе",
        "just finished my night shift, coffee",
    ]:
        assert not rules(text).needs_wifi_socket, text
    assert rules("поработать за ноутбуком").needs_wifi_socket


# ---- stairs, age, kk words -----------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "я пожилой человек, мне тяжело ходить по лестницам, куда можно спокойно сходить рядом",
        "где без лестниц",
        "no stairs please",
        "stairs are hard for me, somewhere calm",
        "картыгадан баспалдақпен жүру қиын",
        "баспалдақсыз орын керек",
    ],
)
def test_stairs_and_slow_walking_are_access(text):
    i = rules(text)
    assert i.accessibility
    assert not i.with_kids


@pytest.mark.parametrize(
    "text",
    ["баласымен ТРЦ-де уақыт өткізетін орын керек, ойнау алаңы бар жер", "баламен қайда барамыз"],
)
def test_kk_with_a_child_is_kids(text):
    assert rules(text).with_kids
    assert (
        "kids_playground"
        in rules("баласымен ТРЦ-де уақыт өткізетін орын керек, ойнау алаңы бар жер").categories
    )


def test_kk_bar_is_a_bar_after_a_conjunction_and_there_is_otherwise():
    assert "bar_nightlife" in rules("хоккей бітті, қазір ашық тұрған кафе немесе бар").categories
    assert "bar_nightlife" in rules("ресторан мен бар керек").categories
    assert "bar_nightlife" not in rules("ойнау алаңы бар жер").categories
    assert "bar_nightlife" not in rules("мұражай бар ма").categories


def test_thesis_writing_needs_a_socket():
    assert rules("write my thesis for a couple of hours").needs_wifi_socket
    assert rules("мне надо писать дипломную").needs_wifi_socket


# ---- diets ---------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "diets"),
    [
        ("вегетарианское что-нибудь есть рядом?", ["vegetarian"]),
        ("где поесть, я вегетарианец, а друг веган", ["vegetarian", "vegan"]),
        ("vegan place nearby", ["vegan"]),
        ("у меня целиакия, что поесть", ["gluten_free"]),
        ("без глютена и без мяса", ["vegetarian", "gluten_free"]),
        ("глютенге аллергиям бар, қайда тамақтануға болады", ["gluten_free"]),
        ("gluten free bakery", ["gluten_free"]),
        ("где поесть кошерную еду", ["kosher"]),
        ("looking for kosher food near the National Museum", ["kosher"]),
    ],
)
def test_diets_are_flags(text, diets):
    assert rules(text).diets == diets


def test_a_diet_word_that_is_negated_is_no_diet():
    assert rules("не вегетарианец, хочу стейк").diets == []
    assert rules("кофе").diets == []


def test_a_diet_request_never_gets_bars_from_the_model():
    text = "глютенге аллергиям бар, қайда тамақтануға болады"
    merged = merge_intents(rules(text), Intent(categories=["bar_nightlife", "restaurant"]), text)
    assert "bar_nightlife" not in merged.categories
    assert merged.diets == ["gluten_free"]


def test_a_model_cannot_set_diets_or_plan_or_landmarks():
    text = "кофе"
    fake = Intent(
        diets=["vegan"], landmark_refs=["Байтерек"], plan_order=["museum_gallery", "cafe"]
    )
    merged = merge_intents(rules(text), fake, text)
    assert merged.diets == []
    assert merged.landmark_refs == []
    assert merged.plan_order == []


def test_the_models_prompt_does_not_carry_the_rules_only_new_fields():
    prompt = refine_prompt("вегетарианское", rules("вегетарианское"))
    assert "diets" not in prompt
    assert "plan_order" not in prompt
    assert "landmark_refs" not in prompt


# ---- vague places --------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("башня с шаром наверху, хочу подняться", "Байтерек"),
        ("үстінде шар бар мұнара қайда", "Байтерек"),
        ("tower with a ball on top", "Байтерек"),
        ("тот большой шатёр рядом, что это и можно ли туда зайти", "Хан Шатыр"),
        ("that big tent, can we go in", "Хан Шатыр"),
        ("that sphere building from the expo, can you walk inside it?", "Nur Alem"),
        ("дерево жизни это что за памятник, далеко идти?", "Дерево жизни"),
    ],
)
def test_a_vague_description_names_the_known_landmark(text, name):
    i = rules(text)
    assert name in i.landmark_refs
    assert name in i.free_text_keywords[:2] or name in i.free_text_keywords


def test_a_description_word_is_read_once_and_a_name_is_not_a_description():
    assert landmark_refs("башня с шаром") == ["Байтерек", "Baiterek"]
    assert landmark_refs("Хан Шатыр рядом") == []
    assert landmark_refs("где поесть") == []


# ---- multi-step plans and deadlines --------------------------------------------------------------------


def test_a_two_step_plan_keeps_both_kinds_in_order():
    i = rules("сначала поесть нормально, потом музей, успеть до 18:00, всё пешком")
    assert i.plan_order == ["restaurant", "museum_gallery"]
    assert {"restaurant", "museum_gallery"} <= set(i.categories)
    assert rules("first lunch, then a museum, need to be done by 6 pm").plan_order == [
        "restaurant",
        "museum_gallery",
    ]
    assert rules("мечеть, потом халяль поесть, потом парк, три часа").plan_order == [
        "attraction_landmark",
        "restaurant",
        "park_garden",
    ]


def test_no_plan_for_one_kind_or_none():
    assert rules("музей, потом ещё музей").plan_order == []
    assert rules("кофе рядом").plan_order == []


@pytest.mark.parametrize(
    ("text", "minutes"),
    [
        ("сначала поесть, потом музей, успеть до 18:00", 240),
        ("first lunch, then a museum, need to be done by 6 pm", 240),
        ("хочу успеть в музей к 17:30", 210),
        ("до 5 часов вечера погулять", 180),
        ("до 18 часов погулять", 240),
    ],
)
def test_a_deadline_is_the_minutes_left_until_it(text, minutes):
    assert rules(text, AFTERNOON).time_budget_min == minutes


def test_a_stated_duration_beats_a_deadline_and_no_clock_no_deadline():
    assert rules("музей, 2 часа, до 18:00", AFTERNOON).time_budget_min == 120
    assert rules("музей до 18:00").time_budget_min == 120  # no request clock: the museum default
    assert rules("музей до 12:00", AFTERNOON).time_budget_min == 120  # already behind us


def test_a_deadline_is_not_an_age_a_range_or_a_duration():
    i = rules("сначала поесть, потом музей, успеть до 18:00", AFTERNOON)
    assert not i.minor
    assert "bar_nightlife" not in i.exclude_categories
    assert rules("парк до 2 часов", AFTERNOON).time_budget_min != 720  # «до 2 часов» is no 02:00
    assert rules("ночной клуб для детей до 18 лет").minor


def test_the_models_longer_time_does_not_beat_a_deadline(monkeypatch):
    monkeypatch.setattr(llm, "llm_available", lambda: True)
    answer = Intent(time_budget_min=500, categories=["museum_gallery"])
    monkeypatch.setattr(
        intent_mod,
        "generate_json",
        lambda *a, **kw: llm.LLMCall(answer, LLMStep(chain=["m"], model="m", ms=5)),
    )
    res = intent_mod.parse_intent("музей, успеть до 18:00", when=AFTERNOON)
    assert res.intent.time_budget_min == 240


# ---- wishes the data cannot answer travel as keywords --------------------------------------------------


@pytest.mark.parametrize(
    ("text", "keyword"),
    [
        ("гуляю с малышом 2 лет, где детская площадка и рядом туалет с пеленальником", "туалет"),
        (
            "гуляю с малышом 2 лет, где детская площадка и рядом туалет с пеленальником",
            "пеленальник",
        ),
        ("playground and a cafe with a kids menu", "детское меню"),
        ("need a changing table and a toilet", "пеленальник"),
        ("жақын жерде дәретхана бар ма", "туалет"),
    ],
)
def test_unanswerable_wishes_become_keywords(text, keyword):
    assert keyword in rules(text).free_text_keywords


# ---- language of gibberish ----------------------------------------------------------------------------


def test_latin_gibberish_is_not_english():
    assert rules("nuqneH jIyaj Qagh vaj Sop 'e' vIneH").language == "ru"
    assert match("qwzx plmk vbnt").language == "ru"


def test_real_english_is_still_english():
    assert rules("coffee").language == "en"
    assert rules("where can i get a quick bite").language == "en"
