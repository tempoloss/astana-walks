"""Districts, the «что с этим делать городу» actions and the demand simulation's sampling."""

from __future__ import annotations

import importlib.util
import json
import random
import sys
from collections import Counter
from pathlib import Path

import pytest

from walks.city_actions import NO_DISTRICT, hours_actions, supply_actions
from walks.demand import DemandRow
from walks.districts import district_of, load_districts
from walks.models import POI
from walks.reqlog import cell_bounds

APP_DIR = Path(__file__).resolve().parents[1]
SQUARE = [[[71.0, 51.0], [71.2, 51.0], [71.2, 51.2], [71.0, 51.2], [71.0, 51.0]]]
HOLE = [[71.05, 51.05], [71.1, 51.05], [71.1, 51.1], [71.05, 51.1], [71.05, 51.05]]


def _geojson(tmp_path: Path) -> Path:
    path = tmp_path / "d.geojson"
    path.write_text(
        json.dumps(
            {
                "type": "FeatureCollection",
                "features": [
                    {
                        "type": "Feature",
                        "properties": {"name": "Есіл ауданы", "name:ru": "район Есиль"},
                        "geometry": {"type": "Polygon", "coordinates": [*SQUARE, HOLE]},
                    },
                    {
                        "type": "Feature",
                        "properties": {"name": "Нұра ауданы"},
                        "geometry": {
                            "type": "MultiPolygon",
                            "coordinates": [
                                [[[72.0, 51.0], [72.1, 51.0], [72.1, 51.1], [72.0, 51.0]]]
                            ],
                        },
                    },
                    {"type": "Feature", "properties": {}, "geometry": None},
                ],
            }
        ),
        encoding="utf-8",
    )
    return path


def test_district_lookup_uses_russian_name_holes_and_multipolygons(tmp_path):
    ds = load_districts(_geojson(tmp_path))
    assert [d.name for d in ds] == [
        "Есиль",
        "Нұра ауданы",
    ]  # «район » stripped; the fallback is the plain name
    assert district_of(51.15, 71.15, ds) == "Есиль"
    assert district_of(51.07, 71.07, ds) is None  # inside the hole
    assert district_of(51.03, 72.09, ds) == "Нұра ауданы"
    assert district_of(52.0, 71.1, ds) is None


def test_missing_or_damaged_districts_file_gives_no_names(tmp_path):
    assert load_districts(tmp_path / "missing.geojson") == ()
    bad = tmp_path / "bad.geojson"
    bad.write_text("{not json", encoding="utf-8")
    assert load_districts(bad) == ()
    assert district_of(51.1, 71.4, ()) is None


def test_the_shipped_districts_cover_the_centre_of_astana():
    names = {d.name for d in load_districts()}
    assert {"Есиль", "Сарыарка", "Алматы", "Байконур"} <= names
    assert district_of(51.1282, 71.4304) == "Есиль"  # Baiterek


def _row(cell: str, category: str, requests: int, no_cat: int, hours: int = 0) -> DemandRow:
    return DemandRow(cell, category, "day", requests, no_cat, hours, 0)


def test_supply_actions_sum_shown_rows_per_district_and_category():
    districts = {"1_1": "Есиль", "1_2": "Есиль", "2_1": None}
    rows = [
        _row("1_1", "park_garden", 8, 6),
        _row("1_2", "park_garden", 7, 3),
        _row("2_1", "cafe", 12, 10),
        _row("1_1", "cafe", 6, 0),  # no gap: not an action
        _row("прочее", "cafe", 4, 4),  # merged row has no location
        _row("1_1", "без категории", 5, 5),
    ]
    acts = supply_actions(rows, districts.get, lambda c: c, top=5)
    assert [(a.district, a.category, a.count, a.of) for a in acts] == [
        (NO_DISTRICT, "cafe", 10, 12),
        ("Есиль", "park_garden", 9, 15),
    ]
    assert all(a.kind == "supply" for a in acts)
    assert "9 из 15" in acts[1].text


def _poi(i: int, category: str, hours: str | None, lon: float) -> POI:
    return POI(id=f"p{i}", name=f"p{i}", lat=51.1, lon=lon, category=category, opening_hours=hours)


def test_hours_actions_pick_the_worst_categories_and_the_district_with_most_missing():
    pois = (
        [_poi(i, "cafe", None, 71.1) for i in range(8)]  # district A: 8 cafes without hours
        + [_poi(10 + i, "cafe", "Mo-Su 09:00-18:00", 71.1) for i in range(2)]
        + [_poi(20 + i, "cafe", None, 71.3) for i in range(3)]  # district B
        + [
            _poi(30 + i, "restaurant", "Mo-Su 09:00-18:00", 71.1) for i in range(10)
        ]  # all have hours
        + [
            _poi(50 + i, "park_garden", None, 71.1) for i in range(20)
        ]  # hours do not matter for a park
        + [_poi(80 + i, "sport", None, 71.1) for i in range(3)]  # too few places
    )
    acts = hours_actions(pois, lambda lat, lon: "A" if lon < 71.2 else "B", lambda c: c, top=5)
    assert [a.category for a in acts] == [
        "cafe"
    ]  # restaurants all have hours, parks / small categories are left out
    (cafe,) = acts
    assert (cafe.district, cafe.count, cafe.of) == ("A", 8, 10)
    assert cafe.text.startswith("Запросить часы работы у 8 кафе в районе A")
    assert "20%" in cafe.text  # 2 of 10 have hours there


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "simulate_demand", APP_DIR / "scripts" / "simulate_demand.py"
    )
    mod = importlib.util.module_from_spec(spec)
    sys.modules["simulate_demand"] = mod
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def sim(monkeypatch):
    monkeypatch.setenv(
        "WALKS_OFFLINE", "1"
    )  # the script sets these at import; monkeypatch restores them
    monkeypatch.setenv("WALKS_REQUEST_LOG", "off")
    mod = _load_script()
    yield mod
    sys.modules.pop("simulate_demand", None)


def test_simulation_samples_origins_proportionally_to_the_population_proxy(
    sim, tmp_path, monkeypatch
):
    proxy = tmp_path / "p.json"
    heavy, light = "11374_9983", "11375_9984"
    proxy.write_text(
        json.dumps({"meta": {}, "cells": {heavy: 90.0, light: 10.0}}), encoding="utf-8"
    )
    monkeypatch.setattr(sim, "PROXY_PATH", proxy)
    rows = list(sim.requests_to_replay([], random.Random(7), 4000))
    cells = Counter()
    for _key, _text, lat, lon, _when, _w in rows:
        for cell in (heavy, light):
            s, w, n, e = cell_bounds(cell)
            if s <= lat < n and w <= lon < e:
                cells[cell] += 1
    assert sum(cells.values()) == 4000  # every origin lies inside one of the cells
    assert cells[heavy] / 4000 == pytest.approx(0.9, abs=0.03)
    assert cells[light] / 4000 == pytest.approx(0.1, abs=0.03)


def test_simulation_is_deterministic_and_follows_the_scenario_and_hour_mix(
    sim, tmp_path, monkeypatch
):
    proxy = tmp_path / "p.json"
    proxy.write_text(json.dumps({"meta": {}, "cells": {"11374_9983": 1.0}}), encoding="utf-8")
    monkeypatch.setattr(sim, "PROXY_PATH", proxy)
    first = [
        (k, t, la, lo, w)
        for k, t, la, lo, w, _ in sim.requests_to_replay([], random.Random(1), 500)
    ]
    again = [
        (k, t, la, lo, w)
        for k, t, la, lo, w, _ in sim.requests_to_replay([], random.Random(1), 500)
    ]
    other = [
        (k, t, la, lo, w)
        for k, t, la, lo, w, _ in sim.requests_to_replay([], random.Random(2), 500)
    ]
    assert first == again
    assert first != other
    kinds = Counter(k for k, *_ in first)
    assert set(kinds) <= {m[0] for m in sim.MIX}
    assert kinds["tz_walk"] > kinds["tz_night"]  # the weights of the mix are used
    night = [w for k, _t, _la, _lo, w in first if k == "tz_night"]
    assert night
    assert all(w.hour == 23 for w in night)
    assert all(8 <= w.hour <= 22 for k, _t, _la, _lo, w in first if k != "tz_night")
    assert len({w.date() for *_, w in first}) == 7  # the whole week is used
