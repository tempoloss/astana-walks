"""The `money` layer (ATMs, bank branches, bureaux de change) on the real dataset: asked for, it is found; otherwise it
is never in the pool or the list (it is used, not strolled), and it never pads another kind's short list."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.i18n import CATEGORY, TIP
from walks.models import CATEGORIES, Intent, load_pois
from walks.radius import NEVER_BACKFILL, backfill_ok
from walks.retrieve import retrieve
from walks.supply import supply_counts

NOON = datetime(2026, 10, 14, 12, 0)
EXPO = (51.0890, 71.4160)
DENSE = (
    51.1456,
    71.4148,
)  # a dense block: grocery / pharmacy places reach a generic list there (owner decision)
POIS = load_pois()


def test_the_layer_is_in_the_data_with_its_three_subtypes():
    money = [p for p in POIS if p.category == "money"]
    assert len(money) > 300
    for tag in ("amenity=atm", "amenity=bank", "amenity=bureau_de_change"):
        assert any(tag in p.tags for p in money), tag


def test_asked_for_money_the_nearest_places_are_found_at_expo():
    res = retrieve(POIS, *EXPO, Intent(categories=["money"]), NOON)
    assert res.candidates
    assert {c.poi.category for c in res.candidates} == {"money"}


@pytest.mark.parametrize("point", [EXPO, DENSE, (51.13, 71.43)])
def test_a_generic_request_never_lists_money(point):
    res = retrieve(POIS, *point, Intent(categories=[]), NOON, top_n=10)
    assert res.candidates
    assert all(c.poi.category != "money" for c in res.candidates)


def test_money_alone_in_the_dataset_is_still_never_a_generic_recommendation():
    money = [p for p in POIS if p.category == "money"]
    assert retrieve(money, *DENSE, Intent(categories=[]), NOON).candidates == []
    assert retrieve(money, *DENSE, Intent(categories=["money"]), NOON).candidates


def test_the_generic_supply_count_leaves_money_out_and_the_asked_one_counts_it():
    money = [p for p in POIS if p.category == "money"]
    assert supply_counts(money, [], NOON) == (0, 0)
    total, _ = supply_counts(money, ["money"], NOON)
    assert total == len(money)


def test_another_kinds_short_list_is_never_padded_with_money():
    res = retrieve(POIS, *EXPO, Intent(categories=["museum_gallery"]), NOON, top_n=20)
    assert all(c.poi.category != "money" for c in res.candidates)


def test_a_money_request_is_never_padded_with_other_kinds_and_money_never_pads():
    assert "money" in NEVER_BACKFILL
    assert not backfill_ok("cafe", Intent(categories=["money"]), stroll=False)
    assert not backfill_ok("money", Intent(categories=["cafe"]), stroll=False)


def test_the_category_is_known_to_the_app_in_every_language():
    assert "money" in CATEGORIES
    kk, ru, en = CATEGORY["money"]
    assert len({kk, ru, en}) == 3
    assert kk != ru
    assert "money" in TIP


# ------------------------------------------------------------------ lodging: the opposite acceptance of money


def test_the_lodging_layer_is_in_the_data_with_its_subtypes_and_the_reclassified_hotel():
    lodging = [p for p in POIS if p.category == "lodging"]
    assert len(lodging) > 100
    for tag in ("tourism=hotel", "tourism=hostel", "tourism=guest_house"):
        assert any(tag in p.tags for p in lodging), tag
    # an Overture «hotel_bar» called «... Отель» is a hotel, not a bar
    assert not [
        p
        for p in POIS
        if p.category != "lodging" and "Отель" in p.name and "overture_category=hotel_bar" in p.tags
    ]


def test_asked_for_lodging_the_nearest_hotels_are_found_at_the_centre():
    res = retrieve(POIS, 51.13, 71.43, Intent(categories=["lodging"]), NOON)
    assert res.candidates
    assert {c.poi.category for c in res.candidates} == {"lodging"}


def test_lodging_unlike_money_is_a_recommendation_a_generic_pool_may_hold():
    lodging = [p for p in POIS if p.category == "lodging"]
    # nothing in the pool gate keeps it out: alone in the dataset a generic request lists it
    assert retrieve(lodging, 51.13, 71.43, Intent(categories=[]), NOON).candidates
    # and money alone is never listed for the same request (the opposite acceptance)
    money = [p for p in POIS if p.category == "money"]
    assert retrieve(money, 51.13, 71.43, Intent(categories=[]), NOON).candidates == []


def test_in_a_dense_block_a_generic_pool_holds_lodging_and_never_money():
    # the two acceptances side by side, on one request at one point (a pool wide enough to see both kinds)
    res = retrieve(POIS, *DENSE, Intent(categories=[]), NOON, top_n=200)
    kinds = {c.poi.category for c in res.candidates}
    assert "lodging" in kinds
    assert "money" not in kinds


def test_lodging_never_pads_another_kinds_list_but_may_be_padded():
    assert "lodging" in NEVER_BACKFILL
    assert not backfill_ok("lodging", Intent(categories=["cafe"]), stroll=False)
    assert backfill_ok(
        "cafe", Intent(categories=["lodging"]), stroll=False
    )  # a hotel is a destination, not a utility


def test_the_lodging_category_is_known_to_the_app_in_every_language():
    assert "lodging" in CATEGORIES
    kk, ru, en = CATEGORY["lodging"]
    assert len({kk, ru, en}) == 3
    assert "lodging" in TIP
