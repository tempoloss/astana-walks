"""Round 4 of the human testers: a card without a description says what its record holds (cuisine, features, brand,
where it is, people's marks) and otherwise one honest line; Kazakh food first and kept by «поближе»; a famous sight
asked to be seen stays when its doors are closed; a museum proper before a gallery; a plain walk starts in a park and
never turns into a playground for an adult; «парк, если не холодно» in the cold offers the nearest park second; «ночью»
while it is dark means now; the time-limit sentences only for a time the person set; the holiday of the asked day;
the events block in Kazakh keeps its month and names the asked day."""

from __future__ import annotations

from datetime import datetime
from types import SimpleNamespace

import pytest

from walks import dialog_lead
from walks.attributes import local_food_signal, museum_proper
from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_change import closer_order
from walks.dialog_facts import answer
from walks.dialog_place import place_from_poi
from walks.dialog_strings import s
from walks.dialog_types import ShownPlace
from walks.dialog_when import read_when
from walks.i18n_events import heading, when_part
from walks.intent import parse_rules
from walks.models import POI, Candidate, Intent, PeopleEvidence
from walks.reasons import Trip, budget_phrase, compose_why
from walks.retrieve import retrieve
from walks.stay import MIN_STAY_OVER_BUDGET
from walks.walking import offline_router
from walks.weather import manual_weather

ORIGIN = (51.1283, 71.4305)
DEG_M = 111_320.0
NOON = datetime(2026, 10, 20, 13, 0)
DAWN = datetime(2026, 10, 20, 6, 50)
MOTHER = (51.1694, 71.4128)


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


def _why(p: POI, lang: str = "ru", **kw) -> str:
    intent = Intent(categories=[p.category], language=lang)  # type: ignore[arg-type]
    return compose_why(_cand(p, **kw), intent, None, [], Trip(4, 30))


# ---- 1. what a record without a description holds ----------------------------------------------------------------


def test_a_bare_record_says_its_brand_or_where_it_is_never_close_to_you():
    branded = _poi("k", 50, "fast_food", name="KFC", tags=["brand=KFC"])
    assert _why(branded) == "Сеть «KFC»."
    located = _poi("t", 50, "cafe", name="TOTEM", address="📍улица Туркестан, 34, Астана")
    assert _why(located).startswith("Где: улица Туркестан, 34")
    marked = _poi("m", 50, "cafe", name="Marks")
    ev = PeopleEvidence(socket=2, quiet=1)
    assert "по отметкам людей" in _why(marked, people=ev).lower()
    assert _why(_poi("n", 50, "cafe", name="Nothing")) == "Других сведений о месте в данных нет."


def test_a_cuisine_comes_before_the_address():
    p = _poi("c", 50, "restaurant", tags=["cuisine=kazakh"], address="улица Туркестан, 34")
    why = _why(p)
    assert "Кухня" in why
    assert "Туркестан" not in why


# ---- 2. Kazakh food ----------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["something kazakh to eat", "бешбармак", "қазақ тағамы", "национальная кухня", "kazakh food"],
)
def test_a_kazakh_food_wish_is_read(text):
    assert parse_rules(text).intent.local_food


def test_kazakh_food_comes_first_and_closer_keeps_it():
    sushi = _poi("s", 30, "restaurant", name="Sushi Bar", tags=["cuisine=sushi"])
    kazakh = _poi("k", 300, "restaurant", name="Тайказан")
    assert local_food_signal(kazakh)
    assert not local_food_signal(sushi)
    intent = parse_rules("где поесть бешбармак").intent
    res = retrieve([sushi, kazakh], *ORIGIN, intent, NOON)
    assert res.candidates[0].poi.id == "k"
    assert "local_food" in res.candidates[0].reasons
    recs = [type("R", (), {"poi": p, "distance_m": d})() for p, d in ((sushi, 30), (kazakh, 300))]
    shown = [ShownPlace(id="k", name="Тайказан", kind="ресторан", distance_m=300)]
    answer = SimpleNamespace(intent=SimpleNamespace(intent=intent), retrieval=res, weather=None)
    assert [r.poi.id for r in closer_order(recs, shown, answer, "ru")] == ["k", "s"]  # type: ignore[arg-type]


def test_is_that_kazakh_food_answers_each_card_and_says_the_menu_once():
    pois = [_poi(f"r{i}", 100 * i, "restaurant", name=f"R{i}") for i in (1, 2, 3)]
    places = [place_from_poi(p, origin=ORIGIN, mode="walk", when=NOON, lang="en") for p in pois]
    texts = [
        answer("menu_kazakh", pl, p, "en", NOON, last=i == 2).text
        for i, (pl, p) in enumerate(zip(places, pois, strict=True))
    ]
    assert [t.startswith(f"R{i}") for i, t in enumerate(texts, 1)] == [True, True, True]
    menu = s("a_menu_dishes_none", "en")
    assert [menu in t for t in texts] == [False, False, True]


# ---- 3. sights and museums ---------------------------------------------------------------------------------------


def test_a_famous_sight_stays_when_its_doors_are_closed():
    tower = _poi(
        "b", 50, "attraction_landmark", name="Bayterek", wikipedia={"en": {"title": "Baiterek"}}
    )
    intent = parse_rules("what should i see").intent
    res = retrieve([tower], *ORIGIN, intent, DAWN)
    assert [c.poi.id for c in res.candidates] == ["b"]
    assert (
        res.candidates[0].hours_state == "closed"
    )  # the card says «закрыто до 10:00», never «открыто»
    cafe = _poi("c", 50, "cafe")
    assert retrieve([cafe], *ORIGIN, parse_rules("кофе").intent, DAWN).candidates == []


def test_a_museum_proper_comes_before_a_gallery_or_an_organiser():
    organiser = _poi(
        "o",
        100,
        "museum_gallery",
        name="Expo",
        tags=["amenity=community_centre", "tourism=gallery"],
    )
    museum = _poi("m", 600, "museum_gallery", name="Museum", tags=["tourism=museum"])
    assert museum_proper(museum)
    assert not museum_proper(organiser)
    res = retrieve([organiser, museum], *ORIGIN, parse_rules("музей").intent, NOON)
    assert res.candidates[0].poi.id == "m"


# ---- 4. walks ----------------------------------------------------------------------------------------------------


def test_a_plain_walk_starts_in_a_park_and_never_offers_a_playground_to_an_adult():
    monument = _poi("m", 250, "attraction_landmark", name="Монумент", hours=None)
    park = _poi("p", 300, "park_garden", name="Аллея", hours=None)
    playground = _poi("k", 50, "kids_playground", name="Детская площадка", hours=None)
    res = retrieve([monument, park, playground], *ORIGIN, parse_rules("погулять").intent, NOON)
    assert res.candidates[0].poi.id == "p"
    assert "k" not in [c.poi.id for c in res.candidates]
    kids = retrieve([playground], *ORIGIN, parse_rules("погулять с ребёнком").intent, NOON)
    assert [c.poi.id for c in kids.candidates] == ["k"]


def test_a_park_if_not_cold_in_the_cold_offers_the_nearest_park_second():
    env = TurnEnv(when=NOON, weather=manual_weather(-15), use_llm=False, router=offline_router())
    turn = take_turn(new_state(*MOTHER, "ru"), "парк если не холодно", env).turn
    assert turn.places
    assert turn.places[0].category != "park_garden"
    assert any(
        p.category == "park_garden" and s("note_fresh_air", "ru") in p.note for p in turn.places[1:]
    )


# ---- 5. time -----------------------------------------------------------------------------------------------------


def test_at_night_while_it_is_still_dark_means_now():
    asked = read_when("best place to see the city lights at night", DAWN)
    assert asked is not None
    assert asked.moment == DAWN
    later = read_when("куда сходить ночью", datetime(2026, 10, 20, 13, 0))
    assert later is not None
    assert later.moment.hour == 23


def test_the_time_limit_sentence_needs_a_time_the_person_set():
    c = _cand(_poi("v", 50, "viewpoint"), reasons=[MIN_STAY_OVER_BUDGET])
    assert budget_phrase(c, parse_rules("смотровая площадка").intent) == ""
    assert budget_phrase(c, parse_rules("смотровая площадка на 20 минут").intent)


def test_the_holiday_is_said_for_the_asked_day(monkeypatch):
    monkeypatch.setattr(dialog_lead, "local_now", lambda: datetime(2026, 10, 19, 9, 0))
    res = type(
        "R",
        (),
        {
            "weather": None,
            "when": datetime(2026, 10, 25, 12, 0),  # Sunday, Republic Day
            "intent": type("I", (), {"intent": Intent()})(),
            "retrieval": type("T", (), {"filters": type("F", (), {"outdoor_request": False})()})(),
        },
    )()
    clauses, _ = dialog_lead.conditions(res, "ru", show_temp=False)  # type: ignore[arg-type]
    assert clauses
    assert clauses[-1].startswith("в воскресенье праздник")


# ---- 7. events ----------------------------------------------------------------------------------------------------


def test_the_kazakh_events_block_keeps_its_month_and_names_the_asked_day():
    hit = type("H", (), {"kind": "run", "until": "2026-11-29T23:00:00"})()
    assert when_part(hit, "kk", NOON) == "29 қарашаға дейін"
    today = datetime(2026, 10, 19, 9, 0)
    assert heading("kk", datetime(2026, 10, 20, 12, 0), today) == "Ертең жақын жерде"
    assert heading("ru", today, today) == "Сегодня рядом"
