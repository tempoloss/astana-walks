"""The satellite tile proxy (web/tiles.py): the region rule, the read-through cache, the failure handling and the route.
No network: the upstream is an injected fake, the cache a tmp_path."""

from __future__ import annotations

import asyncio
import math
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from walks import envcfg
from web import tiles
from web.server import create_app
from web.tiles import TileProxy, TileUnavailable, Upstream

JPEG = b"\xff\xd8\xff\xe0 a tile"
ASTANA = (51.1282, 71.4304)  # lat, lon: the middle of the city
MOSCOW = (55.75, 37.62)


def tile_of(point: tuple[float, float], z: int) -> tuple[int, int]:
    lat, lon = point
    n = 1 << z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


@pytest.fixture(autouse=True)
def online(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv(
        "WALKS_OFFLINE", raising=False
    )  # the fake upstream is only asked on an online stand


class Fake:
    """A fetcher that counts its calls and answers what it is told to."""

    def __init__(self, answer: Upstream | Exception | None = None, delay: float = 0.0) -> None:
        self.answer = answer or Upstream(200, "image/jpeg", JPEG)
        self.delay = delay
        self.urls: list[str] = []

    async def __call__(self, url: str) -> Upstream:
        self.urls.append(url)
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def proxy(tmp_path: Path, fake: Fake) -> TileProxy:
    return TileProxy(cache_root=tmp_path, fetcher=fake)


def files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()]


# ---------------------------------------------------------------- the region rule


@pytest.mark.parametrize("z", [9, 12, 13, 14, 15])
def test_city_tile_is_in_region(z: int) -> None:
    assert tiles.in_region(z, *tile_of(ASTANA, z))


@pytest.mark.parametrize("z", [9, 13, 14, 15])
def test_outside_region_is_empty_and_not_fetched(tmp_path: Path, z: int) -> None:
    fake = Fake()
    assert asyncio.run(proxy(tmp_path, fake).tile(z, *tile_of(MOSCOW, z))) is None
    assert fake.urls == []
    assert files(tmp_path) == []


def test_detail_zoom_is_the_city_box_only(tmp_path: Path) -> None:
    """Inside the map's box but outside the city box: served at z13, not at z14."""
    outskirts = (50.80, 71.0)
    assert tiles.in_region(13, *tile_of(outskirts, 13))
    assert not tiles.in_region(14, *tile_of(outskirts, 14))
    fake = Fake()
    assert asyncio.run(proxy(tmp_path, fake).tile(14, *tile_of(outskirts, 14))) is None
    assert fake.urls == []


def test_zoom_above_15_is_empty_and_not_fetched(tmp_path: Path) -> None:
    fake = Fake()
    assert asyncio.run(proxy(tmp_path, fake).tile(16, *tile_of(ASTANA, 16))) is None
    assert fake.urls == []


@pytest.mark.parametrize(
    ("z", "x", "y"), [(13, -1, 5), (13, 5, -1), (13, 1 << 13, 5), (13, 5, 1 << 13), (-1, 0, 0)]
)
def test_out_of_range_coordinates_are_empty_and_not_fetched(
    tmp_path: Path, z: int, x: int, y: int
) -> None:
    fake = Fake()
    assert asyncio.run(proxy(tmp_path, fake).tile(z, x, y)) is None
    assert fake.urls == []


def test_tile_touching_the_box_is_not_inside_it() -> None:
    n = 1 << 13
    x = math.floor((tiles.MAP_BOUNDS.east + 180) / 360 * n) + 1  # the first column right of the box
    y = tile_of(ASTANA, 13)[1]
    assert not tiles.in_region(13, x, y)


def test_region_tiles_match_the_rule_and_the_budget() -> None:
    for z in range(tiles.SEED_MIN_ZOOM, 16):
        listed = set(tiles.region_tiles(z))
        assert listed
        assert all(tiles.in_region(z, x, y) for x, y in listed)
    assert list(tiles.region_tiles(16)) == []
    # the measured budget of SOURCES §33: the city box at z15 is about 825 tiles
    assert 700 <= len(list(tiles.region_tiles(15))) <= 950


def test_upstream_url_has_row_before_column(tmp_path: Path) -> None:
    fake = Fake()
    x, y = tile_of(ASTANA, 13)
    asyncio.run(proxy(tmp_path, fake).tile(13, x, y))
    assert fake.urls == [
        f"https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/GoogleMapsCompatible/13/{y}/{x}.jpg"
    ]


# ---------------------------------------------------------------- the cache


def test_miss_fetches_writes_and_serves(tmp_path: Path) -> None:
    fake = Fake()
    x, y = tile_of(ASTANA, 14)
    assert asyncio.run(proxy(tmp_path, fake).tile(14, x, y)) == JPEG
    assert (tmp_path / "s2" / "14" / str(x) / f"{y}.jpg").read_bytes() == JPEG
    assert [p.name for p in files(tmp_path)] == [f"{y}.jpg"]  # no temp file left behind


def test_cache_hit_is_served_without_a_fetch(tmp_path: Path) -> None:
    fake = Fake()
    x, y = tile_of(ASTANA, 14)
    path = tmp_path / "s2" / "14" / str(x) / f"{y}.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"cached bytes")
    assert asyncio.run(proxy(tmp_path, fake).tile(14, x, y)) == b"cached bytes"
    assert fake.urls == []


def test_concurrent_misses_of_one_tile_fetch_once(tmp_path: Path) -> None:
    fake = Fake(delay=0.05)
    x, y = tile_of(ASTANA, 15)
    p = proxy(tmp_path, fake)

    async def burst() -> list[bytes | None]:
        return await asyncio.gather(*(p.tile(15, x, y) for _ in range(12)))

    assert asyncio.run(burst()) == [JPEG] * 12
    assert len(fake.urls) == 1
    assert p._locks == {}  # the per-tile locks do not pile up


def test_fetches_are_capped_at_four_at_a_time(tmp_path: Path) -> None:
    running = peak = 0

    async def slow(_: str) -> Upstream:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return Upstream(200, "image/jpeg", JPEG)

    p = TileProxy(cache_root=tmp_path, fetcher=slow)
    x, y = tile_of(ASTANA, 13)

    async def burst() -> None:
        await asyncio.gather(
            *(p.tile(13, x + dx, y) for dx in range(-1, 3)),
            *(p.tile(13, x, y + dy) for dy in range(1, 6)),
        )

    asyncio.run(burst())
    assert peak == tiles.FETCH_CONCURRENCY


def test_upstream_failure_is_empty_uncached_and_retried(tmp_path: Path) -> None:
    fake = Fake(TileUnavailable("down"))
    x, y = tile_of(ASTANA, 14)
    p = proxy(tmp_path, fake)

    async def twice() -> tuple[bytes | None, bytes | None]:
        first = await p.tile(14, x, y)
        fake.answer = Upstream(200, "image/jpeg", JPEG)  # the upstream is back
        return first, await p.tile(14, x, y)

    assert asyncio.run(twice()) == (None, JPEG)
    assert len(fake.urls) == 2


@pytest.mark.parametrize(
    "answer",
    [
        Upstream(200, "image/jpeg", b""),
        Upstream(200, "text/html; charset=utf-8", b"<html>rate limited</html>"),
        Upstream(200, "", JPEG),
        Upstream(200, "image/png", b"\x89PNG"),
        Upstream(404, "image/jpeg", JPEG),
        Upstream(503, "text/plain", b"busy"),
    ],
)
def test_bad_upstream_answer_is_rejected_and_not_cached(tmp_path: Path, answer: Upstream) -> None:
    x, y = tile_of(ASTANA, 14)
    assert asyncio.run(proxy(tmp_path, Fake(answer)).tile(14, x, y)) is None
    assert files(tmp_path) == []


def test_failure_is_logged_once_per_tile(tmp_path: Path, caplog: pytest.LogCaptureFixture) -> None:
    fake = Fake(TileUnavailable("down"))
    x, y = tile_of(ASTANA, 14)
    p = proxy(tmp_path, fake)

    async def thrice() -> None:
        for _ in range(3):
            await p.tile(14, x, y)

    with caplog.at_level("WARNING", logger="web.tiles"):
        asyncio.run(thrice())
    assert len([r for r in caplog.records if r.name == "web.tiles"]) == 1


def test_offline_stand_serves_the_cache_and_never_fetches(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    fake = Fake()
    cached, missing = tile_of(ASTANA, 14), (tile_of(ASTANA, 14)[0] + 1, tile_of(ASTANA, 14)[1])
    path = tmp_path / "s2" / "14" / str(cached[0]) / f"{cached[1]}.jpg"
    path.parent.mkdir(parents=True)
    path.write_bytes(b"cached bytes")
    p = proxy(tmp_path, fake)
    assert asyncio.run(p.tile(14, *cached)) == b"cached bytes"
    assert asyncio.run(p.tile(14, *missing)) is None
    assert fake.urls == []
    assert envcfg.offline()


def test_a_failed_write_still_serves_the_tile(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def full(*_: object) -> None:
        raise OSError("disk full")

    monkeypatch.setattr(tiles, "write_atomic", full)
    x, y = tile_of(ASTANA, 14)
    assert asyncio.run(proxy(tmp_path, Fake()).tile(14, x, y)) == JPEG


# ---------------------------------------------------------------- the route


def client(tmp_path: Path, fake: Fake) -> TestClient:
    app = create_app()
    app.state.tiles = proxy(tmp_path, fake)
    return TestClient(app)


def test_route_hit_is_a_long_lived_jpeg(tmp_path: Path) -> None:
    fake = Fake()
    x, y = tile_of(ASTANA, 14)
    with client(tmp_path, fake) as c:
        res = c.get(f"/tiles/s2/14/{x}/{y}.jpg")
        again = c.get(f"/tiles/s2/14/{x}/{y}.jpg")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert (
        res.headers["cache-control"] == "public, max-age=2592000, immutable"
    )  # SecurityHeaders leaves it alone
    assert "default-src 'self'" in res.headers["content-security-policy"]
    assert res.content == again.content == JPEG
    assert len(fake.urls) == 1


@pytest.mark.parametrize(
    "path",
    [
        f"/tiles/s2/14/{tile_of(MOSCOW, 14)[0]}/{tile_of(MOSCOW, 14)[1]}.jpg",
        f"/tiles/s2/16/{tile_of(ASTANA, 16)[0]}/{tile_of(ASTANA, 16)[1]}.jpg",
        "/tiles/s2/14/99999999/1.jpg",
    ],
)
def test_route_outside_the_region_is_204_no_store(tmp_path: Path, path: str) -> None:
    fake = Fake()
    with client(tmp_path, fake) as c:
        res = c.get(path)
    assert res.status_code == 204
    assert res.headers["cache-control"] == "no-store"
    assert res.content == b""
    assert fake.urls == []


@pytest.mark.parametrize(
    "path",
    [
        "/tiles/s2/14/abc/1.jpg",
        "/tiles/s2/14/1/-5.jpg",
        "/tiles/s2/14/1/1e3.jpg",
        "/tiles/s2/14/123456789012/1.jpg",
    ],
)
def test_route_malformed_coordinates_are_400_not_fetched(tmp_path: Path, path: str) -> None:
    fake = Fake()
    with client(tmp_path, fake) as c:
        res = c.get(path)
    assert res.status_code == 400
    assert res.headers["cache-control"] == "no-store"
    assert fake.urls == []


def test_route_upstream_failure_is_204_no_store(tmp_path: Path) -> None:
    fake = Fake(TileUnavailable("down"))
    x, y = tile_of(ASTANA, 14)
    with client(tmp_path, fake) as c:
        res = c.get(f"/tiles/s2/14/{x}/{y}.jpg")
    assert res.status_code == 204
    assert res.headers["cache-control"] == "no-store"
    assert files(tmp_path) == []
