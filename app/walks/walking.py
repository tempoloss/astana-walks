"""Real pedestrian times from Valhalla (by default the public FOSSGIS instance; WALKS_VALHALLA_URL points to one's
own), with a disk cache and a straight-line fallback.

Used ONLY for the final 1-3 recommendations and the legs of the mini-route (retrieval stays haversine).

Privacy: each request sends two coordinate pairs to a third party - the user's already-rounded (3 decimals,
~100 m) location and a POI. The disk cache `app/.local/walk_cache.json` stores only legs whose endpoints are
PUBLIC points (POI-to-POI, or a demo preset as origin); legs that start at a user-chosen location live in
memory for the process only, so the file never contains somebody's location.

Usage policy of the FOSSGIS service: identify the client, be gentle (max ~1 request/s) - hence the User-Agent
and the minimum interval between network calls. Its terms allow commercial use only when routing is not a
substantial part of the offer: a public stand runs its own Valhalla (deploy/vps/valhalla) and sets
WALKS_VALHALLA_URL=http://127.0.0.1:8002/route; the pause between calls is then 0.
"""

from __future__ import annotations

import json
import math
import os
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Literal

from .envcfg import offline
from .i18n import METHOD, method_label
from .radius import haversine_m

VALHALLA_URL = "https://valhalla1.openstreetmap.de/route"
USER_AGENT = "astana-walks/0.1 (hackathon demo; pedestrian routing for a handful of legs)"
TIMEOUT_S = 5.0
MIN_INTERVAL_S = 1.1  # politeness: at most one network request per ~second
COOLDOWN_S = 60.0  # after a failure skip the network for a minute (a request must not stall 3x5 s)
MAX_MEM_LEGS = (
    5000  # legs a router remembers in memory (user-origin legs are never written to disk)
)


def valhalla_url() -> str:
    """The route endpoint: WALKS_VALHALLA_URL (the full URL, `.../route`), else the public FOSSGIS instance."""
    return os.environ.get("WALKS_VALHALLA_URL", "").strip() or VALHALLA_URL


WALK_M_PER_MIN = 75.0  # 4.5 km/h
FALLBACK_DETOUR = 1.3  # straight line x 1.3 ~ street distance when routing is unavailable

DEFAULT_CACHE_PATH = Path(__file__).resolve().parents[1] / ".local" / "walk_cache.json"
SHIPPED_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "walk_cache.json"  # tracked

Method = Literal["valhalla", "straight"]
Point = tuple[float, float]

# How a time was obtained, as shown to the user next to every walking time (Russian; the UI uses
# walks.i18n.method_label in the user's language).
METHOD_LABEL = {m: method_label(m, "ru") for m in METHOD}


@dataclass(frozen=True)
class Leg:
    distance_m: int  # street distance (valhalla) or straight-line distance (fallback)
    minutes: int
    method: Method
    from_cache: bool = False


def straight_leg(a: Point, b: Point) -> Leg:
    d = haversine_m(a[0], a[1], b[0], b[1])
    return Leg(round(d), max(1, math.ceil(d * FALLBACK_DETOUR / WALK_M_PER_MIN)), "straight")


def _key(a: Point, b: Point) -> str:
    return f"{a[0]:.4f},{a[1]:.4f}>{b[0]:.4f},{b[1]:.4f}"


def _rkey(a: Point, b: Point) -> str:
    return _key(b, a)


def _first_shape(trip: dict) -> str:
    """The encoded street line of the first leg of a Valhalla trip ('' when the answer carries none)."""
    legs = trip.get("legs")
    shape = (
        legs[0].get("shape")
        if isinstance(legs, list) and legs and isinstance(legs[0], dict)
        else None
    )
    return shape if isinstance(shape, str) else ""


def decode_polyline6(code: str) -> list[Point]:
    """Valhalla's encoded polyline (Google's algorithm, 1e-6 precision) as (lat, lon) points."""
    pts: list[Point] = []
    i = lat = lon = 0
    while i < len(code):
        for axis in (0, 1):
            shift = result = 0
            while True:
                b = ord(code[i]) - 63
                i += 1
                result |= (b & 0x1F) << shift
                shift += 5
                if b < 0x20:
                    break
            delta = ~(result >> 1) if result & 1 else result >> 1
            if axis == 0:
                lat += delta
            else:
                lon += delta
        pts.append((lat / 1e6, lon / 1e6))
    return pts


class WalkingRouter:
    """Pedestrian leg lookup: memory -> disk cache -> Valhalla -> straight-line fallback."""

    def __init__(
        self,
        cache_path: Path | str | bool | None = None,
        *,
        enabled: bool = True,
        opener: Callable = urllib.request.urlopen,
        sleep: Callable[[float], None] = time.sleep,
        clock: Callable[[], float] = time.monotonic,
        timeout: float = TIMEOUT_S,
        network: bool = True,
        min_interval: float | None = None,
        url: str | None = None,
        read_only: bool = False,
    ):
        self.enabled, self.network = enabled, network
        self._disk: Path | None = (
            None if cache_path is False else Path(cache_path) if cache_path else DEFAULT_CACHE_PATH
        )
        self._opener, self._sleep, self._clock = opener, sleep, clock
        self._url = url or valhalla_url()
        # the politeness pause is for the shared public server; one's own instance needs none
        if min_interval is None:
            min_interval = MIN_INTERVAL_S if self._url == VALHALLA_URL else 0.0
        self._timeout, self._min_interval = timeout, min_interval
        self._read_only = read_only  # memory only: the disk cache is read, never written
        self._mem: dict[str, dict] = {}
        self._disk_loaded = False
        self._disk_data: dict[str, dict] = {}
        self._last_call: float | None = None
        self._down_until = 0.0
        self.network_calls = 0

    # ---------------------------------------------------------------- cache

    def _load_disk(self) -> None:
        if self._disk_loaded:
            return
        self._disk_loaded = True
        if self._disk is None or not self._disk.is_file():
            return
        try:
            data = json.loads(self._disk.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._disk_data = {
                    k: v for k, v in data.items() if isinstance(v, dict) and "m" in v and "s" in v
                }
        except (OSError, ValueError):
            self._disk_data = {}

    def _lookup(self, a: Point, b: Point) -> dict | None:
        self._load_disk()
        for store in (self._mem, self._disk_data):
            for k in (
                _key(a, b),
                _rkey(a, b),
            ):  # walking is close to symmetric: reuse the reverse leg
                if k in store:
                    return store[k]
        return None

    def _store(self, a: Point, b: Point, entry: dict, persist: bool) -> None:
        k = _key(a, b)
        if k not in self._mem and len(self._mem) >= MAX_MEM_LEGS:
            del self._mem[
                next(iter(self._mem))
            ]  # the oldest leg goes: public input must not grow the process
        self._mem[k] = entry
        if persist and self._disk is not None and not self._read_only:
            self._load_disk()
            self._disk_data[k] = entry
            try:
                self._disk.parent.mkdir(parents=True, exist_ok=True)
                tmp = self._disk.with_suffix(".tmp")
                tmp.write_text(
                    json.dumps(self._disk_data, ensure_ascii=False, sort_keys=True),
                    encoding="utf-8",
                )
                os.replace(tmp, self._disk)
            except OSError:
                pass  # a read-only checkout must not break serving

    # ---------------------------------------------------------------- network

    def _fetch(self, a: Point, b: Point) -> dict | None:
        now = self._clock()
        if now < self._down_until:
            return None
        if self._last_call is not None and now - self._last_call < self._min_interval:
            self._sleep(self._min_interval - (now - self._last_call))
        body = json.dumps(
            {
                "locations": [{"lat": a[0], "lon": a[1]}, {"lat": b[0], "lon": b[1]}],
                "costing": "pedestrian",
                "directions_options": {"units": "kilometers"},
            }
        ).encode("utf-8")
        req = urllib.request.Request(
            self._url,
            data=body,
            method="POST",
            headers={"Content-Type": "application/json", "User-Agent": USER_AGENT},
        )
        self._last_call = self._clock()
        self.network_calls += 1
        try:
            with self._opener(req, timeout=self._timeout) as resp:
                trip = json.loads(resp.read().decode("utf-8"))["trip"]
            summary = trip["summary"]
            meters = round(float(summary["length"]) * 1000)
            seconds = float(summary["time"])
            shape = _first_shape(trip)
        except urllib.error.HTTPError as exc:
            if 400 <= exc.code < 500 and exc.code != 429:
                return None  # e.g. "no route found" for this pair: only this leg falls back, the service is fine
            self._down_until = self._clock() + COOLDOWN_S
            return None
        except (urllib.error.URLError, TimeoutError, OSError, ValueError, KeyError, TypeError):
            self._down_until = self._clock() + COOLDOWN_S
            return None
        entry = {"m": meters, "s": round(seconds), "d": date.today().isoformat()}
        if shape:
            entry["g"] = (
                shape  # Valhalla's encoded polyline (precision 6): the street line of the leg, for the map
            )
        return entry

    # ---------------------------------------------------------------- API

    def reset_cooldown(self) -> None:
        """Forget a recent network failure so the next leg tries Valhalla again (used by the warm-up script)."""
        self._down_until = 0.0

    def leg(self, a: Point, b: Point, *, persist: bool = False) -> Leg:
        """Walking leg a -> b (points rounded to 4 dp for the cache key). `persist`: both endpoints are public
        points, so the result may be written to the disk cache."""
        a, b = (round(a[0], 4), round(a[1], 4)), (round(b[0], 4), round(b[1], 4))
        if self.enabled:
            hit = self._lookup(a, b)
            if hit is not None:
                return Leg(
                    int(hit["m"]), max(1, math.ceil(hit["s"] / 60)), "valhalla", from_cache=True
                )
            fetched = (
                None if offline() or not self.network else self._fetch(a, b)
            )  # offline / cache-only: cache hits or straight line only
            if fetched is not None:
                self._store(a, b, fetched, persist)
                return Leg(fetched["m"], max(1, math.ceil(fetched["s"] / 60)), "valhalla")
        return straight_leg(a, b)

    def shape(self, a: Point, b: Point) -> list[Point] | None:
        """The street line of a leg a -> b, only when this router already has it (memory / disk cache of a leg that
        came with its shape): never a network call. None: the map draws a straight, faint line instead."""
        a, b = (round(a[0], 4), round(a[1], 4)), (round(b[0], 4), round(b[1], 4))
        self._load_disk()
        for store in (self._mem, self._disk_data):
            for key, reverse in ((_key(a, b), False), (_rkey(a, b), True)):
                code = store.get(key, {}).get("g")
                if isinstance(code, str) and code:
                    pts = decode_polyline6(code)
                    return pts[::-1] if reverse else pts
        return None

    def line(self, a: Point, b: Point) -> list[Point] | None:
        """The street line of a leg for the map: the cached one, else (only with a router of one's own configured,
        never the shared public server: a page must not become a burst of calls to it) one request that is kept in
        memory. None: the map draws a straight, faint line."""
        found = self.shape(a, b)
        if found is not None or not self.enabled or not self.network or offline():
            return found
        if self._url == VALHALLA_URL:
            return None
        a, b = (round(a[0], 4), round(a[1], 4)), (round(b[0], 4), round(b[1], 4))
        fetched = self._fetch(a, b)
        if fetched is None or not fetched.get("g"):
            return None
        self._store(a, b, fetched, False)
        return decode_polyline6(fetched["g"])


_default: WalkingRouter | None = None


def default_router() -> WalkingRouter:
    """Process-wide router. WALKS_WALKING=off disables the network; WALKS_WALK_CACHE overrides the cache path
    ('off' = no disk cache)."""
    global _default
    if _default is None:
        cache = os.environ.get("WALKS_WALK_CACHE", "").strip()
        _default = WalkingRouter(
            False if cache.lower() == "off" else cache or None,
            enabled=os.environ.get("WALKS_WALKING", "").strip().lower() != "off",
        )
    return _default


def offline_router() -> WalkingRouter:
    """A router that never touches the network or the disk: every leg is the straight-line estimate."""
    return WalkingRouter(False, enabled=False)


def own_router() -> bool:
    """True when WALKS_VALHALLA_URL names a router of one's own (not the public FOSSGIS one): the stand's wording and
    the pinned demo router follow it."""
    return valhalla_url() != VALHALLA_URL


def shipped_router() -> WalkingRouter:
    """The demo preset's router (WALKS_DEMO_PIN): legs from the tracked data/walk_cache.json, nothing written there;
    a leg that is not in the file is the straight-line estimate, so the same answers on every machine. Only with
    WALKS_VALHALLA_URL naming one's own router (the public stand) does a leg that is not in the file go to it, and
    its answer lives in memory only. The public FOSSGIS server is never asked on this path."""
    return WalkingRouter(SHIPPED_CACHE_PATH, network=own_router(), read_only=True)
