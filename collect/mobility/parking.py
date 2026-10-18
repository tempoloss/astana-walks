"""Paid parking zones of Astana from the ЦОДД UIMS payment gateway (pkg-mobile-gateway-service.jquo.kz).

⚠️ LEGAL STATUS (Main's round-4 review of e963cfd): the gateway has NO licence — the portal's offer is
an SPA stub, and the JSON endpoints are reverse-engineered from the portal's own JS. Same risk class as
avtobys before a contract. This collector is therefore strictly isolated:

* the output goes to its own file `data/mobility/parking_zones.json` marked
  `license: "none (operator gateway, reverse-engineered)"`;
* the whole feature is OFF by default: nothing runs unless `WALKS_MOBILITY_PARKING=1` is set
  (`uv run python -m collect.mobility` skips this module without the flag);
* removing the feature = deleting this file (nothing else imports it, see walks/mobility.py docstring).

What it stores: zone uuid, name, address, polygon/centre, vehicle-type prices and the ordered
tariff_rule_groups (raw integers — the unit is not documented; the portal's public tariffs page shows
«тариф „Простой“ 500 ₸/час», «Дифференцированный» 500 ₸ днём / 300 ₸ ночью), plus free/total spaces.
Attribution: «ЦОДД Астаны / UIMS». ≤1 req/s through the shared polite layer.

Run from the repo root:  WALKS_MOBILITY_PARKING=1 uv run python -m collect.mobility.parking
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

try:
    from collect.net import default_net
except ImportError:  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from collect.net import default_net

from collect.mobility.common import OUT_DIR, in_astana, now_iso, write_json

GATEWAY = "https://pkg-mobile-gateway-service.jquo.kz/api/v1"
PARKINGS_URL = f"{GATEWAY}/parkings?zoom=18"
LICENCE = "none (operator gateway, reverse-engineered)"
ATTRIBUTION = "ЦОДД Астаны / UIMS"
ENABLE_ENV = "WALKS_MOBILITY_PARKING"

VEHICLE_LABELS = {
    "VEHICLE_TYPE_CAR": "car",
    "VEHICLE_TYPE_TRUCK": "truck",
    "VEHICLE_TYPE_MOTORCYCLE": "motorcycle",
    "VEHICLE_TYPE_BUS": "bus",
}


def enabled() -> bool:
    return os.environ.get(ENABLE_ENV, "").strip() == "1"


def _normalize_zone(p: dict, fetched_at: str) -> dict | None:
    loc = p.get("location") or {}
    poly = ((loc.get("polygon") or {}).get("coordinates")) or []
    center = p.get("center") or {}
    lat, lon = center.get("latitude"), center.get("longitude")
    if lat is None or not in_astana(lat, lon):
        return None
    zone = p.get("zone") or {}
    prices = [
        {
            "vehicle": VEHICLE_LABELS.get(
                pr.get("vehicle_type", ""), pr.get("vehicle_type", "")
            ),
            "price": pr.get("price"),
        }
        for pr in zone.get("prices", [])
    ]
    groups = [
        {
            "rules": [
                {
                    "vehicle": VEHICLE_LABELS.get(
                        r.get("vehicle_type", ""), r.get("vehicle_type", "")
                    ),
                    "price": r.get("price"),
                }
                for r in g.get("rules", [])
            ]
        }
        for g in zone.get("tariff_rule_groups", [])
    ]
    return {
        "uuid": p.get("uuid"),
        "name": p.get("name"),
        "address": (p.get("address") or {}).get("house"),
        "description": p.get("description"),
        "is_residential": bool(p.get("is_residential")),
        "status": p.get("status"),
        "spaces_total": p.get("spaces_total"),
        "spaces_free": p.get("spaces_free"),
        "lat": lat,
        "lon": lon,
        "polygon": [[c.get("latitude"), c.get("longitude")] for c in poly] or None,
        "location_type": loc.get("type"),
        "prices": prices,
        "tariff_rule_groups": groups,
        "source": {
            "source": "ЦОДД Астаны / UIMS (pkg-mobile-gateway-service.jquo.kz)",
            "url": PARKINGS_URL,
            "licence": LICENCE,
            "fetched_at": fetched_at,
        },
    }


def collect(net) -> tuple[list[dict], dict]:
    resp = net.get(PARKINGS_URL, timeout=60)
    raw = resp.json().get("parkings", [])
    fetched_at = now_iso()
    zones = [z for p in raw if (z := _normalize_zone(p, fetched_at))]
    zones.sort(key=lambda z: z["uuid"] or "")
    stats = {
        "parkings_raw": len(raw),
        "zones_stored": len(zones),
        "with_polygon": sum(1 for z in zones if z["polygon"]),
        "residential": sum(1 for z in zones if z["is_residential"]),
        "licence": LICENCE,
        "attribution": ATTRIBUTION,
        "enabled_by": ENABLE_ENV,
        "fetched_at": fetched_at,
        "notes": (
            "Цены — целые числа в единицах шлюза (единица не документирована; публичная страница "
            "тарифов портала pkg-payment.jquo.kz называет «Простой» 500 ₸/час и "
            "«Дифференцированный» 500 ₸ день / 300 ₸ ночной час). tariff_rule_groups — упорядоченный "
            "список периодов без времён (времена периодов шлюз не отдаёт без авторизации)."
        ),
    }
    write_json(OUT_DIR / "parking_zones.json", zones)
    write_json(OUT_DIR / "parking_zones_stats.json", stats)
    return zones, stats


def main(argv: list[str] | None = None) -> int:
    if not enabled():
        print(
            f"[parking] выключено: шлюз ЦОДД без лицензии (reverse-engineered). "
            f"Задайте {ENABLE_ENV}=1, чтобы собрать снимок в изолированный файл."
        )
        return 0
    _, stats = collect(default_net())
    print(
        f"[parking] raw={stats['parkings_raw']} stored={stats['zones_stored']} "
        f"(polygons={stats['with_polygon']}, residential={stats['residential']}) "
        f"-> {OUT_DIR / 'parking_zones.json'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
