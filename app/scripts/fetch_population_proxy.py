"""Population proxy for the demand simulation: OSM residential buildings of Astana, aggregated to the 500 m grid of
walks.reqlog and stored as data/population_proxy.json (cell -> relative weight; no coordinates of buildings are kept).

There is no census at 500 m resolution, so «where people live» is approximated by OpenStreetMap buildings that are
residential by tag (building = apartments | residential | dormitory | house | detached | terrace |
semidetached_house) or are a plain `building=yes` with an address (`addr:housenumber`: in Astana most blocks are
mapped that way). One query to Overpass through the polite layer of collect.net (cached, rate-limited). Weight of a
building = building:levels (default: 5 for apartments / residential / dormitory, 1 otherwise) x PER_LEVEL, with
PER_LEVEL = 5 for a block (explicit block kind or 4+ levels) and 2 for a house. These are RELATIVE weights that make a
nine-storey block count more than a house, not headcounts; the simulation only samples origins in proportion to
them. Known bias: a shop in an addressed `building=yes` counts as a dwelling too.

    uv run python scripts/fetch_population_proxy.py [--out ../data/population_proxy.json]
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, datetime
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
ROOT = APP_DIR.parent
sys.path.insert(0, str(APP_DIR))
sys.path.insert(0, str(ROOT))

from collect.net import default_net  # noqa: E402
from collect.overpass_poi import overpass, resolve_area  # noqa: E402

from walks.reqlog import grid_cell_id  # noqa: E402

DEFAULT_OUT = ROOT / "data" / "population_proxy.json"
BLOCKS = ("apartments", "residential", "dormitory")
HOUSES = ("house", "detached", "terrace", "semidetached_house")
BLOCK_LEVELS = 4  # this many levels and a building is a block even if mapped as yes
PER_LEVEL_BLOCK, PER_LEVEL_HOUSE = 5.0, 2.0
DEFAULT_BLOCK_LEVELS = 5
MAX_LEVELS = 40


def weight(tags: dict) -> float:
    """Relative number of residents of one building (see the module docstring)."""
    kind = tags.get("building")
    default = DEFAULT_BLOCK_LEVELS if kind in BLOCKS else 1
    try:
        levels = min(max(int(float(tags.get("building:levels", default))), 1), MAX_LEVELS)
    except ValueError:
        levels = default
    block = kind in BLOCKS or levels >= BLOCK_LEVELS
    return levels * (PER_LEVEL_BLOCK if block else PER_LEVEL_HOUSE)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)
    net = default_net()
    area_id, _bounds = resolve_area(net)
    kinds = "|".join((*BLOCKS, *HOUSES))
    query = (
        f"[out:json][timeout:180];\narea({area_id})->.a;\n"
        f'(way(area.a)["building"~"^({kinds})$"];way(area.a)["building"="yes"]["addr:housenumber"];);\n'
        "out center tags;\n"
    )
    data, fetched_at = overpass(net, query)
    cells: Counter[str] = Counter()
    kinds_count: Counter[str] = Counter()
    for el in data.get("elements", []):
        center, tags = el.get("center"), el.get("tags", {})
        if not center:
            continue
        cells[grid_cell_id(center["lat"], center["lon"])] += weight(tags)
        kinds_count[tags.get("building", "?")] += 1
    out = {
        "meta": {
            "what": "relative residents weight per 500 m cell from OSM residential / addressed buildings (not a headcount)",
            "source": "OpenStreetMap contributors, Overpass API; ODbL",
            "snapshot_date": datetime.fromtimestamp(fetched_at, UTC).date().isoformat(),
            "buildings": sum(kinds_count.values()),
            "buildings_by_kind": dict(kinds_count.most_common()),
            "cells": len(cells),
            "weights": {
                "levels": f"building:levels (default {DEFAULT_BLOCK_LEVELS} for apartments/residential/dormitory, else 1)",
                "per_level": {"block": PER_LEVEL_BLOCK, "house": PER_LEVEL_HOUSE},
                "block": f"explicit block kind or >= {BLOCK_LEVELS} levels",
            },
        },
        "cells": {c: round(w, 1) for c, w in sorted(cells.items())},
    }
    args.out.write_text(
        json.dumps(out, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(
        f"{args.out}: {out['meta']['buildings']} buildings in {len(cells)} cells ({out['meta']['snapshot_date']})"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
