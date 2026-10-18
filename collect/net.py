"""Polite shared HTTP layer for every collector.

* descriptive User-Agent with contact (Wikimedia bans generic UAs);
* per-host token bucket + concurrency cap (WDQS 1 concurrent / >=1 s gap, Wikimedia APIs <=5 req/s,
  Overpass 1 concurrent, Nominatim 1 req/s);
* ``Retry-After`` honoured, exponential backoff with full jitter on 429/5xx/timeouts, bounded retries;
* on-disk response cache (`.local/http_cache.sqlite`, key = method + url + body hash) so reruns never
  re-hit a server;
* checkpoint/resume store for batch jobs (same sqlite file);
* egress failover through the owner's VPS (SOCKS5, env ``WALKS_SOCKS``): home IP first, a host is moved to
  the proxy only after repeated 429/403 from that host, with a cool-down. This is failover, not
  round-robin evasion; every switch is logged to stderr.

Env: WALKS_SOCKS (proxy url, e.g. socks5://127.0.0.1:1081), WALKS_FORCE_SOCKS=1 (always use the proxy,
for testing), WALKS_REFRESH=1 (ignore cache reads, still write), WALKS_HTTP_CACHE (path or "off").
"""

from __future__ import annotations

import email.utils
import hashlib
import json
import os
import random
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from urllib.parse import urlencode, urlsplit

import httpx

USER_AGENT = "astana-walks/0.1 (hackathon; an8kk.sa@gmail.com)"
DEFAULT_SOCKS = "socks5://127.0.0.1:1081"
CACHE_PATH = Path(__file__).resolve().parents[1] / ".local" / "http_cache.sqlite"

RETRY_STATUSES = {429, 500, 502, 503, 504}
BLOCK_STATUSES = {429, 403}  # counted towards failover
MAX_RETRIES = 5
BACKOFF_CAP_S = 120.0
RETRY_AFTER_CAP_S = 300.0
FAILOVER_AFTER = 3  # consecutive 429/403 from one host before switching it to the proxy
FAILOVER_COOLDOWN_S = 900.0


class NetError(RuntimeError):
    pass


@dataclass(frozen=True)
class HostPolicy:
    rate: float  # sustained requests per second (token refill)
    burst: int = 1
    concurrency: int = 1
    backoff_base: float = 2.0
    group: str = ""  # hosts with the same group share one bucket (all Wikimedia APIs <= 5 req/s together)


# Matched by exact host first, then by suffix (".wikipedia.org").
HOST_POLICIES: dict[str, HostPolicy] = {
    "query.wikidata.org": HostPolicy(rate=1.0, burst=1, concurrency=1, backoff_base=5.0),
    "www.wikidata.org": HostPolicy(rate=5.0, burst=1, group="wikimedia-api"),
    "wikimedia.org": HostPolicy(rate=5.0, burst=1, group="wikimedia-api"),
    ".wikipedia.org": HostPolicy(rate=5.0, burst=1, group="wikimedia-api"),
    "overpass-api.de": HostPolicy(rate=0.2, burst=1, concurrency=1, backoff_base=10.0),
    "overpass.kumi.systems": HostPolicy(rate=0.2, burst=1, concurrency=1, backoff_base=10.0),
    "maps.mail.ru": HostPolicy(rate=0.2, burst=1, concurrency=1, backoff_base=10.0),
    "nominatim.openstreetmap.org": HostPolicy(rate=1.0, burst=1),
}
DEFAULT_POLICY = HostPolicy(rate=2.0, burst=2)


def policy_for(host: str) -> HostPolicy:
    if host in HOST_POLICIES:
        return HOST_POLICIES[host]
    for key, pol in HOST_POLICIES.items():
        if key.startswith(".") and host.endswith(key):
            return pol
    return DEFAULT_POLICY


def log(msg: str) -> None:
    print(f"[net] {msg}", file=sys.stderr, flush=True)


class _Bucket:
    """Token bucket + concurrency semaphore for one host."""

    def __init__(self, pol: HostPolicy):
        self.pol = pol
        self.tokens = float(pol.burst)
        self.stamp = time.monotonic()
        self.lock = threading.Lock()
        self.sem = threading.Semaphore(pol.concurrency)

    def acquire(self) -> None:
        while True:
            with self.lock:
                now = time.monotonic()
                self.tokens = min(self.pol.burst, self.tokens + (now - self.stamp) * self.pol.rate)
                self.stamp = now
                if self.tokens >= 1.0:
                    self.tokens -= 1.0
                    return
                wait = (1.0 - self.tokens) / self.pol.rate
            time.sleep(wait)


@dataclass
class HostState:
    blocks: int = 0  # consecutive 429/403 on the direct route
    proxy_until: float = 0.0  # monotonic time until which this host goes through the proxy
    proxy_down_until: float = 0.0
    network: int = 0
    cache_hits: int = 0
    via_proxy: int = 0
    retries: int = 0


@dataclass
class Response:
    status_code: int
    content: bytes
    headers: dict
    url: str
    from_cache: bool = False
    via: str = "direct"  # direct | socks | cache
    fetched_at: float = 0.0  # epoch seconds the body was fetched (cache time for cached responses)

    @property
    def text(self) -> str:
        return self.content.decode("utf-8", errors="replace")

    def json(self):
        return json.loads(self.content)


def _retry_after(headers) -> float | None:
    raw = headers.get("retry-after")
    if not raw:
        return None
    raw = raw.strip()
    if raw.isdigit():
        return float(raw)
    try:
        dt = email.utils.parsedate_to_datetime(raw)
        return max(0.0, dt.timestamp() - time.time())
    except (TypeError, ValueError):
        return None


class Net:
    def __init__(self, cache_path: str | Path | None = None, socks: str | None = None):
        env_cache = os.environ.get("WALKS_HTTP_CACHE")
        target = cache_path if cache_path is not None else (env_cache or CACHE_PATH)
        self._db: sqlite3.Connection | None = None
        if str(target).lower() != "off":
            path = Path(target)
            path.parent.mkdir(parents=True, exist_ok=True)
            self._db = sqlite3.connect(path, check_same_thread=False)
            self._db.execute("PRAGMA journal_mode=WAL")
            self._db.executescript(
                "CREATE TABLE IF NOT EXISTS http_cache(key TEXT PRIMARY KEY, status INTEGER, body BLOB,"
                " headers TEXT, url TEXT, fetched_at REAL);"
                "CREATE TABLE IF NOT EXISTS checkpoint(job TEXT, key TEXT, value TEXT, PRIMARY KEY(job, key));"
            )
            self._db.commit()
        self.socks = socks or os.environ.get("WALKS_SOCKS") or None
        self.force_socks = os.environ.get("WALKS_FORCE_SOCKS") == "1"
        if self.force_socks and not self.socks:
            self.socks = DEFAULT_SOCKS
        self.refresh = os.environ.get("WALKS_REFRESH") == "1"
        self._clients: dict[str, httpx.Client] = {}
        self._buckets: dict[str, _Bucket] = {}
        self.hosts: dict[str, HostState] = {}
        self.checkpoint_hits: dict[str, int] = {}
        self._lock = threading.Lock()

    # ---- plumbing -------------------------------------------------------------------------------

    def _client(self, route: str) -> httpx.Client:
        client = self._clients.get(route)
        if client is None:
            kwargs = {"headers": {"User-Agent": USER_AGENT, "Accept-Encoding": "gzip"}, "follow_redirects": True}
            if route == "socks":
                kwargs["proxy"] = self.socks
            client = httpx.Client(**kwargs)
            self._clients[route] = client
        return client

    def _bucket(self, host: str) -> _Bucket:
        pol = policy_for(host)
        key = pol.group or host
        with self._lock:
            if key not in self._buckets:
                self._buckets[key] = _Bucket(pol)
            return self._buckets[key]

    def _state(self, host: str) -> HostState:
        return self.hosts.setdefault(host, HostState())

    def _route(self, host: str) -> str:
        if not self.socks:
            return "direct"
        now = time.monotonic()
        st = self._state(host)
        if self.force_socks:
            return "socks"
        if st.proxy_until > now and st.proxy_down_until <= now:
            return "socks"
        if st.proxy_until and st.proxy_until <= now:
            st.proxy_until = 0.0
            st.blocks = 0
            log(f"FAILOVER-END host={host} proxy->direct (cool-down over)")
        return "direct"

    def _note_block(self, host: str, status: int) -> None:
        st = self._state(host)
        st.blocks += 1
        if self.socks and st.blocks >= FAILOVER_AFTER and st.proxy_until <= time.monotonic():
            st.proxy_until = time.monotonic() + FAILOVER_COOLDOWN_S
            log(f"FAILOVER host={host} direct->socks after {st.blocks} consecutive HTTP 429/403 "
                f"(last {status}); proxy {self.socks}, cool-down {FAILOVER_COOLDOWN_S:.0f}s")

    # ---- cache ----------------------------------------------------------------------------------

    @staticmethod
    def cache_key(method: str, url: str, body: bytes) -> str:
        return f"{method} {url} {hashlib.sha256(body).hexdigest()}"

    def _cache_get(self, key: str, ttl: float | None) -> Response | None:
        if self._db is None or self.refresh:
            return None
        row = self._db.execute(
            "SELECT status, body, headers, url, fetched_at FROM http_cache WHERE key=?", (key,)
        ).fetchone()
        if not row:
            return None
        if ttl is not None and time.time() - row[4] > ttl:
            return None
        return Response(row[0], row[1], json.loads(row[2]), row[3], from_cache=True, via="cache", fetched_at=row[4])

    def _cache_put(self, key: str, resp: Response) -> None:
        if self._db is None:
            return
        headers = {k: v for k, v in resp.headers.items() if k.lower() in ("content-type", "etag", "last-modified")}
        with self._lock:
            self._db.execute(
                "INSERT OR REPLACE INTO http_cache VALUES (?,?,?,?,?,?)",
                (key, resp.status_code, resp.content, json.dumps(headers), resp.url, time.time()),
            )
            self._db.commit()

    # ---- request --------------------------------------------------------------------------------

    def request(
        self,
        method: str,
        url: str,
        *,
        params: dict | None = None,
        data: dict | None = None,
        timeout: float = 60.0,
        ttl: float | None = None,
        cache_statuses: tuple[int, ...] = (200,),
        ok_statuses: tuple[int, ...] = (200,),
        max_retries: int = MAX_RETRIES,
    ) -> Response:
        """Cached, rate-limited request. Raises NetError unless the final status is in ok_statuses."""
        if params:
            url = f"{url}{'&' if '?' in url else '?'}{urlencode(params, doseq=True)}"
        body = urlencode(data).encode() if data else b""
        key = self.cache_key(method, url, body)
        host = urlsplit(url).hostname or ""
        st = self._state(host)

        cached = self._cache_get(key, ttl)
        if cached is not None:
            st.cache_hits += 1
            return cached

        bucket = self._bucket(host)
        last = "no attempt"
        for attempt in range(max_retries + 1):
            route = self._route(host)
            bucket.sem.acquire()
            try:
                bucket.acquire()
                st.network += 1
                if route == "socks":
                    st.via_proxy += 1
                raw = self._client(route).request(
                    method, url, content=body or None,
                    headers={"Content-Type": "application/x-www-form-urlencoded"} if body else None,
                    timeout=timeout,
                )
                resp = Response(raw.status_code, raw.content, dict(raw.headers), str(raw.url), via=route,
                                fetched_at=time.time())
                retry_after = _retry_after(raw.headers)
            except (httpx.TimeoutException, httpx.TransportError) as exc:
                last = f"{type(exc).__name__}: {exc}"
                if route == "socks":
                    st.proxy_down_until = time.monotonic() + FAILOVER_COOLDOWN_S
                    log(f"FAILOVER-ABORT host={host} proxy unusable ({last}); back to direct for "
                        f"{FAILOVER_COOLDOWN_S:.0f}s")
                resp, retry_after = None, None
            finally:
                bucket.sem.release()

            if resp is not None:
                if resp.status_code in BLOCK_STATUSES:
                    self._note_block(host, resp.status_code)
                elif resp.status_code < 400:
                    st.blocks = 0
                if resp.status_code in ok_statuses or (
                    resp.status_code not in RETRY_STATUSES and resp.status_code not in BLOCK_STATUSES
                ):
                    if resp.status_code in cache_statuses:
                        self._cache_put(key, resp)
                    if resp.status_code in ok_statuses:
                        return resp
                    raise NetError(f"{method} {url}: HTTP {resp.status_code} {resp.text[:200]!r}")
                last = f"HTTP {resp.status_code}"

            if attempt == max_retries:
                break
            st.retries += 1
            if retry_after is not None:
                delay = min(retry_after, RETRY_AFTER_CAP_S) + random.uniform(0, 1)
            else:
                ceiling = min(BACKOFF_CAP_S, policy_for(host).backoff_base * 2**attempt)
                delay = random.uniform(ceiling / 2, ceiling)
            log(f"retry host={host} {last} attempt={attempt + 1}/{max_retries} sleep={delay:.1f}s route={route}")
            time.sleep(delay)
        raise NetError(f"{method} {url}: failed after {max_retries + 1} attempts ({last})")

    def get(self, url: str, **kw) -> Response:
        return self.request("GET", url, **kw)

    def post(self, url: str, **kw) -> Response:
        return self.request("POST", url, **kw)

    def cached(self, method: str, url: str, *, data: dict | None = None, ttl: float | None = None) -> Response | None:
        """The cached response of an identical request, or None. Never touches the network."""
        body = urlencode(data).encode() if data else b""
        resp = self._cache_get(self.cache_key(method, url, body), ttl)
        if resp is not None:
            self._state(urlsplit(url).hostname or "").cache_hits += 1
        return resp

    # ---- checkpoint / resume --------------------------------------------------------------------

    def checkpoint(self, job: str) -> "Checkpoint":
        return Checkpoint(self, job)

    # ---- reporting ------------------------------------------------------------------------------

    def summary(self) -> dict[str, dict]:
        return {
            h: {"network": s.network, "cache_hits": s.cache_hits, "via_proxy": s.via_proxy, "retries": s.retries}
            for h, s in sorted(self.hosts.items())
        }

    def log_summary(self, label: str) -> None:
        parts = [f"{h}: net={v['network']} cache={v['cache_hits']} proxy={v['via_proxy']}"
                 for h, v in self.summary().items()]
        ck = ", ".join(f"{j}={n}" for j, n in sorted(self.checkpoint_hits.items()))
        log(f"{label} cumulative requests -> " + ("; ".join(parts) or "none")
            + (f" | checkpoint hits (batch results reused): {ck}" if ck else ""))

    def close(self) -> None:
        for c in self._clients.values():
            c.close()
        if self._db is not None:
            self._db.close()


@dataclass
class Checkpoint:
    """Persistent key -> JSON value store for resumable batch jobs."""

    net: Net
    job: str
    _mem: dict = field(default_factory=dict)

    def get(self, key: str):
        db = self.net._db
        if self.net.refresh:
            return None
        if db is None:
            return self._mem.get(key)
        row = db.execute("SELECT value FROM checkpoint WHERE job=? AND key=?", (self.job, key)).fetchone()
        if row:
            self.net.checkpoint_hits[self.job] = self.net.checkpoint_hits.get(self.job, 0) + 1
            return json.loads(row[0])
        return None

    def put(self, key: str, value) -> None:
        db = self.net._db
        if db is None:
            self._mem[key] = value
            return
        with self.net._lock:
            db.execute("INSERT OR REPLACE INTO checkpoint VALUES (?,?,?)",
                       (self.job, key, json.dumps(value, ensure_ascii=False)))
            db.commit()

    def done(self) -> set[str]:
        db = self.net._db
        if db is None:
            return set(self._mem)
        return {r[0] for r in db.execute("SELECT key FROM checkpoint WHERE job=?", (self.job,))}


_default: Net | None = None


def default_net() -> Net:
    """Process-wide Net so all stages of one build share buckets, failover state and stats."""
    global _default
    if _default is None:
        _default = Net()
    return _default
