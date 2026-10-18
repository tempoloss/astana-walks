"""Unit tests of the data-collection helpers (no network).

Run from the repository root:  uv run --with pytest python -m pytest collect/tests -q
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect import coord_quality as cq  # noqa: E402
from collect import districts, merge, overpass_poi, wiki_merge  # noqa: E402
from collect.overture_places import KIDS_PRIMARIES, TAXONOMY_MAP, classify, taxonomy_hash  # noqa: E402

# ---- Overture classification ----------------------------------------------------------------------


def test_name_rule_fires_only_in_generic_buckets():
    assert classify("sport_or_fitness_facility", [], "Батутный парк KANGO Астана") == (
        "entertainment", "kids_leisure_name", True)
    assert classify("arts_and_entertainment", [], "Fame City Entertainment Centre") == (
        "entertainment", "leisure_name", False)
    assert classify("shopping", [], "ТРЦ Asia Park") == ("mall", "mall_name", False)
    # kindergartens / classes called "Kids" are not places to take a child to
    assert classify("school", [], 'Детский Сад "Aiya KIDS"')[0] == "other"
    assert classify("education", [], "UMA Kids")[0] == "other"
    # the mall pattern is anchored: a shop *inside* a mall stays other
    assert classify("shopping", [], "Магазин одежды в ТЦ Keruen")[0] == "other"


def test_taxonomy_wins_over_name_and_kids_flag():
    assert classify("childrens_museum", [], "Музей") == ("museum_gallery", None, True)
    assert classify("indoor_playcenter", [], "X") == ("entertainment", None, True)
    assert classify("museum", [], "Батут") == ("museum_gallery", None, False)
    assert "indoor_playcenter" in KIDS_PRIMARIES and TAXONOMY_MAP["planetarium"] == "museum_gallery"


def test_taxonomy_hash_covers_name_rules(monkeypatch):
    before = taxonomy_hash()
    monkeypatch.setattr("collect.overture_places.KIDS_PRIMARIES", frozenset({"x"}))
    assert taxonomy_hash() != before


# ---- OSM rules ------------------------------------------------------------------------------------


def test_indoor_playground_is_entertainment_not_outdoor_playground():
    assert overpass_poi.match_rule({"leisure": "playground"})[0] == "kids_playground"
    assert overpass_poi.match_rule({"leisure": "playground", "indoor": "yes"})[0] == "entertainment"
    el = {"type": "way", "id": 1, "center": {"lat": 51.1, "lon": 71.4}, "tags": {"leisure": "playground",
                                                                                "indoor": "yes"}}
    rec = overpass_poi.normalize(el, "2026-10-17T00:00:00+00:00")
    assert rec["category"] == "entertainment" and rec["name"] == overpass_poi.INDOOR_PLAYGROUND_NAME
    assert "indoor=yes" in rec["tags"]


def test_extra_mode_filters_by_name_and_drops_unmapped():
    def el(tags):
        return {"type": "node", "id": 2, "lat": 51.1, "lon": 71.4, "tags": tags}

    assert overpass_poi.normalize(el({"club": "sport", "name": "Athletic Boxing"}), "t", extra=True) is None
    assert overpass_poi.normalize(el({"club": "sport", "name": "Лыжная база"}), "t", extra=True)["category"] == "sport"
    assert overpass_poi.normalize(el({"club": "chess", "name": "Chess club"}), "t", extra=True) is None
    assert overpass_poi.normalize(el({"amenity": "fountain"}), "t", extra=True) is None  # unnamed
    assert overpass_poi.normalize(el({"shop": "books", "name": "Меломан"}), "t", extra=True) is None
    book_cafe = overpass_poi.normalize(el({"shop": "books", "name": "Books & Coffee"}), "t", extra=True)
    assert book_cafe["category"] == "cafe"


def test_extra_records_never_override_first_request():
    main = {"id": "node/1", "name": "Фонтан", "lat": 51.1, "lon": 71.4}
    data = {"elements": [
        {"type": "node", "id": 1, "lat": 51.1, "lon": 71.4, "tags": {"amenity": "fountain", "name": "Фонтан"}},
        {"type": "node", "id": 9, "lat": 51.10001, "lon": 71.4, "tags": {"amenity": "fountain", "name": "Фонтан"}},
        {"type": "node", "id": 10, "lat": 51.2, "lon": 71.5, "tags": {"amenity": "fountain", "name": "Солнце"}},
    ]}
    out = overpass_poi.add_extra([main], {"node/1"}, data, "t")
    assert [p["id"] for p in out] == ["node/10"]  # node/1 is in the first request, node/9 duplicates "Фонтан"


# ---- coordinate quality ---------------------------------------------------------------------------


def ov(i: int, address: str | None, lat=51.12, lon=71.43, conf=0.9, category="cafe") -> dict:
    return {"id": f"o{i}", "lat": lat, "lon": lon, "name": f"Place {i}", "operating_status": None,
            "confidence": conf, "category": category,
            "addresses": [{"freeform": address}] if address else []}


def test_collapsed_point_needs_many_records_with_disagreeing_addresses():
    streets = ["Абая 1", "Туран 2", "Достык 3", "Кунаева 4", "Сыганак 5", "Бейбитшилик 6", "Мира 7", "Жумабаева 8"]
    placeholder = [ov(i, f"улица {s}") for i, s in enumerate(streets)]
    assert len(cq.collapsed_points(placeholder)) == 8
    mall = [ov(i, "проспект Туран 24") for i in range(12)]  # one building: one address
    assert cq.collapsed_points(mall) == {}
    small = [ov(i, f"улица {s}") for i, s in enumerate(streets[:3])]  # 3 records: a real mall + neighbours
    assert cq.collapsed_points(small) == {}


def test_street_keys_match_across_spellings_and_prefixes():
    assert cq.street_keys("Ұлы Дала даңғылы 19") & cq.street_keys("проспект Улы Дала 30/5")
    assert cq.street_keys("Дпд Казахстан, Ұлы Дала даңғылы 19") & cq.street_keys("Ұлы Дала даңғылы 19")
    assert cq.address_query("Дпд Казахстан, Ұлы Дала даңғылы 19") == "Ұлы Дала даңғылы 19"
    assert cq.address_query("Астана") == "Астана"


def test_far_from_street_needs_enough_references():
    refs = [ov(100 + i, "улица Абая 1", lat=51.13, lon=71.40 + i * 0.0005) for i in range(6)]
    osm = []
    ref = cq.street_references(osm, refs, set())
    near = ov(1, "улица Абая 5", lat=51.131, lon=71.402)
    far = ov(2, "улица Абая 7", lat=51.03, lon=71.46)
    assert cq.far_from_street(near, ref) is None
    assert cq.far_from_street(far, ref) > cq.FAR_M
    sparse = cq.street_references(osm, refs[:3], set())
    assert cq.far_from_street(far, sparse) is None  # < REF_MIN references: no verdict


# ---- Wikidata / Wikipedia merge -------------------------------------------------------------------


def rec(i: str, name: str, cat: str, lat: float, lon: float) -> dict:
    return {"id": i, "name": name, "names": {}, "name_generated": False, "lat": lat, "lon": lon, "category": cat}


def place(name: str, cat: str, lat: float, lon: float) -> dict:
    return {"qid": "Q1", "name": name, "names": {}, "lat": lat, "lon": lon, "category": cat}


def test_wiki_duplicate_prefers_same_category_and_strong_match_enriches():
    park = rec("way/1", "Сквер Музея первого президента", "park_garden", 51.1500, 71.4000)
    museum = rec("way/2", "Музей первого президента РК Н. А. Назарбаева", "museum_gallery", 51.1503, 71.4003)
    grid = merge.Grid([park, museum])
    pl = place("Музей Первого Президента Республики Казахстан", "museum_gallery", 51.1501, 71.4001)
    found, dist, score, same = wiki_merge.best_duplicate(pl, grid, merge.osm_names)
    assert found["id"] == "way/2" and same and dist < wiki_merge.SAME_CAT_M and score >= wiki_merge.SAME_CAT_SCORE
    assert wiki_merge.strong(26.0, 92.0, False) and not wiki_merge.strong(120.0, 74.0, False)


def test_wiki_place_far_from_everything_is_new():
    grid = merge.Grid([rec("way/1", "Парк защитников Отечества", "park_garden", 51.15, 71.40)])
    pl = place("Монумент защитникам Отечества", "attraction_landmark", 51.1520, 71.4030)
    dup = wiki_merge.best_duplicate(pl, grid, merge.osm_names)
    assert dup is None or not wiki_merge.strong(dup[1], dup[2], dup[3])


# ---- districts ------------------------------------------------------------------------------------


def test_rings_are_joined_and_holes_assigned():
    a = [(0, 0), (4, 0), (4, 4)]
    b = [(4, 4), (0, 4), (0, 0)]  # two fragments of the outer ring, the second one reversed
    hole = [(1, 1), (2, 1), (2, 2), (1, 2), (1, 1)]
    rings = districts.join_rings([a, b[::-1]])
    assert len(rings) == 1 and rings[0][0] == rings[0][-1]
    polys = districts.to_polygons(rings, [hole])
    assert len(polys) == 1 and len(polys[0]) == 2
    assert districts.point_in_ring((3, 1), rings[0]) and not districts.point_in_ring((5, 5), rings[0])


# ---- Overture per-record licences ------------------------------------------------------------------

_DATA = Path(__file__).resolve().parents[2] / "data"
_META = {"release": "2026-09-23.1"}


def _ov(dataset: str, license_: str | None, record_id: str = "r1") -> dict:
    source = {"dataset": dataset, "record_id": "x"}
    if license_:
        source["license"] = license_
    return {"id": record_id, "sources": [source]}


def test_overture_field_licence_is_the_contributors_not_one_theme_licence():
    meta_rec = merge.overture_fs(_ov("meta", "CDLA-Permissive-2.0"), "2026-10-16", _META)
    assert meta_rec["license"] == "CDLA-Permissive-2.0" and meta_rec["contributor"] == "meta"
    fsq = merge.overture_fs(_ov("Foursquare", "Apache-2.0", "f1"), "2026-10-16", _META)
    assert (fsq["license"], fsq["contributor"], fsq["record_id"]) == ("Apache-2.0", "Foursquare", "f1")
    assert merge.overture_fs(_ov("AllThePlaces", "CC0-1.0"), None, _META)["license"] == "CC0-1.0"


def test_overture_record_without_a_licence_is_an_error_not_a_default():
    try:
        merge.overture_fs(_ov("meta", None), "2026-10-16", _META)
    except ValueError as exc:
        assert "no source licence" in str(exc)
    else:
        raise AssertionError("a record without a licence must not get a default one")


def test_shipped_overture_fields_carry_the_licence_of_their_overture_record():
    """Every `field_sources` entry that names Overture as the source repeats the licence of that record's own
    `sources[]` (Foursquare = Apache-2.0 means data/NOTICE_overture.txt applies; AllThePlaces = CC0)."""
    places = json.loads((_DATA / "overture_places.json").read_text(encoding="utf-8"))["places"]
    upstream = {p["id"]: p for p in places}
    records = json.loads((_DATA / "poi.enriched.json").read_text(encoding="utf-8"))
    seen = set()
    for rec in records:
        for field, src in (rec.get("field_sources") or {}).items():
            if src.get("source") != "overture":
                continue
            sources = upstream[src["record_id"]]["sources"]
            assert src["license"] == " + ".join(sorted({s["license"] for s in sources})), (rec["id"], field)
            assert src["contributor"] == ", ".join(sorted({s["dataset"] for s in sources})), (rec["id"], field)
            seen.add(src["license"])
    assert seen == {"CDLA-Permissive-2.0", "Apache-2.0", "CC0-1.0"}


def test_foursquare_notice_ships_with_the_data():
    notice = (_DATA / "NOTICE_overture.txt").read_text(encoding="utf-8")
    assert "Copyright 2024 Foursquare Labs, Inc." in notice
    assert "preserve attribution to Foursquare, including preserving the full content of this NOTICE.txt file" in notice
    assert (_DATA.parent / "LICENSES" / "Apache-2.0.txt").is_file()
