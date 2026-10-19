"""Fill the satellite tile cache (web/tiles.py) for the whole region the route serves: z8-13 over the map's box and z14-15
over the city box (about 1.1 thousand tiles, ~14 MB of Sentinel-2 cloudless 2016, CC BY 4.0).

    uv run python scripts/seed_tiles.py [--cache DIR] [--min-zoom 8]

It runs the same `TileProxy` the route runs (the region rule, the 4-at-a-time fetch cap, the jpeg check, the atomic
write) into `--cache` (default: WALKS_TILE_CACHE, else app/.local/tiles). Idempotent: a tile already on disk is skipped
without a request, so a second run changes nothing, and a run that was interrupted or hit an upstream failure resumes.
Prints the tiles per zoom (already there / fetched now / failed) and the size of the cache; exit code 1 when a tile
could not be fetched.
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from dataclasses import dataclass
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from web import tiles  # noqa: E402


@dataclass
class Count:
    total: int = 0
    present: int = 0
    fetched: int = 0
    failed: int = 0
    size: int = 0


async def seed(proxy: tiles.TileProxy, min_zoom: int) -> dict[int, Count]:
    counts = {z: Count() for z in range(min_zoom, proxy.provider.max_zoom + 1)}
    jobs: asyncio.Queue[tuple[int, int, int]] = asyncio.Queue()
    for z in counts:
        for x, y in tiles.region_tiles(z):
            counts[z].total += 1
            if proxy.path(z, x, y).exists():
                counts[z].present += 1
            else:
                jobs.put_nowait((z, x, y))

    async def worker() -> None:
        while True:
            try:
                z, x, y = jobs.get_nowait()
            except asyncio.QueueEmpty:
                return
            got = await proxy.tile(
                z, x, y
            )  # the counters are updated after the await: `+=` reads before it
            counts[z].fetched += got is not None
            counts[z].failed += got is None

    await asyncio.gather(*(worker() for _ in range(tiles.FETCH_CONCURRENCY)))
    for z, count in counts.items():
        count.size = sum(
            proxy.path(z, x, y).stat().st_size
            for x, y in tiles.region_tiles(z)
            if proxy.path(z, x, y).exists()
        )
    return counts


async def main(cache: Path, min_zoom: int) -> int:
    proxy = tiles.TileProxy(cache_root=cache)
    try:
        counts = await seed(proxy, min_zoom)
    finally:
        await proxy.close()
    print(f"cache: {cache}")
    print(f"{'zoom':>4} {'tiles':>6} {'present':>8} {'fetched':>8} {'failed':>7} {'MB':>7}")
    for z, c in counts.items():
        print(
            f"{z:>4} {c.total:>6} {c.present:>8} {c.fetched:>8} {c.failed:>7} {c.size / 1e6:>7.2f}"
        )
    total = sum(c.total for c in counts.values())
    failed = sum(c.failed for c in counts.values())
    megabytes = sum(c.size for c in counts.values()) / 1e6
    print(f"total: {total} tiles, {total - failed} on disk, {failed} failed, {megabytes:.2f} MB")
    return 1 if failed else 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument("--cache", type=Path, default=tiles.default_cache_root())
    parser.add_argument("--min-zoom", type=int, default=tiles.SEED_MIN_ZOOM)
    args = parser.parse_args()
    sys.exit(asyncio.run(main(args.cache, args.min_zoom)))
