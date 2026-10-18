"""Warm app/.local/walk_cache.json so a recorded demo needs no network.

Requests covered: the 5 case scenarios plus the hero query, from every one of the 5 UI presets, at a daytime, an
evening and the scenario's own time, under normal / freezing / smoggy conditions and with adaptation off.
  1. retrieval gives the top candidates (the places the LLM may pick from);
  2. Valhalla is asked for the preset -> candidate walking leg of every one of them;
  3. the whole no-AI pipeline runs for the scenario buttons (scenario at its own preset) and the hero query, which
     also fetches the POI -> POI legs of the mini-route.
Only public points are involved (presets and POIs), so everything may be stored on disk.

    uv run python scripts/precompute_walks.py [--date 2026-10-19] [--top 10] [--dry-run]

The service is rate-limited politely (~1 request/s), so a full run takes several minutes. Cached legs are skipped,
so the script can be interrupted and re-run.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import date, datetime
from datetime import time as dtime

from walks.hours import to_local_naive
from walks.intent import parse_rules
from walks.pipeline import get_pois, recommend, round_location
from walks.presets import PRESETS, SCENARIOS
from walks.retrieve import retrieve
from walks.walking import WalkingRouter
from walks.weather import make_weather, manual_weather

DAYTIME, EVENING = dtime(14, 0), dtime(19, 0)
HERO = "Я у EXPO, хочу что-то необычное на 1–2 часа, пешком"

CONDITIONS = [
    ("обычные условия", make_weather(10, 10, pm25=5)),
    ("-30°C", manual_weather(-30)),
    ("смог", manual_weather(10, pm25=80)),
    ("без адаптации", None),
]


def requests(day: date):
    """(text, preset name, when, conditions label, weather, full_pipeline) for everything the demo may show."""
    for text, own_preset, at in [(sc.text, sc.preset, sc.at) for sc in SCENARIOS] + [
        (HERO, "EXPO", None)
    ]:
        times = sorted({DAYTIME, EVENING} | ({at} if at else set()))
        for preset in PRESETS:
            for t in times:
                for label, weather in CONDITIONS:
                    # the pipeline run (POI -> POI legs) only for what the buttons / hero query really trigger
                    full = preset == own_preset and (
                        label == "без адаптации" or at is not None or t == DAYTIME
                    )
                    yield text, preset, datetime.combine(day, t), label, weather, full


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument(
        "--date",
        type=date.fromisoformat,
        default=date.today(),
        help="day to simulate (default: today)",
    )
    ap.add_argument(
        "--top", type=int, default=10, help="candidates per request to warm (default 10)"
    )
    ap.add_argument("--dry-run", action="store_true", help="only count the legs, no network")
    args = ap.parse_args()
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    pois = get_pois()
    router = WalkingRouter()  # the real cache file, network on

    # 1. collect preset -> candidate legs
    legs: dict[tuple, str] = {}
    full_runs = []
    total = 0
    for text, preset, when, _label, weather, full in requests(args.date):
        intent = parse_rules(text).intent
        if intent.mode != "walk":
            continue
        total += 1
        origin = round_location(*PRESETS[preset])
        res = retrieve(pois, origin[0], origin[1], intent, when, top_n=args.top, weather=weather)
        for c in res.candidates:
            legs[(origin, (c.poi.lat, c.poi.lon))] = f"{preset} → {c.poi.name}"
        if full:
            full_runs.append((text, preset, when, weather))
    print(
        f"requests: {total}, distinct preset → place legs: {len(legs)}, full pipeline runs: {len(full_runs)}"
    )
    if args.dry_run:
        return 0

    failed = 0
    started = time.monotonic()
    for n, (a, b) in enumerate(legs, 1):
        leg = router.leg(a, b, persist=True)
        if leg.method != "valhalla":  # network hiccup: wait out the cooldown once and retry
            time.sleep(5)
            router.reset_cooldown()
            leg = router.leg(a, b, persist=True)
        failed += leg.method != "valhalla"
        if n % 25 == 0 or n == len(legs):
            print(
                f"  legs {n}/{len(legs)} ({time.monotonic() - started:.0f} s, network calls "
                f"{router.network_calls}, failed {failed})",
                flush=True,
            )

    # 2. full pipeline: also fetches the POI -> POI legs of the mini-routes
    for n, (text, preset, when, weather) in enumerate(full_runs, 1):
        lat, lon = PRESETS[preset]
        res = recommend(
            text,
            lat,
            lon,
            to_local_naive(when),
            use_llm=False,
            pois=pois,
            weather=weather,
            router=router,
        )
        failed += res.walk_stats.get("straight", 0)
        if n % 10 == 0 or n == len(full_runs):
            print(
                f"  pipeline {n}/{len(full_runs)} ({time.monotonic() - started:.0f} s, network calls "
                f"{router.network_calls}, fallback legs {failed})",
                flush=True,
            )

    print(
        f"done: {router.network_calls} network calls; legs on straight-line fallback: {failed}"
        + (" - re-run when the network is back" if failed else "")
    )
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
