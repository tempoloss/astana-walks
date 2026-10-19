"""Round 3 of the human testers (rules only, no key): weather follow-ups, «скучно», a message of mixed languages, and the
day an answer speaks about. Behaviour, not wording: topics, categories, languages, moments."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from walks import metno
from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_nlu import detect, language_votes
from walks.dialog_weather import weather_at
from walks.dialog_when import read_when
from walks.outing import is_bored
from walks.walking import offline_router
from walks.weather import make_weather
from web.turns import answer_time

EXPO = (51.0890, 71.4160)
SATURDAY = datetime(2026, 10, 17, 15, 0)
FOOD = {"cafe", "restaurant", "fast_food"}


def _env(feels: float = 3.0) -> TurnEnv:
    now = make_weather(feels, feels, 6.0, 0.0, source="metar", observed_at="2026-10-17T14:50+05:00")
    return TurnEnv(when=SATURDAY, use_llm=False, router=offline_router(), weather=now)


@pytest.fixture
def forecast():
    metno.reset()
    metno._state.entries = [
        metno._Entry(  # Sunday 13:00 in Astana
            time=datetime(2026, 10, 18, 8, 0, tzinfo=UTC),
            temperature_c=9.0,
            humidity_pct=50.0,
            wind_ms=3.0,
            precipitation_mm=0.0,
            cloud_pct=20.0,
            symbol="clearsky_day",
        )
    ]
    yield
    metno.reset()


def dialogue(lang: str, *messages: str, env: TurnEnv | None = None):
    env = env or _env()
    state, outs = new_state(*EXPO, lang), []
    for m in messages:
        out = take_turn(state, m, env)
        state = out.state
        outs.append(out)
    return outs, state


# ------------------------------------------------------------------ 1. weather follow-ups


@pytest.mark.parametrize(
    "text",
    [
        "а завтра днём будет теплее?",
        "will it be warmer tomorrow afternoon",
        "ертең күндіз жылырақ па",
    ],
)
def test_will_it_be_warmer_is_the_forecast_against_now_never_a_search(text, forecast):
    outs, _ = dialogue("ru", "кофе рядом", "какая погода?", text)
    out = outs[2]
    assert out.turn.kind == "place_answer"
    assert out.result is None
    weather = out.turn.answers[0]
    assert weather.topic == "weather"
    assert weather.known
    assert "+9" in weather.text
    assert "+3" in weather.text  # the present, said as what it is compared with
    assert [p.id for p in out.turn.places] == [p.id for p in outs[0].turn.places]


def test_colder_and_the_same_are_said_too(forecast):
    outs, _ = dialogue("ru", "а завтра днём будет теплее?", env=_env(20.0))
    assert "Холоднее" in outs[0].turn.answers[0].text
    outs, _ = dialogue("ru", "а завтра днём будет теплее?", env=_env(9.0))
    assert "так же" in outs[0].turn.answers[0].text


def test_a_second_weather_question_in_the_dialogue_is_answered_too(forecast):
    outs, _ = dialogue(
        "kk",
        "кафе жақын жерде",
        "ауа райы қандай, балаларды жылы киіндіру керек пе",
        "какая сейчас погода, как одеть детей",
    )
    first, second = outs[1], outs[2]
    assert first.turn.kind == second.turn.kind == "place_answer"
    assert first.turn.answers[0].topic == second.turn.answers[0].topic == "weather"
    assert second.turn.lang == "ru"
    assert second.turn.reply


def test_the_weather_in_a_message_with_a_comparison_and_no_forecast_says_so():
    metno.reset()
    outs, _ = dialogue("ru", "а завтра днём будет теплее?")
    answer = outs[0].turn.answers[0]
    assert not answer.known
    assert "прогноза" in answer.text.lower()


# ------------------------------------------------------------------ 2. «скучно»


@pytest.mark.parametrize(
    "text",
    [
        "щас скучно куда сходить",
        "скучно, чем заняться",
        "i'm bored, where should i go",
        "зеріктім, қайда барсам болады",
    ],
)
def test_bored_is_an_outing_never_a_cafe_first(text):
    assert is_bored(text)
    outs, state = dialogue("ru", text)
    out = outs[0]
    assert out.turn.kind == "places"
    assert out.turn.places
    assert not FOOD & {p.category for p in out.turn.places}
    assert not FOOD & set(state.conversation.intent.categories)
    assert {"entertainment", "culture_theatre_cinema"} & set(state.conversation.intent.categories)


def test_bored_after_a_new_search_is_the_same_outing():
    outs, _ = dialogue("ru", "хочу кофе", "новый поиск", "щас скучно куда сходить")
    assert not FOOD & {p.category for p in outs[2].turn.places}


def test_where_should_i_go_without_boredom_keeps_its_default_kinds():
    _, state = dialogue("ru", "куда сходить")
    assert "cafe" in state.conversation.intent.categories
    assert not is_bored("куда сходить")


# ------------------------------------------------------------------ 3. mixed languages


@pytest.mark.parametrize(
    ("text", "fallback", "expected"),
    [
        ("музей сегодня открыт? хочу с детьми в воскресенье", "kk", "ru"),
        (
            "кафе с детским меню",
            "kk",
            "kk",
        ),  # one russian word at most: a close vote, the kazakh interface's language
        (
            "музей бүгін ашық па, хочу с детьми",
            "kk",
            "kk",
        ),  # three words each: the interface's language
        ("музей бүгін ашық па, хочу с детьми", "ru", "ru"),
        ("мұражай ашық па, хочу", "ru", "kk"),  # three kazakh words against one russian
        ("ертең музей қайда", "ru", "kk"),
        ("туалет бар ма", "ru", "kk"),
        ("хочу кофе", "kk", "kk"),
    ],
)
def test_a_message_of_mixed_languages_is_read_by_its_words(text, fallback, expected):
    assert detect(text, fallback) == expected


def test_a_word_both_languages_share_votes_for_neither():
    assert language_votes("музей кафе") == (0, 0)
    assert language_votes("қазір бар жерде") == (2, 0)


def test_a_russian_phrase_in_a_kazakh_dialogue_is_answered_in_russian():
    outs, _ = dialogue(
        "kk", "кафе жақын жерде", "музей сегодня открыт? хочу с детьми в воскресенье"
    )
    assert outs[0].turn.lang == "kk"
    assert outs[1].turn.lang == "ru"
    assert outs[1].turn.reply.startswith("Завтра, 12:00.")  # the Sunday of this Saturday


# ------------------------------------------------------------------ 4. the day an answer speaks about


def test_the_weather_of_a_later_time_is_the_forecast_not_the_present(forecast):
    asked = read_when("ертең", SATURDAY)
    now = make_weather(-8.0, -8.0, 6.0, 0.0, source="metar", observed_at="2026-10-17T14:50+05:00")
    then = weather_at(now, asked)
    assert then.temperature_c == 9.0
    assert then.forecast_used
    assert weather_at(now, None) is now
    assert weather_at(now, read_when("сейчас кофе", SATURDAY)) is now


def test_no_forecast_for_that_time_claims_no_temperature():
    metno.reset()
    asked = read_when("ертең", SATURDAY)
    now = make_weather(-8.0, -8.0, 6.0, 0.0, source="metar", observed_at="2026-10-17T14:50+05:00")
    assert weather_at(now, asked).temperature_c is None


def test_the_cold_verdict_for_tomorrow_speaks_about_tomorrow(forecast):
    outs, _ = dialogue(
        "kk", "ертең балаларды қайда апарсам болады, суық емес болса", env=_env(-8.0)
    )
    reply = outs[0].turn.reply
    assert reply.startswith("Ертең, 12:00.")
    assert "+9" in reply  # the forecast, not the -8 of now
    assert "−8" not in reply
    assert "Қазір" not in reply


def test_a_search_for_tomorrow_says_nothing_about_the_cold_or_dark_of_now(forecast):
    outs, _ = dialogue("kk", "музей ертең", env=_env(-20.0))
    out = outs[0]
    assert out.result.weather.temperature_c == 9.0
    assert not out.result.weather.adverse
    assert "Қазір" not in out.turn.reply


def test_the_answer_says_how_many_days_ahead_it_is(forecast):
    env = _env()
    state = new_state(*EXPO, "ru")
    today = take_turn(state, "кофе", env)
    tomorrow = take_turn(state, "музей завтра", env)
    assert answer_time(today, "кофе", SATURDAY)["day"] >= 0
    later = answer_time(tomorrow, "музей завтра", SATURDAY)
    assert later["day"] > answer_time(today, "кофе", SATURDAY)["day"]
    assert later["time"] == "12:00"
