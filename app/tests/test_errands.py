"""Errands: pharmacies, food shops, cash machines, clinics, post offices and hotels (categories `pharmacy`, `grocery`,
`money`, `clinic`, `post`, `lodging` of the shipped dataset). A request for one finds them in ru / kk / en; no other
request ever sees one (not as a back-fill, nor as a stop of a walk); at night what is open comes first, round the
clock before the rest; with none in the data the answer says so; «торговый центр» stays a mall; the model never widens
a request into an errand."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_strings import STRINGS
from walks.intent import merge_intents, parse_rules
from walks.models import POI, Intent, load_pois
from walks.pipeline import recommend
from walks.presets import PRESETS
from walks.radius import ERRAND_KINDS
from walks.supply import UTILITY_KINDS
from walks.walking import offline_router

BAITEREK = PRESETS["Байтерек"]
AITU = (51.0906, 71.4180)
NOON = datetime(2026, 10, 20, 13, 0)
LATE = datetime(2026, 10, 20, 23, 30)
ORIGIN = (51.1283, 71.4305)
DEG_M = 111_320.0


def test_every_errand_kind_has_its_lead_and_its_honest_line():
    for kind in sorted(ERRAND_KINDS):
        assert {f"ld_errand_{kind}", f"ld_errand_open_{kind}", f"none_{kind}"} <= set(STRINGS), kind


@pytest.fixture(scope="module")
def pois():
    return load_pois()


def _ask(pois, text, where=BAITEREK, when=NOON):
    return recommend(text, *where, when, use_llm=False, pois=pois, router=offline_router())


def _poi(poi_id: str, north_m: float, category: str, hours: str | None = "24/7") -> POI:
    lat = ORIGIN[0] + north_m / DEG_M
    return POI(
        id=poi_id, name=poi_id, lat=lat, lon=ORIGIN[1], category=category, opening_hours=hours
    )


@pytest.mark.parametrize(
    "text",
    [
        "где купить продукты",
        "ночной магазин",
        "за продуктами",
        "где купить еду",
        "азық-түлік дүкені қайда",
        "grocery store near me",
        "buy food",
    ],
)
def test_food_shopping_words_read_as_grocery(text):
    assert parse_rules(text).intent.categories == ["grocery"]


@pytest.mark.parametrize("text", ["в торговый центр", "поеду в магазин", "магазин одежды"])
def test_a_mall_request_stays_a_mall(text):
    assert parse_rules(text).intent.categories == ["mall"]


def test_the_model_never_adds_an_errand_the_words_do_not_name():
    text = "где поесть"
    merged = merge_intents(
        parse_rules(text).intent, Intent(categories=["cafe", *ERRAND_KINDS]), text
    )
    assert not ERRAND_KINDS & set(merged.categories)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("где купить продукты", "grocery"),
        ("азық-түлік дүкені қайда", "grocery"),
        ("grocery store near me", "grocery"),
        ("аптека рядом", "pharmacy"),
        ("банкомат рядом", "money"),
        ("ломбард рядом", "money"),
        ("где стоматолог", "clinic"),
        ("почта рядом", "post"),
    ],
)
@pytest.mark.parametrize("where", [BAITEREK, AITU], ids=["baiterek", "aitu"])
def test_errand_requests_find_only_that_errand_and_lead_the_way_to_one(pois, text, kind, where):
    res = _ask(pois, text, where)
    assert res.recs
    assert {r.poi.category for r in res.recs} == {kind}
    assert all(r.padding in ("none", "expanded") for r in res.recs)
    assert res.route is not None
    assert len(res.route.stops) == 1  # the way to the first one, not a walk from shop to shop


@pytest.mark.parametrize("where", [BAITEREK, AITU], ids=["baiterek", "aitu"])
@pytest.mark.parametrize("text", ["где переночевать", "hotel near me"])
def test_a_hotel_request_may_be_padded_but_the_way_leads_to_the_hotel(pois, text, where):
    res = _ask(pois, text, where)
    assert res.recs[0].poi.category == "lodging"
    assert all(r.padding == "backfill" for r in res.recs if r.poi.category != "lodging")
    assert res.route is not None
    assert res.route.stops == [res.recs[0].poi.id]


@pytest.mark.parametrize(
    "text", ["кофе", "где поесть", "погулять", "что посмотреть", "в торговый центр", "музей"]
)
@pytest.mark.parametrize("when", [NOON, LATE], ids=["noon", "late"])
def test_a_request_for_something_else_never_shows_an_errand(pois, text, when):
    res = _ask(pois, text, AITU, when)
    assert all(c.poi.category not in ERRAND_KINDS for c in res.retrieval.candidates)


@pytest.mark.parametrize("text", ["что рядом", "куда сходить", "есть 30 минут"])
def test_a_request_that_names_no_kind_never_gets_a_utility(pois, text):
    # a dense block of shops and pharmacies: the generic pool takes none of them (a hotel it may)
    res = _ask(pois, text, (51.1605, 71.4704))
    assert res.recs
    assert all(c.poi.category not in UTILITY_KINDS for c in res.retrieval.candidates)


@pytest.mark.parametrize(
    "text", ["аптека и кафе", "банкомат и кафе", "отель и кафе", "почта и кафе"]
)
def test_an_errand_is_never_a_stop_of_a_walk(pois, text):
    res = _ask(pois, text)
    kinds = {r.poi.category for r in res.recs}
    assert "cafe" in kinds
    assert kinds & ERRAND_KINDS
    by_id = {r.poi.id: r.poi.category for r in res.recs}
    assert res.route is not None
    assert all(by_id[s] not in ERRAND_KINDS for s in res.route.stops)


@pytest.mark.parametrize(
    ("text", "kind"),
    [
        ("ночной магазин", "grocery"),
        ("аптека ночью", "pharmacy"),
        ("банкомат", "money"),
        ("гостиница", "lodging"),
        ("клиника рядом", "clinic"),
        ("почта рядом", "post"),
    ],
)
def test_at_night_open_errands_come_first_and_round_the_clock_before_the_rest(text, kind):
    pois = [
        _poi("unknown_near", 60, kind, hours=None),
        _poi("late_open", 100, kind, hours="Mo-Su 08:00-24:00"),
        _poi("all_night", 300, kind, hours="24/7"),
    ]
    res = recommend(text, *ORIGIN, LATE, use_llm=False, pois=pois, router=offline_router())
    assert [r.poi.id for r in res.recs][:2] == ["all_night", "late_open"]


@pytest.mark.parametrize(
    ("text", "lang", "word"),
    [
        ("где купить продукты", "ru", "продуктовых магазинов"),
        ("азық-түлік дүкені қайда", "kk", "азық-түлік"),
        ("grocery store near me", "en", "grocery"),
        ("аптека рядом", "ru", "аптек"),
        ("дәріхана қайда", "kk", "дәріхана"),
        ("pharmacy near me", "en", "pharmacies"),
        ("банкомат рядом", "ru", "банкоматов"),
        ("atm near me", "en", "ATMs"),
        ("отель рядом", "ru", "гостиниц"),
        ("hotel near me", "en", "hotels"),
        ("где стоматолог", "ru", "клиник"),
        ("почта рядом", "ru", "почтовых"),
        ("post office near me", "en", "post offices"),
    ],
)
def test_no_errand_in_the_data_is_said_and_nothing_stands_in(text, lang, word):
    pois = [_poi("mall1", 150, "mall"), _poi("cafe1", 80, "cafe"), _poi("cafe2", 120, "cafe")]
    env = TurnEnv(when=NOON, use_llm=False, router=offline_router(), pois=pois)
    turn = take_turn(new_state(*ORIGIN, lang), text, env).turn
    assert turn.kind == "none_found"
    assert turn.places == []
    assert word in turn.reply
    assert "longer" not in {c.id for c in turn.chips}
