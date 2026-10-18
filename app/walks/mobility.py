"""Getting there and parking, as a pure read-only API over `data/mobility/*.json` (SOURCES.md §14.2).

Three layers, each designed to add at most one short line to a card, only when relevant:

* `parking_at(lat, lon, when)` — the paid zone holding the point (ЦОДД UIMS gateway, **no licence**,
  reverse-engineered private JSON; the whole layer is OFF unless `WALKS_MOBILITY_PARKING=1` and the
  file exists — removable by deleting collect/mobility/parking.py). `when` is accepted for the future
  per-period tariffs; the gateway exposes no period times, so the answer is the zone's vehicle price
  set plus an honest note, not a claim about the price right now.
* `nearest_stops(lat, lon, n=2)` — bus stops (Zenodo GTFS CC BY 4.0 + OSM ODbL, merged), walk minutes
  = straight line × 1.3 at 75 m/min, exactly like walks.walking straight legs.
* `airport_bus(now)` — the airport's own bus facts: for «турист, 2 часа до вылета» the next/last
  city→airport departures and the fare.

Absence of data is never a fact about the world: a missing file or an empty radius yields None / ()
and the caller says «данных нет», not «нет».
"""

from __future__ import annotations

import json
import math
import os
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "mobility"
PARKING_ENABLE_ENV = "WALKS_MOBILITY_PARKING"
FALLBACK_DETOUR = 1.3  # = walking.FALLBACK_DETOUR
WALK_M_PER_MIN = 75.0  # = walking.WALK_M_PER_MIN (4.5 km/h)

VEHICLE_RU = {
    "car": "легковые",
    "truck": "тягачи",
    "motorcycle": "мототехника",
    "bus": "автобусы",
}


def _load(name: str):
    try:
        return json.loads((DATA_DIR / name).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


@dataclass(frozen=True)
class ParkingZone:
    uuid: str
    name: str
    address: str | None
    lat: float
    lon: float
    is_residential: bool
    polygon: list[list[float]] | None
    prices: list[dict]  # [{vehicle, price}]
    source_url: str
    licence: str

    def contains(self, lat: float, lon: float) -> bool:
        if not self.polygon or len(self.polygon) < 3:
            return False
        return _in_ring(
            lat, lon, [(p[1], p[0]) for p in self.polygon]
        )  # stored (lat, lon) -> ring (lon, lat)

    def price_text(self) -> str | None:
        car = next((p for p in self.prices if p["vehicle"] == "car"), None)
        if car is None:
            return None
        price = car["price"]
        if isinstance(price, dict):  # {min?, max} in the gateway's undocumented unit
            low = price.get("min", price.get("max", "?"))
            return f"цена {low}–{price.get('max', '?')} (единица шлюза, не документирована)"
        return f"цена {price} (единица шлюза, не документирована)"


@dataclass(frozen=True)
class BusStop:
    name: str | None
    lat: float
    lon: float
    distance_m: int
    walk_min: int
    sources: list[dict]


@dataclass(frozen=True)
class AirportBusInfo:
    fare_card_kzt: int
    fare_cash_kzt: int
    working_hours: tuple[str, str] | None  # ("06:00", "23:00")
    routes: tuple[dict, ...]  # [{route, direction, first_departure, last_departure, headway_min}]
    last_to_airport: tuple[str, str] | None  # (route, HH:MM)
    source_url: str
    fetched_at: str = ""  # the day the page was read (YYYY-MM-DD)

    def next_from_airport(self, now: datetime) -> tuple[str, str] | None:
        """The route whose airport→city window is still running at `now` (local), latest last: (route, last)."""
        hhmm = now.strftime("%H:%M")
        running = [
            r
            for r in self.routes
            if r["direction"] == "аэропорта в город" and r["last_departure"] >= hhmm
        ]
        if not running:
            return None
        best = min(running, key=lambda r: r["last_departure"])
        return best["route"], best["last_departure"]


def _in_ring(lat: float, lon: float, ring: list[tuple[float, float]]) -> bool:
    """Even-odd rule, the same as walks.districts._in_ring."""
    inside = False
    j = len(ring) - 1
    for i, (xi, yi) in enumerate(ring):
        xj, yj = ring[j]
        if (yi > lat) != (yj > lat) and lon < (xj - xi) * (lat - yi) / (yj - yi) + xi:
            inside = not inside
        j = i
    return inside


def parking_at(lat: float, lon: float, when: datetime | None = None) -> ParkingZone | None:
    """The paid zone whose polygon holds the point, or None (no zone in the data — NOT «parking is free»)."""
    if os.environ.get(PARKING_ENABLE_ENV, "").strip() != "1":
        return None  # the layer is off by default: the gateway has no licence
    zones = _load("parking_zones.json")
    if not zones:
        return None
    for z in zones:
        poly = z.get("polygon")
        if not poly:
            continue
        if _in_ring(lat, lon, [(p[1], p[0]) for p in poly]):
            src = z.get("source") or {}
            return ParkingZone(
                uuid=z.get("uuid") or "",
                name=z.get("name") or "",
                address=z.get("address"),
                lat=z["lat"],
                lon=z["lon"],
                is_residential=bool(z.get("is_residential")),
                polygon=poly,
                prices=z.get("prices", []),
                source_url=src.get("url", ""),
                licence=src.get("licence", parking_licence()),
            )
    return None


def parking_licence() -> str:
    return "none (operator gateway, reverse-engineered)"


def nearest_stops(lat: float, lon: float, n: int = 2) -> tuple[BusStop, ...]:
    """The n nearest bus stops with straight-line×1.3 walk minutes; () when the file is missing."""
    stops = _load("stops.json")
    if not stops:
        return ()
    ranked = sorted(
        stops,
        key=lambda s: (s["lat"] - lat) ** 2 + (s["lon"] - lon) ** 2,
    )
    out: list[BusStop] = []
    for s in ranked[: max(1, n)]:
        d = _haversine(lat, lon, s["lat"], s["lon"])
        out.append(
            BusStop(
                name=s.get("name"),
                lat=s["lat"],
                lon=s["lon"],
                distance_m=round(d),
                walk_min=max(1, math.ceil(d * FALLBACK_DETOUR / WALK_M_PER_MIN)),
                sources=s.get("sources", []),
            )
        )
    return tuple(out)


def airport_bus(now: datetime | None = None) -> AirportBusInfo | None:
    """Airport bus facts from nn-airport.kz; None when the snapshot file is absent («данных нет»)."""
    doc = _load("airport_bus.json")
    if not doc:
        return None
    routes = tuple(doc.get("routes", []))
    last_to_airport = None
    candidates = [r for r in routes if r.get("direction") == "города в аэропорт"]
    if candidates:
        best = max(candidates, key=lambda r: r["last_departure"])
        last_to_airport = (best["route"], best["last_departure"])
    hours = doc.get("buses_working_hours")
    fare = doc.get("fare") or {}
    return AirportBusInfo(
        fare_card_kzt=fare.get("by_transport_card_kzt", 0),
        fare_cash_kzt=fare.get("cash_kzt", 0),
        working_hours=(hours["from"], hours["to"]) if hours else None,
        routes=routes,
        last_to_airport=last_to_airport,
        source_url=doc.get("source_url", "https://nn-airport.kz/pages/bus"),
        fetched_at=str(doc.get("fetched_at", ""))[:10],
    )


def _haversine(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371008.8
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dphi = p2 - p1
    dl = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
