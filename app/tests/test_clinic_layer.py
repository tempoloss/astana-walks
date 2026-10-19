"""The `clinic` layer (dentists, clinics, doctor's offices, medical centres, laboratories) on the real dataset: asked
for, it is found; otherwise it is never in the pool or the list (it is used, not strolled, like money), and it never
pads another kind's short list. «Зубной» deliberately is not a stem: toothpaste / toothbrushes are grocery."""

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


def test_the_layer_is_in_the_data_with_its_subtypes():
    clinic = [p for p in POIS if p.category == "clinic"]
    assert clinic
    # the 168 of the harvest: dentists and clinics (amenity), the doctor's offices came as amenity=doctors
    # (OSM's older spelling of healthcare=doctor; both selectors match through the key itself)
    for tag in ("amenity=dentist", "amenity=clinic", "amenity=doctors"):
        assert any(tag in p.tags for p in clinic), tag


def test_the_layer_is_named_only():
    clinic = [p for p in POIS if p.category == "clinic"]
    assert all(p.name and not p.name.startswith("Клиника (") for p in clinic)


def test_asked_for_clinic_the_nearest_places_are_found_at_the_dense_block():
    res = retrieve(POIS, *DENSE, Intent(categories=["clinic"]), NOON)
    assert res.candidates
    assert {c.poi.category for c in res.candidates} == {"clinic"}


@pytest.mark.parametrize("point", [EXPO, DENSE, (51.13, 71.43)])
def test_a_generic_request_never_lists_clinics(point):
    res = retrieve(POIS, *point, Intent(categories=[]), NOON, top_n=10)
    assert res.candidates
    assert all(c.poi.category != "clinic" for c in res.candidates)


def test_a_clinic_request_is_never_padded_and_clinics_never_pad():
    assert "clinic" in NEVER_BACKFILL
    assert not backfill_ok("cafe", Intent(categories=["clinic"]), stroll=False)
    assert not backfill_ok("clinic", Intent(categories=["cafe"]), stroll=False)


def test_the_category_is_known_to_the_app_in_every_language():
    assert "clinic" in CATEGORIES
    kk, ru, en = CATEGORY["clinic"]
    assert len({kk, ru, en}) == 3
    assert "clinic" in TIP


def test_clinic_words_reach_clinic():
    from walks.dialog_nlu import named_categories

    assert "clinic" in named_categories("где клиника")
    assert "clinic" in named_categories("стоматолог рядом")
    assert "clinic" in named_categories("травмпункт")
    assert "clinic" in named_categories("к врачу")
    assert "clinic" in named_categories("зубной врач")


# ------------------------------------------------------------- antiregressions: «зуб» stays with grocery


def test_toothpaste_and_toothbrushes_never_reach_clinic():
    from walks.dialog_nlu import named_categories

    assert "clinic" not in named_categories("купить зубную пасту")
    assert "clinic" not in named_categories("зубные щётки")


def test_лечить_зубы_is_not_clinic_but_стоматолог_is():
    from walks.dialog_nlu import named_categories

    assert "clinic" not in named_categories("лечить зубы")
    # «у стоматолога» — locative (где я, а не что хочу; behavior соответствует «у аптеки»/«у музея»)
    assert "clinic" in named_categories("лечу зубы, где стоматолог")
