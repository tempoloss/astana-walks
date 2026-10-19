"""Round 5 of the human testers: one card per place; a meal before a coffee shop and the nearer place when hours are
rare; «поближе» never puts a farther place under «ближайшее»; readable addresses and cards that say what a place is;
the sights wish beats the shelter rule unless the weather is harsh, an evening walk keeps the lit sight that is open,
museums without exhibition organisers, a far viewpoint with a near sight; no category echo; a short closed note."""

from __future__ import annotations

from datetime import datetime

from walks.attributes import coffee_shop, event_organiser
from walks.chains import distinct, lead_order
from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_strings import s
from walks.facts import clean_address, features
from walks.generate import required_cards, template_rec
from walks.intent import parse_rules
from walks.models import POI, Candidate, Intent
from walks.retrieve import retrieve
from walks.shelter import LIT_NEAR
from walks.walking import offline_router
from walks.want import names_the_wish
from walks.weather import harsh, make_weather, manual_weather
from walks.wish_rank import hours_rare

ORIGIN = (51.1283, 71.4305)
DEG_M = 111_320.0
MORNING = datetime(2026, 10, 20, 9, 0)


def _poi(poi_id: str, north_m: float, category: str, **kw) -> POI:
    return POI(
        id=poi_id,
        name=kw.pop("name", poi_id),
        lat=ORIGIN[0] + north_m / DEG_M,
        lon=ORIGIN[1],
        category=category,
        opening_hours=kw.pop("hours", None),
        **kw,
    )


def _cand(p: POI, walk: int = 4, state: str = "unknown", score: float = 5.0, **kw) -> Candidate:
    return Candidate(
        poi=p,
        distance_m=walk * 70,
        walk_min=walk,
        travel_min=walk,
        hours_state=state,
        score=score,
        **kw,
    )


def _rec(p: POI, **kw):
    return template_rec(_cand(p, **kw), Intent(categories=[p.category]), None, [])


# ---- 1. one card per place -----------------------------------------------------------------------------------------


def test_two_records_of_one_place_are_one_card():
    a = _poi("site/a", 100, "cafe", name="Coffee BOOM, Мәңгілік Ел даңғылы, 53")
    b = _poi("node/b", 120, "restaurant", name="Coffee BOOM")
    other = _poi("node/c", 150, "cafe", name="TOTEM")
    recs = [_rec(a), _rec(b), _rec(a), _rec(other)]
    assert [r.poi.id for r in distinct(recs)] == ["site/a", "node/c"]


# ---- 2. food ranking -----------------------------------------------------------------------------------------------


def test_a_meal_place_leads_a_coffee_shop_for_food():
    coffee = _poi("c", 100, "cafe", name="Coffee BOOM", hours="Mo-Su 08:00-24:00")
    kitchen = _poi("k", 300, "fast_food", name="I'm")
    cafe = _poi("j", 250, "cafe", name="Smart casual cafe JOULE 27")
    assert coffee_shop(coffee)
    assert not coffee_shop(cafe)
    intent = parse_rules("го пожрать").intent
    assert intent.eat
    top = retrieve([coffee, kitchen, cafe], *ORIGIN, intent, MORNING).candidates
    assert top[0].poi.id != "c"
    assert not parse_rules("хочу кофе").intent.eat  # a coffee is no meal: the coffee shop may lead


def test_when_hours_are_rare_the_open_bonus_shrinks_to_a_tie_break():
    near = _cand(_poi("n", 50, "cafe"), walk=2, state="unknown", score=4.0)
    far = _cand(_poi("f", 800, "cafe"), walk=14, state="open", score=4.5)
    rest = [_cand(_poi(f"u{i}", 300 + i, "cafe"), state="unknown", score=1.0) for i in range(3)]
    lifted = {c.poi.id: c.score for c in hours_rare([near, far, *rest], daytime=True)}
    assert lifted["n"] > lifted["f"]
    assert hours_rare([near, far], daytime=False) == [
        near,
        far,
    ]  # at night «unknown» stays a penalty


# ---- 3. «поближе» ----------------------------------------------------------------------------------------------------


def test_closer_never_puts_a_farther_place_under_the_nearest():
    park = _poi("park", 300, "park_garden", name="Аллея", tags=["leisure=park"])
    landmark = _poi("mon", 700, "attraction_landmark", name="Монумент", tags=["historic=monument"])
    env = TurnEnv(when=MORNING, use_llm=False, router=offline_router(), pois=[park, landmark])
    first = take_turn(new_state(*ORIGIN, "ru"), "погулять", env)
    assert first.turn.places[0].id == "park"
    closer = take_turn(first.state, "Поближе", env).turn
    shown_min = min(p.walk.distance_m for p in first.turn.places)
    assert closer.places
    assert closer.places[0].walk.distance_m <= shown_min
    assert closer.reply.startswith(s("ch_closer_none", "ru").split(" —")[0])


# ---- 4. readable cards ---------------------------------------------------------------------------------------------


def test_an_address_is_shown_as_street_and_number():
    assert clean_address("Астана қ., Мәңгілік Ел даңғылы, 55, B2.4") == "Мәңгілік Ел даңғылы, 55"
    assert clean_address(
        "010000, Казахстан, город Астана, район Сарайшық, улица Жұмекен Нәжімеденов, дом 16Г"
    ) == ("улица Жұмекен Нәжімеденов, 16Г")
    assert (
        clean_address("Астана қаласы, Қабанбай батыр даңғылы, 62 үй")
        == "Қабанбай батыр даңғылы, 62"
    )
    assert clean_address("Астана") == ""


def test_a_card_says_what_the_place_is_from_its_tags():
    park = _cand(_poi("p", 50, "park_garden", tags=["leisure=park", "start_date=2005"]))
    assert features(park, "ru") == ["городской парк", "открыт в 2005 году"]
    sight = _cand(_poi("a", 50, "attraction_landmark", tags=["tourism=attraction"]))
    assert "аттракцион" not in " ".join(features(sight, "ru"))
    fountain = _cand(
        _poi("f", 50, "attraction_landmark", tags=["overture_category=public_fountain"])
    )
    assert features(fountain, "en") == ["a fountain"]


def test_the_closed_note_is_one_short_clause_after_the_answer():
    text = s("known_hours_closed", "ru", n=2, places="места", closed="закрыты")
    assert text == "(ещё 2 места рядом сейчас закрыты)"


# ---- 5. sights -----------------------------------------------------------------------------------------------------


def test_the_sights_wish_beats_the_shelter_rule_unless_it_is_harsh():
    gallery = _poi("g", 300, "museum_gallery", name="Picture Day")
    tower = _poi("b", 50, "attraction_landmark", name="Bayterek")
    intent = parse_rules("what should i see").intent
    recs = [_rec(gallery), _rec(tower)]
    mild = make_weather(1, -3, 11, 0, pm25=40)
    assert not harsh(mild)
    assert [r.poi.id for r in lead_order(recs, intent, mild)] == ["b", "g"]
    assert harsh(manual_weather(-20))
    assert harsh(make_weather(5, 3, 5, 3.0))
    assert [r.poi.id for r in lead_order(recs, intent, manual_weather(-20))] == ["g", "b"]


def test_an_evening_walk_keeps_the_open_lit_sight():
    tower = _cand(_poi("b", 50, "attraction_landmark"), state="open", reasons=[LIT_NEAR])
    fountain = _cand(_poi("f", 300, "attraction_landmark"), reasons=["dark_outdoor"])
    intent = parse_rules("i want a nice walk this evening, about an hour, with lights").intent
    assert intent.time_budget_min == 60
    assert intent.time_stated
    assert [c.poi.id for c in required_cards([fountain, tower], intent)] == ["b"]
    day = parse_rules("кофе").intent
    assert required_cards([fountain, tower], day) == []


def test_an_exhibitions_organiser_is_no_museum():
    expo = _poi(
        "e", 100, "museum_gallery", name="Астана-Экспо КС", tags=["amenity=community_centre"]
    )
    museum = _poi("m", 900, "museum_gallery", name="Музей", tags=["tourism=museum"])
    assert event_organiser(expo)
    assert not event_organiser(museum)
    found = retrieve([expo, museum], *ORIGIN, parse_rules("museum").intent, MORNING).candidates
    assert [c.poi.id for c in found] == ["m"]


def test_a_far_viewpoint_comes_with_a_near_sight():
    view = _poi("v", 4500, "viewpoint", name="Смотровая площадка", tags=["tourism=viewpoint"])
    tower = _poi("b", 300, "attraction_landmark", name="Монумент", tags=["historic=monument"])
    env = TurnEnv(when=MORNING, use_llm=False, router=offline_router(), pois=[view, tower])
    turn = take_turn(new_state(*ORIGIN, "ru"), "смотровая площадка", env).turn
    assert turn.places[0].id == "v"
    assert (
        s("note_far_view", "ru", n=turn.places[0].walk.minutes).split(" — ")[1]
        in turn.places[0].note
    )
    assert [p.id for p in turn.places[1:2]] == ["b"]


# ---- 6. no category echo ----------------------------------------------------------------------------------------------


def test_a_category_echo_is_no_paraphrase_of_the_wish():
    bar = parse_rules("где побухать с друзьями").intent
    assert not names_the_wish("Вы ищете заведения категории бар и ночная жизнь", bar)
    assert names_the_wish("Вы ищете бар, чтобы посидеть с друзьями", bar)
