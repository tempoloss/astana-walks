"""Honest ranking: halal, step-free access, the real walking route against the card, the night, anonymous records, the
transport mode, the user's own words about the weather, the kinds the user has just been to, and a kind that is absent
nearby. Each test is a defect class of the fuzz runs, on a small synthetic map around one origin."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks import generate as gen_mod
from walks import pipeline
from walks.claims import unsupported_wishes
from walks.generate import _from_llm, keep_required, pick_diverse
from walks.i18n import t
from walks.kids import unnamed_more
from walks.llm_output import LLMOutput, LLMRec
from walks.models import POI, Candidate, Intent, IntentResult
from walks.radius import NEAREST_FAR, km_text, one_way_limit_min
from walks.realfit import replace_unreachable, sync_stays
from walks.retrieve import retrieve
from walks.shelter import apply_shelter_rule, is_outdoor_place, is_outdoor_sport
from walks.walking import Leg
from walks.weather import manual_weather, with_user_hint

LANGS = ("kk", "ru", "en")
ORIGIN = (51.09, 71.41)
NOON = datetime(2026, 10, 14, 12, 0)
NIGHT_0200 = datetime(2026, 10, 14, 2, 0)
M = 1 / 111_000  # one metre in degrees of latitude
NAMES = ["Алма", "Бета", "Гамма", "Дельта", "Эпсилон", "Зета", "Йота", "Каппа", "Лямбда"]


def P(pid: str, name: str, north_m: float, category="cafe", east_m: float = 0.0, **kw) -> POI:
    return POI(
        id=pid,
        name=name,
        lat=ORIGIN[0] + north_m * M,
        lon=ORIGIN[1] + east_m * M * 1.6,
        category=category,
        sources=["osm"],
        **kw,
    )


def best(pois, intent, when=NOON, **kw) -> list[Candidate]:
    return retrieve(pois, *ORIGIN, intent, when, **kw).candidates


def run(pois, intent, when=NOON, weather=None, monkeypatch=None, router=None):
    """The whole pipeline with a fixed intent (the rule parser is not what is under test)."""
    monkeypatch.setattr(
        pipeline, "parse_intent", lambda *a, **k: IntentResult(intent=intent, parser="rules")
    )
    return pipeline.recommend(
        "x", *ORIGIN, when, use_llm=False, pois=pois, weather=weather, router=router
    )


# ---------------------------------------------------------------- halal


@pytest.mark.parametrize("lang", LANGS)
def test_halal_marked_places_come_first_and_the_others_are_not_called_halal(lang):
    pois = [
        P("near1", "Стейк Хаус", 150, "restaurant"),
        P("near2", "Пицца Рома", 200, "restaurant", tags=["cuisine=pizza"]),
        P("halal", "Дастархан", 600, "restaurant", tags=["overture_category=halal_restaurant"]),
        P("named", "Халал Бар", 650, "restaurant"),
    ]
    top = best(pois, Intent(halal=True, categories=["restaurant"], language=lang))
    assert {c.poi.id for c in top[:2]} == {"halal", "named"}  # the record's tag, the word in a name
    assert all("halal" in c.reasons for c in top[:2])
    assert all("halal" not in c.reasons and "halal_unverified" in c.reasons for c in top[2:])


@pytest.mark.parametrize("lang", LANGS)
def test_when_no_place_is_marked_halal_every_card_says_so(lang, monkeypatch):
    pois = [
        P("a", "Стейк Хаус", 150, "restaurant"),
        P("b", "Пицца Рома", 200, "restaurant"),
        P("c", "Бургер Лаб", 250, "restaurant"),
    ]
    res = run(
        pois, Intent(halal=True, categories=["restaurant"], language=lang), monkeypatch=monkeypatch
    )
    assert res.recs
    for r in res.recs:
        assert t("note_halal_none", lang) in r.notes
        assert "халяль" not in r.why.lower()
        assert "halal" not in r.why.lower()
    for c in res.retrieval.candidates:
        assert "halal" not in c.reasons


def test_a_halal_card_says_it_by_the_field_and_carries_no_unverified_note(monkeypatch):
    pois = [
        P("h", "Дастархан", 300, "restaurant", tags=["overture_category=halal_restaurant"]),
        P("a", "Стейк Хаус", 150, "restaurant"),
    ]
    res = run(pois, Intent(halal=True, categories=["restaurant"]), monkeypatch=monkeypatch)
    first = res.recs[0]
    assert first.poi.id == "h"
    assert t("fit_halal", "ru").lower() in first.why.lower()
    assert t("note_halal", "ru") not in first.notes
    other = next(r for r in res.recs if r.poi.id == "a")
    assert t("note_halal", "ru") in other.notes  # the others are not presented as halal


# ---------------------------------------------------------------- step-free access


def test_places_with_confirmed_step_free_access_outrank_nearer_unverified_ones():
    pois = [
        P("near", "Кафе рядом", 100),
        P("ok", "Кафе с пандусом", 450, wheelchair="yes"),
    ]
    top = best(pois, Intent(accessibility=True, categories=["cafe"]))
    assert [c.poi.id for c in top] == ["ok", "near"]
    assert "wheelchair_unverified" in top[1].reasons


# ---------------------------------------------------------------- the card and the route


def test_the_cards_time_on_site_is_the_one_the_route_allots_after_shrinking(monkeypatch):
    pois = [P(f"r{i}", f"Ресторан {NAMES[i]}", 250 + 60 * i, "restaurant") for i in range(3)]
    res = run(pois, Intent(time_budget_min=60, categories=["restaurant"]), monkeypatch=monkeypatch)
    assert res.route is not None
    assert res.route.shrunk  # three restaurants do not fit 60 minutes whole
    stay = dict(zip(res.route.stops, res.route.stay_min, strict=True))
    assert stay
    for r in res.recs:
        if r.poi.id in stay:
            assert r.time_on_site_min == stay[r.poi.id]
        assert f"~{r.time_on_site_min} мин" not in r.why or r.poi.id in stay


def test_sync_stays_leaves_a_card_the_route_dropped_alone():
    pois = [P("a", "А", 200), P("b", "Б", 300)]
    recs = pipeline_recs(pois)
    from walks.route import build_route

    route = build_route(*ORIGIN, recs[:1], "walk", 60)
    before = recs[1].time_on_site_min
    sync_stays(recs, route)
    assert recs[1].time_on_site_min == before
    assert recs[0].time_on_site_min == route.stay_min[0]


def pipeline_recs(pois, intent=None):
    intent = intent or Intent(categories=["cafe"])
    cands = best(pois, intent)
    return [gen_mod.template_rec(c, intent, None, cands) for c in cands]


class DetourRouter:
    """A router that knows a barrier: some places are reached only by a long way round."""

    def __init__(self, minutes: dict[str, int]):
        self.minutes = minutes  # "lat" of the place rounded to 4 decimals -> real one-way minutes

    def leg(self, a, b, *, persist=False) -> Leg:
        key = max((a, b), key=lambda p: abs(p[0] - ORIGIN[0]))
        minutes = self.minutes.get(f"{key[0]:.4f}", 8)
        return Leg(minutes * 80, minutes, "valhalla")


def test_a_card_whose_real_route_is_too_long_is_replaced_by_one_that_fits(monkeypatch):
    names = ["Алма", "Бета", "Гамма", "Дельта", "Эпсилон"]
    pois = [P(f"c{i}", f"Кафе {n}", 380 + 40 * i) for i, n in enumerate(names)]
    far = f"{pois[0].lat:.4f}"  # the nearest cafe is behind a river: 1.9 km on foot
    res = run(
        pois,
        Intent(time_budget_min=60, categories=["cafe"]),
        monkeypatch=monkeypatch,
        router=DetourRouter({far: 23}),
    )
    ids = [r.poi.id for r in res.recs]
    assert "c0" not in ids
    assert len(ids) == 3
    limit = one_way_limit_min(res.intent.intent)
    assert all(r.walk_min <= limit for r in res.recs)
    assert res.route is not None
    assert res.route.fits


def test_when_no_replacement_fits_the_card_stays_and_the_route_is_honest(monkeypatch):
    pois = [P("c0", "Кафе Алма", 400), P("c1", "Кафе Бета", 450)]
    slow = DetourRouter({f"{p.lat:.4f}": 25 for p in pois})
    res = run(
        pois, Intent(time_budget_min=60, categories=["cafe"]), monkeypatch=monkeypatch, router=slow
    )
    assert {r.poi.id for r in res.recs} == {"c0", "c1"}
    assert all(r.walk_min == 25 for r in res.recs)
    assert res.route is not None
    assert res.route.fits == (
        res.route.total_min <= res.route.budget_min
    )  # the route says it as it is


def test_replace_unreachable_uses_a_bounded_number_of_routing_requests():
    pois = [P(f"c{i}", f"Кафе {NAMES[i]}", 380 + 20 * i) for i in range(9)]
    intent = Intent(time_budget_min=60, categories=["cafe"])
    cands = best(pois, intent)
    recs = [gen_mod.template_rec(c, intent, None, cands) for c in cands[:3]]
    asked: list = []

    def leg(a, b):
        asked.append(b)
        return 3000, 40, "valhalla"  # everything is far

    for r in recs:
        r.walk_min = 40
    replace_unreachable(recs, cands, intent, None, leg, ORIGIN)
    assert len(asked) <= 4


# ---------------------------------------------------------------- the night


def test_between_23_and_06_a_confirmed_open_place_outranks_a_nearer_one_with_unknown_hours():
    pois = [
        P("unknown", "Кафе без часов", 100),
        P("open", "Кафе 24/7", 500, opening_hours="24/7"),
    ]
    for when in (NIGHT_0200, datetime(2026, 10, 14, 5, 30), datetime(2026, 10, 14, 23, 20)):
        top = best(pois, Intent(categories=["cafe"]), when)
        assert [c.poi.id for c in top] == ["open", "unknown"], when


def test_the_ai_pick_of_an_unknown_hours_place_is_swapped_for_its_open_twin_at_night():
    unknown = Candidate(
        poi=P("unknown", "Кафе без часов", 100),
        distance_m=100,
        walk_min=2,
        travel_min=2,
        hours_state="unknown",
        score=3.0,
    )
    opened = Candidate(
        poi=P("open", "Кафе 24/7", 500, opening_hours="24/7"),
        distance_m=500,
        walk_min=8,
        travel_min=8,
        hours_state="open",
        score=2.5,
    )
    out = LLMOutput(
        recommendations=[
            LLMRec(
                poi_id="unknown",
                why="Уютное кафе.",
                time_on_site_min=30,
                what_to_do="Кофе.",
                confidence="high",
                generated_idea=False,
            )
        ]
    )
    intent = Intent(categories=["cafe"])
    night, _ = _from_llm(out, [unknown, opened], intent, None, NIGHT_0200)
    assert [r.poi.id for r in night] == ["open"]
    assert night[0].text_source == "template"  # the model's sentences described another place
    day, _ = _from_llm(out, [unknown, opened], intent, None, NOON)
    assert [r.poi.id for r in day] == ["unknown"]


def test_outdoor_sport_grounds_are_outdoor_for_the_dark_and_shelter_rules():
    ski = P("ski", "Лыжная база", 300, "sport", tags=["club=sport", "building=yes"])
    stadium = P("st", "Стадион", 300, "sport", tags=["overture_category=stadium_arena"])
    gym = P("gym", "Фитнес-клуб", 300, "sport", tags=["leisure=sports_centre"])
    pool = P("pool", "Бассейн", 300, "sport", tags=["overture_category=swimming_pool"])
    assert is_outdoor_sport(ski)
    assert is_outdoor_sport(stadium)
    assert not is_outdoor_sport(gym)
    assert not is_outdoor_sport(pool)
    assert is_outdoor_place(ski)
    assert not is_outdoor_place(gym)
    dark = manual_weather(10.0, force_dark=True)
    top = best(
        [ski, gym], Intent(categories=["sport"]), datetime(2026, 10, 14, 23, 45), weather=dark
    )
    assert [c.poi.id for c in top] == ["gym", "ski"]
    assert "dark_outdoor" in top[1].reasons
    kept, removed = apply_shelter_rule(
        [
            Candidate(
                poi=p, distance_m=1, walk_min=1, travel_min=1, hours_state="unknown", score=1.0
            )
            for p in (ski, gym, P("cafe", "Кафе", 100))
        ]
    )
    assert {c.poi.id for c in kept} == {"gym", "cafe"}
    assert removed == 1


# ---------------------------------------------------------------- anonymous records


@pytest.mark.parametrize("lang", LANGS)
def test_one_card_for_the_anonymous_playgrounds_that_says_how_many_more_there_are(
    lang, monkeypatch
):
    pois = [
        P(f"pg{i}", "Детская площадка", 120 + 25 * i, "kids_playground", name_generated=True)
        for i in range(5)
    ]
    res = run(
        pois,
        Intent(language=lang, with_kids=True, categories=["kids_playground"]),
        monkeypatch=monkeypatch,
    )
    playgrounds = [r for r in res.recs if r.poi.name_generated]
    assert len(playgrounds) == 1
    assert unnamed_more(4, lang) in playgrounds[0].notes
    assert sum(1 for c in res.retrieval.candidates if c.poi.name_generated) == 1


def test_unnamed_more_is_grammatical_in_russian():
    assert unnamed_more(1, "ru") == "И ещё 1 безымянное место этого типа рядом."
    assert "2 безымянных места" in unnamed_more(2, "ru")
    assert "5 безымянных мест" in unnamed_more(5, "ru")
    assert "11 безымянных мест" in unnamed_more(11, "ru")


def test_two_branches_of_one_chain_do_not_fill_two_cards_while_another_place_exists():
    star1 = Candidate(
        poi=P("s1", "Starbucks", 100),
        distance_m=100,
        walk_min=2,
        travel_min=2,
        hours_state="unknown",
        score=3.0,
    )
    star2 = Candidate(
        poi=P("s2", "Starbucks", 900, east_m=900),
        distance_m=900,
        walk_min=12,
        travel_min=12,
        hours_state="unknown",
        score=2.9,
    )
    other = Candidate(
        poi=P("o", "Кофейня Лето", 300),
        distance_m=300,
        walk_min=4,
        travel_min=4,
        hours_state="unknown",
        score=2.0,
    )
    ids = [c.poi.id for c in pick_diverse([star1, star2, other])]
    assert ids == ["s1", "o"]


# ---------------------------------------------------------------- transport mode


def test_a_mode_the_user_did_not_ask_for_is_walking(monkeypatch):
    pois = [P("a", "Музей", 800, "museum_gallery"), P("b", "Музей 2", 3500, "museum_gallery")]
    guess = Intent(
        time_budget_min=360, mode="car", categories=["museum_gallery"], mode_explicit=False
    )
    res = run(pois, guess, monkeypatch=monkeypatch)
    assert res.intent.intent.mode == "walk"
    assert res.retrieval.filters.mode == "walk"
    assert res.retrieval.filters.radius_declared_m < 5000  # a walking radius, not 15 km
    asked = guess.model_copy(update={"mode_explicit": True})
    res = run(pois, asked, monkeypatch=monkeypatch)
    assert res.intent.intent.mode == "car"


# ---------------------------------------------------------------- the user's own words about the weather


@pytest.mark.parametrize("hint", ["cold", "rain", "heat", "smog"])
@pytest.mark.parametrize("lang", LANGS)
def test_the_users_words_about_the_weather_move_the_walk_indoors_even_without_a_measurement(
    hint, lang, monkeypatch
):
    pois = [
        P("park", "Парк", 200, "park_garden"),
        P("museum", "Музей", 300, "museum_gallery"),
        P("cafe", "Кафе", 250),
    ]
    intent = Intent(language=lang, categories=["park_garden"], weather_hint=hint)
    res = run(pois, intent, weather=None, monkeypatch=monkeypatch)
    assert res.weather is not None
    assert res.weather.user_hint == hint
    assert res.weather.indoor_preferred
    assert res.retrieval.filters.weather_adapted
    assert "park" not in {
        r.poi.id for r in res.recs
    }  # frost / smog rule: outdoor places are dropped
    assert all(r.padding == "substituted" for r in res.recs)
    assert all(t(f"wx_hint_{hint}", lang) in r.why for r in res.recs)


def test_a_measured_condition_that_already_says_the_same_is_kept():
    frost = manual_weather(-30.0)
    assert with_user_hint(frost, "cold") is frost
    fine = manual_weather(10.0, pm25=5.0)
    hinted = with_user_hint(fine, "cold")
    assert hinted is not fine
    assert hinted.adverse
    assert hinted.user_hint == "cold"
    assert with_user_hint(fine, "none") is fine
    assert with_user_hint(None, "smog").air_bad


# ---------------------------------------------------------------- the kind the user has just been to


def test_a_kind_the_user_has_just_visited_is_left_out_unless_nothing_else_remains(monkeypatch):
    mosque = P("m", "Мечеть", 40, "attraction_landmark")
    cafes = [P("c1", "Кафе 1", 200), P("c2", "Кафе 2", 260)]
    intent = Intent(exclude_categories=["attraction_landmark"])
    top = best([mosque, *cafes], intent)
    assert "m" not in {c.poi.id for c in top}
    only = best([mosque], intent)
    assert [c.poi.id for c in only] == ["m"]


# ---------------------------------------------------------------- a kind that is absent nearby


@pytest.mark.parametrize("lang", LANGS)
def test_an_absent_kind_gets_the_nearest_one_with_its_distance_not_unrelated_back_fill(
    lang, monkeypatch
):
    pois = [
        P("church", "Церковь", 300, "attraction_landmark"),
        P("mall", "ТЦ", 400, "mall"),
        P("cafe", "Кафе", 250),
        P("cinema", "Кинотеатр", 6000, "culture_theatre_cinema"),
    ]
    intent = Intent(language=lang, time_budget_min=90, categories=["culture_theatre_cinema"])
    res = run(pois, intent, monkeypatch=monkeypatch)
    assert [r.poi.id for r in res.recs] == ["cinema"]
    card = res.recs[0]
    assert card.padding == "expanded"
    assert t("note_nearest_far", lang, cat="", km="")[:6] in card.notes
    assert km_text(6000, lang) in card.notes
    assert NEAREST_FAR in res.retrieval.candidates[0].reasons


def test_an_absent_kind_that_the_city_does_not_have_gives_an_honest_empty_answer(monkeypatch):
    pois = [P("church", "Церковь", 300, "attraction_landmark"), P("mall", "ТЦ", 400, "mall")]
    res = run(pois, Intent(categories=["culture_theatre_cinema"]), monkeypatch=monkeypatch)
    assert res.recs == []


def test_a_stroll_keeps_its_back_fill_because_a_park_answers_it(monkeypatch):
    pois = [P("park", "Парк", 300, "park_garden"), P("cafe", "Кафе", 250)]
    res = run(pois, Intent(categories=["viewpoint"]), monkeypatch=monkeypatch)
    assert "park" in {r.poi.id for r in res.recs}


# ---------------------------------------------------------------- budget / short time: the nearer twin


def test_a_budget_request_gets_the_nearer_twin_of_the_models_far_pick_and_a_plain_one_does_not():
    near = Candidate(
        poi=P("near", "Кафе рядом", 200),
        distance_m=200,
        walk_min=3,
        travel_min=3,
        hours_state="unknown",
        score=2.0,
    )
    far = Candidate(
        poi=P("far", "Кафе далеко", 900),
        distance_m=900,
        walk_min=12,
        travel_min=12,
        hours_state="unknown",
        score=2.6,
    )
    out = LLMOutput(
        recommendations=[
            LLMRec(
                poi_id="far",
                why="Хороший выбор.",
                time_on_site_min=30,
                what_to_do="Кофе.",
                confidence="high",
                generated_idea=False,
            )
        ]
    )
    cheap, _ = _from_llm(out, [far, near], Intent(budget="low", categories=["cafe"]))
    assert [r.poi.id for r in cheap] == ["near"]
    plain, _ = _from_llm(out, [far, near], Intent(categories=["cafe"]))
    assert [r.poi.id for r in plain] == ["far"]
    quick, _ = _from_llm(out, [far, near], Intent(time_budget_min=40, categories=["cafe"]))
    assert [r.poi.id for r in quick] == ["near"]


def test_an_absent_kind_is_back_filled_only_by_kinds_that_still_answer_it(monkeypatch):
    pois = [
        P("church", "Церковь", 300, "attraction_landmark"),
        P("mall", "ТЦ", 400, "mall"),
        P("cafe", "Кафе", 250),
        P("play", "Батутный парк", 350, "entertainment"),
    ]
    res = run(
        pois,
        Intent(time_budget_min=90, categories=["culture_theatre_cinema"]),
        monkeypatch=monkeypatch,
    )
    assert [r.poi.id for r in res.recs] == ["play"]
    assert res.recs[0].padding == "backfill"  # still labelled as outside the request


def test_a_gym_wish_ranks_an_outdoor_sports_ground_below_a_gym_even_by_day():
    ski = P("ski", "Лыжная база", 100, "sport", tags=["club=sport", "building=yes"])
    gym = P("gym", "Фитнес-клуб", 500, "sport", tags=["leisure=sports_centre"])
    plain = best([ski, gym], Intent(categories=["sport"]))
    assert plain[0].poi.id == "ski"  # no wish: the nearer one
    wish = best([ski, gym], Intent(categories=["sport"], free_text_keywords=["спортзал"]))
    assert [c.poi.id for c in wish] == ["gym", "ski"]


def test_a_kind_that_is_nearby_but_does_not_fit_the_time_is_shown_flagged_not_replaced_by_unrelated_places(
    monkeypatch,
):
    pois = [
        P("church", "Церковь", 300, "attraction_landmark"),
        P("mall", "ТЦ", 400, "mall"),
        P("cinema", "Кинотеатр", 700, "culture_theatre_cinema"),
    ]
    res = run(
        pois,
        Intent(time_budget_min=120, time_stated=True, categories=["culture_theatre_cinema"]),
        monkeypatch=monkeypatch,
    )
    assert [r.poi.id for r in res.recs] == ["cinema"]
    assert (
        NEAREST_FAR not in res.retrieval.candidates[0].reasons
    )  # it is not far: it just does not fit whole
    assert t("budget_over", "ru", lo=120).split(":")[0] in res.recs[0].why + res.recs[0].notes


# ---------------------------------------------------------------- round 2: diets, the night, plans, unanswerable wishes

MEAT = {"tags": ["cuisine=steak_house;barbecue"]}


@pytest.mark.parametrize("lang", LANGS)
def test_a_vegetarian_request_ranks_the_marked_place_first_and_meat_houses_last(lang):
    pois = [
        P("meat", "KAL'BI MEAT HOUSE", 100, "restaurant", **MEAT),
        P("pub", "Shashlyk Pub", 120, "restaurant"),
        P("plain", "Ресторан Лето", 150, "restaurant"),
        P(
            "veg",
            "Veggie Кафе",
            500,
            "restaurant",
            tags=["overture_category=vegetarian_restaurant"],
        ),
    ]
    top = best(pois, Intent(diets=["vegetarian"], categories=["restaurant"], language=lang))
    assert top[0].poi.id == "veg"
    assert "diet:vegetarian" in top[0].reasons
    assert {c.poi.id for c in top[-2:]} == {
        "pub",
        "meat",
    }  # both meat places last, whatever the distance


def test_diet_words_among_the_keywords_count_without_the_rule_parsers_field():
    meat = P("meat", "Steak Hub", 100, "restaurant", **MEAT)
    veg = P("veg", "Green", 400, "restaurant", tags=["diet:vegan=yes"])
    top = best([meat, veg], Intent(categories=["restaurant"], free_text_keywords=["vegetarian"]))
    assert top[0].poi.id == "veg"


@pytest.mark.parametrize("lang", LANGS)
@pytest.mark.parametrize("diet", ["gluten_free", "kosher", "vegetarian", "vegan"])
def test_when_no_place_marks_a_diet_every_card_says_so_and_a_coeliac_is_told_to_ask(
    diet, lang, monkeypatch
):
    pois = [P(f"r{i}", f"Ресторан {NAMES[i]}", 150 + 40 * i, "restaurant") for i in range(3)]
    res = run(
        pois,
        Intent(diets=[diet], categories=["restaurant"], language=lang),
        monkeypatch=monkeypatch,
    )
    assert res.recs
    for r in res.recs:
        assert t(f"note_diet_none_{diet}", lang) in r.notes
        assert ("не содержат глютена" in r.why) is False
        assert (t("note_gluten_medical", lang) in r.notes) == (diet == "gluten_free")
    assert all(not any(x.startswith("diet:") for x in c.reasons) for c in res.retrieval.candidates)


def test_a_marked_diet_place_is_said_by_its_field_and_the_others_say_unverified(monkeypatch):
    pois = [
        P("v", "Veggie", 300, "restaurant", tags=["overture_category=vegetarian_restaurant"]),
        P("a", "Лето", 150, "restaurant"),
    ]
    res = run(
        pois, Intent(diets=["vegetarian"], categories=["restaurant"]), monkeypatch=monkeypatch
    )
    first = next(r for r in res.recs if r.poi.id == "v")
    assert t("fit_diet_vegetarian", "ru").lower() in first.why.lower()
    assert t("note_diet_vegetarian", "ru") not in first.notes
    other = next(r for r in res.recs if r.poi.id == "a")
    assert t("note_diet_vegetarian", "ru") in other.notes


def test_a_vegan_mark_backs_a_vegetarian_claim_but_not_the_other_way_round():
    from walks.attributes import diet_signal

    vegan = P("v", "V", 1, "restaurant", tags=["diet:vegan=yes"])
    vegetarian = P("w", "W", 1, "restaurant", tags=["diet:vegetarian=yes"])
    assert diet_signal(vegan, "vegetarian")
    assert diet_signal(vegan, "vegan")
    assert diet_signal(vegetarian, "vegetarian")
    assert not diet_signal(vegetarian, "vegan")
    assert not diet_signal(P("s", "Steak", 1, "restaurant", **MEAT), "gluten_free")


def test_at_night_confirmed_open_food_comes_before_anything_with_unknown_hours():
    pois = [
        P("u1", "Кафе А", 100),
        P("u2", "Кафе Б", 150, "fast_food"),
        P("mall", "ТЦ", 120, "mall"),
        P("open", "Круглосуточная столовая", 600, "restaurant", opening_hours="24/7"),
    ]
    top = best(
        pois,
        Intent(categories=["restaurant", "cafe", "fast_food", "mall"], time_budget_min=90),
        NIGHT_0200,
    )
    assert top[0].poi.id == "open"
    assert "mall" not in {c.poi.id for c in top}  # unknown hours at 2 a.m. in a mall: closed
    assert all("night_unknown" in c.reasons for c in top[1:])


@pytest.mark.parametrize("lang", LANGS)
def test_a_night_card_with_unknown_hours_says_it_may_be_closed(lang, monkeypatch):
    pois = [P("u", "Кафе А", 100)]
    res = run(
        pois, Intent(categories=["cafe"], language=lang), when=NIGHT_0200, monkeypatch=monkeypatch
    )
    assert t("note_night_unknown", lang) in res.recs[0].notes
    day = run(pois, Intent(categories=["cafe"], language=lang), monkeypatch=monkeypatch)
    assert t("note_night_unknown", lang) not in day.recs[0].notes


def test_a_plan_in_stages_gets_one_stop_per_stage_in_the_users_order(monkeypatch):
    pois = [
        P("f1", "Кафе 1", 100),
        P("f2", "Кафе 2", 130),
        P("f3", "Кафе 3", 160),
        P("m", "Музей", 700, "museum_gallery"),
    ]
    intent = Intent(
        categories=["cafe", "museum_gallery"],
        plan_order=["cafe", "museum_gallery"],
        time_budget_min=180,
    )
    res = run(pois, intent, monkeypatch=monkeypatch)
    cats = [r.poi.category for r in res.recs]
    assert "museum_gallery" in cats
    assert "cafe" in cats
    assert res.route is not None
    stop_cats = {r.poi.id: r.poi.category for r in res.recs}
    stops = [stop_cats[s] for s in res.route.stops]
    assert stops[0] == "cafe"
    assert stops[-1] == "museum_gallery"
    reverse = intent.model_copy(update={"plan_order": ["museum_gallery", "cafe"]})
    res = run(pois, reverse, monkeypatch=monkeypatch)
    stop_cats = {r.poi.id: r.poi.category for r in res.recs}
    assert stop_cats[res.route.stops[0]] == "museum_gallery"


def test_a_named_landmark_the_user_described_outranks_a_nearer_look_alike():
    near = P("near", "Монумент Нур", 100, "attraction_landmark")
    tower = P("tower", "Байтерек", 500, "attraction_landmark")
    plain = best([near, tower], Intent(categories=["attraction_landmark"]))
    assert plain[0].poi.id == "near"
    named = best(
        [near, tower], Intent(categories=["attraction_landmark"], landmark_refs=["Байтерек"])
    )
    assert named[0].poi.id == "tower"


@pytest.mark.parametrize("lang", LANGS)
def test_a_wish_no_record_can_answer_is_said_on_the_card(lang, monkeypatch):
    pois = [P("pg", "Игровая площадка", 100, "kids_playground")]
    intent = Intent(
        language=lang,
        categories=["kids_playground"],
        free_text_keywords=["туалет", "пеленальный столик"],
    )
    res = run(pois, intent, monkeypatch=monkeypatch)
    notes = res.recs[0].notes
    asked = unsupported_wishes(intent.free_text_keywords, lang)
    assert len(asked) == 2
    assert all(t("note_unsupported", lang, what=w) in notes for w in asked)


def test_a_spelling_remark_of_a_wikipedia_sentence_is_not_the_advice_of_the_card():
    from walks.reasons import _first_sentence

    text = (
        "Хан Шатыр (по-русски: ошибочно — «Ханский шатёр», правильно — «Хан среди шатров») — торговый "
        "центр в Астане. Второе предложение."
    )
    assert _first_sentence(text) == "Хан Шатыр — торговый центр в Астане."


@pytest.mark.parametrize("lang", LANGS)
def test_when_bars_are_excluded_for_a_minor_the_card_says_so(lang, monkeypatch):
    pois = [P("bar", "Бар", 100, "bar_nightlife"), P("cafe", "Кафе", 200), P("c2", "Кафе 2", 250)]
    intent = Intent(
        language=lang, minor=True, categories=["bar_nightlife", "cafe"], time_budget_min=90
    )
    res = run(pois, intent, monkeypatch=monkeypatch)
    assert res.recs
    assert "bar" not in {r.poi.id for r in res.recs}
    assert all(t("note_minor", lang) in r.notes for r in res.recs)


# ---------------------------------------------------------------- round 3: pets, groups, prices, asking about a place


@pytest.mark.parametrize("lang", LANGS)
def test_pets_and_group_wishes_are_said_not_assumed_on_every_card(lang, monkeypatch):
    pois = [P("a", "Кафе А", 100), P("b", "Кафе Б", 150, tags=["dog=yes", "capacity=30"])]
    intent = Intent(language=lang, categories=["cafe"], pets=True, group_size=8, time_budget_min=90)
    res = run(pois, intent, monkeypatch=monkeypatch)
    cards = {r.poi.id: r for r in res.recs}
    assert t("note_pets", lang) in cards["a"].notes
    assert t("note_group", lang) in cards["a"].notes
    assert t("note_pets", lang) not in cards["b"].notes
    assert t("note_group", lang) not in cards["b"].notes
    assert res.recs[0].poi.id == "b"  # the place the data mark for dogs outranks the nearer one


@pytest.mark.parametrize("lang", LANGS)
def test_a_price_cap_in_tenge_gets_the_no_price_data_note(lang, monkeypatch):
    pois = [P("a", "Кафе А", 100), P("b", "Кафе Б", 150)]
    intent = Intent(language=lang, categories=["cafe"], budget="low", price_cap_kzt=3000)
    res = run(pois, intent, monkeypatch=monkeypatch)
    for r in res.recs:
        assert t("note_price_cap", lang, cap=3000) in r.notes
        assert t("note_cheaper", lang) not in r.notes


@pytest.mark.parametrize("lang", LANGS)
def test_cheaper_changes_the_ranking_by_kind_and_says_prices_are_unknown(lang, monkeypatch):
    pois = [
        P("rest", "Ресторан А", 100, "restaurant"),
        P("fast", "Фастфуд Б", 400, "fast_food"),
        P("cafe", "Кафе В", 300),
    ]
    cats = ["restaurant", "fast_food", "cafe"]
    plain = best(pois, Intent(categories=cats, time_budget_min=90))
    cheap = best(pois, Intent(categories=cats, budget="low", time_budget_min=90))
    assert plain[0].poi.id == "rest"
    assert cheap[0].poi.id in {"fast", "cafe"}
    assert cheap[-1].poi.id == "rest"
    res = run(
        pois,
        Intent(categories=cats, budget="low", language=lang, time_budget_min=90),
        monkeypatch=monkeypatch,
    )
    assert all(t("note_cheaper", lang) in r.notes for r in res.recs)


@pytest.mark.parametrize("lang", LANGS)
def test_the_place_asked_about_comes_first_even_far_away_and_closed_is_the_answer(
    lang, monkeypatch
):
    pois = [
        P("near", "Кафе рядом", 100),
        P("shatyr", "Хан Шатыр", 4000, "mall", opening_hours="Mo-Su 10:00-11:00"),
    ]
    intent = Intent(
        language=lang, categories=["cafe"], info_about=["Хан Шатыр"], time_budget_min=60
    )
    res = run(pois, intent, monkeypatch=monkeypatch)
    assert res.recs[0].poi.id == "shatyr"
    assert res.recs[0].hours_state == "closed"
    assert t("fact_closed_now", lang) in res.recs[0].why
    assert t("fit_info", lang).lower() in res.recs[0].why.lower()
    open_ = pois[1].model_copy(update={"opening_hours": "Mo-Su 00:00-24:00"})
    res = run([pois[0], open_], intent, monkeypatch=monkeypatch)
    assert res.recs[0].poi.id == "shatyr"
    assert res.recs[0].hours_state == "open"


def test_a_round_the_clock_place_stays_open_on_a_holiday_with_the_caveat(monkeypatch):
    pois = [
        P("a", "Кафе 24/7", 100, opening_hours="24/7"),
        P("b", "Кафе днём", 120, opening_hours="Mo-Su 09:00-22:00"),
    ]
    holiday = datetime(2026, 10, 26, 12, 0)
    res = run(pois, Intent(categories=["cafe"]), when=holiday, monkeypatch=monkeypatch)
    by = {r.poi.id: r for r in res.recs}
    assert by["a"].hours_state == "open"
    assert by["b"].hours_state == "unknown"
    assert t("note_holiday", "ru", name="День Республики Казахстан (перенос)") in by["a"].notes
    assert by["a"].confidence != "high"


def test_something_else_never_brings_back_a_branch_of_a_chain_already_shown():
    from walks.models import Constraints

    shown = P("s1", "Starbucks", 100)
    other_branch = P("s2", "Starbucks", 2000, east_m=1500)
    other = P("o", "Кофейня Лето", 400)
    top = retrieve(
        [shown, other_branch, other],
        *ORIGIN,
        Intent(categories=["cafe"], time_budget_min=120),
        NOON,
        constraints=Constraints(exclude_ids=["s1"]),
    ).candidates
    assert [c.poi.id for c in top] == ["o"]


@pytest.mark.parametrize("lang", LANGS)
def test_the_model_cannot_drop_the_diet_marked_place_or_the_place_asked_about(lang):
    veg = Candidate(
        poi=P(
            "veg",
            "Veggie",
            600,
            category="restaurant",
            tags=["overture_category=vegetarian_restaurant"],
        ),
        distance_m=600,
        walk_min=8,
        travel_min=8,
        hours_state="unknown",
        score=6.0,
        reasons=["diet:vegetarian"],
    )
    others = [
        Candidate(
            poi=P(f"r{i}", f"Ресторан {NAMES[i]}", 100 + 50 * i, category="restaurant"),
            distance_m=100 + 50 * i,
            walk_min=2 + i,
            travel_min=2 + i,
            hours_state="open",
            score=3.0 - i * 0.1,
            reasons=["diet_unverified:vegetarian"],
        )
        for i in range(3)
    ]
    cands = [veg, *others]
    out = LLMOutput(
        recommendations=[
            LLMRec(
                poi_id=c.poi.id,
                why="Хорошее место.",
                time_on_site_min=30,
                what_to_do="Обед.",
                confidence="high",
                generated_idea=False,
            )
            for c in others
        ]
    )
    intent = Intent(
        language=lang, categories=["restaurant"], diets=["vegetarian"], time_budget_min=90
    )
    recs, _ = _from_llm(out, cands, intent)
    assert "veg" not in {r.poi.id for r in recs}  # the raw model answer drops it ...
    kept = keep_required(recs, cands, intent, None)
    assert "veg" in {r.poi.id for r in kept}  # ... the answer does not
    assert len(kept) <= 3
