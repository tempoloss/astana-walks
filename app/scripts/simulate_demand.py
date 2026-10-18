"""Simulated city demand for the «Для города» page: data/demand_sim.jsonl and data/demand_sim.meta.json.

There is no real traffic yet, so the page is filled by replaying the real pipeline, offline and with a seeded RNG. The
file is SIMULATED DEMAND, not an observation about the city; what it shows is the mechanism (anonymous record, 500 m
cells, k-anonymity, export). How a request is drawn:

  origin   a 500 m cell with probability proportional to its weight in data/population_proxy.json (OSM residential /
           addressed buildings x levels, see scripts/fetch_population_proxy.py), a uniform point inside the cell; a
           tourist request starts near a landmark, museum, viewpoint or mall instead of a home;
  text     the five scenarios of the case (walks.presets.SCENARIOS, without the place name that fixed their origin)
           plus everyday requests (coffee, food, park, cinema, sport), with the weights in MIX;
  time     weekday / weekend by the calendar, hour of day by HOUR_WEIGHTS (evening peak), the night scenario at 23:00;
  weather  mostly an ordinary autumn day, some frost, some smog (CONDITIONS);
  answer   walks.pipeline.recommend with the rules parser and templates (no network), turned into the very record the
           app logs (walks.reqlog.record_for).

    uv run python scripts/simulate_demand.py [--n 10000] [--seed 20261019] [--k 5] [--out ../data/demand_sim.jsonl]
"""

from __future__ import annotations

import argparse
import json
import math
import os
import random
import sys
from collections import Counter
from datetime import date, datetime, time, timedelta
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP_DIR))
os.environ["WALKS_OFFLINE"] = "1"  # template text, no network
os.environ["WALKS_REQUEST_LOG"] = "off"  # the real log is never touched

from walks.city_actions import NO_DISTRICT  # noqa: E402
from walks.demand import ANY_CATEGORY, aggregate_demand, cell_center, load_requests  # noqa: E402
from walks.districts import district_of, load_districts  # noqa: E402
from walks.i18n import category_name  # noqa: E402
from walks.models import POI  # noqa: E402
from walks.pipeline import get_pois, recommend  # noqa: E402
from walks.presets import SCENARIOS  # noqa: E402
from walks.reqlog import cell_bounds, record_for  # noqa: E402
from walks.walking import offline_router  # noqa: E402
from walks.weather import manual_weather  # noqa: E402

DATA_DIR = APP_DIR.parent / "data"
DEFAULT_OUT = DATA_DIR / "demand_sim.jsonl"
PROXY_PATH = DATA_DIR / "population_proxy.json"
SEED = 20261019
DEFAULT_N = 10000
WEEK_START = date(2026, 10, 12)  # a Monday: ordinary days, no public holiday
M_PER_DEG_LAT = 111_320.0
TOURIST_ORIGIN_CATEGORIES = ("attraction_landmark", "museum_gallery", "viewpoint", "mall")
TOURIST_JITTER_M = 150
# hour of day -> relative weight: a lunch bump, an evening peak, a thin morning and a thin late evening
HOUR_WEIGHTS = {
    8: 3,
    9: 4,
    10: 5,
    11: 6,
    12: 9,
    13: 8,
    14: 6,
    15: 6,
    16: 7,
    17: 9,
    18: 12,
    19: 12,
    20: 9,
    21: 6,
    22: 3,
}
# (apparent °C, precipitation mm/h, PM2.5, weight)
CONDITIONS = ((8.0, 0.0, 12.0, 0.7), (-25.0, 0.0, 12.0, 0.15), (10.0, 0.0, 90.0, 0.15))
# (key, text, weight, origin model); the first five are the scenarios of the case (ТЗ), the rest are everyday requests
MIX: list[tuple[str, str, float, str]] = [
    ("tz_walk", "Прогулка 30–60 мин", 0.18, "home"),
    ("tz_quiet_cafe", SCENARIOS[1].text, 0.17, "home"),
    ("tz_kids", SCENARIOS[2].text, 0.12, "home"),
    ("tz_tourist", SCENARIOS[3].text, 0.08, "tourist"),
    ("tz_night", SCENARIOS[4].text, 0.07, "home"),
    ("coffee", "Где выпить кофе рядом", 0.12, "home"),
    ("food", "Где пообедать", 0.10, "home"),
    ("park", "Хочу в парк, 45 минут", 0.06, "home"),
    ("cinema", "Сходить в кино или театр", 0.05, "home"),
    ("sport", "Спорт, 1 час", 0.05, "home"),
]
NIGHT_AT = SCENARIOS[4].at or time(23, 0)


def load_proxy(path: Path | None = None) -> tuple[list[str], list[float], dict]:
    """(cells, weights, meta) of the population proxy; run scripts/fetch_population_proxy.py when it is missing."""
    data = json.loads((path or PROXY_PATH).read_text(encoding="utf-8"))
    cells = sorted(data["cells"])
    return cells, [float(data["cells"][c]) for c in cells], data["meta"]


def point_in_cell(rng: random.Random, cell: str) -> tuple[float, float]:
    s, w, n, e = cell_bounds(cell)
    return rng.uniform(s, n), rng.uniform(w, e)


def point_near(rng: random.Random, p: POI, radius_m: float) -> tuple[float, float]:
    r = radius_m * math.sqrt(rng.random())
    a = rng.uniform(0, 2 * math.pi)
    return (
        p.lat + r * math.cos(a) / M_PER_DEG_LAT,
        p.lon + r * math.sin(a) / (M_PER_DEG_LAT * math.cos(math.radians(p.lat))),
    )


def weather_for(rng: random.Random):
    apparent, precip, pm25, _w = rng.choices(CONDITIONS, weights=[c[3] for c in CONDITIONS])[0]
    return manual_weather(apparent, precip, pm25=pm25)


def requests_to_replay(pois: list[POI], rng: random.Random, n: int):
    """(source key, text, lat, lon, when, weather) of the n simulated requests."""
    cells, weights, _meta = load_proxy()
    landmarks = [p for p in pois if p.category in TOURIST_ORIGIN_CATEGORIES]
    keys = [m[0] for m in MIX]
    hours = list(HOUR_WEIGHTS)
    for _ in range(n):
        key, text, _w, origin = MIX[keys.index(rng.choices(keys, weights=[m[2] for m in MIX])[0])]
        if origin == "tourist" and landmarks:
            lat, lon = point_near(rng, rng.choice(landmarks), TOURIST_JITTER_M)
        else:
            lat, lon = point_in_cell(rng, rng.choices(cells, weights=weights)[0])
        at = (
            NIGHT_AT
            if key == "tz_night"
            else time(rng.choices(hours, weights=[HOUR_WEIGHTS[h] for h in hours])[0], 0)
        )
        day = WEEK_START + timedelta(days=rng.randrange(7))
        yield key, text, lat, lon, datetime.combine(day, at), weather_for(rng)


def summarise(path: Path, k: int, n_expected: int) -> dict:
    """Print what the simulated file says (with the new indicators) and return the figures for the meta file."""
    districts = load_districts()
    reqs = load_requests(path)
    by_cell = aggregate_demand(reqs, k, by=("cell",))
    detail = aggregate_demand(reqs, k, by=("cell", "category"))
    print(f"{path}: {len(reqs)} requests (expected {n_expected})")
    print(
        f"cells: {by_cell.cells_total}; shown at k={k}: {by_cell.cells_total - by_cell.cells_suppressed}; "
        f"suppressed (merged into «прочее»): {by_cell.cells_suppressed} cells, {by_cell.requests_suppressed} requests"
    )
    print(
        f"no_requested_category_nearby: {by_cell.total_no_category}; hours_unknown_nearby: "
        f"{by_cell.total_hours_unknown}; padded: {by_cell.total_padded}; of {by_cell.total_requests}"
    )
    top_cell = max(Counter(r.cell for r in reqs).values(), default=0)
    print(f"largest cell: {top_cell} requests ({top_cell / max(len(reqs), 1):.1%})")
    print(f"top-8 cell x category by no_requested_category_nearby (k={k}):")
    rows = [r for r in detail.shown if r.no_requested_category_nearby][:8]
    for r in rows:
        lat, lon = cell_center(r.cell)
        district = district_of(lat, lon, districts) or NO_DISTRICT
        print(
            f"  {district}, cell {r.cell}  {category_name(r.category or ANY_CATEGORY, 'ru')}: "
            f"{r.no_requested_category_nearby} of {r.requests} requests"
        )
    per_district = Counter()
    for r in reqs:
        lat, lon = cell_center(r.cell)
        per_district[district_of(lat, lon, districts) or NO_DISTRICT] += 1
    print(f"requests per district: {dict(per_district.most_common())}")
    return {
        "k": k,
        "requests": by_cell.total_requests,
        "cells": by_cell.cells_total,
        "cells_shown": by_cell.cells_total - by_cell.cells_suppressed,
        "cells_suppressed": by_cell.cells_suppressed,
        "requests_in_suppressed_cells": by_cell.requests_suppressed,
        "no_requested_category_nearby": by_cell.total_no_category,
        "hours_unknown_nearby": by_cell.total_hours_unknown,
        "padded": by_cell.total_padded,
        "requests_per_district": dict(per_district.most_common()),
        "largest_cell_share": round(top_cell / max(len(reqs), 1), 4),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--n", type=int, default=DEFAULT_N, help="number of simulated requests")
    ap.add_argument("--seed", type=int, default=SEED)
    ap.add_argument("--k", type=int, default=5, help="k-anonymity of the printed statistics")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT)
    args = ap.parse_args(argv)

    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    rng = random.Random(args.seed)
    pois = get_pois()
    router = offline_router()
    sources: Counter[str] = Counter()
    args.out.parent.mkdir(parents=True, exist_ok=True)
    tmp = args.out.with_suffix(".tmp")
    with tmp.open("w", encoding="utf-8", newline="\n") as fh:
        for source, text, lat, lon, when, weather in requests_to_replay(pois, rng, args.n):
            res = recommend(
                text, lat, lon, when, use_llm=False, pois=pois, weather=weather, router=router
            )
            fh.write(json.dumps(record_for(res), ensure_ascii=False) + "\n")
            sources[source] += 1
    tmp.replace(args.out)

    stats = summarise(args.out, args.k, args.n)
    _cells, _weights, proxy = load_proxy()
    meta = {
        "simulated": True,
        "what": "SIMULATED demand: the real pipeline replayed on drawn requests; not an observation about the city",
        "seed": args.seed,
        "n": args.n,
        "date": date.today().isoformat(),
        "method": {
            "origin": "500 m cell with probability proportional to the OSM residential-building weight "
            "(data/population_proxy.json), uniform point in the cell; tourist scenario: near a landmark / museum / "
            "viewpoint / mall",
            "population_proxy": {
                "file": "data/population_proxy.json",
                "source": proxy["source"],
                "snapshot_date": proxy["snapshot_date"],
                "buildings": proxy["buildings"],
                "cells": proxy["cells"],
            },
            "scenario_mix": {m[0]: m[2] for m in MIX},
            "scenario_counts": dict(sources),
            "hour_weights": HOUR_WEIGHTS,
            "weekdays": "uniform over the 7 days of the week of 2026-10-12",
            "weather": [
                {"apparent_c": c[0], "precip_mm_h": c[1], "pm25": c[2], "weight": c[3]}
                for c in CONDITIONS
            ],
            "answer": "walks.pipeline.recommend, rules parser, templates, offline router",
        },
        "poi_dataset_places": len(pois),
        "stats": stats,
    }
    meta_path = args.out.with_name(args.out.stem + ".meta.json")
    meta_path.write_text(
        json.dumps(meta, ensure_ascii=False, indent=1) + "\n", encoding="utf-8", newline="\n"
    )
    print(f"{meta_path}: seed {args.seed}, n {args.n}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
