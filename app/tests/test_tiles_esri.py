"""The Esri imagery proxy (web/tiles.py EsriProxy, /tiles/esri/…): the key stays on the server, nothing is stored, no
upstream call outside the region or without a key. No network: the upstream is an injected fake (or an httpx
MockTransport for the real fetch path) and the key a recognizable fake one."""

from __future__ import annotations

import asyncio
import logging
import math
from pathlib import Path

import httpx
import pytest
from starlette.testclient import TestClient

from web import tiles
from web.server import create_app
from web.tiles import EsriProxy, TileUnavailable, Upstream

KEY = "FAKE-esri-key-7c1d9e3a5b"
JPEG = b"\xff\xd8\xff\xe0 esri tile"
ASTANA = (51.1283, 71.4305)
MOSCOW = (55.75, 37.62)
OUTSKIRTS = (51.30, 71.20)  # inside the map's box, outside the city box


def tile_of(point: tuple[float, float], z: int) -> tuple[int, int]:
    lat, lon = point
    n = 1 << z
    x = int((lon + 180) / 360 * n)
    y = int((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n)
    return x, y


@pytest.fixture(autouse=True)
def stand(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    monkeypatch.delenv("WALKS_OFFLINE", raising=False)
    monkeypatch.delenv(tiles.ESRI_KEY_ENV, raising=False)
    monkeypatch.setenv(tiles.CACHE_ENV, str(tmp_path / "cache"))  # nothing may land here


class Fake:
    def __init__(self, answer: Upstream | Exception | None = None, delay: float = 0.0) -> None:
        self.answer = answer or Upstream(200, "image/jpeg", JPEG)
        self.delay = delay
        self.calls: list[tuple[str, str]] = []

    async def __call__(self, url: str, key: str) -> Upstream:
        self.calls.append((url, key))
        if self.delay:
            await asyncio.sleep(self.delay)
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def files(root: Path) -> list[Path]:
    return [p for p in root.rglob("*") if p.is_file()]


# ---------------------------------------------------------------- the key and the region


def test_no_key_is_empty_and_not_fetched() -> None:
    fake = Fake()
    proxy = EsriProxy(key=None, fetcher=fake)
    assert not proxy.configured
    assert asyncio.run(proxy.tile(14, *tile_of(ASTANA, 14))) is None
    assert fake.calls == []


@pytest.mark.parametrize("key", ["", None])
def test_empty_key_is_no_key(key: str | None) -> None:
    assert not EsriProxy(key=key).configured


@pytest.mark.parametrize(
    ("point", "z"),
    [(MOSCOW, 9), (MOSCOW, 14), (OUTSKIRTS, 14), (OUTSKIRTS, 17), (ASTANA, 19), (ASTANA, 22)],
)
def test_outside_the_region_is_empty_and_not_fetched(point: tuple[float, float], z: int) -> None:
    fake = Fake()
    proxy = EsriProxy(key=KEY, fetcher=fake)
    assert asyncio.run(proxy.tile(z, *tile_of(point, z))) is None
    assert fake.calls == []


@pytest.mark.parametrize(
    ("z", "x", "y"), [(13, -1, 5), (13, 5, -1), (14, 1 << 14, 5), (14, 5, 1 << 14), (-1, 0, 0)]
)
def test_out_of_range_coordinates_are_empty_and_not_fetched(z: int, x: int, y: int) -> None:
    fake = Fake()
    assert asyncio.run(EsriProxy(key=KEY, fetcher=fake).tile(z, x, y)) is None
    assert fake.calls == []


@pytest.mark.parametrize(
    ("point", "z"), [(OUTSKIRTS, 9), (OUTSKIRTS, 13), (ASTANA, 14), (ASTANA, 17), (ASTANA, 18)]
)
def test_the_map_box_to_z13_and_the_city_box_to_z18_are_served(
    point: tuple[float, float], z: int
) -> None:
    fake = Fake()
    x, y = tile_of(point, z)
    assert asyncio.run(EsriProxy(key=KEY, fetcher=fake).tile(z, x, y)) == JPEG
    # row before column; the key travels beside the URL, never in it
    assert [url for url, _ in fake.calls] == [
        f"https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"
    ]
    assert KEY not in fake.calls[0][0]
    assert fake.calls[0][1] == KEY


def test_offline_stand_makes_no_call(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    fake = Fake()
    proxy = EsriProxy(key=KEY, fetcher=fake)
    assert not proxy.configured
    assert asyncio.run(proxy.tile(14, *tile_of(ASTANA, 14))) is None
    assert fake.calls == []


# ---------------------------------------------------------------- failures and limits


@pytest.mark.parametrize(
    "answer",
    [
        TileUnavailable("down"),
        Upstream(200, "image/jpeg", b""),
        Upstream(
            200, "text/plain", b'{"error": {"code": 498, "message": "Invalid token"}}'
        ),  # Esri's errors are 200s
        Upstream(200, "", JPEG),
        Upstream(403, "image/jpeg", JPEG),
        Upstream(500, "text/html", b"<html>oops</html>"),
    ],
)
def test_a_bad_upstream_is_empty_and_nothing_is_written(
    answer: Upstream | Exception, tmp_path: Path
) -> None:
    proxy = EsriProxy(key=KEY, fetcher=Fake(answer))
    assert asyncio.run(proxy.tile(14, *tile_of(ASTANA, 14))) is None
    assert files(tmp_path) == []


def test_fetches_are_capped_at_eight_at_a_time() -> None:
    running = peak = 0

    async def slow(_: str, __: str) -> Upstream:
        nonlocal running, peak
        running += 1
        peak = max(peak, running)
        await asyncio.sleep(0.02)
        running -= 1
        return Upstream(200, "image/jpeg", JPEG)

    proxy = EsriProxy(key=KEY, fetcher=slow)
    x, y = tile_of(ASTANA, 15)

    async def burst() -> None:
        await asyncio.gather(*(proxy.tile(15, x + dx, y) for dx in range(-8, 8)))

    asyncio.run(burst())
    assert peak == tiles.ESRI_CONCURRENCY


def test_a_down_upstream_is_logged_once_a_minute(caplog: pytest.LogCaptureFixture) -> None:
    proxy = EsriProxy(key=KEY, fetcher=Fake(TileUnavailable("down")))
    x, y = tile_of(ASTANA, 14)

    async def many() -> None:
        for dx in range(5):
            await proxy.tile(14, x + dx, y)

    with caplog.at_level(logging.WARNING, logger="web.tiles"):
        asyncio.run(many())
    assert len([r for r in caplog.records if r.name == "web.tiles"]) == 1


def test_nothing_is_stored_by_a_served_tile(tmp_path: Path) -> None:
    asyncio.run(EsriProxy(key=KEY, fetcher=Fake()).tile(14, *tile_of(ASTANA, 14)))
    assert files(tmp_path) == []
    assert not (tmp_path / "cache").exists()


# ---------------------------------------------------------------- the key never leaks


def mock_proxy(handler) -> EsriProxy:
    proxy = EsriProxy(key=KEY)
    proxy._client = httpx.AsyncClient(transport=httpx.MockTransport(handler))
    return proxy


def test_the_real_fetch_sends_the_key_as_a_query_token_and_serves_the_jpeg() -> None:
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)

    x, y = tile_of(ASTANA, 17)
    assert asyncio.run(mock_proxy(handler).tile(17, x, y)) == JPEG
    assert seen[0].url.params["token"] == KEY
    assert seen[0].url.path.endswith(f"/tile/17/{y}/{x}")


@pytest.mark.parametrize("failure", ["status", "text", "connect", "timeout"])
def test_no_log_record_carries_the_key(failure: str, caplog: pytest.LogCaptureFixture) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if failure == "connect":
            raise httpx.ConnectError(
                f"cannot reach {request.url}", request=request
            )  # httpx texts may carry the URL
        if failure == "timeout":
            raise httpx.ReadTimeout(f"timed out: {request.url}", request=request)
        if failure == "text":
            return httpx.Response(
                200, headers={"content-type": "text/plain"}, content=b"Invalid token"
            )
        return httpx.Response(500, content=b"oops")

    proxy = mock_proxy(handler)
    with caplog.at_level(logging.DEBUG):  # every logger, every level
        assert asyncio.run(proxy.tile(14, *tile_of(ASTANA, 14))) is None
    assert caplog.records, "the failure is logged"
    for record in caplog.records:
        assert KEY not in record.getMessage()
        assert KEY not in (record.exc_text or "")
        assert record.exc_info is None
        assert KEY not in repr(record.args)


def test_httpx_does_not_log_the_url_even_at_debug(caplog: pytest.LogCaptureFixture) -> None:
    """httpx's own INFO line «HTTP Request: GET <url> …» would carry the token."""

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(200, headers={"content-type": "image/jpeg"}, content=JPEG)

    with caplog.at_level(logging.DEBUG):
        assert asyncio.run(mock_proxy(handler).tile(14, *tile_of(ASTANA, 14))) == JPEG
    assert all(KEY not in r.getMessage() for r in caplog.records)


# ---------------------------------------------------------------- the routes and /api/config


def client(fake: Fake | None, key: str | None = KEY) -> TestClient:
    app = create_app()
    app.state.esri = EsriProxy(key=key, fetcher=fake or Fake())
    return TestClient(app)


def test_route_success_is_private_jpeg_with_no_key_in_it(tmp_path: Path) -> None:
    fake = Fake()
    x, y = tile_of(ASTANA, 17)
    with client(fake) as c:
        res = c.get(f"/tiles/esri/17/{x}/{y}.jpg")
    assert res.status_code == 200
    assert res.headers["content-type"] == "image/jpeg"
    assert res.headers["cache-control"] == "private, max-age=86400"
    assert res.content == JPEG
    assert KEY not in repr(dict(res.headers)) + res.text
    assert "default-src 'self'" in res.headers["content-security-policy"]
    assert res.headers["referrer-policy"] == "no-referrer"
    assert files(tmp_path) == []


@pytest.mark.parametrize(
    ("path", "key"),
    [
        (f"/tiles/esri/14/{tile_of(MOSCOW, 14)[0]}/{tile_of(MOSCOW, 14)[1]}.jpg", KEY),
        (f"/tiles/esri/19/{tile_of(ASTANA, 19)[0]}/{tile_of(ASTANA, 19)[1]}.jpg", KEY),
        (f"/tiles/esri/14/{tile_of(ASTANA, 14)[0]}/{tile_of(ASTANA, 14)[1]}.jpg", None),
    ],
)
def test_route_empty_answers_are_204_no_store(path: str, key: str | None) -> None:
    fake = Fake()
    with client(fake, key) as c:
        res = c.get(path)
    assert res.status_code == 204
    assert res.headers["cache-control"] == "no-store"
    assert res.content == b""
    assert fake.calls == []


def test_route_upstream_failure_is_204_no_store() -> None:
    x, y = tile_of(ASTANA, 14)
    with client(Fake(TileUnavailable("down"))) as c:
        res = c.get(f"/tiles/esri/14/{x}/{y}.jpg")
    assert res.status_code == 204
    assert res.headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    "path",
    ["/tiles/esri/14/abc/1.jpg", "/tiles/esri/14/1/-5.jpg", "/tiles/esri/14/123456789012/1.jpg"],
)
def test_route_malformed_coordinates_are_400_not_fetched(path: str) -> None:
    fake = Fake()
    with client(fake) as c:
        res = c.get(path)
    assert res.status_code == 400
    assert fake.calls == []


def test_config_exposes_the_boolean_and_never_the_key(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "arcgis.key"
    key_file.write_text(f"{KEY}\n", encoding="utf-8")
    monkeypatch.setenv(tiles.ESRI_KEY_ENV, str(key_file))
    with TestClient(create_app()) as c:
        res = c.get("/api/config")
    assert res.json()["satellite_hd"] is True
    assert KEY not in res.text
    monkeypatch.delenv(tiles.ESRI_KEY_ENV)
    with TestClient(create_app()) as c:
        assert c.get("/api/config").json()["satellite_hd"] is False


def test_config_says_no_hd_on_the_offline_stand(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    key_file = tmp_path / "arcgis.key"
    key_file.write_text(KEY, encoding="utf-8")
    monkeypatch.setenv(tiles.ESRI_KEY_ENV, str(key_file))
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    with TestClient(create_app()) as c:
        assert c.get("/api/config").json()["satellite_hd"] is False


def test_the_key_file_is_read_once_per_app_and_only_its_first_line(tmp_path: Path) -> None:
    key_file = tmp_path / "k"
    key_file.write_text(f"  {KEY}  \nsomething else\n", encoding="utf-8")
    assert tiles.read_esri_key(str(key_file)) == KEY
    assert tiles.read_esri_key(str(tmp_path / "missing")) is None
    (tmp_path / "empty").write_text("\n", encoding="utf-8")
    assert tiles.read_esri_key(str(tmp_path / "empty")) is None
    assert tiles.read_esri_key("") is None
