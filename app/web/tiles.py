"""The satellite layer's tiles, both same-origin so the browser never talks to an imagery host and the CSP stays as it is.

    GET /tiles/s2/{z}/{x}/{y}.jpg    EOX Sentinel-2 cloudless 2016 (CC BY 4.0, 10 m per pixel), a read-through disk cache
    GET /tiles/esri/{z}/{x}/{y}.jpg  Esri World Imagery (sub-metre) through an ArcGIS Location Platform key, NO storage

EOX: a tile is read from the disk cache (`<root>/s2/<z>/<x>/<y>.jpg`); a miss is fetched once, checked, written atomically
and served. The route is not an open proxy and the disk is bounded: only the tiles the map can ask for are served (the
region rule below), everything else is an empty 204 with no upstream call. An upstream failure is a 204 `no-store`,
never cached: the next request asks again. The 2016 imagery never changes, so a served tile is `immutable` for 30 days.
The raster source on the page declares `maxzoom: 15`, so MapLibre overzooms the z15 tiles instead of asking for more.
Under WALKS_OFFLINE=1 a miss is not fetched (the stand makes no network request): only what the cache holds is served.
The cache root is `WALKS_TILE_CACHE` (default app/.local/tiles; on the server /var/lib/anyq/tiles); scripts/seed_tiles.py
fills it for the whole region with the very code below.

Esri: the key is read once from the file named by `ARCGIS_API_KEY_FILE`; without it (or offline) every request is an empty
204 and `/api/config` says `satellite_hd: false`. Esri's terms allow no storage, so a tile is fetched per request, passed
through, and kept by the visitor's browser only (`private`, a day): a CDN in front must not store it. The key lives in the
upstream URL's query (Esri's header form is not accepted by its tile service), so no log line or error of this module
ever carries the URL: only a status or an exception's type name.
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import math
import os
import tempfile
import time
from collections.abc import AsyncIterator, Awaitable, Callable, Iterator
from dataclasses import dataclass
from http import HTTPStatus
from pathlib import Path
from typing import NamedTuple

import httpx
from starlette.requests import Request
from starlette.responses import Response

from walks import envcfg

APP = Path(__file__).resolve().parents[1]
CACHE_ENV = "WALKS_TILE_CACHE"
DEFAULT_CACHE = APP / ".local" / "tiles"
TILE_PATH = "/tiles/s2/{z}/{x}/{y}.jpg"
ESRI_PATH = "/tiles/esri/{z}/{x}/{y}.jpg"
USER_AGENT = "anyq-walks/1.0 (+https://anyq.an8kk.dev; satellite layer, Sentinel-2 cloudless 2016)"
TIMEOUT_S = 8.0
FETCH_CONCURRENCY = 4
MAX_AGE = 30 * 24 * 3600
HIT_CACHE_CONTROL = f"public, max-age={MAX_AGE}, immutable"
NO_STORE = {"cache-control": "no-store"}
MAX_DIGITS = 8  # a coordinate longer than this is garbage, not a tile

log = logging.getLogger("web.tiles")
# httpx logs every request's full URL at INFO, and an Esri tile URL carries the key: the lines are not wanted at all
logging.getLogger("httpx").setLevel(logging.WARNING)


@dataclass(frozen=True)
class Provider:
    id: str
    upstream_template: str
    expected_prefix: str  # the only URLs the fetcher may call
    max_zoom: int
    media_type: str
    extension: str


# the EOX 2016 release; the template is {z}/{y}/{x} (WMTS: row before column)
SENTINEL_2016 = Provider(
    id="s2",
    upstream_template="https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/GoogleMapsCompatible/{z}/{y}/{x}.jpg",
    expected_prefix="https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/GoogleMapsCompatible/",
    max_zoom=15,
    media_type="image/jpeg",
    extension="jpg",
)


class Box(NamedTuple):
    south: float
    north: float
    west: float
    east: float


# The map's own box (web/static/js/map.js MAP_BOUNDS, scripts/ui_tour_places.py): the city and its surroundings.
MAP_BOUNDS = Box(south=50.74, north=51.54, west=70.83, east=72.08)
# The city itself: the detail zooms are cached for this box only (z15 ≈ 825 tiles ≈ 10 MB).
CITY_BOX = Box(south=51.03, north=51.25, west=71.28, east=71.55)
# (highest zoom, the box it is served over): a tile is served when it intersects the box of the first rule that covers its zoom
REGION_RULES = ((13, MAP_BOUNDS), (SENTINEL_2016.max_zoom, CITY_BOX))
Rules = tuple[tuple[int, Box], ...]
SEED_MIN_ZOOM = 8  # the map's minZoom is 9; the whole box fits a laptop at about z9, one more for the tiles at its edge


class Upstream(NamedTuple):
    status: int
    content_type: str
    body: bytes


class TileUnavailable(Exception):
    """The upstream could not give a tile (network, timeout, a bad answer): never cached."""


Fetcher = Callable[[str], Awaitable[Upstream]]


# ---------------------------------------------------------------- the region


def tile_box(z: int, x: int, y: int) -> Box:
    n = 1 << z

    def lat(row: int) -> float:
        return math.degrees(math.atan(math.sinh(math.pi * (1 - 2 * row / n))))

    return Box(south=lat(y + 1), north=lat(y), west=x / n * 360 - 180, east=(x + 1) / n * 360 - 180)


def region_box(z: int, rules: Rules = REGION_RULES) -> Box | None:
    return next((box for top, box in rules if z <= top), None)


def in_region(z: int, x: int, y: int, rules: Rules = REGION_RULES) -> bool:
    """A real tile of a served zoom that intersects the box of its zoom (a tile that only touches the box does not)."""
    box = region_box(z, rules) if 0 <= z <= rules[-1][0] else None
    if box is None or not (0 <= x < 1 << z and 0 <= y < 1 << z):
        return False
    t = tile_box(z, x, y)
    return t.west < box.east and t.east > box.west and t.south < box.north and t.north > box.south


def region_tiles(z: int) -> Iterator[tuple[int, int]]:
    """Every (x, y) of the zoom the region rule serves."""
    box = region_box(z)
    if box is None or z > SENTINEL_2016.max_zoom:
        return
    n = 1 << z

    def column(lon: float) -> int:
        return min(max(math.floor((lon + 180) / 360 * n), 0), n - 1)

    def row(lat: float) -> int:
        return min(
            max(math.floor((1 - math.asinh(math.tan(math.radians(lat))) / math.pi) / 2 * n), 0),
            n - 1,
        )

    for x in range(column(box.west), column(box.east) + 1):
        for y in range(row(box.north), row(box.south) + 1):
            if in_region(z, x, y):
                yield x, y


# ---------------------------------------------------------------- the cache


def default_cache_root() -> Path:
    return Path(os.environ.get(CACHE_ENV) or DEFAULT_CACHE)


def write_atomic(path: Path, body: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(dir=path.parent, prefix=f".{path.name}.", delete=False) as out:
        temp = Path(out.name)
        try:
            out.write(body)
        except BaseException:
            out.close()
            temp.unlink(missing_ok=True)
            raise
    try:
        temp.replace(path)
    except BaseException:
        temp.unlink(missing_ok=True)
        raise


def read_cached(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None


class TileProxy:
    """The read-through cache. One per app: it owns the shared HTTP client, the fetch semaphore and the per-tile locks
    (all created on first use, inside the running loop). `fetcher` is injectable for tests."""

    def __init__(
        self,
        cache_root: Path | None = None,
        fetcher: Fetcher | None = None,
        provider: Provider = SENTINEL_2016,
    ) -> None:
        self.root = cache_root if cache_root is not None else default_cache_root()
        self.provider = provider
        self._fetcher = fetcher or self._http_fetch
        self._client: httpx.AsyncClient | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._locks: dict[tuple[int, int, int], list] = {}  # tile -> [lock, users]
        self._reported: set[tuple[int, int, int]] = set()

    def path(self, z: int, x: int, y: int) -> Path:
        return self.root / self.provider.id / str(z) / str(x) / f"{y}.{self.provider.extension}"

    def url(self, z: int, x: int, y: int) -> str:
        url = self.provider.upstream_template.format(z=z, x=x, y=y)
        if not url.startswith(self.provider.expected_prefix):
            msg = "unexpected tile upstream URL"
            raise ValueError(msg)
        return url

    async def _http_fetch(self, url: str) -> Upstream:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S)
        try:
            res = await self._client.get(url)
        except httpx.HTTPError as exc:
            msg = f"upstream request failed: {type(exc).__name__}"
            raise TileUnavailable(msg) from exc
        return Upstream(res.status_code, res.headers.get("content-type", ""), res.content)

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None and not client.is_closed:
            await client.aclose()

    @contextlib.asynccontextmanager
    async def _tile_lock(self, key: tuple[int, int, int]) -> AsyncIterator[None]:
        entry = self._locks.setdefault(key, [asyncio.Lock(), 0])
        entry[1] += 1
        try:
            async with entry[0]:
                yield
        finally:
            entry[1] -= 1
            if entry[1] == 0:
                del self._locks[key]

    async def _fetch(self, z: int, x: int, y: int) -> bytes:
        if envcfg.offline():  # WALKS_OFFLINE: not one network request, the cache is all there is
            msg = "WALKS_OFFLINE: no upstream request"
            raise TileUnavailable(msg)
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(FETCH_CONCURRENCY)
        async with self._semaphore:
            got = await self._fetcher(self.url(z, x, y))
        if got.status != HTTPStatus.OK:
            msg = f"upstream answered HTTP {got.status}"
            raise TileUnavailable(msg)
        if not got.content_type.lower().startswith(self.provider.media_type):
            msg = f"upstream sent {got.content_type or 'no content type'}, not {self.provider.media_type}"
            raise TileUnavailable(msg)
        if not got.body:
            msg = "upstream sent an empty body"
            raise TileUnavailable(msg)
        return got.body

    async def tile(self, z: int, x: int, y: int) -> bytes | None:
        """The tile's bytes, or None: outside the region (no upstream call), or the upstream failed (nothing is cached)."""
        if not in_region(z, x, y):
            return None
        path = self.path(z, x, y)
        hit = await asyncio.to_thread(read_cached, path)
        if hit is not None:
            return hit
        key = (z, x, y)
        async with self._tile_lock(key):
            hit = await asyncio.to_thread(
                read_cached, path
            )  # whoever held the lock may have filled it
            if hit is not None:
                return hit
            try:
                body = await self._fetch(z, x, y)
            except TileUnavailable as exc:
                if (
                    key not in self._reported
                ):  # once per tile: a down upstream must not flood the log
                    self._reported.add(key)
                    log.warning("satellite tile z%s/%s/%s unavailable: %s", z, x, y, exc)
                return None
            self._reported.discard(key)
            try:
                await asyncio.to_thread(write_atomic, path, body)
            except OSError as exc:
                log.warning("satellite tile z%s/%s/%s not cached: %s", z, x, y, exc)
            return body


# ---------------------------------------------------------------- the route


def _coordinate(raw: str) -> int | None:
    return int(raw) if raw.isascii() and raw.isdigit() and len(raw) <= MAX_DIGITS else None


async def _serve(request: Request, proxy: TileProxy | EsriProxy, cache_control: str) -> Response:
    coords = [_coordinate(request.path_params[k]) for k in ("z", "x", "y")]
    if None in coords:
        return Response(status_code=HTTPStatus.BAD_REQUEST, headers=NO_STORE)
    body = await proxy.tile(*coords)
    if body is None:
        return Response(status_code=HTTPStatus.NO_CONTENT, headers=NO_STORE)
    return Response(
        body, media_type=proxy.provider.media_type, headers={"cache-control": cache_control}
    )


async def tile_view(request: Request) -> Response:
    return await _serve(request, request.app.state.tiles, HIT_CACHE_CONTROL)


# ---------------------------------------------------------------- Esri World Imagery (no storage)

ESRI = Provider(
    id="esri",
    upstream_template="https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}",
    expected_prefix="https://ibasemaps-api.arcgis.com/arcgis/rest/services/World_Imagery/MapServer/tile/",
    max_zoom=18,
    media_type="image/jpeg",
    extension="jpg",
)
# the map's box up to z13, the city box up to z18 (what the map can ask for; the rest is an empty 204, no call)
ESRI_RULES: Rules = ((13, MAP_BOUNDS), (ESRI.max_zoom, CITY_BOX))
ESRI_KEY_ENV = "ARCGIS_API_KEY_FILE"
ESRI_CONCURRENCY = 8
ESRI_CACHE_CONTROL = "private, max-age=86400"  # the visitor's browser only: Esri's terms allow no storage by a CDN or by us
ESRI_LOG_EVERY_S = 60.0  # a down upstream must not flood the log

EsriFetcher = Callable[[str, str], Awaitable[Upstream]]  # (tile URL without the key, the key)


def read_esri_key(path: str | None = None) -> str | None:
    """The key from the file `ARCGIS_API_KEY_FILE` names (first line); None when there is no file or it is empty."""
    name = path if path is not None else os.environ.get(ESRI_KEY_ENV, "")
    if not name:
        return None
    try:
        lines = Path(name).read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return None
    return lines[0].strip() or None if lines else None


class EsriProxy:
    """Esri World Imagery tiles passed through to the browser: no disk, no memory, the key never leaves the server.
    `fetcher` is injectable for tests; `key` is what read_esri_key found (or a test's)."""

    def __init__(self, key: str | None = None, fetcher: EsriFetcher | None = None) -> None:
        self._key = key
        self._fetcher = fetcher or self._http_fetch
        self.provider = ESRI
        self._client: httpx.AsyncClient | None = None
        self._semaphore: asyncio.Semaphore | None = None
        self._logged_at = -ESRI_LOG_EVERY_S

    @classmethod
    def from_env(cls) -> EsriProxy:
        return cls(read_esri_key())

    @property
    def configured(self) -> bool:
        """The layer can be offered: there is a key and the stand may use the network."""
        return bool(self._key) and not envcfg.offline()

    async def _http_fetch(self, url: str, key: str) -> Upstream:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(headers={"User-Agent": USER_AGENT}, timeout=TIMEOUT_S)
        try:
            res = await self._client.get(url, params={"token": key})
        except httpx.HTTPError as exc:
            msg = f"upstream request failed: {type(exc).__name__}"  # never `exc` itself: its text may carry the URL
            raise TileUnavailable(msg) from None
        return Upstream(res.status_code, res.headers.get("content-type", ""), res.content)

    async def close(self) -> None:
        client, self._client = self._client, None
        if client is not None and not client.is_closed:
            await client.aclose()

    def _complain(self, reason: str) -> None:
        now = time.monotonic()
        if now - self._logged_at >= ESRI_LOG_EVERY_S:
            self._logged_at = now
            log.warning("Esri imagery tile unavailable: %s", reason)

    async def tile(self, z: int, x: int, y: int) -> bytes | None:
        """The tile's bytes, or None: no key, offline, outside the region (no upstream call), or the upstream failed.
        Esri answers an error with HTTP 200 and a text body, so only an `image/jpeg` is a tile."""
        if not self.configured or not in_region(z, x, y, ESRI_RULES):
            return None
        if self._semaphore is None:
            self._semaphore = asyncio.Semaphore(ESRI_CONCURRENCY)
        url = ESRI.upstream_template.format(z=z, y=y, x=x)
        if not url.startswith(ESRI.expected_prefix):
            return None
        try:
            async with self._semaphore:
                got = await self._fetcher(url, self._key or "")
        except TileUnavailable as exc:
            self._complain(str(exc))
            return None
        if (
            got.status != HTTPStatus.OK
            or not got.content_type.lower().startswith(ESRI.media_type)
            or not got.body
        ):
            self._complain(
                f"upstream answered HTTP {got.status} ({got.content_type.split(';')[0] or 'no content type'})"
            )
            return None
        return got.body


async def esri_view(request: Request) -> Response:
    return await _serve(request, request.app.state.esri, ESRI_CACHE_CONTROL)
