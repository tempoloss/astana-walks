"""City-state layers (walks.city_layers): note signals near a POI, lit share along a route, honesty rules.

Fixtures only: no network, the data directory is a tmp_path passed through WALKS_CITY_DIR / the `path` argument.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from walks import city_layers as cl
from walks.models import POI


@pytest.fixture
def city_dir(tmp_path, monkeypatch) -> Path:
    monkeypatch.setenv("WALKS_CITY_DIR", str(tmp_path))
    return tmp_path


def _write(d: Path, name: str, rows: list[dict]) -> None:
    (d / name).write_text(json.dumps(rows, ensure_ascii=False), encoding="utf-8")


def _poi(lat: float, lon: float, name: str = "Кофейня Тест", category: str = "cafe") -> POI:
    return POI(id="p1", name=name, lat=lat, lon=lon, category=category)


# ---- signals_for_poi ------------------------------------------------------------------------------


def test_open_closure_note_near_named_poi_is_a_signal(city_dir):
    _write(
        city_dir,
        "osm_notes.json",
        [
            {
                "id": 1,
                "lat": 51.10,
                "lon": 71.41,
                "status": "open",
                "date_created": "2026-10-12",
                "classification": "closure",
                "snippet": "Говорят, Кофейня Тест закрылась",
                "url": "https://www.openstreetmap.org/note/1",
            }
        ],
    )
    sigs = cl.signals_for_poi(_poi(51.10, 71.41))
    assert len(sigs) == 1
    assert sigs[0].classification == "closure"
    assert sigs[0].id == 1
    assert "osm.org/note/1" in sigs[0].url or sigs[0].url.endswith("/note/1")


def test_note_far_or_mentioning_something_else_is_not_a_signal(city_dir):
    _write(
        city_dir,
        "osm_notes.json",
        [
            {  # 60 m north: outside the 50 m radius
                "id": 1,
                "lat": 51.10054,
                "lon": 71.41,
                "status": "open",
                "classification": "closure",
                "snippet": "Кофейня Тест закрылась",
                "url": "u1",
                "date_created": "2026-10-12",
            },
            {  # close, but about another place
                "id": 2,
                "lat": 51.10,
                "lon": 71.41,
                "status": "open",
                "classification": "closure",
                "snippet": "Аптека закрылась",
                "url": "u2",
                "date_created": "2026-10-12",
            },
            {  # closed notes never signal
                "id": 3,
                "lat": 51.10,
                "lon": 71.41,
                "status": "closed",
                "classification": "closure",
                "snippet": "Кофейня Тест закрылась",
                "url": "u3",
                "date_created": "2026-09-01",
            },
        ],
    )
    assert cl.signals_for_poi(_poi(51.10, 71.41)) == []


def test_kind_word_in_note_counts_as_a_mention(city_dir):
    _write(
        city_dir,
        "osm_notes.json",
        [
            {
                "id": 5,
                "lat": 51.10,
                "lon": 71.41,
                "status": "open",
                "classification": "closure",
                "snippet": "Кафе тут больше нет",
                "url": "u5",
                "date_created": "2026-10-12",
            }
        ],
    )
    sigs = cl.signals_for_poi(_poi(51.10, 71.41, name="Какое-то место", category="cafe"))
    assert len(sigs) == 1
    assert sigs[0].id == 5


def test_missing_data_file_means_no_signals_and_no_claims(city_dir):
    assert cl.signals_for_poi(_poi(51.10, 71.41)) == []


# ---- lit_share ------------------------------------------------------------------------------------

M_PER_DEG_LON = 69_000.0  # ~1 deg lon at lat 51.1


def _ew_route(lat: float, lon0: float, lon1: float, n: int = 12) -> list[tuple[float, float]]:
    return [(lat, lon0 + (lon1 - lon0) * i / (n - 1)) for i in range(n)]


def test_lit_share_counts_only_tagged_ways(city_dir):
    # the first ~5% of a 1.4 km route lies on a lit=yes way, the rest has no tags at all
    geom = [
        [51.10, 71.40 + i * 0.0005 / 36] for i in range(37)
    ]  # 71.4000..71.4035, a vertex every ~10 m
    _write(
        city_dir, "lit.json", [{"id": 1, "highway": "residential", "lit": "yes", "geometry": geom}]
    )
    route = _ew_route(51.10, 71.40, 71.42, 24)
    ls = cl.lit_share(route)
    assert ls is not None
    assert 0.01 < ls.lit_yes < 0.15  # a small known share…
    assert ls.unknown > 0.8  # …the rest is honestly unknown, never «не освещено»
    assert ls.lit_no == 0.0
    assert ls.known_share == pytest.approx(ls.lit_yes, abs=1e-9)
    assert (
        ls.known_share < cl.MEANINGFUL_SHARE
    )  # and below the bar the caller must not claim anything


def test_lit_no_is_a_tagged_fact_not_an_inference(city_dir):
    # the way is explicitly lit=no: the share goes to lit_no, NOT to «данных нет»
    geom = [[51.10, 71.40 + i * 0.0002] for i in range(36)]  # 71.400..71.407, a vertex every ~14 m
    _write(city_dir, "lit.json", [{"id": 1, "highway": "footway", "lit": "no", "geometry": geom}])
    ls = cl.lit_share(_ew_route(51.10, 71.40, 71.4035, 10))
    assert ls.lit_no > 0.9
    assert ls.unknown < 0.1


def test_absence_of_tags_is_never_read_as_unlit(city_dir):
    # no lit data at all: the answer is None («данных нет»), and NOTHING is ever reported as unlit
    assert cl.lit_share(_ew_route(51.10, 71.40, 71.41)) is None
    _write(
        city_dir,
        "lit.json",
        [
            {
                "id": 1,
                "highway": "residential",
                "lit": "yes",
                "geometry": [[51.50, 71.90], [51.50, 71.91]],
            }
        ],
    )  # a way in another part of the city
    ls = cl.lit_share(_ew_route(51.10, 71.40, 71.41))
    assert ls is not None
    assert ls.lit_yes == 0.0
    assert ls.lit_no == 0.0
    assert ls.unknown == 1.0
    # ...and with a real known share below the meaningfulness bar the caller is told not to claim anything
    assert ls.known_share < cl.MEANINGFUL_SHARE


def test_low_known_share_is_reported_as_not_meaningful(city_dir):
    # 100 m of known lit against a 1 km route: known_share ≈ 0.1 < MEANINGFUL_SHARE
    geom = [
        [51.10, 71.40 + i * 0.0002] for i in range(2)
    ]  # ~14 m of way, corridor covers ~2 samples
    _write(
        city_dir, "lit.json", [{"id": 1, "highway": "residential", "lit": "yes", "geometry": geom}]
    )
    ls = cl.lit_share(_ew_route(51.10, 71.40, 71.4145, 100))
    assert ls.known_share < cl.MEANINGFUL_SHARE


# ---- construction ---------------------------------------------------------------------------------


def test_construction_near_route_and_point(city_dir):
    _write(
        city_dir,
        "construction.json",
        [
            {
                "id": 9,
                "highway": "construction",
                "construction": "road",
                "name": "Новая улица",
                "geometry": [[51.10, 71.405], [51.10, 71.406]],
            },
            {
                "id": 10,
                "highway": "construction",
                "construction": None,
                "name": None,
                "geometry": [[51.30, 71.60], [51.30, 71.61]],
            },  # far away
        ],
    )
    route = _ew_route(51.10, 71.40, 71.41)
    ids = {w["id"] for w in cl.construction_near_route(route)}
    assert ids == {9}
    assert {w["id"] for w in cl.construction_near(51.10, 71.4055)} == {9}
    assert (
        cl.construction_near(51.10, 71.40) == []
    )  # 50 m default radius: 71.405 is ~35 m east of 71.40? no:
    # 0.005 deg lon at lat 51.1 ≈ 345 m -> outside the 50 m radius


def test_construction_empty_data_is_not_a_fact_about_the_city(city_dir):
    assert cl.construction_near_route(_ew_route(51.10, 71.40, 71.41)) == []
    assert cl.construction_near(51.10, 71.41) == []


# ---- city_summary ---------------------------------------------------------------------------------


def test_city_summary_counts_and_lists_open_notes(city_dir):
    _write(
        city_dir,
        "osm_notes.json",
        [
            {
                "id": 1,
                "lat": 51.1,
                "lon": 71.4,
                "status": "open",
                "classification": "closure",
                "snippet": "закрыта",
                "url": "u1",
                "date_created": "2026-10-12",
                "fetched_at": "2026-10-17T06:00:00+00:00",
            },
            {
                "id": 2,
                "lat": 51.1,
                "lon": 71.4,
                "status": "closed",
                "classification": "new_place",
                "snippet": "открылось",
                "url": "u2",
                "date_created": "2026-10-01",
                "fetched_at": "2026-10-17T06:00:00+00:00",
            },
        ],
    )
    _write(
        city_dir,
        "lit.json",
        [
            {
                "id": 3,
                "lit": "yes",
                "highway": "footway",
                "geometry": [[51.1, 71.4], [51.1, 71.41]],
            },
            {"id": 4, "lit": "no", "highway": "path", "geometry": [[51.2, 71.4], [51.2, 71.41]]},
        ],
    )
    _write(
        city_dir,
        "construction.json",
        [
            {"id": 5, "highway": "construction", "geometry": [[51.1, 71.4], [51.1, 71.41]]},
        ],
    )
    s = cl.city_summary()
    assert s is not None
    assert s.notes_open == 1
    assert s.notes_total == 2
    assert s.lit_yes == 1
    assert s.lit_no == 1
    assert s.construction == 1
    assert s.by_classification == {"closure": 1, "new_place": 1}
    assert s.snapshot_date == "2026-10-17"
    assert s.attribution == "© OpenStreetMap contributors, ODbL"
    assert len(s.open_notes) == 1
    assert s.open_notes[0]["id"] == 1
    d = s.as_dict()
    assert d["notes_open"] == 1
    assert isinstance(json.dumps(d, ensure_ascii=False), str)


def test_city_summary_none_without_data(city_dir):
    assert cl.city_summary() is None
