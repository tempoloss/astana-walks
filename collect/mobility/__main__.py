"""Entry point of the mobility collectors: `uv run python -m collect.mobility`.

Runs the stop merge and the airport-bus facts always; the ЦОДД parking snapshot only with
`WALKS_MOBILITY_PARKING=1` (no licence — see collect/mobility/parking.py). Prints one stats line
per source and a JSON summary.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

try:
    from collect.net import default_net
except ImportError:  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from collect.net import default_net

from collect.mobility import airport_bus, parking, stops


def main(argv: list[str] | None = None) -> int:
    net = default_net()
    summary: dict[str, dict] = {}

    _, stops_stats = stops.collect(net)
    summary["stops"] = {
        k: v for k, v in stops_stats.items() if k not in ("attribution", "read_me_note")
    }
    routes_doc = airport_bus.collect(net)
    summary["airport_bus"] = {
        "routes": len(routes_doc["routes"]),
        "fare_by_card_kzt": routes_doc["fare"]["by_transport_card_kzt"],
        "last_to_airport": airport_bus.last_departure_to_airport(routes_doc),
    }

    if parking.enabled():
        _, parking_stats = parking.collect(net)
        summary["parking"] = {
            "zones_stored": parking_stats["zones_stored"],
            "with_polygon": parking_stats["with_polygon"],
            "licence": parking.LICENCE,
        }
    else:
        print(
            f"[parking] пропущено: сбор с шлюза ЦОДД выключен ({parking.ENABLE_ENV}!=1); "
            "шлюз без лицензии — фича по умолчанию снята."
        )

    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
