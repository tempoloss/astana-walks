"""Round 5 of the human testers (rules only, no key): a message that asks several things about the shown place, a
kids' request that the data cannot answer with a play place, one comparison of degrees in every language, and the
afisha block that speaks the answer's language. Behaviour, not wording: topics, categories, numbers."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from walks import metno
from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_extras import events_block
from walks.dialog_questions import place_question
from walks.dialog_weather import compare_clause
from walks.models import POI, Bookmark
from walks.walking import offline_router
from walks.weather import make_weather

EXPO = (51.0890, 71.4160)
SATURDAY = datetime(2026, 10, 24, 15, 0)
HOME = Bookmark(name="Үй", kind="home", lat=51.10, lon=71.45)
CYRILLIC = set("абвгдеёжзийклмнопрстуфхцчшщъыьэюя")


def _env(feels: float = 1.0, *, when: datetime = SATURDAY, pois=None, bookmarks=()) -> TurnEnv:
    now = make_weather(feels, feels, 6.0, 0.0, source="metar", observed_at="2026-10-24T14:50+05:00")
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


# ------------------------------------------------------------------ 1. compound questions


@pytest.mark.parametrize(
    ("text", "topics"),
    [
        ("а до скольки он работает и есть ли розетки и вайфай", ["hours", "socket", "wifi"]),
        ("а розетки есть и вайфай", ["socket", "wifi"]),
        ("есть ли там розетки и wi-fi?", ["socket", "wifi"]),
    ],
)
def test_every_part_of_a_compound_question_is_answered_about_the_shown_place(text, topics):
    poi = POI(
        id="t/1",
        name="Test Cafe",
        lat=51.0895,
        lon=71.4165,
        category="cafe",
        opening_hours="Mo-Su 09:00-23:00",
        tags=["amenity=cafe", "socket:schuko=4", "internet_access=wlan"],
        internet_access="wlan",
    )
    env = _env(pois=[poi])
    first = take_turn(
        new_state(*EXPO, "ru").model_copy(
            update={
                "shown": [
                    __import__("walks.dialog_types", fromlist=["ShownPlace"]).ShownPlace(
                        id=poi.id, name=poi.name, kind="кафе", minutes=3
                    )
                ]
            }
        ),
        text,
        env,
    )
    assert first.turn.kind == "place_answer"
    assert first.result is None
    assert [a.topic for a in first.turn.answers] == topics
    assert [p.id for p in first.turn.places] == ["t/1"]
    wifi = [a for a in first.turn.answers if a.topic == "wifi"]
    assert all(a.known for a in wifi)


def test_wifi_words_are_the_wifi_topic():
    for word in ("вайфай", "wi-fi", "wifi", "интернет"):
        assert place_question(f"а {word} там есть?").topic == "wifi"


def test_a_compound_question_after_a_search_is_not_a_new_search():
    outs, _ = dialogue("ru", "кофе рядом", "а до скольки он работает и есть ли розетки и вайфай")
    assert outs[1].result is None
    assert outs[1].turn.kind == "place_answer"
    assert outs[1].turn.places[0].id == outs[0].turn.places[0].id


def test_a_request_with_a_kind_and_wifi_is_still_a_search():
    outs, _ = dialogue("ru", "кофе рядом", "кафе с вайфаем")
    assert outs[1].turn.kind == "places"


# ------------------------------------------------------------------ 2-3. kids when the data has no play place


FROST = _env(-25.0)


@pytest.mark.parametrize(
    "texts",
    [
        ("детям тоңып қалды, жылы кафе керек", "үйдің жанында балаларға ойнайтын жер бар ма"),
        ("үйдің жанында балаларға ойнайтын жер бар ма",),
        ("балалармен қайда барсам болады",),
    ],
)
def test_a_kids_request_that_gets_no_play_place_says_so(texts):
    env = _env(-25.0, bookmarks=[HOME])
    outs, state = dialogue("kk", *texts, env=env)
    out = outs[-1]
    intent = state.conversation.intent
    assert out.turn.kind == "places"
    assert "kids_playground" in intent.categories
    assert intent.with_kids
    assert "cafe" not in intent.categories
    kids = {p.category for p in out.turn.places}
    if "kids_playground" not in kids:
        assert out.turn.reply.startswith("Жақын жерде балалар алаңдары")


def test_the_gap_is_not_said_when_a_play_place_is_shown():
    outs, _ = dialogue("ru", "с ребёнком куда сходить")
    assert any(p.category == "kids_playground" for p in outs[0].turn.places)
    assert "в данных нет" not in outs[0].turn.reply


def test_the_kids_request_near_the_saved_home_is_a_new_search_there():
    env = _env(bookmarks=[HOME])
    outs, state = dialogue(
        "kk",
        "детям тоңып қалды, жылы кафе керек",
        "үйдің жанында балаларға ойнайтын жер бар ма",
        env=env,
    )
    assert outs[1].turn.origin == (HOME.lat, HOME.lon)
    assert state.bookmark == "Үй"
    assert "kids_playground" in state.conversation.intent.categories


def test_where_to_go_with_the_kids_means_kids_places():
    outs, state = dialogue("kk", "балалармен қайда барсам болады")
    assert {"kids_playground", "museum_gallery"} <= set(state.conversation.intent.categories)
    assert state.conversation.intent.with_kids
    assert outs[0].turn.places


# ------------------------------------------------------------------ 4. one comparison


@pytest.mark.parametrize(
    ("then", "now", "kind", "degrees"),
    [
        (4.4, 0.6, "warmer", 3),
        (3.7, 0.7, "warmer", 3),
        (-2.4, 1.4, "colder", 3),
        (4.2, 4.0, "same", None),
    ],
)
def test_the_difference_is_of_the_degrees_the_answer_shows(then, now, kind, degrees):
    said = {lang: compare_clause(then, now, lang) for lang in ("kk", "ru", "en")}
    for text in said.values():
        if degrees is not None:
            assert f"{degrees} °C" in text
    key = {
        "warmer": ("жылырақ", "Теплее", "Warmer"),
        "colder": ("суығырақ", "Холоднее", "Colder"),
        "same": ("шамасында", "так же", "same"),
    }[kind]
    assert key[0] in said["kk"]
    assert key[1] in said["ru"]
    assert key[2] in said["en"]


def test_plus_four_against_plus_one_is_three_in_every_language():
    for lang in ("kk", "ru", "en"):
        assert " 3 °C" in compare_clause(3.6, 0.6, lang)
        assert "+4" not in compare_clause(3.6, 0.6, lang)
        assert "+1 °C" in compare_clause(3.6, 0.6, lang)


@pytest.fixture
def forecast():
    metno.reset()
    metno._state.entries = [
        metno._Entry(
            time=datetime(2026, 10, 25, 7, 0, tzinfo=UTC),
            temperature_c=3.6,
            humidity_pct=50.0,
            wind_ms=3.0,
            precipitation_mm=0.0,
            cloud_pct=20.0,
            symbol="clearsky_day",
        )
    ]
    yield
    metno.reset()


def test_afternoon_is_the_same_hour_in_kazakh_and_russian():
    from walks.dialog_when import read_when

    kk, ru = read_when("ертең күндіз", SATURDAY), read_when("завтра днём", SATURDAY)
    assert kk.moment == ru.moment == datetime(2026, 10, 25, 13, 0)


def test_the_same_forecast_gives_the_same_difference_in_kazakh_and_russian(forecast):
    env = _env(0.6)
    ru, _ = dialogue("ru", "а завтра днём будет теплее?", env=env)
    kk, _ = dialogue("kk", "ертең күндіз жылырақ па", env=env)
    assert "на 3 °C" in ru[0].turn.answers[0].text
    assert "3 °C жылырақ" in kk[0].turn.answers[0].text


# ------------------------------------------------------------------ 5. the afisha block speaks the answer's language


@pytest.mark.parametrize("lang", ["kk", "ru", "en"])
def test_the_events_block_words_are_the_answers_language(lang):
    block = events_block(*EXPO, SATURDAY, lang, today=SATURDAY, window_min=600)
    assert block is not None
    own = [
        block.heading,
        block.note,
        *(i.when for i in block.items),
        *(i.price for i in block.items),
    ]
    spoken = " ".join(own).lower()
    has_cyrillic = bool(CYRILLIC & set(spoken))
    if lang == "en":
        assert not has_cyrillic
    else:
        assert "рядом" in block.heading.lower() or "жақын" in block.heading.lower()
    assert ("жақын жерде" in block.heading) == (lang == "kk")
    assert (block.heading == "Сегодня рядом") == (lang == "ru")
    assert (block.heading == "Nearby today") == (lang == "en")


def test_the_turn_carries_the_events_in_the_turn_language():
    outs, _ = dialogue("kk", "кафе жақын жерде")
    block = outs[0].turn.events
    assert block is None or "жақын жерде" in block.heading
