"""Round 3 of the human testers: a card's reason is a fact of its record, never «рядом с вами» while the record holds
more and never an address; the wish beats variety; the shelter rule is never said; «подешевле» and a named fast-food
dish bring fast food first; the Kazhydromet notice and the conditions belong to a walk; a walk is never a
restaurant; a play centre or a children's museum the data lacks is said so."""

from __future__ import annotations

from datetime import datetime

from walks import generate as gen_mod
from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_change import change_label
from walks.dialog_extras import weather_notice
from walks.dialog_strings import s
from walks.dialog_types import ShownPlace
from walks.facts import vague_ids
from walks.followup import FollowUp
from walks.i18n import STRINGS, pick, t
from walks.intent import parse_rules
from walks.kids import kids_gap
from walks.llm_output import LLMOutput, LLMRec
from walks.models import POI, Candidate, Intent, WeatherWarning
from walks.reasons import Trip, compose_why
from walks.retrieve import retrieve
from walks.specific import keep_status, vague_conditions
from walks.variety import fresh_first
from walks.walking import offline_router
from walks.weather import make_weather, manual_weather

ORIGIN = (51.1283, 71.4305)
DEG_M = 111_320.0
NOON = datetime(2026, 10, 20, 13, 0)
NIGHT = datetime(2026, 10, 19, 1, 30)
AITU = (51.0906, 71.4180)
KHAN = (51.1326, 71.4035)
FOG = WeatherWarning(
    kind="storm",
    title="Штормовое предупреждение",
    text="г. Астана: 19 октября ночью и утром ожидается туман.",
    source_url="https://www.kazhydromet.kz/ru/storm",
    valid_to="2026-10-19T10:00+05:00",
    active=True,
)
WX = make_weather(0, -4, 11, 0, pm25=40, warnings=(FOG,))


def _poi(poi_id: str, north_m: float, category: str, **kw) -> POI:
    return POI(
        id=poi_id,
        name=kw.pop("name", poi_id),
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        opening_hours=kw.pop("hours", "Mo-Su 10:00-23:00"),
        **kw,
    )


def _cand(p: POI, walk: int = 4, **kw) -> Candidate:
    return Candidate(
        poi=p,
        distance_m=walk * 70,
        walk_min=walk,
        travel_min=walk,
        hours_state="open",
        score=5.0,
        **kw,
    )


def _talk(lang: str, origin: tuple[float, float], when: datetime, *messages: str):
    env = TurnEnv(when=when, weather=WX, use_llm=False, router=offline_router())
    state, turns = new_state(*origin, lang), []
    for m in messages:
        out = take_turn(state, m, env)
        state = out.state
        turns.append(out.turn)
    return turns


# ---- 1. the reason of a card ----------------------------------------------------------------------------------


def _model_card(cand: Candidate, why: str, lang: str = "ru"):
    out = LLMOutput(
        recommendations=[
            LLMRec(
                poi_id=cand.poi.id,
                why=why,
                time_on_site_min=30,
                what_to_do="Загляните." if lang != "en" else "Drop in.",
                confidence="medium",
                generated_idea=False,
            )
        ]
    )
    intent = parse_rules("хочу поесть" if lang != "en" else "something to eat").intent
    return gen_mod._from_llm(out, [cand], intent, None, NOON)[0][0]


def test_a_fact_with_filler_is_no_vague_card_a_bare_address_is():
    p = _poi(
        "c",
        100,
        "restaurant",
        name="Арарат",
        tags=["cuisine=caucasian", "outdoor_seating=yes"],
        address="улица Туркестан, 34А, Астана",
    )
    cand = _cand(p)
    factual = _model_card(cand, "Отлично подходит для ужина: кавказская кухня, столики на улице.")
    assert "кавказская кухня" in factual.why  # the filler phrase does not throw the fact away
    assert vague_ids([factual], [cand], "ru") == []
    address = _model_card(cand, "Это заведение расположено на улице Туркестан 34А.")
    assert vague_ids([address], [cand], "ru") == ["c"]  # asked again, then the template's own card


def test_the_model_may_not_tell_the_person_what_they_like():
    p = _poi("g", 100, "museum_gallery", name="Picture Day", tags=["overture_category=art_gallery"])
    card = _model_card(
        _cand(p), "An indoor art gallery. It fits your interest in museums and galleries.", "en"
    )
    assert "interest" not in card.why


def test_a_status_differing_from_code_goes_a_feature_and_the_same_hours_stay():
    status = "Открыто до 22:00"
    assert keep_status("Есть открытая терраса.", status) == "Есть открытая терраса."
    assert keep_status("An open kitchen.", "Open until 22:00") == "An open kitchen."
    assert keep_status("Работает до 22:00, успеете.", status) == "Работает до 22:00, успеете."
    assert keep_status("Работает до 05:00. Летняя веранда.", status) == "Летняя веранда."


def test_an_address_is_no_fact_the_model_may_rest_a_card_on():
    p = _poi("c", 100, "cafe", name="TOTEM", address="улица Туркестан, 34А, Астана")
    cand = _cand(p)
    card = _model_card(cand, "Это кафе расположено на улице Туркестан 34А.")
    assert vague_ids([card], [cand], "ru") == ["c"]


def test_the_template_reason_is_the_records_own_words_never_its_address():
    p = _poi(
        "k", 100, "cafe", name="Cups", tags=["cuisine=coffee_shop"], address="улица Туркестан, 34А"
    )
    intent = parse_rules("хочу кофе").intent
    why = compose_why(_cand(p), intent, None, [], Trip(4, 30))
    assert why
    assert "Туркестан" not in why
    assert "кофе" in why.lower()


def test_the_last_resort_is_an_honest_line_never_a_nearness_claim():
    for lang in ("kk", "ru", "en"):
        line = t("why_none", lang)
        assert "рядом с вами" not in line
        assert "close to you" not in line
        assert "жақын жердегі" not in line.lower()
    assert t("why_none", "ru") == "Других сведений о месте в данных нет."


# ---- 2. the wish beats variety ---------------------------------------------------------------------------------


def test_the_only_museum_shown_before_comes_back_before_a_new_cafe():
    museum = _cand(_poi("m", 100, "museum_gallery"))
    cafe = _cand(_poi("c", 50, "cafe"))
    assert [
        c.poi.id for c in fresh_first([museum, cafe], ["m"], frozenset({"museum_gallery"}))
    ] == [
        "m",
        "c",
    ]
    assert [c.poi.id for c in fresh_first([museum, cafe], ["m"], frozenset())] == ["c"]


def test_a_museum_asked_twice_is_a_museum_first_both_times():
    turns = _talk("en", ORIGIN, NOON, "museum?", "museum?")
    assert all(turn.places and turn.places[0].category == "museum_gallery" for turn in turns)


def test_no_alcohol_after_other_places_widens_instead_of_emptying_the_map():
    turns = _talk(
        "ru", AITU, NIGHT, "ок а где побухать норм с друзьями", "Другие места", "Без алкоголя"
    )
    assert turns[-1].kind == "places"
    assert turns[-1].places
    assert all(p.category != "bar_nightlife" for p in turns[-1].places)


# ---- 3. the shelter rule is never said ---------------------------------------------------------------------------


def test_no_note_says_the_shelter_rule_in_any_language():
    for key, entry in STRINGS.items():
        for text in entry:
            assert "не предлагаем" not in text, key
            assert "ұсынбаймыз" not in text, key
            assert "not offered in these conditions" not in text, key
    for lang in ("kk", "ru", "en"):
        assert t("note_off_category_weather", lang).startswith(
            pick(STRINGS["note_off_category"], lang).split(":")[0]
        )


# ---- 4. cheap food and fast food -------------------------------------------------------------------------------


def test_cheaper_and_a_fast_food_dish_put_fast_food_before_a_cafe():
    pois = [_poi("cafe", 50, "cafe"), _poi("ff", 120, "fast_food")]
    smog = manual_weather(
        8, pm25=80
    )  # the indoor bonus of a café must not outweigh the kind asked for
    cheap = parse_rules("хочу поесть").intent.model_copy(
        update={"budget": "low", "categories": ["fast_food", "cafe"]}
    )
    dish = parse_rules("где шаурму взять или бургер").intent
    for intent in (cheap, dish):
        res = retrieve(pois, *ORIGIN, intent, NOON, weather=smog)
        assert res.candidates[0].poi.id == "ff", intent


def test_closer_after_a_fast_food_lead_keeps_fast_food():
    shown = [
        ShownPlace(id="a", name="Al-Shawarma", kind="фастфуд", distance_m=500),
        ShownPlace(id="m", name="Movenpick", kind="кафе", distance_m=0),
    ]
    rec = gen_mod.template_recs(
        [_cand(_poi("a", 0, "fast_food", name="Al-Shawarma"), walk=7)],
        parse_rules("поесть").intent,
        None,
    )
    rec[0].distance_m = 500
    res = type("R", (), {"retrieval": None})()
    assert change_label(FollowUp(closer=True), res, rec, shown, "ru") == s("ch_closer_none", "ru")


def test_closer_on_a_student_answer_keeps_the_kind_it_led_with():
    # Каталог-мёрж дал кафе/ресторанам у KHAN настоящие часы: в 01:30 (NIGHT) внутри «поближе»-радиуса
    # (0.8 × самого дальнего из ответа) рестораны закрыты, и ответ законно ведут круглосуточные кафе —
    # инвариант «тот же вид» переносим на полдень, где у ведущего вида есть кандидаты поближе.
    first, closer = _talk("ru", KHAN, NOON, "го пожрать недорого, я студент", "Поближе")
    assert closer.places[0].kind == first.places[0].kind


# ---- 5. notices and conditions belong to a walk ------------------------------------------------------------------


def test_the_storm_notice_is_titled_by_its_phenomenon_with_its_words_behind_it():
    notice = weather_notice(WX, "en")
    assert notice is not None
    assert notice.text == "Kazhydromet: fog"
    assert "туман" in (notice.detail or "")
    assert notice.source.url.endswith("/storm")
    assert weather_notice(WX, "kk").text == "Қазгидромет: тұман"


def test_the_notice_and_the_conditions_stay_off_a_cafe_answer():
    cafe = _talk("en", AITU, NIGHT, "a cafe nearby")[0]
    assert not any(n.kind == "weather" for n in cafe.notices)
    assert "fog" not in cafe.reply.lower()
    walk = _talk("en", AITU, NIGHT, "a walk in a park")[0]
    assert any(n.text == "Kazhydromet: fog" for n in walk.notices)


def test_an_opening_about_the_conditions_without_numbers_is_a_template():
    assert vague_conditions("В условиях плохого воздуха и холода подойдёт ресторан «Berezka».")
    assert not vague_conditions("Сейчас 0 °C, ощущается как −4 °C: советую «Berezka».")
    assert not vague_conditions("Советую «Berezka», 7 мин пешком.")


# ---- 6. wishes that need the right kinds -----------------------------------------------------------------------


def test_a_night_walk_with_a_girlfriend_is_a_walk_never_a_restaurant():
    intent = parse_rules("где красиво ночью пройтись с девушкой, ток недалеко").intent
    assert set(intent.categories) <= {"park_garden", "attraction_landmark", "viewpoint"}
    turn = _talk("ru", AITU, NIGHT, "где красиво ночью пройтись с девушкой, ток недалеко")[0]
    assert turn.places
    assert all(
        p.category in {"park_garden", "attraction_landmark", "viewpoint"} for p in turn.places
    )


def test_a_trampoline_or_a_play_centre_is_kids_entertainment():
    for text in ("балаларға батут немесе ойын орталығы", "игровой центр для детей", "батут"):
        intent = parse_rules(text).intent
        assert intent.categories == ["entertainment"], text
        assert intent.with_kids, text


def test_a_play_centre_or_a_kids_museum_the_data_lacks_is_said_so():
    play = Intent(categories=["entertainment"], wished=["entertainment"], with_kids=True)
    hall = _poi("h", 50, "entertainment", name="Музыкальная Академия")
    kids = _poi("k", 50, "entertainment", name="Детский центр Бамбини")
    assert kids_gap(play, [hall]) == "entertainment"
    assert kids_gap(play, [hall, kids]) == ""
    turn = _talk("ru", (51.1694, 71.4128), NOON, "детский музей")[0]
    assert turn.reply.startswith(s("kids_none_museum_gallery", "ru")) or any(
        "дет" in p.name.lower() for p in turn.places
    )
