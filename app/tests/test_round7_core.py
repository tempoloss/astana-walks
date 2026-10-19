"""Friends' screenshots of the live stand (wave 8): a reason taken from the place's own name is no reason; a brand that
already says «сеть» is said as it is; the Kazakh lead never declines a quoted name; «about an hour» is two or three
stops; among places about as near, the better known one is picked (no rating is claimed)."""

from __future__ import annotations

from walks.chains import asked_on_the_way, fill_time
from walks.dialog_strings import s
from walks.generate import template_rec, template_recs
from walks.intent import parse_rules
from walks.models import POI, Candidate, Intent
from walks.reasons import _brand_fact
from walks.specific import opening_ok, uses_fact, without_filler
from walks.wish_rank import evidence, evidence_first

ORIGIN = (51.1283, 71.4305)
DEG_M = 111_320.0


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


def _cand(p: POI, walk: int, state: str = "unknown", score: float = 5.0, **kw) -> Candidate:
    return Candidate(
        poi=p,
        distance_m=walk * 80,
        walk_min=walk,
        travel_min=walk,
        hours_state=state,
        score=score,
        **kw,
    )


# ---- 1. the name is no fact ----------------------------------------------------------------------------------------

PINTA = "ПИНТА Bar & Grill"


def test_a_word_of_the_name_is_no_fact_in_either_script():
    echo = "Для обеда или перерыва предлагаю «ПИНТА Bar & Grill», где в названии указан гриль."
    assert not uses_fact(echo, ["гриль"], PINTA)  # «гриль» is the «Grill» of the name
    assert not uses_fact("A place with grill, as its name says.", ["grill"], PINTA)
    assert not uses_fact("Атауында гриль бар.", ["гриль"], PINTA)
    assert uses_fact(
        "Здесь есть летняя терраса.", ["летняя терраса"], PINTA
    )  # a fact of the record still counts


def test_a_sentence_that_argues_from_the_name_is_dropped():
    text = "В названии указан гриль. Есть летняя терраса."
    assert without_filler(text) == "Есть летняя терраса."
    assert without_filler("As the name suggests, it grills. Outdoor seating.") == "Outdoor seating."
    assert without_filler("Атауы айтып тұрғандай, гриль. Терраса бар.") == "Терраса бар."
    assert not opening_ok("«ПИНТА Bar & Grill», где в названии указан гриль.", "ru", set(), [])


# ---- 2. a brand that says «сеть» ------------------------------------------------------------------------------------


def test_a_brand_that_names_its_chain_is_said_as_it_is():
    chain = _cand(
        _poi("p", 100, "bar_nightlife", name=PINTA, tags=["brand=Сеть ресторанов ПИНТА"]), 2
    )
    for lang in ("ru", "en", "kk"):
        assert _brand_fact(chain, lang) == "Сеть ресторанов ПИНТА."
    plain = _cand(_poi("c", 100, "cafe", name="Coffee BOOM", tags=["brand=Coffee BOOM"]), 2)
    assert _brand_fact(plain, "ru") == "Сеть «Coffee BOOM»."


# ---- 3. the Kazakh lead never declines a quoted name ---------------------------------------------------------------


def test_the_kazakh_pick_puts_no_case_ending_on_the_name():
    pick = s("ld_pick", "kk", name="Туалет", walk="жаяу 7 мин", tail="")
    assert pick == "«Туалет», жаяу 7 мин"
    assert "жеріне" not in pick


# ---- 4. «about an hour» --------------------------------------------------------------------------------------------


def _card(c: Candidate, intent: Intent):
    return template_rec(c, intent, None, [])


def test_an_hour_long_walk_gets_two_or_three_stops():
    intent = parse_rules("i want a nice walk this evening, about an hour, with lights").intent
    assert intent.time_stated
    kinds = intent.wished
    tower = _cand(_poi("tower", 150, kinds[0], name="Bayterek"), 2, "open")
    more = [
        _cand(_poi(f"s{i}", 500 + 300 * i, kinds[0], name=f"Sight {i}"), 7 + 4 * i)
        for i in range(3)
    ]
    one = [_card(tower, intent).model_copy(update={"time_on_site_min": 30})]
    out = fill_time(one, [tower, *more], intent, lambda c: _card(c, intent), 3)
    assert out[0].poi.id == "tower"
    assert 2 <= len(out) <= 3
    unstated = parse_rules("i want a nice walk this evening").intent
    assert fill_time(one, [tower, *more], unstated, lambda c: _card(c, unstated), 3) == one


def test_on_the_way_back_every_card_is_a_sight():
    intent = Intent(
        categories=["attraction_landmark", "park_garden", "entertainment"],
        wished=["attraction_landmark", "park_garden"],
    )
    hatiko = _cand(_poi("hatiko", 800, "attraction_landmark", name="Хатико"), 10)
    mall = _cand(_poi("mall", 300, "entertainment", name="Fame City"), 4)
    kobyz = _cand(_poi("kobyz", 1000, "attraction_landmark", name="Қобызшы"), 13)
    recs = [_card(hatiko, intent), _card(mall, intent)]
    out = asked_on_the_way(recs, [hatiko, mall, kobyz], intent, lambda c: _card(c, intent))
    assert [r.poi.id for r in out] == ["hatiko", "kobyz"]
    alone = asked_on_the_way(recs, [hatiko, mall], intent, lambda c: _card(c, intent))
    assert [r.poi.id for r in alone] == ["hatiko", "mall"]  # no other sight: the card stays


# ---- 5. «а рейтинг?» -----------------------------------------------------------------------------------------------


def test_the_better_known_place_is_picked_among_places_about_as_near():
    bare = _cand(_poi("bare", 300, "cafe", name="Кафе"), 4, score=6.0)
    known = _cand(
        _poi(
            "known",
            400,
            "cafe",
            name="TOTEM",
            website="https://totem.kz",
            tags=["brand=TOTEM"],
            hours="Mo-Su 08:00-23:00",
        ),
        6,
        "open",
        score=5.5,
    )
    far = _cand(
        _poi("far", 900, "cafe", name="Far", website="https://far.kz", tags=["brand=Far"]),
        11,
        score=5.0,
    )
    assert evidence(known) > evidence(bare)
    assert [c.poi.id for c in evidence_first([bare, known])] == ["known", "bare"]
    assert [c.poi.id for c in evidence_first([bare, far])] == [
        "bare",
        "far",
    ]  # 7 min apart: the rank holds
    halal = bare.model_copy(update={"reasons": ["halal"]})
    assert [c.poi.id for c in evidence_first([halal, known])] == [
        "bare",
        "known",
    ]  # a wish mark is never lost
    picked = template_recs([bare, known], Intent(categories=["cafe"], wished=["cafe"]))
    assert picked[0].poi.id == "known"
    assert "рейтинг" not in picked[0].why.lower()
