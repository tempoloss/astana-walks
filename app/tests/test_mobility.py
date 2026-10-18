"""Unit tests of walks/mobility.py (pure layer over data/mobility/*.json): no network, fixture files only.

Run from app/:  uv run pytest tests/test_mobility.py -q
"""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from walks import mobility as mob

# ---- fixtures ---------------------------------------------------------------------------------------

_ZONE = {
    "uuid": "u1",
    "name": "3005",
    "address": "ул. Пушкина, 10/1",
    "lat": 51.159286,
    "lon": 71.466354,
    "is_residential": False,
    "polygon": [
        [51.158802, 71.46555],
        [51.159027, 71.46603],
        [51.159657, 71.46726],
        [51.159267, 71.46575],
    ],
    "prices": [{"vehicle": "car", "price": {"max": 10000}}],
    "source": {
        "url": "https://pkg-mobile-gateway-service.jquo.kz/api/v1/parkings?zoom=18",
        "licence": "none (operator gateway, reverse-engineered)",
    },
}
_STOPS = [
    {
        "osm_id": "node/1",
        "name": "Близкая",
        "lat": 51.13010,
        "lon": 71.40010,
        "gtfs_ids": ["g1"],
        "sources": [{"source": "osm", "licence": "ODbL-1.0"}],
    },
    {
        "osm_id": None,
        "name": "Средняя",
        "lat": 51.13200,
        "lon": 71.40200,
        "gtfs_ids": ["g2"],
        "sources": [{"source": "zenodo_gtfs", "licence": "CC-BY-4.0"}],
    },
    {
        "osm_id": "node/3",
        "name": "Далёкая",
        "lat": 51.14000,
        "lon": 71.41000,
        "gtfs_ids": [],
        "sources": [{"source": "osm", "licence": "ODbL-1.0"}],
    },
]
_AIRPORT = {
    "source_url": "https://nn-airport.kz/pages/bus",
    "routes": [
        {
            "route": "10",
            "direction": "города в аэропорт",
            "first_departure": "05:50",
            "last_departure": "21:23",
            "headway_min": "5-7",
        },
        {
            "route": "10",
            "direction": "аэропорта в город",
            "first_departure": "06:40",
            "last_departure": "22:24",
            "headway_min": "5-7",
        },
        {
            "route": "12",
            "direction": "города в аэропорт",
            "first_departure": "06:40",
            "last_departure": "21:20",
            "headway_min": "15",
        },
    ],
    "fare": {"by_transport_card_kzt": 90, "cash_kzt": 180},
    "buses_working_hours": {"from": "06:00", "to": "23:00"},
}


@pytest.fixture
def mobility_data(tmp_path, monkeypatch):
    d = tmp_path / "mobility"
    d.mkdir()
    (d / "parking_zones.json").write_text(json.dumps([_ZONE], ensure_ascii=False), encoding="utf-8")
    (d / "stops.json").write_text(json.dumps(_STOPS, ensure_ascii=False), encoding="utf-8")
    (d / "airport_bus.json").write_text(json.dumps(_AIRPORT, ensure_ascii=False), encoding="utf-8")
    monkeypatch.setattr(mob, "DATA_DIR", d)
    return d


# ---- parking_at -------------------------------------------------------------------------------------


def test_parking_at_inside_polygon(mobility_data, monkeypatch):
    monkeypatch.setenv("WALKS_MOBILITY_PARKING", "1")
    zone = mob.parking_at(51.1593, 71.4663, datetime(2026, 10, 17, 14, 0))
    assert zone is not None
    assert zone.name == "3005"
    assert zone.address == "ул. Пушкина, 10/1"
    assert zone.licence.startswith("none")
    assert zone.price_text() is not None
    assert "не документирована" in zone.price_text()


def test_parking_at_outside_polygon_is_none(mobility_data, monkeypatch):
    monkeypatch.setenv("WALKS_MOBILITY_PARKING", "1")
    # Khan Shatyr is far from the Pushkina zone
    assert mob.parking_at(51.133596, 71.406851, datetime(2026, 10, 17, 14, 0)) is None


def test_parking_at_off_by_default(mobility_data, monkeypatch):
    monkeypatch.delenv("WALKS_MOBILITY_PARKING", raising=False)
    assert mob.parking_at(51.1593, 71.4663, datetime(2026, 10, 17, 14, 0)) is None


# ---- nearest_stops ----------------------------------------------------------------------------------


def test_nearest_stops_ordered_with_walk_minutes(mobility_data):
    stops = mob.nearest_stops(51.13000, 71.40000, n=2)
    assert [s.name for s in stops] == ["Близкая", "Средняя"]
    first = stops[0]
    assert first.distance_m < 20
    assert first.walk_min == 1  # max(1, ...) floor
    # ~210 m straight line × 1.3 / 75 = 3.6 -> 4 minutes (haversine gives ~263 m -> 5)
    assert stops[1].walk_min == 5


def test_nearest_stops_walk_minutes_match_app_formula(mobility_data):
    stops = mob.nearest_stops(51.13000, 71.40000, n=1)
    import math

    d = mob._haversine(51.13000, 71.40000, _STOPS[0]["lat"], _STOPS[0]["lon"])
    assert stops[0].walk_min == max(1, math.ceil(d * 1.3 / 75.0))


def test_nearest_stops_empty_when_no_data(tmp_path, monkeypatch):
    monkeypatch.setattr(mob, "DATA_DIR", tmp_path)  # no stops.json here
    assert mob.nearest_stops(51.13, 71.40) == ()


# ---- airport_bus ------------------------------------------------------------------------------------


def test_airport_bus_last_departure(mobility_data):
    info = mob.airport_bus()
    assert info is not None
    assert info.last_to_airport == ("10", "21:23")  # the latest among 10 (21:23) and 12 (21:20)
    assert info.fare_card_kzt == 90
    assert info.fare_cash_kzt == 180


def test_airport_bus_next_from_airport_boundary(mobility_data):
    info = mob.airport_bus()
    assert info is not None
    # at the last departure exactly, the bus still goes; a minute later — nothing («данных нет»)
    assert info.next_from_airport(datetime(2026, 10, 17, 22, 24)) == ("10", "22:24")
    assert info.next_from_airport(datetime(2026, 10, 17, 22, 25)) is None


def test_airport_bus_none_when_no_snapshot(tmp_path, monkeypatch):
    monkeypatch.setattr(mob, "DATA_DIR", tmp_path)
    assert mob.airport_bus() is None
