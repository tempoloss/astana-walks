"""Add the street line (`g`, Valhalla's encoded polyline) to every walking leg of data/walk_cache.json that lacks it.

The shape comes from one's own Valhalla (WALKS_VALHALLA_URL is REQUIRED: the public FOSSGIS server is never asked
for a bulk job, see deploy/vps/valhalla). The minutes and metres of a leg are NEVER changed (so no cache key and no
answer moves): the stored entry keeps its `m`, `s`, `d` and only gains `g`. A leg whose new duration differs from the
stored one by more than 5 % is left as it is and listed; so is a leg the server could not route. No leg is added: only
the keys that are already in the file are touched.

The stand's Valhalla listens on the server's loopback only; reach it through an ssh tunnel:

    ssh -N -L 18002:127.0.0.1:8002 <the stand's ssh target>
    WALKS_VALHALLA_URL=http://127.0.0.1:18002/route uv run python scripts/backfill_shapes.py [--dry-run]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from walks.walking import SHIPPED_CACHE_PATH, WalkingRouter, decode_polyline6, own_router

TOLERANCE = 0.05
Point = tuple[float, float]


def parse_key(key: str) -> tuple[Point, Point]:
    """'51.0890,71.4160>51.0894,71.4180' -> ((51.089, 71.416), (51.0894, 71.418))."""
    a, _, b = key.partition(">")
    pa, pb = (tuple(float(x) for x in part.split(",")) for part in (a, b))
    return (pa[0], pa[1]), (pb[0], pb[1])


def backfill(
    cache: dict[str, dict], router: WalkingRouter, *, dry_run: bool = False
) -> dict[str, list[str] | int]:
    """Fill `cache` in place; the counters and the lists of the legs that were left as they are."""
    out: dict[str, list[str] | int] = {"filled": 0, "had_shape": 0, "skipped": [], "failed": []}
    for key, entry in sorted(cache.items()):
        if entry.get("g"):
            out["had_shape"] += 1  # type: ignore[operator]
            continue
        if dry_run:
            continue
        a, b = parse_key(key)
        fresh = router._fetch(a, b)
        router.reset_cooldown()
        if fresh is None or not fresh.get("g"):
            out["failed"].append(f"{key}: no street line from the server")  # type: ignore[union-attr]
            continue
        change = abs(fresh["s"] - entry["s"]) / max(entry["s"], 1)
        if change > TOLERANCE:
            out["skipped"].append(  # type: ignore[union-attr]
                f"{key}: {entry['s']} s stored, {fresh['s']} s now ({change:.0%})"
            )
            continue
        entry["g"] = fresh["g"]
        out["filled"] += 1  # type: ignore[operator]
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="count the legs, call nothing")
    args = ap.parse_args(argv)
    sys.stdout.reconfigure(encoding="utf-8")
    if not own_router():
        print(
            "WALKS_VALHALLA_URL must name one's own Valhalla (see the module docstring)",
            file=sys.stderr,
        )
        return 2
    path: Path = SHIPPED_CACHE_PATH
    cache: dict[str, dict] = json.loads(path.read_text(encoding="utf-8"))
    before = {k: (v["m"], v["s"], v["d"]) for k, v in cache.items()}

    router = WalkingRouter(False)  # no disk cache of its own: only the fetch is used
    res = backfill(cache, router, dry_run=args.dry_run)
    assert {
        k: (v["m"], v["s"], v["d"]) for k, v in cache.items()
    } == before  # nothing but `g` moved
    for line in (*res["skipped"], *res["failed"]):  # type: ignore[misc]
        print(f"LEFT AS IT IS {line}")
    if res["filled"]:
        path.write_text(json.dumps(cache, ensure_ascii=False, sort_keys=True), encoding="utf-8")
        longest = max(len(decode_polyline6(v["g"])) for v in cache.values() if v.get("g"))
        print(f"longest street line: {longest} points")
    print(
        f"legs in the file: {len(cache)}; shapes added: {res['filled']}; already had one: {res['had_shape']}; "
        f"skipped (duration moved over {TOLERANCE:.0%}): {len(res['skipped'])}; no answer: {len(res['failed'])}"  # type: ignore[arg-type]
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
