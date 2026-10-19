"""«Ещё N мест рядом»: under the cards of a search answer the further candidates of the same wish, ranked, built by
code only. An errand lists only its own kinds; the first three places and the text are not touched."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_more import MORE_MAX, order_key
from walks.models import POI, Candidate, load_pois
from walks.radius import ERRAND_KINDS
from walks.walking import offline_router

AITU = (51.0906, 71.4180)
NOON = datetime(2026, 10, 20, 13, 0)
FOOD = {"restaurant", "cafe", "fast_food", "bar_nightlife"}


@pytest.fixture(scope="module")
def pois():
    return load_pois()


def _turn(pois, text, lang="ru"):
    env = TurnEnv(when=NOON, use_llm=False, pois=pois, router=offline_router())
    return take_turn(new_state(*AITU, lang=lang), text, env=env).turn


def test_food_answer_has_up_to_seven_more_places_never_the_shown_ones(pois):
    turn = _turn(pois, "хочу поесть")
    assert len(turn.places) == 3
    assert 5 <= len(turn.more) <= MORE_MAX
    assert not {p.id for p in turn.places} & {p.id for p in turn.more}
    assert len({p.id for p in turn.more}) == len(turn.more)


def test_a_more_row_has_the_facts_of_a_card_from_code_and_no_text_of_the_model(pois):
    for place in _turn(pois, "хочу поесть").more:
        assert place.name
        assert place.kind
        assert place.hours.state in {"open", "closed", "unknown"}
        assert place.hours.text
        assert place.walk.minutes > 0
        assert place.walk.distance_m > 0
        assert place.why == ""
        assert place.what_to_do == ""
        assert not place.ai_idea
        assert place.text_source == "template"
        assert place.padding in {"none", "expanded"}


def test_the_longer_list_is_of_the_same_wish(pois):
    assert {p.category for p in _turn(pois, "хочу поесть").more} <= FOOD


def test_the_longer_list_is_nearest_first_by_the_minutes_it_shows(pois):
    turn = _turn(pois, "хочу поесть")
    keys = [(p.walk.minutes, p.walk.distance_m) for p in turn.more]
    assert keys == sorted(keys)
    assert turn.more_order == "distance"


def test_an_errand_list_is_open_first_then_nearest_and_says_so(pois):
    turn = _turn(pois, "банкомат рядом")
    assert turn.more
    assert turn.more_order == "open_first"
    keys = [(p.hours.state != "open", p.walk.minutes, p.walk.distance_m) for p in turn.more]
    assert keys == sorted(keys)


def test_an_errand_order_is_open_then_unknown_then_closed_nearest_within_each():
    def cand(pid, state, minutes):
        return Candidate(
            poi=POI(id=pid, name=pid, lat=51.09, lon=71.42, category="pharmacy"),
            distance_m=minutes * 80,
            walk_min=minutes,
            travel_min=minutes,
            hours_state=state,
            score=1.0,
        )

    pool = [
        cand("closed-near", "closed", 1),
        cand("unknown-near", "unknown", 2),
        cand("open-far", "open", 9),
        cand("unknown-far", "unknown", 7),
        cand("open-near", "open", 5),
    ]
    errand = [c.poi.id for c in sorted(pool, key=lambda c: order_key(c, True))]
    assert errand == ["open-near", "open-far", "unknown-near", "unknown-far", "closed-near"]
    plain = [c.poi.id for c in sorted(pool, key=lambda c: order_key(c, False))]
    assert plain == ["closed-near", "unknown-near", "open-near", "unknown-far", "open-far"]


def test_no_rows_no_order(pois):
    turn = _turn(pois, "привет")
    assert not turn.more
    assert turn.more_order == ""


@pytest.mark.parametrize("text", ["банкомат рядом", "где купить продукты"])
def test_an_errand_lists_only_its_own_kinds(pois, text):
    turn = _turn(pois, text)
    kinds = {p.category for p in turn.places}
    assert kinds <= ERRAND_KINDS
    assert {p.category for p in turn.more} <= kinds


def test_the_dialogue_remembers_only_the_three_shown_places(pois):
    env = TurnEnv(when=NOON, use_llm=False, pois=pois, router=offline_router())
    out = take_turn(new_state(*AITU), "хочу поесть", env=env)
    assert len(out.turn.more) >= 5
    assert [p.id for p in out.turn.places] == [p.id for p in out.state.shown]


def test_the_longer_list_is_in_every_language(pois):
    for lang in ("kk", "en"):
        turn = _turn(pois, "хочу поесть", lang=lang)
        assert turn.more
        assert all(p.hours.text for p in turn.more)
