"""Round 6 of the human testers (a daytime run with errands): «поближе» compares the walking metres the cards show and
reaches the nearest place shown before; an errand is the nearest place that works (confirmed open first, a cash
machine for «банкомат»), said by what it is, with no settings, chips or closed note that do not matter there; a meal
before a coffee shop whatever picked it; the night is not said by day; fog is not a storm; plain overnight hours."""

from __future__ import annotations

from datetime import datetime

from walks.chains import lead_order, walk_order
from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_chips import refine_chips
from walks.dialog_lead import by_the_clock
from walks.generate import required_cards, template_rec
from walks.intent import parse_rules
from walks.kazhydromet import harsh_notice
from walks.models import POI, Candidate, Constraints, Intent, WeatherWarning
from walks.status import status_text
from walks.walking import offline_router
from walks.weather import make_weather
from walks.wishes import errand_order

ORIGIN = (51.1283, 71.4305)
DEG_M = 111_320.0
NOON = datetime(2026, 10, 19, 11, 30)


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


def _cand(p: POI, metres: int, state: str = "unknown", **kw) -> Candidate:
    return Candidate(
        poi=p,
        distance_m=metres,
        walk_min=max(1, metres // 80),
        travel_min=max(1, metres // 80),
        hours_state=state,
        score=kw.pop("score", 5.0),
        **kw,
    )


def _rec(p: POI, metres: int, state: str = "unknown", padding: str = "none"):
    r = template_rec(_cand(p, metres, state), Intent(categories=[p.category]), None, [])
    return r.model_copy(update={"distance_m": metres, "padding": padding})


# ---- 1. «поближе» ---------------------------------------------------------------------------------------------------


def _env(pois):
    return TurnEnv(when=NOON, use_llm=False, router=offline_router(), pois=pois)


def test_closer_reaches_the_nearest_card_on_foot():
    """The straight line said «far» of the nearer shop: the cap is the walk to the nearest card, so it stays a
    candidate and leads, and «ближе нет» names it, never a farther one."""
    near = _poi("near", 600, "grocery", name="Рамстор")
    far = _poi("far", 900, "grocery", name="ЭКСПО Маркет")
    env = _env([near, far])
    first = take_turn(new_state(*ORIGIN, "ru"), "продуктовый магазин", env)
    assert [p.id for p in first.turn.places] == ["near", "far"]  # the nearer walk first
    closer = take_turn(first.state, "Поближе", env).turn
    assert closer.places[0].id == "near"
    assert "Рамстор" in closer.reply


def test_closer_after_other_places_offers_the_nearer_one_shown_before():
    """Europharma (24/7) and A-farm (open) lead, Улы Дала (nearest, hours unknown) is third; «другие места» shows
    two more; «поближе» then offers Улы Дала again, nearer than both, never «ближе нет»."""
    pois = [
        _poi("e", 700, "pharmacy", name="Europharma", hours="24/7"),
        _poi("f", 720, "pharmacy", name="A-farm", hours="Mo-Su 08:00-23:00"),
        _poi("u", 540, "pharmacy", name="Улы Дала"),
        _poi("p", 560, "pharmacy", name="Планета Фарм"),
        _poi("d", 640, "pharmacy", name="ДӘІХАНА+"),
    ]
    env = _env(pois)
    first = take_turn(new_state(*ORIGIN, "ru"), "аптека", env)
    assert [p.id for p in first.turn.places] == ["e", "f", "u"]
    assert first.turn.reply.startswith("Ближайшая открытая аптека — «Europharma»")
    other = take_turn(first.state, "Другие места", env)
    assert [p.id for p in other.turn.places] == ["p", "d"]
    closer = take_turn(other.state, "Поближе", env).turn
    assert closer.places[0].id == "u"
    assert not closer.reply.startswith("Ближе таких мест нет")


def test_the_nearest_card_is_never_a_bit_farther():
    near = _rec(_poi("n", 900, "pharmacy"), 900, padding="expanded")
    far = _rec(_poi("f", 1400, "pharmacy", hours="24/7"), 1400, "open", padding="expanded")
    out = walk_order([far, near], Intent(categories=["pharmacy"], wished=["pharmacy"]), NOON, False)
    assert [r.poi.id for r in out] == ["f", "n"]  # confirmed open first
    assert {r.poi.id: r.padding for r in out} == {"f": "expanded", "n": "none"}


# ---- 2. errands -----------------------------------------------------------------------------------------------------


def test_an_errand_is_the_nearest_confirmed_open_then_the_nearest_unknown():
    open_far = _cand(_poi("o", 600, "money", hours="Mo-Su 09:00-22:00"), 600, "open")
    open_near = _cand(_poi("p", 300, "money", hours="Mo-Su 09:00-20:00"), 300, "open")
    unknown_nearest = _cand(_poi("u", 100, "money"), 100)
    out = errand_order([open_far, unknown_nearest, open_near], frozenset({"money"}), NOON, False)
    assert [c.poi.id for c in out] == ["p", "o", "u"]


def test_a_night_shop_asked_by_day_is_one_open_at_night():
    late = _cand(_poi("late", 300, "grocery", hours="Mo-Su 08:00-23:00"), 300, "open")
    all_night = _cand(_poi("247", 800, "grocery", hours="24/7"), 800, "open")
    unknown = _cand(_poi("u", 500, "grocery"), 500)
    out = errand_order([late, unknown, all_night], frozenset({"grocery"}), NOON, True)
    assert [c.poi.id for c in out] == ["247", "u", "late"]


def test_a_cash_machine_is_asked_by_its_word():
    assert parse_rules("где банкомат, надо снять налик").intent.subkind == "atm"
    assert parse_rules("банкомат бар ма, ақша алу керек").intent.subkind == "atm"
    assert parse_rules("где банк").intent.subkind == ""
    bank = _cand(
        _poi("bank", 100, "money", hours="Mo-Fr 09:00-18:00", tags=["amenity=bank"]), 100, "open"
    )
    atm = _cand(_poi("atm", 400, "money", hours="24/7", tags=["amenity=atm"]), 400, "open")
    out = errand_order([bank, atm], frozenset({"money"}), NOON, False, sub="atm")
    assert out[0].poi.id == "atm"


def test_the_code_s_first_errand_card_stays_whatever_the_model_picked():
    atm = _cand(_poi("atm", 400, "money", hours="24/7", tags=["amenity=atm"]), 400, "open")
    bank = _cand(_poi("bank", 100, "money", tags=["amenity=bank"]), 100, "open")
    intent = Intent(categories=["money"], wished=["money"], subkind="atm")
    assert [c.poi.id for c in required_cards([atm, bank], intent)] == ["atm"]
    walk = Intent(categories=["park_garden"], wished=["park_garden"])
    assert required_cards([_cand(_poi("park", 100, "park_garden"), 100)], walk) == []


def test_an_errand_lead_says_what_it_is_with_no_echo_chips_or_closed_note():
    shut = _poi("shut", 200, "pharmacy", name="Ночная", hours="Mo-Su 20:00-23:00")
    unknown = _poi("u", 400, "pharmacy", name="Улы Дала")
    turn = take_turn(
        new_state(*ORIGIN, "ru"), "где тут аптека, голова болит", _env([shut, unknown])
    ).turn
    assert turn.reply.startswith("Ближайшая аптека — «Улы Дала»")
    assert "Вы ищете" not in turn.reply
    assert "закрыт" not in turn.reply
    labels = {c.id for c in turn.chips}
    assert not labels & {"kids", "longer", "cheaper"}
    assert turn.places[0].why.startswith(
        "Где: район"
    )  # a bare errand card says where, not «nothing more»


def test_errand_chips_keep_only_what_changes_an_errand():
    intent = Intent(categories=["public_toilet"], wished=["public_toilet"])
    ids = [c.id for c in refine_chips(intent, Constraints(), [], "en")]
    assert ids == ["new"]


# ---- 3. food --------------------------------------------------------------------------------------------------------


def test_a_meal_leads_a_coffee_shop_whatever_picked_them():
    intent = parse_rules("го пожрать, щас уже поздно").intent
    coffee = _rec(_poi("c", 100, "cafe", name="Coffee BOOM"), 100)
    meal = _rec(_poi("t", 300, "restaurant", name="Тануки"), 300)
    assert [r.poi.id for r in lead_order([coffee, meal], intent, None)] == ["t", "c"]


def test_the_night_is_not_said_by_day():
    class _Res:
        when = NOON

    assert by_the_clock("Вы ищете, где поесть ночью", _Res()) == ""
    assert by_the_clock("Вы ищете, где поесть", _Res()) == "Вы ищете, где поесть"
    _Res.when = datetime(2026, 10, 19, 23, 30)
    assert by_the_clock("где поесть ночью", _Res()) == "где поесть ночью"


# ---- 5. sights ------------------------------------------------------------------------------------------------------


def test_a_museum_is_never_answered_with_a_cinema():
    """No museum in reach: the nearest museum with how far it is, never a cinema as «another kind of place»."""
    cinema = _poi("cinema", 300, "culture_theatre_cinema", name="Chaplin Cinemas")
    museum = _poi("museum", 4000, "museum_gallery", name="Музей", tags=["tourism=museum"])
    turn = take_turn(new_state(*ORIGIN, "en"), "I want a museum", _env([cinema, museum])).turn
    assert [p.id for p in turn.places] == ["museum"]
    assert "4.0 km" in turn.places[0].note


# ---- 4. weather -----------------------------------------------------------------------------------------------------


def _notice(text: str) -> WeatherWarning:
    return WeatherWarning(
        kind="storm",
        title="Штормовое предупреждение",
        text=text,
        source_url="https://kazhydromet.kz",
        active=True,
    )


def test_fog_is_no_storm_and_a_storm_wind_is():
    assert not harsh_notice("г. Астана: ночью и утром туман.")
    assert harsh_notice("Ожидается сильный ветер 15-20 м/с.")
    fog = make_weather(13, 7, 25, 0.0, warnings=[_notice("г. Астана: ночью и утром туман.")])
    assert not fog.adverse
    assert "storm_warning" not in fog.conditions
    wind = make_weather(
        13, 7, 25, 0.0, warnings=[_notice("Ожидается сильный ветер, порывы 23 м/с.")]
    )
    assert wind.adverse


# ---- 6. hours wording -----------------------------------------------------------------------------------------------


def test_overnight_closes_are_said_as_a_person_says_them():
    midnight = _poi("m", 100, "cafe", hours="Mo-Su 11:30-24:00")
    early = _poi("e", 100, "cafe", hours="Mo-Su 08:00-05:00")
    assert (
        status_text(midnight, "open", datetime(2026, 10, 19, 11, 30), "ru") == "Открыто до полуночи"
    )
    assert (
        status_text(midnight, "open", datetime(2026, 10, 19, 11, 30), "en") == "Open until midnight"
    )
    assert (
        status_text(midnight, "open", datetime(2026, 10, 19, 11, 30), "kk")
        == "түн ортасына дейін ашық"
    )
    assert (
        status_text(early, "open", datetime(2026, 10, 19, 13, 0), "ru") == "Открыто до 05:00 утра"
    )
    assert status_text(early, "open", datetime(2026, 10, 19, 13, 0), "en") == "Open until 5 am"
    assert (
        status_text(early, "open", datetime(2026, 10, 19, 13, 0), "kk")
        == "таңғы 05:00-ге дейін ашық"
    )
