"""Round-3 fuzz findings of the intent step: tenge budgets, group size, `other` from the model, photo spots, a child's age,
language of short english questions, named places and questions about them, pets, kk words."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks import intent as intent_mod
from walks import llm
from walks.intent import merge_intents, parse_rules, refine_prompt
from walks.lexicon import is_info_question, named_places
from walks.models import Intent, LLMStep
from walks.quantities import child_age, group_size, price_cap_kzt

NIGHT = datetime(2026, 10, 14, 21, 0)


def rules(text: str, when: datetime | None = None) -> Intent:
    return parse_rules(text, when).intent


# ---- tenge budgets -------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "cap"),
    [
        ("обед до 3000 тг", 3000),
        ("не дороже 5000 тенге", 5000),
        ("где поесть, бюджет 4 500 тг", 4500),
        ("3000 теңгеге дейін тамақ", 3000),
        ("5 мыңға дейін", 5000),
        ("under 3000 tenge", 3000),
        ("lunch up to 5k tenge", 5000),
        ("до 5 тысяч", 5000),
        ("в пределах 2 тыс. тенге", 2000),
        ("coffee for 1500 KZT", 1500),
        ("1500₸ на двоих", 1500),
    ],
)
def test_a_tenge_cap_is_read_and_means_low(text, cap):
    i = rules(text)
    assert i.price_cap_kzt == cap
    assert i.budget == "low"


@pytest.mark.parametrize(
    "text",
    [
        "прогулка 30-60 мин",
        "2 часа, кофе",
        "кофе в 5 минутах",
        "нас 3000",  # a number of people is not money
        "5 тысяч человек на концерте",
        "парк, 15:30",
        "до 18:00",
        "+35 жара",
    ],
)
def test_no_money_no_cap(text):
    assert rules(text).price_cap_kzt == 0


def test_a_big_cap_is_not_a_low_budget_and_fancy_stays_fancy():
    i = rules("ужин до 50000 тг")
    assert i.price_cap_kzt == 50000
    assert i.budget == "any"
    assert rules("fine dining, up to 5000 tenge").budget == "high"
    assert price_cap_kzt("") == 0


def test_a_model_cannot_set_the_cap_or_group_or_info():
    fake = Intent(price_cap_kzt=100, group_size=40, info_about=["Байтерек"], pets=True)
    merged = merge_intents(rules("кофе"), fake, "кофе")
    assert (merged.price_cap_kzt, merged.group_size, merged.info_about, merged.pets) == (
        0,
        0,
        [],
        False,
    )


def test_the_models_prompt_has_none_of_the_round3_fields():
    prompt = refine_prompt("кофе до 3000 тг", rules("кофе до 3000 тг"))
    for name in ("price_cap_kzt", "group_size", "info_about", "pets"):
        assert name not in prompt


# ---- group size ----------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "n"),
    [
        ("нас 8 человек, нужен стол", 8),
        ("нужен стол на большую компанию, нас восемь", 8),
        ("сегіз адаммыз", 8),
        ("біз 8 адамбыз, қайда тамақтанамыз", 8),
        ("party of 8, where can we all have dinner together", 8),
        ("table for 6 please", 6),
        ("we are 5 people", 5),
        ("12 of us", 12),
        ("нас двое", 2),
        ("компания из 7 человек", 7),
    ],
)
def test_group_size_is_read(text, n):
    assert group_size(text) == n
    assert rules(text).group_size == n


@pytest.mark.parametrize(
    "text",
    ["кофе", "нас 2 часа", "мне 25 лет", "party time", "5 минут", "в 8 вечера", "one coffee"],
)
def test_no_group_no_size(text):
    assert group_size(text) == 0


def test_a_party_in_the_evening_is_not_a_night_out():
    for text in [
        "party of 8, where can we all have dinner together",
        "вечером party of 6",
        "party of 5 tonight",
    ]:
        i = rules(text, NIGHT)
        assert not i.night, text
        assert "bar_nightlife" not in i.categories, text
        assert i.group_size >= 5


def test_a_party_that_is_a_party_is_still_one():
    assert "bar_nightlife" in rules("хочу на party", NIGHT).categories
    assert rules("let's party tonight", NIGHT).night


def test_a_group_with_no_place_kind_gets_places_to_sit():
    assert rules("нас 8 человек").categories == ["restaurant", "cafe"]
    assert rules("нас 8 человек, хочу в кино").categories == ["culture_theatre_cinema"]


def test_a_birthday_party_is_a_celebration_not_a_club():
    i = rules("birthday party for 8 of us", NIGHT)
    assert "bar_nightlife" not in i.categories
    assert {"restaurant", "entertainment"} & set(i.categories)


# ---- the model's `other` -------------------------------------------------------------------------------


def test_other_from_the_model_never_replaces_or_joins_the_rules_categories():
    text = "тыныш жәңе аз адам жер керек"
    draft = rules(text)
    merged = merge_intents(draft, Intent(categories=["other"]), text)
    assert "other" not in merged.categories
    assert merged.categories == draft.categories
    merged = merge_intents(
        rules("кофе"), Intent(categories=["other", "cafe", "museum_gallery"]), "кофе"
    )
    assert merged.categories == ["cafe", "museum_gallery"]


def test_other_through_parse_intent(monkeypatch):
    monkeypatch.setattr(llm, "llm_available", lambda: True)
    answer = Intent(categories=["other"], quiet=True)
    monkeypatch.setattr(
        intent_mod,
        "generate_json",
        lambda *a, **kw: llm.LLMCall(answer, LLMStep(chain=["m"], model="m", ms=5)),
    )
    res = intent_mod.parse_intent("тыныш жәңе аз адам жер керек")
    assert "other" not in res.intent.categories
    assert res.intent.quiet
    assert "other" in res.note


def test_the_model_cannot_make_a_daytime_request_a_night_out():
    text = "куда сходить вечером"
    merged = merge_intents(rules(text), Intent(night=True), text)
    assert not merged.night
    night_text = "что открыто ночью"
    assert merge_intents(rules(night_text), Intent(night=True), night_text).night


# ---- photo spots, a child's age, short english questions -----------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "где сделать красивые фото, фотогеничные места",
        "хочу сфотографироваться в красивом месте",
        "фотоспот рядом",
        "суретке түсу үшін әдемі орындар",
        "best photo spots nearby",
        "somewhere photogenic to take pictures",
    ],
)
def test_photo_spots_are_viewpoints_and_landmarks(text):
    cats = rules(text).categories
    assert "viewpoint" in cats
    assert "museum_gallery" not in cats
    assert "restaurant" not in cats


def test_a_kk_picture_gallery_is_still_a_museum():
    assert "museum_gallery" in rules("сурет галереясы қайда").categories


@pytest.mark.parametrize(
    "text",
    [
        "raining all day, indoor fun for a 5 year old",
        "with my 4-year-old son, somewhere warm",
        "ребёнку 4 года, куда сходить",
        "сыну 6 лет, что посмотреть",
        "5 жасар баламмен қайда барамыз",
        "5 жаста баламен",
    ],
)
def test_a_young_childs_age_is_with_kids(text):
    i = rules(text)
    assert i.with_kids
    assert "bar_nightlife" not in i.categories


def test_a_teenagers_age_is_a_minor_not_a_small_child():
    i = rules("a 15 year old wants to go out")
    assert i.minor
    assert not i.with_kids
    assert child_age("a 5 year old")
    assert not child_age("a 15 year old")
    assert not child_age("мне 2 часа")


def test_a_young_child_without_a_place_kind_gets_kids_places():
    assert rules("a 5 year old is bored").categories == ["kids_playground", "museum_gallery"]


@pytest.mark.parametrize(
    "text",
    ["Anything open on Capital Day July 6?", "is anything open on Sunday", "what is open today"],
)
def test_short_english_questions_are_english(text):
    assert rules(text).language == "en"


def test_gibberish_and_russian_with_a_latin_word_keep_their_language():
    assert rules("nuqneH jIyaj Qagh vaj Sop 'e' vIneH").language == "ru"
    assert rules("хочу в Starbucks сегодня").language == "ru"


# ---- named places and questions about them -------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("какие часы работы у Хан Шатыра", "Хан Шатыр"),
        ("Хан Шатырдың жұмыс уақыты қандай", "Хан Шатыр"),
        ("what are the opening hours of Khan Shatyr", "Khan Shatyr"),
        ("стоит ли идти в Национальный музей сейчас", "Национальный музей"),
        ("Ұлт музейіне қазір бару керек пе", "Национальный музей"),
        ("is Baiterek worth visiting", "Байтерек"),
        ("Байтерек открыт ли сейчас", "Байтерек"),
        ("что это за Нур Алем", "Nur Alem"),
        ("Хазрет Султан мечеті ашық па", "Хазрет Султан"),
    ],
)
def test_a_question_about_a_named_place_names_it(text, name):
    i = rules(text)
    assert name in i.info_about
    assert name in i.landmark_refs
    assert name in i.free_text_keywords


def test_a_kk_go_question_is_not_a_bar():
    assert "bar_nightlife" not in rules("Ұлт музейіне қазір бару керек пе").categories


@pytest.mark.parametrize(
    ("text", "name"),
    [
        ("хочу в Байтерек", "Байтерек"),
        ("go to Khan Shatyr", "Khan Shatyr"),
        ("Нур Алем рядом, дойду пешком?", "Nur Alem"),
    ],
)
def test_a_named_goal_is_a_landmark_ref_without_a_question(text, name):
    i = rules(text)
    assert name in i.landmark_refs
    assert i.info_about == []


@pytest.mark.parametrize(
    "text",
    [
        "рядом с Хан Шатыром хочу кофе",
        "возле Байтерека где поесть",
        "около ТРЦ Хан Шатыр кафе",
        "near Khan Shatyr a quiet cafe",
        "Хан Шатыр жанында кафе керек",
        "в районе Байтерека парк",
    ],
)
def test_a_name_that_only_says_where_the_user_is_is_not_a_goal(text):
    i = rules(text)
    assert i.landmark_refs == []
    assert i.info_about == []


def test_a_location_is_still_the_location_in_a_hours_question_about_something_else():
    assert not is_info_question("рядом с Байтереком хочу кофе")
    assert named_places("рядом с Байтереком хочу кофе") == [(("Байтерек", "Baiterek"), True)]


def test_the_description_of_a_tent_is_still_khan_shatyr_and_the_name_is_read_once():
    assert rules("большой шатёр, что это").landmark_refs[:2] == ["Хан Шатыр", "Khan Shatyr"]
    assert rules("какие часы у Хан Шатыра").landmark_refs == ["Хан Шатыр", "Khan Shatyr"]


# ---- pets, quiet wishes, heat words --------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "можно с собакой в кафе или на террасу",
        "where to walk my dog",
        "pet friendly cafe",
        "итпен серуендегім келеді",
        "с кошкой куда можно",
    ],
)
def test_a_pet_comes_along(text):
    assert rules(text).pets


def test_no_pet_no_flag():
    assert not rules("кофе рядом").pets


@pytest.mark.parametrize(
    "text",
    ["somewhere less crowded", "a quieter place please", "поменьше людей", "менее людное место"],
)
def test_less_crowded_is_quiet(text):
    assert rules(text).quiet


def test_kk_heat_and_chill_words_are_weather():
    assert rules("ыссы, көлеңке жер керек").weather_hint == "heat"
    assert rules("бүгін салқын, қайда барамыз").weather_hint == "cold"
