"""Музейный реестр e-museum.kz (source `museum_register`) в ответах приложения: цена со своим источником,
часы реестра без дней недели не решают «открыто», и ни одна фраза не называет реестр «OpenStreetMap» или сырым
`museum_register`. ru / kk / en."""

from __future__ import annotations

from datetime import datetime

from walks.dialog_place import answer, sources_of
from walks.dialog_types import Hours, Place, Walk
from walks.models import MUSEUM_REGISTER, POI, Candidate
from walks.reasons import _open_fact, hours_notes, hours_state_text

WED = datetime(2026, 10, 14, 12, 0)
CARD = "https://e-museum.kz/ru/museum/68da37a0228ab7ad4-ru/"
PRICE_SRC = {
    "source": MUSEUM_REGISTER,
    "license": "facts from the ministry museum register (e-museum.kz)",
    "snapshot_date": "2026-10-17",
    "url": CARD,
    "snippet": '"ticket_price":"500 тг"',
}
UNQ_SRC = {**PRICE_SRC, "hours_flags": ["needs_days"], "snippet": '"work_hours":"09:00 - 18:00"'}


def museum(**kw) -> POI:
    base = {
        "id": "way/240376692",
        "name": "Музей Сакена Сейфуллина",
        "lat": 51.17,
        "lon": 71.42,
        "category": "museum_gallery",
        "sources": ["osm", MUSEUM_REGISTER],
        "field_sources": {"price_text": PRICE_SRC},
        "price_text": "500 тг",
    }
    return POI(**{**base, **kw})


def place(poi: POI, **hkw) -> Place:
    hours = Hours(state=hkw.pop("state", "unknown"), text="", **hkw)
    return Place(
        id=poi.id,
        name=poi.name,
        kind="музей",
        category=poi.category,
        lat=poi.lat,
        lon=poi.lon,
        walk=Walk(minutes=5, distance_m=400),
        hours=hours,
    )


def unqualified_candidate() -> Candidate:
    poi = museum(
        opening_hours=None,
        hours_unqualified="09:00 - 18:00",
        field_sources={"price_text": PRICE_SRC, "hours_unqualified": UNQ_SRC},
    )
    return Candidate(
        poi=poi,
        distance_m=400,
        walk_min=5,
        travel_min=5,
        hours_state="unknown",
        hours_issue="unqualified",
        score=1.0,
    )


def test_the_register_price_is_answered_with_the_register_as_its_source():
    for lang in ("kk", "ru", "en"):
        a = answer("price", place(museum()), museum(), lang, WED)
        assert a.known
        assert "500 тг" in a.text
        assert a.source.url == CARD
    ru = answer("price", place(museum()), museum(), "ru", WED).text
    assert "по данным реестра музеев" in ru


def test_the_register_price_never_says_openstreetmap_and_never_prints_the_raw_label():
    for lang in ("kk", "ru", "en"):
        text = answer("price", place(museum()), museum(), lang, WED).text
        assert "museum_register" not in text
        assert "OpenStreetMap" not in text


def test_a_place_without_a_price_keeps_the_honest_no_data_answer():
    poi = museum(price_text=None, field_sources={})
    for lang in ("kk", "ru", "en"):
        a = answer("price", place(poi), poi, lang, WED)
        assert not a.known


def test_the_data_label_and_the_source_list_name_the_register():
    poi = museum()
    assert "реестр музеев e-museum.kz" in poi.data_label("ru")
    assert "мұражайлар реестрі e-museum.kz" in poi.data_label("kk")
    assert "e-museum.kz museum register" in poi.data_label("en")
    labels = [x.label for x in sources_of(poi, "ru")]
    assert any("реестр" in label for label in labels)
    assert "museum_register" not in labels


def test_a_price_from_another_layer_names_its_own_source_not_osm():
    # `price_text` may come from a sibling data branch: the answer reads the field whatever its source label is
    src = {
        "source": "travel_guide",
        "url": "https://en.wikivoyage.org/wiki/Astana",
        "snapshot_date": "2026-10-17",
    }
    poi = museum(field_sources={"price_text": src})
    for lang, needle in (
        ("ru", "en.wikivoyage.org"),
        ("kk", "en.wikivoyage.org"),
        ("en", "en.wikivoyage.org"),
    ):
        a = answer("price", place(poi), poi, lang, WED)
        assert a.known
        assert "500 тг" in a.text
        assert needle in a.text
        assert "travel_guide" not in a.text
        assert "OpenStreetMap" not in a.text
    no_url = museum(field_sources={"price_text": {"source": "travel_guide"}})
    a = answer("price", place(no_url), no_url, "ru", WED)
    assert "travel_guide" not in a.text
    assert "OpenStreetMap" not in a.text


def test_register_hours_without_days_stay_unqualified_and_are_named_as_the_register():
    poi = museum(
        opening_hours=None,
        hours_unqualified="09:00 - 18:00",
        field_sources={"price_text": PRICE_SRC, "hours_unqualified": UNQ_SRC},
    )
    assert poi.hours_source() == MUSEUM_REGISTER
    assert poi.hours_source_url() == CARD
    text = hours_state_text("open", MUSEUM_REGISTER, "ru")
    assert "реестр" in text
    assert "OSM" not in text
    assert hours_state_text("unknown", MUSEUM_REGISTER, "ru") == hours_state_text(
        "unknown", None, "ru"
    )


def test_a_museum_card_with_register_hours_names_the_register():
    c = unqualified_candidate()
    for lang, needle in (
        ("ru", "в реестре музеев"),
        ("kk", "мұражайлар реестрінде"),
        ("en", "museum register"),
    ):
        note = hours_notes(c, lang)[0]
        assert needle in note
        assert "09:00 - 18:00" in note
    # the card line names the register too when a day-qualified register schedule decides «open»
    open_poi = museum(
        opening_hours="Mo-Su 09:00-18:00",
        price_text=None,
        field_sources={"opening_hours": {**PRICE_SRC, "source": MUSEUM_REGISTER}},
    )
    c_open = Candidate(
        poi=open_poi, distance_m=400, walk_min=5, travel_min=5, hours_state="open", score=1.0
    )
    line = _open_fact(c_open, "ru")
    assert "реестр" in line
    assert "OSM" not in line
