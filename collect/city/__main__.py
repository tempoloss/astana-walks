"""Entry point: `uv run python -m collect.city` — writes data/city/{osm_notes,lit,construction}.json + city_stats.json.

Idempotent through the polite layer's disk cache; every record carries source_url, fetched_at, licence and
attribution «© OpenStreetMap contributors, ODbL».
"""

from __future__ import annotations

import argparse
from pathlib import Path

from collect.city import notes, roads
from collect.city.common import ATTRIBUTION
from collect.net import default_net
from collect.overpass_poi import write_json

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "city"


def collect(out_dir: Path = DATA_DIR) -> dict:
    net = default_net()
    out_dir.mkdir(parents=True, exist_ok=True)
    note_rows, notes_meta = notes.collect(net)
    road_rows, roads_meta = roads.collect(net)
    write_json(out_dir / "osm_notes.json", note_rows)
    write_json(out_dir / "lit.json", road_rows["lit"])
    write_json(out_dir / "construction.json", road_rows["construction"])
    stats = {
        "attribution": ATTRIBUTION,
        "notes": notes_meta,
        "lit": roads_meta,
        "construction": {
            "count": roads_meta["construction_count"],
            "by_kind": roads_meta["construction_by_kind"],
        },
    }
    write_json(out_dir / "city_stats.json", stats)
    return stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", default=str(DATA_DIR), help="output directory (default data/city)")
    args = parser.parse_args(argv)
    stats = collect(Path(args.out))
    n = stats["notes"]
    print(f"osm_notes.json: {n['count']} заметок ({n['by_status']}; классификация: {n['by_classification']})")
    l = stats["lit"]
    print(f"lit.json: {l['lit_count']} отрезков (yes {l['lit_by_value'].get('yes', 0)}, "
          f"no {l['lit_by_value'].get('no', 0)}); construction.json: {stats['construction']['count']}")
    print(f"Атрибуция: {ATTRIBUTION}; снапшот {l['snapshot_date']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
