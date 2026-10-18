"""Bus stops of Astana, merged from two licences we may store:

* Zenodo record 15769359 («From Raw GPS to GTFS: A Real-World Open Dataset for Bus Travel Time
  Prediction», CC BY 4.0, Mansurova, Mussina, Aubakirov, Nugumanova, Yedilkhan, Data 10(8):119, 2025)
  — `gtfs_data.zip` -> `stops.txt`, 173 stops with coordinates. The record's READ-ME note (quoted in
  SOURCES.md §14.2) says the GTFS timings are reconstructed from GPS: we store the STOPS only, never
  the stop_times. Attribution text is kept verbatim in the output.
* OpenStreetMap `highway=bus_stop` / `public_transport=platform` (ODbL 1.0) via the Overpass mirror
  `maps.mail.ru` (overpass-api.de and kumi are unreachable from this host).

Merge rule: a GTFS stop within MATCH_RADIUS_M of an OSM platform is one stop — the OSM record wins
(it carries names/literal tags), the GTFS id is kept as `gtfs_id` (CC BY provenance stays in
`sources[]`). Outputs data/mobility/stops.json + stops_stats.json.

Run from the repo root:  uv run python -m collect.mobility.stops
"""

from __future__ import annotations

import argparse
import csv
import io
import sys
import zipfile
from datetime import UTC, datetime
from pathlib import Path

try:
    from collect.net import default_net
except ImportError:  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
    from collect.net import default_net

from collect.mobility.common import (
    OUT_DIR,
    haversine_m,
    in_astana,
    now_iso,
    write_json,
)

ZENODO_RECORD = "https://zenodo.org/records/15769359"
ZENODO_ZIP_URL = "https://zenodo.org/api/records/15769359/files/gtfs_data.zip/content"
ATTRIBUTION = (
    "GTFS stops: Mansurova, Aigerim; Mussina, Aigerim; Aubakirov, Sanzhar; Nugumanova, Aliya; "
    "Yedilkhan, Didar (2025): «From Raw GPS to GTFS: A Real-World Open Dataset for Bus Travel Time "
    "Prediction», Zenodo, https://zenodo.org/records/15769359, CC BY 4.0 "
    "(doi:10.5281/zenodo.15769359; journal version doi:10.3390/data10080119). "
    "OSM platforms: © OpenStreetMap contributors, ODbL 1.0, https://www.openstreetmap.org/copyright."
)
# The dataset's own READ-ME note, quoted (SOURCES.md §14.2): timings are reconstructed, stops only.
READ_ME_NOTE = (
    "Записи остановок (stops.txt) используются как есть; расписания GTFS этого датасета — "
    "реконструкция из GPS-треков 2024 года, для текущего расписания они не годятся, поэтому хранятся "
    "только остановки."
)

LICENCE_GTFS = "CC-BY-4.0"
LICENCE_OSM = "ODbL-1.0"
MATCH_RADIUS_M = 40.0  # same stop on the two maps is rarely farther apart

GTFS_CACHE = (
    Path(__file__).resolve().parents[2] / ".local" / "mobility" / "gtfs_data.zip"
)

OVERPASS_MIRROR = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"


def stops_query() -> str:
    return (
        "[out:json][timeout:120];\n"
        "area(1520)->.a;\n"  # Q1520 = Astana
        "(\n"
        '  nwr(area.a)["highway"="bus_stop"];\n'
        '  nwr(area.a)["public_transport"="platform"]["bus"="yes"];\n'
        '  nwr(area.a)["public_transport"="platform"]["highway"="bus_stop"];\n'
        ");\n"
        "out center tags;\n"
    )


def _overpass(net, query: str) -> tuple[dict, float]:
    from collect.overpass_poi import overpass

    return overpass(
        net, query
    )  # the shared mirror-failover helper (ENDPOINTS end with mail.ru)


def _gtfs_stops() -> tuple[list[dict], str]:
    """Read stops.txt from the cached zip (download once); return (records, fetched_at)."""
    if not GTFS_CACHE.exists():
        GTFS_CACHE.parent.mkdir(parents=True, exist_ok=True)
        import httpx

        with httpx.stream(
            "GET",
            ZENODO_ZIP_URL,
            timeout=180,
            follow_redirects=True,
            headers={"User-Agent": "astana-walks/0.1 (hackathon; an8kk.sa@gmail.com)"},
        ) as r:
            r.raise_for_status()
            with GTFS_CACHE.open("wb") as f:
                for chunk in r.iter_bytes(1 << 16):
                    f.write(chunk)
    fetched_at = (
        datetime.fromtimestamp(GTFS_CACHE.stat().st_mtime)
        .astimezone()
        .isoformat(timespec="seconds")
    )
    with zipfile.ZipFile(GTFS_CACHE) as z:
        raw = z.read("gtfs_data/stops.txt").decode(
            "cp1251"
        )  # the file is Windows-1251, not UTF-8
    rows = list(csv.DictReader(io.StringIO(raw), delimiter="\t"))
    out = []
    for r in rows:
        lat, lon = float(r["stop_lat"]), float(r["stop_lon"])
        if not in_astana(lat, lon):
            continue
        out.append(
            {
                "gtfs_id": r["stop_id"],
                "name": r["stop_name"].strip(),
                "lat": lat,
                "lon": lon,
            }
        )
    return out, fetched_at


def _osm_stops(net) -> tuple[list[dict], str]:
    data, fetched = _overpass(net, stops_query())
    fetched_at = datetime.fromtimestamp(fetched, UTC).replace(microsecond=0).isoformat()
    out = []
    for el in data.get("elements", []):
        tags = el.get("tags", {})
        if "center" in el:
            lat, lon = el["center"]["lat"], el["center"]["lon"]
        else:  # a node
            lat, lon = el["lat"], el["lon"]
        if not in_astana(lat, lon):
            continue
        name = tags.get("name") or tags.get("name:ru")
        out.append(
            {
                "osm_id": f"{el['type']}/{el['id']}",
                "name": name,
                "lat": lat,
                "lon": lon,
                "tags": {
                    k: v
                    for k, v in tags.items()
                    if k in ("highway", "public_transport", "bus", "shelter")
                },
            }
        )
    return out, fetched_at


def merge(gtfs: list[dict], osm: list[dict]) -> tuple[list[dict], int]:
    """One stop = an OSM record plus every GTFS point within MATCH_RADIUS_M (they share the platform)."""
    used_gtfs: set[int] = set()
    merged: list[dict] = []
    for o in osm:
        ids = [
            g
            for g, s in enumerate(gtfs)
            if g not in used_gtfs
            and haversine_m(o["lat"], o["lon"], s["lat"], s["lon"]) <= MATCH_RADIUS_M
        ]
        for g in ids:
            used_gtfs.add(g)
        merged.append({**o, "gtfs_ids": [gtfs[g]["gtfs_id"] for g in ids]})
    # GTFS-only stops: deduplicated among themselves (same stop within MATCH_RADIUS_M)
    kept: list[dict] = []
    gtfs_only = 0
    for g, s in enumerate(gtfs):
        if g in used_gtfs:
            continue
        if any(
            haversine_m(s["lat"], s["lon"], p["lat"], p["lon"]) <= MATCH_RADIUS_M
            for p in kept
        ):
            continue  # a duplicate of a GTFS stop already kept
        kept.append(s)
        merged.append(
            {
                "osm_id": None,
                "name": s["name"],
                "lat": s["lat"],
                "lon": s["lon"],
                "tags": {},
                "gtfs_ids": [s["gtfs_id"]],
            }
        )
        gtfs_only += 1
    merged.sort(key=lambda p: p["osm_id"] or f"gtfs/{p['gtfs_ids'][0]}")
    return merged, gtfs_only


def collect(net) -> tuple[list[dict], dict]:
    gtfs, gtfs_at = _gtfs_stops()
    osm, _ = _osm_stops(net)
    stops, gtfs_only = merge(gtfs, osm)
    for p in stops:
        if p["osm_id"] is not None:
            p["sources"] = [
                {"source": "osm", "licence": LICENCE_OSM, "fetched_at": now_iso()},
                *(
                    {
                        "source": "zenodo_gtfs",
                        "licence": LICENCE_GTFS,
                        "fetched_at": gtfs_at,
                    }
                    for _ in [0]
                    if p["gtfs_ids"]
                ),
            ]
        else:
            p["sources"] = [
                {
                    "source": "zenodo_gtfs",
                    "licence": LICENCE_GTFS,
                    "fetched_at": gtfs_at,
                }
            ]
    stats = {
        "gtfs_stops_raw": len(gtfs),
        "gtfs_fetched_at": gtfs_at,
        "osm_stops_raw": len(osm),
        "merged_total": len(stops),
        "with_osm": sum(1 for p in stops if p["osm_id"] is not None),
        "gtfs_only": gtfs_only,
        "osm_unmatched": sum(
            1 for p in stops if p["osm_id"] is not None and not p["gtfs_ids"]
        ),
        "licence_gtfs": LICENCE_GTFS,
        "licence_osm": LICENCE_OSM,
        "attribution": ATTRIBUTION,
        "read_me_note": READ_ME_NOTE,
    }
    write_json(OUT_DIR / "stops.json", stops)
    write_json(OUT_DIR / "stops_stats.json", stats)
    return stops, stats


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.parse_args(argv)
    _, stats = collect(default_net())
    print(
        f"[stops] gtfs={stats['gtfs_stops_raw']} osm={stats['osm_stops_raw']} "
        f"merged={stats['merged_total']} (osm+gtfs={stats['with_osm']}, gtfs_only={stats['gtfs_only']}) "
        f"-> {OUT_DIR / 'stops.json'}"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
