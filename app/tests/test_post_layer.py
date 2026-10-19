"""The `post` layer (named post offices of Astana, amenity=post_office) on the real dataset: asked for, it is found;
otherwise it is never in the pool or the list (it is used, not strolled, like money), and it never pads another kind's
short list. The census proved the supply before pouring: post_office 50/50 named."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.i18n import CATEGORY, TIP
from walks.models import CATEGORIES, Intent, load_pois
from walks.radius import NEVER_BACKFILL, backfill_ok
from walks.retrieve import retrieve

NOON = datetime(2026, 10, 14, 12, 0)
EXPO = (51.0890, 71.4160)
DENSE = (
    51.1456,
    71.4148,
)  # a dense block: grocery / pharmacy places reach a generic list there (owner decision)
POIS = load_pois()


def test_the_layer_is_in_the_data_with_its_tag():
    post = [p for p in POIS if p.category == "post"]
    assert post
    assert any("amenity=post_office" in p.tags for p in post)


def test_the_layer_is_named_only():
    post = [p for p in POIS if p.category == "post"]
    assert all(p.name and not p.name.startswith("Почта (") for p in post)


def test_asked_for_post_the_nearest_places_are_found_at_the_dense_block():
    res = retrieve(POIS, *DENSE, Intent(categories=["post"]), NOON)
    assert res.candidates
    assert {c.poi.category for c in res.candidates} == {"post"}


@pytest.mark.parametrize("point", [EXPO, DENSE, (51.13, 71.43)])
def test_a_generic_request_never_lists_post_offices(point):
    res = retrieve(POIS, *point, Intent(categories=[]), NOON, top_n=10)
    assert res.candidates
    assert all(c.poi.category != "post" for c in res.candidates)


def test_a_post_request_is_never_padded_and_post_never_pads():
    assert "post" in NEVER_BACKFILL
    assert not backfill_ok("cafe", Intent(categories=["post"]), stroll=False)
    assert not backfill_ok("post", Intent(categories=["cafe"]), stroll=False)


def test_the_category_is_known_to_the_app_in_every_language():
    assert "post" in CATEGORIES
    kk, ru, en = CATEGORY["post"]
    assert len({kk, ru, en}) == 3
    assert "post" in TIP


def test_post_words_reach_post():
    from walks.dialog_nlu import named_categories

    assert "post" in named_categories("где почта")
    assert "post" in named_categories("отправить посылку")
    assert "post" in named_categories("почтовое отделение рядом")


# ------------------------------------------------------------- antiregressions: «пош-»/«хат» are not the post


def test_пошли_words_never_reach_post():
    from walks.dialog_nlu import named_categories

    assert "post" not in named_categories("пошли гулять")
    assert "post" not in named_categories("мы пошли в парк")


def test_kk_жолдау_is_not_the_post():
    from walks.dialog_nlu import named_categories

    assert "post" not in named_categories("маған хат жолдау")
