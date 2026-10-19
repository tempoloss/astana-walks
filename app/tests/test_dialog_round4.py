"""Round 4 of the human testers (rules only, no key): weather questions inside a dialogue about a place, several
questions in one message, closing hours, kids follow-ups near a saved place, a refused kind that was never asked for,
and a time of day that has gone by. Behaviour, not wording: topics, ids, categories, moments."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from walks import metno
from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_questions import place_question
from walks.dialog_types import DialogState, ShownPlace
from walks.dialog_when import read_when
from walks.models import POI, Bookmark
from walks.walking import offline_router
from walks.weather import make_weather

EXPO = (51.0890, 71.4160)
SATURDAY = datetime(2026, 10, 17, 15, 0)
HOME = Bookmark(name="Үй", kind="home", lat=51.10, lon=71.45)


def _env(*, when: datetime = SATURDAY, pois=None, bookmarks=()) -> TurnEnv:
    now = make_weather(3.0, 0.0, 6.0, 0.0, source="metar", observed_at="2026-10-17T14:50+05:00")
    return TurnEnv(
        when=when,
        use_llm=False,
        router=offline_router(),
        weather=now,
        pois=pois,
        bookmarks=list(bookmarks),
    )


def dialogue(lang: str, *messages: str, env: TurnEnv | None = None):
    env = env or _env()
    state, outs = new_state(*EXPO, lang), []
    for m in messages:
        out = take_turn(state, m, env)
        state = out.state
        outs.append(out)
    return outs, state


def cafe(**fields) -> POI:
    return POI(id="t/1", name="Test Cafe", lat=51.0895, lon=71.4165, category="cafe", **fields)


def showing(poi: POI, lang: str = "ru") -> DialogState:
    return new_state(*EXPO, lang).model_copy(
        update={"shown": [ShownPlace(id=poi.id, name=poi.name, kind="кафе", minutes=3)]}
    )


@pytest.fixture
def rainy_tomorrow():
    metno.reset()
    metno._state.entries = [
        metno._Entry(  # Sunday 12:00 in Astana
            time=datetime(2026, 10, 18, 7, 0, tzinfo=UTC),
            temperature_c=5.0,
            humidity_pct=80.0,
            wind_ms=3.0,
            precipitation_mm=1.4,
            cloud_pct=100.0,
            symbol="rain",
        )
    ]
    yield
    metno.reset()


# ------------------------------------------------------------------ 1. weather inside a dialogue about a place


def test_is_it_cold_outside_after_a_place_is_the_weather_not_the_terrace():
    outs, _ = dialogue("ru", "кофе рядом", "а на улице щас холодно, мне идти?")
    out = outs[1]
    assert out.turn.kind == "place_answer"
    assert out.result is None
    assert out.turn.answers[0].topic == "weather"
    assert out.turn.answers[0].known
    assert [p.id for p in out.turn.places] == [p.id for p in outs[0].turn.places]


def test_will_it_rain_tomorrow_is_the_forecast_and_no_report_of_rain(rainy_tomorrow):
    outs, state = dialogue("ru", "кофе рядом", "а завтра дождь будет?")
    out = outs[1]
    answer = out.turn.answers[0]
    assert out.turn.kind == "place_answer"
    assert out.result is None
    assert answer.topic == "weather"
    assert "дожд" in answer.text
    assert "По вашим словам" not in out.turn.reply
    assert state.conversation.intent.weather_hint == "none"  # a question is not the person's report


def test_a_report_of_rain_inside_a_request_is_still_a_report():
    outs, state = dialogue("ru", "идёт дождь, хочу кофе")
    assert outs[0].turn.kind == "places"
    assert state.conversation.intent.weather_hint == "rain"


# ------------------------------------------------------------------ 2. questions about the shown place


def test_the_kids_menu_here_is_a_question_about_the_shown_place_in_kazakh():
    outs, state = dialogue("kk", "кафе жақын жерде", "мұнда балалар мәзірі бар ма")
    out = outs[1]
    assert out.turn.kind == "place_answer"
    assert out.result is None
    assert out.turn.answers[0].topic == "menu_kids"
    assert out.state.shown == state.shown


def test_the_kazakh_there_is_question_without_here_is_still_a_search():
    assert place_question("балалар мәзірі бар кафе бар ма") is None


def test_both_parts_of_a_message_are_answered():
    poi = cafe(price_text="500 тг.", tags=["amenity=cafe", "toilets=yes"])
    env = _env(pois=[poi])
    out = take_turn(showing(poi), "сколько стоит вход и есть ли там туалет", env)
    topics = [a.topic for a in out.turn.answers]
    assert topics == ["entry", "toilet"]
    assert out.turn.answers[0].known
    assert out.turn.answers[1].known
    assert "500" in out.turn.reply
    assert "туалет" in out.turn.reply.lower()


def test_a_toilet_the_record_does_not_hold_is_honestly_not_in_the_data():
    poi = cafe()
    out = take_turn(showing(poi), "сколько стоит вход и есть ли там туалет", _env(pois=[poi]))
    entry, toilet = out.turn.answers
    assert not entry.known
    assert not toilet.known
    assert "в данных этого нет" in toilet.text


def test_a_price_question_alone_is_not_answered_twice():
    pq = place_question("сколько стоит вход", allow_kind=True)
    assert pq.topic == "entry"
    assert pq.also == ()


def test_until_what_time_is_the_closing_time_today_when_it_is_open():
    poi = cafe(opening_hours="Tu-Su 10:00-18:00")
    out = take_turn(showing(poi), "а до какого часа он работает?", _env(pois=[poi]))
    (a,) = out.turn.answers
    assert a.topic == "hours"
    assert a.known
    assert "18:00" in a.text
    assert a.source is not None
    assert a.source.label in a.text or "OpenStreetMap" in a.text


def test_until_what_time_when_closed_is_the_next_opening_and_the_closing_after_it():
    poi = cafe(opening_hours="Tu-Sa 10:00-18:00")
    env = _env(
        when=datetime(2026, 10, 17, 19, 0), pois=[poi]
    )  # Saturday evening, shut until Tuesday
    out = take_turn(showing(poi), "до скольки он работает", env)
    (a,) = out.turn.answers
    assert a.topic == "hours"
    assert a.known
    assert "10:00" in a.text
    assert "18:00" in a.text
    assert "сейчас закрыто" in a.text


def test_until_what_time_without_a_schedule_says_the_data_has_none():
    poi = cafe()
    out = take_turn(showing(poi), "до какого часа он работает?", _env(pois=[poi]))
    (a,) = out.turn.answers
    assert not a.known


# ------------------------------------------------------------------ 3. kids follow-ups near a saved place


def test_a_play_place_for_kids_near_the_saved_home_is_a_new_search_near_it():
    env = _env(bookmarks=[HOME])
    outs, state = dialogue(
        "kk",
        "балалар тоңып қалды, жылы кафе керек",
        "үйдің жанында балаларға ойнайтын жер бар ма",
        env=env,
    )
    out = outs[1]
    intent = state.conversation.intent
    assert out.turn.kind == "places"
    assert "kids_playground" in intent.categories
    assert "cafe" not in intent.categories
    assert out.turn.origin == (HOME.lat, HOME.lon)
    assert state.bookmark == "Үй"


def test_a_kind_refused_that_was_never_asked_for_stays_refused_on_kids_places():
    outs, state = dialogue(
        "kk", "балаларға батут немесе ойын орталығы", "жоқ, бұл емес… сауда орталығы емес"
    )
    out = outs[1]
    assert out.turn.kind == "places"
    assert all(p.category != "mall" for p in out.turn.places)
    assert "mall" in state.conversation.intent.refused
    assert state.conversation.intent.with_kids


def test_refusing_the_only_kind_asks_what_instead():
    for lang, first, refusal in (
        ("ru", "хочу в торговый центр", "нет, не то, не торговый центр"),
        ("kk", "сауда орталығына барайық", "жоқ, бұл емес… сауда орталығы емес"),
    ):
        outs, _ = dialogue(lang, first, refusal)
        assert outs[1].turn.kind == "clarify"
        assert outs[1].turn.places == []


# ------------------------------------------------------------------ 4. a time of day that has gone by


NIGHT = datetime(2026, 10, 17, 23, 0)
SMALL_HOURS = datetime(2026, 10, 18, 2, 0)


@pytest.mark.parametrize(
    ("text", "now", "moment", "note"),
    [
        ("кафе вечером", NIGHT, datetime(2026, 10, 18, 19, 0), "passed_evening"),
        ("утром музей", NIGHT, datetime(2026, 10, 18, 9, 0), "passed_morning"),
        (
            "кафе в 19:00",
            datetime(2026, 10, 17, 20, 0),
            datetime(2026, 10, 18, 19, 0),
            "passed_clock",
        ),
        ("кафе вечером", SMALL_HOURS, datetime(2026, 10, 18, 19, 0), "small_hours"),
        ("кафе вечером", SATURDAY, datetime(2026, 10, 17, 19, 0), ""),
        ("кафе в 19:00", SATURDAY, datetime(2026, 10, 17, 19, 0), ""),
        ("кафе at 7pm", SATURDAY, datetime(2026, 10, 17, 19, 0), ""),
    ],
)
def test_a_part_of_the_day_or_a_clock_time_that_has_gone_by_is_moved_and_said(
    text, now, moment, note
):
    asked = read_when(text, now)
    assert asked.moment == moment
    assert asked.note == note
    assert asked.rest in {"кафе", "музей", "кафе at"} or asked.rest == "кафе"


def test_the_reply_says_the_evening_is_over():
    outs, _ = dialogue("ru", "кафе вечером", env=_env(when=NIGHT))
    reply = outs[0].turn.reply
    assert reply.startswith("Завтра вечером, 19:00.")
    assert "вечер уже прошёл" in reply
    assert outs[0].result.when == datetime(2026, 10, 18, 19, 0)


def test_the_reply_says_a_clock_time_has_gone_by_in_english():
    outs, _ = dialogue("en", "cafe at 19:00", env=_env(when=datetime(2026, 10, 17, 20, 0)))
    assert "has gone by today" in outs[0].turn.reply


def test_a_time_still_ahead_is_not_commented():
    outs, _ = dialogue("ru", "кафе в 19:00")
    assert "уже прошло" not in outs[0].turn.reply
    assert outs[0].turn.reply.startswith("Сегодня, 19:00.")


def test_a_decimal_number_is_no_clock_time():
    assert read_when("кафе рядом 1.5 км", SATURDAY) is None
