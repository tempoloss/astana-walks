"""Round 7 of the mother persona (rules only, no key): symptoms are not weather, a sick child is a clinic or pharmacy
wish with the child as the reason, and a close vote of a mixed message goes to the Kazakh dialogue's language."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_nlu import detect, language_votes
from walks.dialog_weather import asks_weather
from walks.intent import parse_rules
from walks.symptoms import has_symptom, sick_who
from walks.walking import offline_router
from walks.weather import make_weather

EXPO = (51.0890, 71.4160)
WED = datetime(2026, 10, 28, 12, 0)


def _env() -> TurnEnv:
    now = make_weather(16.0, 16.0, 6.0, 0.0, source="metar", observed_at="2026-10-28T11:50+05:00")
    return TurnEnv(when=WED, use_llm=False, router=offline_router(), weather=now)


def dialogue(lang: str, *messages: str):
    state, outs = new_state(*EXPO, lang), []
    for m in messages:
        out = take_turn(state, m, _env())
        state = out.state
        outs.append(out)
    return outs, state


SYMPTOMS = [
    "детская поликлиника рядом, ребёнок температурит",
    "дәріхана керек, балам ыстықтап жатыр",
    "аптека, у ребёнка жар",
    "балалар емханасы қайда, температура көтерілді",
    "ауырып қалды баламның, емхана бар ма жақын жерде",
    "аптека нужна, ребёнок заболел",
    "кашель у сына, где аптека",
    "my kid has a fever, where is a pharmacy",
    "қызуы көтерілді, дәріхана қайда",
]


# ------------------------------------------------------------------ 1. symptoms are not weather


@pytest.mark.parametrize("text", SYMPTOMS)
def test_a_symptom_never_routes_to_the_weather_answer(text):
    assert has_symptom(text)
    assert not asks_weather(text)
    out = take_turn(new_state(*EXPO, "ru"), text, _env())
    assert out.turn.kind != "place_answer"
    assert all(a.topic != "weather" for a in out.turn.answers)


@pytest.mark.parametrize("text", SYMPTOMS)
def test_a_symptom_is_never_a_weather_hint(text):
    assert parse_rules(text).intent.weather_hint == "none"


def test_a_fever_after_a_kazakh_search_is_still_a_clinic_search_not_the_weather():
    outs, state = dialogue(
        "kk",
        "ауырып қалды баламның, емхана бар ма жақын жерде",
        "детская поликлиника рядом, ребёнок температурит",
    )
    assert outs[1].turn.kind == "places"
    assert outs[1].turn.answers == []
    assert state.conversation.intent.categories == ["clinic"]


def test_the_heat_of_the_weather_is_still_a_hint_and_the_temperature_still_a_weather_question():
    assert parse_rules("жара, хочу посидеть в тени").intent.weather_hint == "heat"
    assert parse_rules("ыстық, кофе ішейік").intent.weather_hint == "heat"
    assert asks_weather("какая температура завтра")
    assert not has_symptom("температура воздуха 38 градусов")
    assert not has_symptom("сегодня жарко")


def test_symptom_words_are_read_in_three_languages():
    for text in (
        "заболел",
        "кашель",
        "ауырып қалды",
        "жөтел",
        "fever",
        "sore throat",
        "у меня жар",
    ):
        assert has_symptom(text), text


# ------------------------------------------------------------------ 2. a sick child, the child as a reason


@pytest.mark.parametrize(
    ("text", "kinds"),
    [
        ("детская поликлиника рядом, ребёнок температурит", ["clinic"]),
        ("дәріхана керек, балам ыстықтап жатыр", ["pharmacy"]),
        ("аптека нужна, ребёнок заболел", ["pharmacy"]),
        ("ауырып қалды баламның, емхана бар ма жақын жерде", ["clinic"]),
    ],
)
def test_a_sick_child_wants_the_clinic_or_pharmacy_named_and_no_kids_places(text, kinds):
    intent = parse_rules(text).intent
    assert intent.categories == kinds
    assert intent.sick == "child"
    assert not intent.with_kids
    out = take_turn(new_state(*EXPO, "ru"), text, _env())
    assert all(p.category != "kids_playground" for p in out.turn.places)


@pytest.mark.parametrize(
    "text",
    ["ребёнок температурит", "кашель у сына", "балам ыстықтап жатыр", "my daughter has a fever"],
)
def test_an_illness_without_a_kind_is_a_clinic_and_pharmacy_request(text):
    intent = parse_rules(text).intent
    assert intent.categories == ["clinic", "pharmacy"]
    assert intent.sick == "child"
    assert not intent.with_kids
    assert intent.wished == []


def test_a_sick_adult_is_marked_apart_and_a_healthy_request_is_not_marked():
    assert parse_rules("заболел, где аптека").intent.sick == "adult"
    assert parse_rules("хочу кофе").intent.sick == ""
    assert sick_who("хочу кофе") == ""
    assert sick_who("у сына жар", child=False) == "child"


def test_a_child_with_a_wish_for_a_place_is_still_a_kids_request():
    intent = parse_rules("с ребёнком куда сходить").intent
    assert intent.with_kids
    assert intent.sick == ""


def test_a_symptom_beside_a_wish_for_coffee_keeps_the_coffee():
    intent = parse_rules("хочу кофе, у меня кашель").intent
    assert intent.categories == ["cafe"]
    assert intent.sick == "adult"


def test_a_polyclinic_and_a_pediatrician_are_clinics():
    for text in ("детская поликлиника рядом", "педиатр", "балалар емханасы"):
        assert parse_rules(text).intent.categories == ["clinic"], text


# ------------------------------------------------------------------ 3. a close vote in a Kazakh dialogue


@pytest.mark.parametrize(
    ("text", "fallback", "expected"),
    [
        ("кафе с детским меню", "kk", "kk"),
        ("Вы ищете кафе с детским меню", "kk", "ru"),  # two russian words: a clear vote
        ("кафе с детским меню", "ru", "ru"),
        ("хочу кофе", "ru", "ru"),
        ("музей сегодня открыт? хочу с детьми в воскресенье", "kk", "ru"),
        ("тихое место, где можно посидеть с ребёнком", "kk", "ru"),
        ("ещё варианты", "kk", "ru"),
        ("кофе ішкім келеді", "ru", "kk"),
        ("hello", "kk", "en"),
    ],
)
def test_a_close_vote_goes_to_the_kazakh_dialogue_a_clear_russian_vote_does_not(
    text, fallback, expected
):
    assert detect(text, fallback) == expected


def test_one_russian_function_word_is_a_close_vote():
    assert language_votes("кафе с детским меню") == (0, 1)


def test_a_russian_phrase_in_a_kazakh_dialogue_with_one_function_word_answers_in_kazakh():
    outs, _ = dialogue("kk", "кафе жақын жерде", "кафе с детским меню")
    assert outs[1].turn.lang == "kk"
    assert not outs[1].turn.reply.startswith("Вы ищете")


# ------------------------------------------------------------------ 4. the cache keys of the recorded demo do not move


def test_the_sick_flag_stays_out_of_the_prompt_and_the_generation_cache_key():
    from walks.generate import _WORD_FIELDS
    from walks.intent import RULES_ONLY_FIELDS

    assert "sick" in RULES_ONLY_FIELDS
    assert "sick" in _WORD_FIELDS


# ------------------------------------------------------------------ 5. chit-chat, sports and trivia: the scope line


SCOPE = {
    "ru": "Я подсказываю места в Астане: где поесть, погулять, что посмотреть, аптеки и банкоматы рядом. Что поищем?",
    "en": "I suggest places in Astana: where to eat, walk, what to see, pharmacies and cash machines nearby. What shall we look for?",
}


@pytest.mark.parametrize(
    ("lang", "text"),
    [
        ("en", "who won the champions league last night?"),
        ("en", "tell me a joke about astana"),
        ("en", "what is the capital of france"),
        ("ru", "расскажи анекдот"),
        ("ru", "кто выиграл вчера в футбол"),
        ("ru", "какие новости"),
        ("ru", "курс доллара"),
    ],
)
def test_chit_chat_sports_news_and_trivia_get_the_scope_line_and_no_place(lang, text):
    out = take_turn(new_state(*EXPO, lang), text, _env())
    assert out.turn.reply == SCOPE[lang]
    assert out.turn.places == []


def test_the_scope_line_comes_in_kazakh_too():
    out = take_turn(new_state(*EXPO, "kk"), "анекдот айт", _env())
    assert out.turn.reply.startswith("Мен Астанадағы орындарды ұсынамын")
    assert out.turn.places == []


def test_a_place_asked_beside_the_sports_gets_its_own_honest_answer():
    out = take_turn(new_state(*EXPO, "en"), "where to watch the champions league", _env())
    assert out.turn.reply.startswith("Places that show matches are not marked in our data")
    assert out.turn.places


def test_a_plain_search_and_a_cash_question_are_not_chit_chat():
    for text in ("где обменять доллары", "кафе рядом", "news near me"):
        assert take_turn(new_state(*EXPO, "ru"), text, _env()).turn.reply not in SCOPE.values(), (
            text
        )


# ------------------------------------------------------------------ 6. an unmapped kind: PS clubs


@pytest.mark.parametrize(
    "text",
    [
        "где поиграть в плейстейшен, ПС клуб",
        "ПС-клуб",
        "PS клуб",
        "хочу на приставку",
        "xbox",
        "иксбокс",
        "киберклуб",
        "игровой клуб",
        "компьютерный клуб",
        "playstation club",
    ],
)
def test_a_gaming_club_is_said_to_be_missing_never_a_bar(text):
    out = take_turn(new_state(*EXPO, "ru"), text, _env())
    assert out.turn.reply.startswith(("Игровых клубов", "The data has no PS"))
    assert all(p.category != "bar_nightlife" for p in out.turn.places)


def test_a_nightclub_is_still_a_nightclub():
    out = take_turn(new_state(*EXPO, "ru"), "хочу в ночной клуб", _env())
    assert not out.turn.reply.startswith("Игровых клубов")


# ------------------------------------------------------------------ 7. a river or a district is no street


@pytest.mark.parametrize(
    "target",
    ["Есиля", "Есиль", "реки Есиль", "Ишим", "район Алматы", "Нуры", "Сарыарка", "Байконур"],
)
def test_a_river_or_a_district_resolves_to_the_district_not_a_street(target):
    from walks.dialog_toward import area_target

    got = area_target(target)
    assert got is not None
    assert got[2].startswith("район ")


def test_a_street_and_a_bare_city_name_are_no_area():
    from walks.dialog_toward import area_target

    assert area_target("улица Есил") is None
    assert area_target("Алматы") is None
    assert area_target("Байтерек") is None


def test_toward_the_river_says_the_district_in_the_lead():
    out = take_turn(
        new_state(*EXPO, "ru"), "где красиво вечером пройтись, в сторону Есиля по пути", _env()
    )
    assert "«район Есиль»" in out.turn.reply
    assert "улица" not in out.turn.reply


# ------------------------------------------------------------------ 8. hospitals are not in the data, clinics are


@pytest.mark.parametrize(
    "text", ["поликлиника рядом", "врач рядом", "педиатр", "детская поликлиника", "где терапевт"]
)
def test_a_polyclinic_and_a_doctor_are_clinics(text):
    out = take_turn(new_state(*EXPO, "ru"), text, _env())
    assert out.turn.kind == "places"
    assert all(p.category == "clinic" for p in out.turn.places)
    assert "нет больниц" not in out.turn.reply


@pytest.mark.parametrize(
    ("lang", "text", "starts"),
    [
        ("ru", "больница рядом", "В моих данных нет больниц и скорой помощи"),
        ("ru", "скорая помощь", "В моих данных нет больниц и скорой помощи"),
        ("ru", "где стационар", "В моих данных нет больниц и скорой помощи"),
        ("en", "hospital near me", "My data has no hospitals or ambulances"),
    ],
)
def test_a_hospital_is_honestly_missing_with_the_number_to_call(lang, text, starts):
    out = take_turn(new_state(*EXPO, lang), text, _env())
    assert out.turn.reply.startswith(starts)
    assert "103" in out.turn.reply
    assert out.turn.places == []


# ------------------------------------------------------------------ 9. the weather, then what to do in it


def test_a_weather_question_with_a_request_for_something_to_do_answers_the_weather_then_searches_indoors():
    out = take_turn(
        new_state(*EXPO, "ru"), "а че там с погодой, и чем занимать себя, если дождь", _env()
    )
    assert out.turn.reply.startswith("Сейчас в Астане +16 °C")
    assert out.turn.places
    assert "идёт дождь" not in out.turn.reply


def test_a_plain_weather_question_still_clears_nothing():
    out = take_turn(new_state(*EXPO, "ru"), "а че там с погодой", _env())
    assert out.turn.kind == "place_answer"
    assert out.turn.reply.startswith("Сейчас в Астане +16 °C")


def test_a_condition_is_not_a_report_of_the_weather():
    assert parse_rules("чем заняться если дождь").intent.weather_hint == "none"
    assert parse_rules("идёт дождь, хочу кофе").intent.weather_hint == "rain"
