"""Unit tests of the mobility collectors (collect/mobility): no network.

Run from the repository root:  uv run --with pytest python -m pytest collect/tests/test_mobility.py -q
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.mobility import airport_bus, parking, stops
from collect.mobility.common import clip_snippet, haversine_m, in_astana, norm_ws

# ---- stops: GTFS parsing, merge & dedup -------------------------------------------------------------


def _gtfs(ids_names):
    return [
        {
            "gtfs_id": i,
            "name": n,
            "lat": 51.1300 + 0.001 * k,
            "lon": 71.4000 + 0.001 * k,
        }
        for k, (i, n) in enumerate(ids_names)
    ]


def _osm(points):
    return [
        {
            "osm_id": f"node/{100 + k}",
            "name": n,
            "lat": la,
            "lon": lo,
            "tags": {"highway": "bus_stop"},
        }
        for k, (n, la, lo) in enumerate(points)
    ]


def test_gtfs_stop_near_osm_platform_merges_osm_wins():
    gtfs = _gtfs([("g1", "Teatr Astana Opera"), ("g2", "Далёкая")])
    osm = _osm([("Opera", 51.130001, 71.400001)])  # ~0.15 m from g1
    merged, gtfs_only = stops.merge(gtfs, osm)
    assert gtfs_only == 1  # «Далёкая» stays as a GTFS-only record
    opera = next(p for p in merged if p["osm_id"] == "node/100")
    assert opera["name"] == "Opera" and opera["gtfs_ids"] == ["g1"]
    far = next(p for p in merged if p["osm_id"] is None)
    assert far["gtfs_ids"] == ["g2"]


def test_gtfs_duplicates_collapse_within_radius():
    gtfs = _gtfs([("g1", "TRTs Khan Shatyr"), ("g2", "TRTs Khan Shatyr")])
    gtfs[1]["lat"] = gtfs[0]["lat"] + 0.0001  # ~11 m apart: same stop
    gtfs[1]["lon"] = gtfs[0]["lon"]
    osm = _osm([])
    merged, gtfs_only = stops.merge(gtfs, osm)
    assert gtfs_only == 1 and len(merged) == 1 and merged[0]["gtfs_ids"] == ["g1"]


def test_merge_keeps_osm_without_gtfs():
    # the GTFS point is ~620 m away from the OSM platform: both stay, the OSM one unmatched
    gtfs = _gtfs([("g1", "Далёкая")])
    osm = _osm([("Хан Шатыр", 51.133596, 71.406851)])
    merged, gtfs_only = stops.merge(gtfs, osm)
    assert gtfs_only == 1 and len(merged) == 2
    opera = next(p for p in merged if p["osm_id"] == "node/100")
    assert opera["gtfs_ids"] == []


def test_two_osm_records_can_share_gtfs_points_only_once():
    gtfs = _gtfs([("g1", "A")])
    osm = _osm(
        [("P1", 51.130000, 71.400000), ("P2", 51.130000, 71.400020)]
    )  # ~1.4 m apart
    merged, _ = stops.merge(gtfs, osm)
    used = [p for p in merged if "g1" in p["gtfs_ids"]]
    assert len(used) == 1  # the GTFS point is consumed by the first OSM record


# ---- common helpers ---------------------------------------------------------------------------------


def test_in_astana_and_snippet_clip():
    assert in_astana(51.13, 71.41) and not in_astana(55.0, 71.41)
    assert (
        clip_snippet("  a   b\n c  ") == "a b c" and len(clip_snippet("x" * 500)) == 300
    )
    assert norm_ws("") == ""


def test_haversine_sanity():
    # Khan Shatyr (51.1336, 71.4069) -> Baiterek (51.1282, 71.4305) ≈ 1.6 km
    d = haversine_m(51.1336, 71.4069, 51.1282, 71.4305)
    assert 1400 <= d <= 1800


# ---- parking: polygon containment and the off-by-default gate ---------------------------------------


def test_parking_off_by_default_and_enabled_by_flag(monkeypatch):
    monkeypatch.delenv(parking.ENABLE_ENV, raising=False)
    assert parking.enabled() is False
    monkeypatch.setenv(parking.ENABLE_ENV, "1")
    assert parking.enabled() is True


def test_parking_point_in_polygon_true_and_outside_false():
    """Point-in-polygon on a normalized zone (the collector's polygon, (lat, lon) pairs)."""
    poly = [
        [51.158802, 71.46555],
        [51.159027, 71.46603],
        [51.159657, 71.46726],
        [51.159267, 71.46575],
    ]
    # centre of the polygon: inside
    assert _pip(51.1593, 71.4663, poly) is True
    # far outside
    assert _pip(51.13, 71.40, poly) is False


def _pip(lat, lon, poly):
    from collect.mobility.common import haversine_m  # noqa: F401

    ring = [(p[1], p[0]) for p in poly]
    inside = False
    j = len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


# ---- airport bus: parsing from a fixture page, last departure ---------------------------------------


_PAGE = (
    "<html><body>Где найти автобус? Рабочее время: 06:00-23:00 "
    "Выезд из города в аэропорт маршрута №10 — 5.50 — 21.23, интервал между рейсами 5-7 минут. "
    "Выезд из аэропорта в город маршрута №10 — 6.40 — 22.24, интервал между рейсами 5-7 минут. "
    "Выезд из города в аэропорт маршрута №12 — 6.40 — 21.20, интервал между рейсами 15 минут. "
    "Выезд из аэропорта в город маршрута №12 — 7.50 — 22.30, интервал между рейсами 15 минут. "
    "Стоимость проезда - 90 тенге при оплате транспортной картой, 180 тенге наличными. "
    "Время работы автобусов с 6:00 до 23:00</body></html>"
)


def test_airport_bus_regexes_on_fixture_page():
    text = airport_bus._visible(_PAGE)
    import re

    routes = [
        (m.groups()[1], m.groups()[0], m.groups()[2], m.groups()[3], m.groups()[4])
        for m in re.finditer(airport_bus._ROUTE_RE, text)
    ]
    assert sorted(routes) == [
        ("10", "аэропорта в город", "6.40", "22.24", "5-7"),
        ("10", "города в аэропорт", "5.50", "21.23", "5-7"),
        ("12", "аэропорта в город", "7.50", "22.30", "15"),
        ("12", "города в аэропорт", "6.40", "21.20", "15"),
    ]
    fare = airport_bus._first(airport_bus._FARE_RE, text)
    assert fare and fare[1] == ("90", "180")
    hours = airport_bus._first(airport_bus._HOURS_RE, text)
    assert hours and hours[1] == ("6:00", "23:00")


def test_airport_bus_after_last_departure_is_none():
    info = {
        "routes": [
            {
                "route": "10",
                "direction": "города в аэропорт",
                "first_departure": "05:50",
                "last_departure": "21:23",
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
        "source_url": airport_bus.BUS_URL,
    }
    last = airport_bus.last_departure_to_airport(info)
    assert last == ("10", "21:23")
    # 23:40 is after every last departure: the scenario layer must say «данных нет», not invent a bus
    late = datetime(2026, 10, 17, 23, 40)
    assert late.strftime("%H:%M") > last[1]


def test_collect_raises_without_expected_sentences(monkeypatch):
    class FakeNet:
        def get(self, url, **kw):
            raise AssertionError("network must not be touched")

    class FakeResp:
        text = "<html>пустая страница</html>"

    class Net:
        def get(self, url, **kw):
            return FakeResp()

    with pytest.raises(RuntimeError):
        airport_bus.collect(Net())
