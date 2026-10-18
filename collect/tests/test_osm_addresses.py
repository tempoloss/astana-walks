"""The address collector (collect/osm_addresses.py) on a small Overpass answer: no network.

Run from the repository root:  uv run python -m pytest collect/tests/test_osm_addresses.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect import osm_addresses as oa  # noqa: E402

ROAD = {"type": "way", "id": 1, "center": {"lat": 51.10, "lon": 71.43}, "tags": {"highway": "primary", "name": "Мәңгілік Ел даңғылы", "name:ru": "проспект Мангилик Ел", "name:en": "Mangilik El Avenue"}}
ROAD_FAR = {"type": "way", "id": 2, "center": {"lat": 51.12, "lon": 71.45}, "tags": {"highway": "primary", "name": "Мәңгілік Ел даңғылы"}}
ROAD_OUT = {"type": "way", "id": 3, "center": {"lat": 55.7, "lon": 37.6}, "tags": {"highway": "primary", "name": "Тверская"}}


def house(i: int, number: str, street: str, lat: float = 51.10, lon: float = 71.43) -> dict:
    return {"type": "node", "id": 100 + i, "lat": lat, "lon": lon, "tags": {"addr:housenumber": number, "addr:street": street}}


def test_the_query_asks_for_houses_and_named_roads_of_the_area():
    q = oa.build_query(3603087155)
    assert "area(3603087155)" in q
    assert '["addr:housenumber"]["addr:street"]' in q
    assert '["highway"' in q
    assert q.count("out center tags;") == 1


def test_spellings_of_one_street_are_one_street():
    streets, houses = oa.reduce([ROAD, ROAD_FAR, house(1, "55", "проспект Мангилик Ел"), house(2, "55/22", "Mangilik El Avenue")])
    assert len(streets) == 1
    assert set(streets[0]["names"]) == {"Мәңгілік Ел даңғылы", "проспект Мангилик Ел", "Mangilik El Avenue"}
    assert streets[0]["houses"] == 2
    assert [h[1] for h in houses] == ["55", "55/22"]
    assert {h[0] for h in houses} == {streets[0]["id"]}


def test_the_position_of_a_street_lies_on_it():
    streets, _ = oa.reduce([ROAD, ROAD_FAR, house(1, "1", "Мәңгілік Ел даңғылы", 51.11, 71.44)])
    assert (streets[0]["lat"], streets[0]["lon"]) in {(51.1, 71.43), (51.12, 71.45), (51.11, 71.44)}


def test_outside_elements_and_houses_without_a_street_are_dropped():
    bare = {"type": "node", "id": 7, "lat": 51.1, "lon": 71.4, "tags": {"addr:housenumber": "9"}}
    streets, houses = oa.reduce([ROAD_OUT, bare, house(1, "3", "Тверская", 55.7, 37.6)])
    assert streets == []
    assert houses == []


def test_the_same_number_twice_on_a_street_is_one_house():
    _, houses = oa.reduce([ROAD, house(1, "5А", "проспект Мангилик Ел"), house(2, "5а", "проспект Мангилик Ел", 51.101, 71.431)])
    assert len(houses) == 1


def test_build_carries_the_licence_and_the_counts():
    out = oa.build({"elements": [ROAD, house(1, "55", "проспект Мангилик Ел")]}, "2026-10-18T17:06:50+00:00", 3603087155)
    assert out["license"] == "ODbL 1.0"
    assert out["attribution"] == "© OpenStreetMap contributors"
    assert out["counts"] == {"elements": 2, "streets": 1, "houses": 1}
    assert out["retrieved_at"] == "2026-10-18T17:06:50+00:00"
