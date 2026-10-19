"""What real testers hit on the live stand (rules only, no key): direct questions about the place just shown, weather
questions, time words, the kazakh «бар» («there is»), words about children inside a new request, kazakh corrections.
Behaviour, not wording: topics, ids, fields, categories, moments."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from walks import metno
from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_questions import place_question
from walks.dialog_types import DialogState, ShownPlace
from walks.dialog_when import read_when
from walks.models import WeatherWarning
from walks.walking import Leg, offline_router
from walks.weather import make_weather

EXPO = (51.0890, 71.4160)
SATURDAY = datetime(2026, 10, 17, 15, 0)  # a Saturday, 15:00 Astana time
MUSEUM = (
    "node/4894937300"  # the national museum: 1000 тг. from the museum register, Tu-Su 10:00-18:00
)
DEL_PAPA = "node/10064384673"  # cuisine=italian, Fr-Sa 11:00-01:00; Mo-Th,Su 11:00-24:00
BAITEREK = "way/230401645"  # a price in the record, Mo-Th,Su 10:00-21:00; Fr,Sa 09:00-21:00
ENV = TurnEnv(when=SATURDAY, use_llm=False, router=offline_router())


def showing(place_id: str, name: str, lang: str = "ru") -> DialogState:
    state = new_state(*EXPO, lang)
    return state.model_copy(
        update={"shown": [ShownPlace(id=place_id, name=name, kind="x", distance_m=300, minutes=4)]}
    )


def say(state: DialogState, text: str, env: TurnEnv = ENV):
    out = take_turn(state, text, env)
    return out.turn, out.state, out


def dialogue(lang: str, *messages: str, env: TurnEnv = ENV):
    state, outs = new_state(*EXPO, lang), []
    for m in messages:
        out = take_turn(state, m, env)
        state = out.state
        outs.append(out)
    return outs, state


# ------------------------------------------------------------------ 1. questions about the shown place


@pytest.mark.parametrize(
    "text", ["does it cost money to go in", "вход платный?", "is it free to enter", "киру ақылы ма"]
)
def test_entry_fee_is_the_museum_registers_price_with_its_source_and_day(text):
    turn, _, _ = say(showing(MUSEUM, "Национальный музей"), text)
    assert turn.kind == "place_answer"
    (a,) = turn.answers
    assert a.topic == "entry"
    assert a.known
    assert "1000" in a.text
    assert a.source is not None
    assert "e-museum" in (a.source.label + (a.source.url or ""))
    assert "17.10.2026" in a.text  # the day the register was read


def test_entry_fee_says_plainly_when_the_data_has_none():
    turn, _, _ = say(showing(DEL_PAPA, "Del Papa"), "does it cost money to go in")
    (a,) = turn.answers
    assert a.topic == "entry"
    assert not a.known
    assert turn.kind == "place_answer"


def test_a_question_about_going_in_is_not_an_hours_answer():
    turn, _, _ = say(showing(MUSEUM, "Национальный музей"), "does it cost money to go in")
    assert [a.topic for a in turn.answers] == ["entry"]


def test_what_do_they_serve_is_the_cuisine_tag_and_never_a_new_search():
    turn, state, _ = say(
        showing(DEL_PAPA, "Del Papa", "en"), "is that kazakh food? what do they serve"
    )
    assert turn.kind == "place_answer"
    assert turn.places[0].id == DEL_PAPA
    (a,) = turn.answers
    assert a.topic == "menu_kazakh"
    assert a.known
    assert "Italian" in a.text
    assert a.text.lower().startswith("del papa: no")  # the tag says Italian: not Kazakh
    assert state.shown == showing(DEL_PAPA, "Del Papa").shown  # the shown places are untouched


def test_kids_menu_is_honestly_absent_and_the_cuisine_is_still_said():
    turn, _, _ = say(showing(DEL_PAPA, "Del Papa"), "есть детское меню?")
    (a,) = turn.answers
    assert a.topic == "menu_kids"
    assert not a.known
    assert "детск" in a.text
    assert "итальян" in a.text


def test_menu_of_a_place_with_no_cuisine_says_the_data_has_none():
    turn, _, _ = say(showing(MUSEUM, "Национальный музей"), "что там в меню?")
    (a,) = turn.answers
    assert a.topic == "menu"
    assert not a.known


def test_walk_time_to_a_named_place_is_a_route_answer_from_the_person():
    long_question = "how long does it take to walk from here to baiterek"
    turn, _, out = say(showing(DEL_PAPA, "Del Papa", "en"), long_question)
    assert turn.kind == "place_answer"
    assert out.result is None
    (a,) = turn.answers
    assert a.topic == "route"
    assert a.known
    assert turn.places[0].id == BAITEREK
    assert turn.places[0].walk.minutes >= 1
    assert f"{turn.places[0].walk.minutes} min" in a.text


class _StreetRouter:
    """A walking router that has the street leg: 17 minutes, 1300 m."""

    def leg(self, a, b, *, persist=False):
        return Leg(1300, 17, "valhalla")


def test_walk_time_uses_the_street_leg_when_the_router_has_it():
    env = TurnEnv(when=SATURDAY, use_llm=False, router=_StreetRouter())
    turn, _, _ = say(showing(DEL_PAPA, "Del Papa", "en"), "how long to walk to baiterek?", env)
    (a,) = turn.answers
    assert a.topic == "route"
    assert turn.places[0].walk.method == "valhalla"
    assert turn.places[0].walk.minutes == 17
    assert "by the streets" in a.text
    assert "17 min" in a.text


def test_hours_for_another_day_name_the_day_and_that_days_hours():
    state = showing(DEL_PAPA, "Del Papa", "en")
    turn, _, _ = say(state, "is it open on Monday?")
    (a,) = turn.answers
    assert a.topic == "hours"
    assert a.known
    assert "on Monday" in a.text
    assert "11:00–24:00" in a.text
    turn, _, _ = say(state, "is it open tomorrow")  # the Sunday of the record
    assert "tomorrow" in turn.answers[0].text
    assert "11:00–24:00" in turn.answers[0].text
    assert "now" not in turn.answers[0].text.split("(")[0]  # never «open now» for another day


def test_place_question_reads_the_new_topics():
    assert place_question("does it cost money to go in").topic == "entry"
    assert (
        place_question("is that kazakh food? what do they serve", allow_kind=True).topic
        == "menu_kazakh"
    )
    assert place_question("есть детское меню?").topic == "menu_kids"
    assert place_question("how long does it take to walk from here to baiterek").topic == "route"


# ------------------------------------------------------------------ 2. the weather


@pytest.fixture
def forecast():
    metno.reset()
    metno._state.entries = [
        metno._Entry(
            time=datetime(2026, 10, 18, 7, 0, tzinfo=UTC),  # Sunday 12:00 in Astana
            temperature_c=-4.0,
            humidity_pct=60.0,
            wind_ms=5.0,
            precipitation_mm=0.6,
            cloud_pct=90.0,
            symbol="snow",
        )
    ]
    yield
    metno.reset()


def _weather_env(warnings=()):
    now = make_weather(
        2.0,
        -1.0,
        18.0,
        0.0,
        source="metar",
        observed_at="2026-10-17T14:50+05:00",
        warnings=list(warnings),
    )
    return TurnEnv(when=SATURDAY, use_llm=False, router=offline_router(), weather=now)


STORM = WeatherWarning(
    kind="storm",
    title="Штормовое предупреждение",
    text="Астана: 18 октября сильный ветер до 25 м/с.",
    source_url="https://www.kazhydromet.kz/ru/pogoda/shtormovye-preduprezhdeniya",
    valid_from="2026-10-17T06:00:00+05:00",
    valid_to="2026-10-18T23:00:00+05:00",
    active=True,
)


@pytest.mark.parametrize(
    "text",
    ["какая погода?", "а че там с погодой", "what's the weather", "что надеть", "ауа райы қандай"],
)
def test_a_weather_question_is_answered_from_the_data_and_keeps_the_map(text, forecast):
    env = _weather_env([STORM])
    (first, *_), state = dialogue("ru", "кофе рядом", env=env)
    ids = [p.id for p in first.turn.places]
    out = take_turn(state, text, env)
    turn = out.turn
    assert turn.kind == "place_answer"
    assert out.result is None
    assert [p.id for p in turn.places] == ids  # the places stay: the map is not cleared
    assert out.state.shown == state.shown
    assert out.state.conversation == state.conversation
    weather, notice = turn.answers
    assert weather.topic == "weather"
    assert weather.known
    assert "+2" in weather.text
    assert weather.source is not None
    assert "METAR" in weather.source.label
    assert notice.topic == "weather_notice"
    assert notice.source.url == STORM.source_url
    assert turn.notices
    assert turn.notices[0].source.url == STORM.source_url


def test_a_weather_question_before_any_search_has_no_places_but_still_answers(forecast):
    turn, state, _ = say(new_state(*EXPO, "en"), "whats the weather gonna be like?", _weather_env())
    assert turn.kind == "place_answer"
    assert turn.places == []
    assert turn.answers[0].topic == "weather"
    assert state.conversation is None


def test_tomorrows_weather_is_the_met_norway_forecast_of_that_hour(forecast):
    state = new_state(*EXPO, "en")
    turn, _, _ = say(
        state, "whats the weather gonna be like tomorrow? what should i wear", _weather_env()
    )
    (a,) = turn.answers
    assert "−4" in a.text
    assert "tomorrow" in a.text.lower()
    assert "12:00" in a.text
    assert "snow" in a.text
    assert "What to wear" in a.text
    assert a.source is not None
    assert "MET Norway" in a.source.label
    assert "+2" not in a.text  # the present observation is not tomorrow's weather


def test_no_forecast_for_the_asked_time_is_said_not_guessed():
    metno.reset()
    turn, _, _ = say(new_state(*EXPO, "ru"), "какая погода завтра", _weather_env())
    (a,) = turn.answers
    assert not a.known
    assert "прогноза" in a.text.lower()


@pytest.mark.parametrize(
    "text",
    [
        "где поесть в такую погоду",
        "куда пойти если дождь",
        "кофе в такую погоду",
        "what to do in this weather",
    ],
)
def test_a_request_with_the_weather_in_it_is_still_a_search(text):
    turn, _, _ = say(new_state(*EXPO, "ru"), text, _weather_env())
    assert turn.kind != "place_answer"


# ------------------------------------------------------------------ 3. time words


@pytest.mark.parametrize(
    ("text", "moment", "rest"),
    [
        ("завтра", datetime(2026, 10, 18, 12, 0), ""),
        ("tomorrow morning", datetime(2026, 10, 18, 9, 0), ""),
        ("lunch tomorrow", datetime(2026, 10, 18, 13, 0), "lunch"),
        ("в воскресенье днём", datetime(2026, 10, 18, 13, 0), ""),
        ("on Sunday", datetime(2026, 10, 18, 12, 0), ""),
        ("жексенбіде", datetime(2026, 10, 18, 12, 0), ""),
        ("ертең", datetime(2026, 10, 18, 12, 0), ""),
        ("кешке", datetime(2026, 10, 17, 19, 0), ""),
        ("утром", datetime(2026, 10, 18, 9, 0), ""),
        ("ночью кофе", datetime(2026, 10, 17, 23, 0), "кофе"),
        ("кафе в понедельник вечером", datetime(2026, 10, 19, 19, 0), "кафе"),
        ("послезавтра", datetime(2026, 10, 19, 12, 0), ""),
    ],
)
def test_time_words_set_the_moment_and_leave_the_rest(text, moment, rest):
    asked = read_when(text, SATURDAY)
    assert asked is not None
    assert asked.moment == moment
    assert asked.rest == rest
    assert asked.shifted


@pytest.mark.parametrize("text", ["кофе рядом", "в субботу", "сейчас", "кафе", "good place"])
def test_no_time_word_no_time(text):
    asked = read_when(text, SATURDAY)  # «в субботу» on a Saturday is today: no shift
    assert asked is None or not asked.shifted


def test_a_search_with_a_time_checks_open_now_for_that_time_and_says_it():
    outs, _ = dialogue("en", "lunch tomorrow")
    out = outs[0]
    assert out.result is not None
    assert out.result.when == datetime(2026, 10, 18, 13, 0)
    assert out.turn.reply.startswith("Tomorrow, 13:00.")


def test_a_time_alone_repeats_the_previous_kind_for_that_time():
    outs, _ = dialogue("ru", "хочу кофе", "в понедельник днём")
    first, second = outs
    assert second.turn.kind == "places"
    assert second.result.when == datetime(2026, 10, 19, 13, 0)
    assert second.turn.reply.startswith("В понедельник днём, 13:00.")
    assert second.state.conversation.intent.categories == first.state.conversation.intent.categories


def test_a_time_alone_with_nothing_before_asks_what_for():
    turn, _, _ = say(new_state(*EXPO, "ru"), "в воскресенье")
    assert turn.kind == "clarify"
    assert turn.places == []


def test_a_day_alone_after_a_question_about_a_place_asks_that_places_hours():
    state = showing(DEL_PAPA, "Del Papa", "en")
    _, state, _ = say(state, "is it open now?")
    turn, _, out = say(state, "and tomorrow?")
    assert turn.kind == "place_answer"
    assert out.result is None
    (a,) = turn.answers
    assert a.topic == "hours"
    assert "tomorrow" in a.text
    assert "11:00–24:00" in a.text


def test_the_present_is_not_stamped():
    outs, _ = dialogue("ru", "хочу кофе")
    assert not outs[0].turn.reply.startswith(("Сегодня", "Завтра", "В "))


# ------------------------------------------------------------------ 4. kazakh «бар» is «there is»


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("туалет бар ма", "public_toilet"),
        ("дәретхана бар ма, балам сұранып жатыр", "public_toilet"),
        ("балалар ойнайтын жер бар ма", "kids_playground"),
        ("кафе бар ма екен", "cafe"),
        ("қай жерде кафе бар", "cafe"),
    ],
)
def test_bar_ma_searches_for_the_thing_asked_about(text, kind):
    outs, state = dialogue("kk", text)
    intent = state.conversation.intent
    assert kind in (*intent.categories, *intent.wished)
    assert "bar_nightlife" not in intent.categories
    assert outs[0].turn.lang == "kk"


@pytest.mark.parametrize("text", ["барға барайық", "бар іздеп жүрмін", "pub/bar", "хочу в бар"])
def test_bar_as_a_noun_is_the_bar_kind(text):
    _, state = dialogue("kk", text)
    assert "bar_nightlife" in state.conversation.intent.categories


# ------------------------------------------------------------------ 5. children inside a new request


def test_children_words_with_a_kind_named_start_a_new_search_with_the_child_flag():
    _, state = dialogue(
        "kk", "кофе ішкім келеді", "суық емес болса саябаққа барайық, балаларға ойнайтын жер"
    )
    intent = state.conversation.intent
    assert "cafe" not in intent.categories
    assert "park_garden" in intent.categories
    assert intent.with_kids


def test_children_words_alone_stay_a_refinement_of_the_last_request():
    _, state = dialogue("ru", "хочу кофе", "с ребёнком")
    intent = state.conversation.intent
    assert "cafe" in intent.categories
    assert intent.with_kids


# ------------------------------------------------------------------ 6. kazakh corrections


@pytest.mark.parametrize(
    ("lang", "first", "refusal"),
    [
        ("kk", "сауда орталығына барайық", "жоқ, бұл емес… сауда орталығы емес"),
        ("ru", "хочу в торговый центр", "нет, не то, не торговый центр"),
        ("en", "i want a mall", "no, not that, not a mall"),
    ],
)
def test_a_refused_kind_is_not_offered_again(lang, first, refusal):
    outs, _ = dialogue(lang, first, refusal)
    assert outs[0].turn.places
    assert outs[0].turn.places[0].category == "mall"
    assert outs[1].turn.kind == "clarify"
    assert outs[1].turn.places == []


def test_a_refused_kind_leaves_the_other_kinds_of_the_request():
    outs, state = dialogue("ru", "хочу кафе или торговый центр", "не торговый центр")
    assert outs[1].turn.kind == "places"
    assert all(p.category != "mall" for p in outs[1].turn.places)
    intent = state.conversation.intent
    assert "mall" not in intent.categories
    assert "mall" in intent.refused
    assert "cafe" in intent.categories


@pytest.mark.parametrize("text", ["басқа", "бұл емес"])
def test_another_without_a_kind_still_shows_other_places_of_the_same_kind(text):
    outs, state = dialogue("kk", "сауда орталығына барайық", text)
    assert outs[1].turn.kind == "places"
    assert "mall" in state.conversation.intent.categories
    assert not {p.id for p in outs[1].turn.places} & {p.id for p in outs[0].turn.places}
