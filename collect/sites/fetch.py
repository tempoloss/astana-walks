"""Polite fetching of an official site: robots.txt, <= 1 request/s per domain, disk cache, link/sitemap discovery.

Every response goes through `collect.net.Net` (shared SQLite cache `.local/http_cache.sqlite`, retries, User-Agent
`astana-walks/0.1 (hackathon; an8kk.sa@gmail.com)`), so the verifier can later re-read the exact page a fact came from
without touching the network. Evidence URLs must be the URL passed to `fetch` (the cache key), not a redirect target.
"""

from __future__ import annotations

import gzip
import html as htmllib
import re
import threading
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from html.parser import HTMLParser
from urllib.parse import urldefrag, urljoin, urlsplit
from urllib.robotparser import RobotFileParser

from collect.net import USER_AGENT, NetError, default_net
from collect.sites.domains import registrable_domain
from collect.sites.jsonld import extract_jsonld_branches, jsonld_blocks

ROBOTS_AGENT = "astana-walks"
MIN_INTERVAL_S = 1.0
OK_STATUSES = (200, 404, 410)
LINK_KEYWORDS = re.compile(
    r"stores?|branch(?:es)?|filial\w*|филиал|адрес|contacts?|контакт|мекенжай|astana|астана|nur-sultan|нур-султан"
    r"|locations?|restaurants?|ресторан|shops?|магазин|график|режим|schedule|hours|where-to-buy|точки",
    re.IGNORECASE)
_ASSET = re.compile(r"\.(?:jpe?g|png|gif|svg|webp|pdf|zip|css|js|ico|mp4|docx?|xlsx?)(?:\?|$)", re.IGNORECASE)
_WS = re.compile(r"\s+")


def _iso(epoch: float) -> str:
    return datetime.fromtimestamp(epoch or time.time(), UTC).isoformat(timespec="seconds")


@dataclass
class Page:
    url: str  # requested URL = cache key = evidence URL
    status: int  # HTTP status; 0 = not fetched (robots / network error)
    text: str = ""
    content_type: str = ""
    fetched_at: str = ""  # ISO-8601 UTC of the network fetch (cache time for cached pages)
    from_cache: bool = False
    final_url: str = ""
    error: str = ""
    robots_blocked: bool = False

    @property
    def ok(self) -> bool:
        return self.status == 200


def decode_body(content: bytes, content_type: str = "") -> str:
    """HTML/JSON bytes -> str honouring the header / <meta> charset (windows-1251 is common on .kz sites)."""
    enc = None
    if m := re.search(r"charset=([\w-]+)", content_type or "", re.IGNORECASE):
        enc = m[1]
    elif mb := re.search(rb"<meta[^>]+charset=[\"']?([\w-]+)", content[:4096], re.IGNORECASE):
        enc = mb[1].decode("ascii", errors="ignore")
    try:
        return content.decode(enc or "utf-8", errors="replace")
    except LookupError:
        return content.decode("utf-8", errors="replace")


class _TextParser(HTMLParser):
    SKIP = {"script", "style", "noscript", "template", "svg", "head"}
    BLOCK = {"p", "div", "br", "li", "ul", "ol", "tr", "td", "th", "table", "section", "article", "header", "footer",
             "h1", "h2", "h3", "h4", "h5", "h6", "address", "dd", "dt", "dl", "span", "a", "b", "strong", "em", "i"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0

    def handle_starttag(self, tag, attrs):
        if tag in self.SKIP:
            self.skip += 1
        elif tag in self.BLOCK:
            self.parts.append(" ")

    def handle_endtag(self, tag):
        if tag in self.SKIP:
            self.skip = max(0, self.skip - 1)
        elif tag in self.BLOCK:
            self.parts.append(" ")

    def handle_data(self, data):
        if not self.skip:
            self.parts.append(data)


def visible_text(page_html: str) -> str:
    """Whitespace-normalised visible text of an HTML page (scripts/styles dropped, entities decoded)."""
    p = _TextParser()
    p.feed(page_html)
    p.close()
    return _WS.sub(" ", "".join(p.parts)).strip()


def page_links(page_html: str, base_url: str) -> list[tuple[str, str]]:
    """[(absolute URL, anchor text)] of every <a href>, fragments dropped."""
    out = []
    for m in re.finditer(r"<a\b[^>]*?\bhref\s*=\s*[\"']([^\"'#][^\"']*)[\"'][^>]*>(.*?)</a\s*>", page_html,
                         re.IGNORECASE | re.DOTALL):
        href = htmllib.unescape(m[1]).strip()
        if href.lower().startswith(("mailto:", "tel:", "javascript:")):
            continue
        out.append((urldefrag(urljoin(base_url, href))[0], visible_text(m[2])))
    return out


def relevant_links(page_html: str, base_url: str, limit: int = 40) -> list[str]:
    """Same-site links whose URL or text looks like a branch list / contacts / Astana page (keyword hits first)."""
    site = registrable_domain(base_url)
    scored: dict[str, int] = {}
    for url, text in page_links(page_html, base_url):
        if registrable_domain(url) != site or _ASSET.search(url) or not url.startswith("http"):
            continue
        hits = len(LINK_KEYWORDS.findall(url)) + len(LINK_KEYWORDS.findall(text))
        if hits:
            scored[url] = max(scored.get(url, 0), hits)
    return sorted(scored, key=lambda u: -scored[u])[:limit]


def _sitemap_locs(content: bytes) -> tuple[list[str], bool]:
    """(<loc> URLs, is_index) of a sitemap body (plain or gzip)."""
    if content[:2] == b"\x1f\x8b":
        try:
            content = gzip.decompress(content)
        except OSError:
            return [], False
    xml = content.decode("utf-8", errors="replace")
    locs = [htmllib.unescape(u).strip() for u in re.findall(r"<loc>\s*(.*?)\s*</loc>", xml, re.DOTALL)]
    return locs, "<sitemapindex" in xml


class SiteFetcher:
    """Robots-aware, rate-limited, cached GET. One instance per crawl run; safe to share across threads."""

    def __init__(self, net=None, min_interval: float = MIN_INTERVAL_S, sleep=time.sleep, clock=time.monotonic):
        self.net = net or default_net()
        self.min_interval = min_interval
        self._sleep, self._clock = sleep, clock
        self._last: dict[str, float] = {}
        self._lock = threading.Lock()
        self._robots: dict[str, tuple[RobotFileParser | None, str]] = {}  # origin -> (parser | None = allow all, status)
        self.pages: dict[str, Page] = {}

    # ---- plumbing --------------------------------------------------------------------------------

    def _throttle(self, host: str, delay: float = 0.0) -> None:
        """Reserve the next request slot of `host` (>= max(min_interval, robots Crawl-delay) after the previous)."""
        with self._lock:
            now = self._clock()
            slot = max(now, self._last.get(host, -1e9) + max(self.min_interval, delay))
            self._last[host] = slot
        if slot > now:
            self._sleep(slot - now)

    def _get(self, url: str, delay: float = 0.0) -> Page:
        resp = self.net.cached("GET", url)
        if resp is None:
            self._throttle(urlsplit(url).netloc, delay)
            try:
                resp = self.net.get(url, timeout=30.0, ok_statuses=OK_STATUSES, cache_statuses=OK_STATUSES,
                                    max_retries=2)
            except NetError as exc:
                return Page(url=url, status=0, error=str(exc)[:300])
        ctype = resp.headers.get("content-type", "")
        return Page(url=url, status=resp.status_code, text=decode_body(resp.content, ctype), content_type=ctype,
                    fetched_at=_iso(resp.fetched_at), from_cache=resp.from_cache, final_url=resp.url)

    # ---- robots.txt ------------------------------------------------------------------------------

    def _robots_for(self, url: str) -> tuple[RobotFileParser | None, str]:
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self._robots:
            page = self._get(f"{origin}/robots.txt")
            if page.status == 200:
                rp = RobotFileParser()
                rp.parse(page.text.splitlines())
                self._robots[origin] = (rp, "ok")
            elif page.status in (404, 410):  # RFC 9309: robots.txt absent = everything allowed
                self._robots[origin] = (None, "absent")
            else:  # 5xx / unreachable: crawling not allowed (RFC 9309 section 2.3.1.4)
                rp = RobotFileParser()
                rp.disallow_all = True
                self._robots[origin] = (rp, f"unreachable:{page.status or page.error[:80]}")
        return self._robots[origin]

    def allowed(self, url: str) -> bool:
        rp, _ = self._robots_for(url)
        return True if rp is None else rp.can_fetch(ROBOTS_AGENT, url)

    def robots_status(self, url: str) -> str:
        """'ok' (robots.txt read) | 'absent' (404: all allowed) | 'unreachable:...' (crawling not allowed)."""
        return self._robots_for(url)[1]

    def crawl_delay(self, url: str) -> float:
        rp, _ = self._robots_for(url)
        return float(rp.crawl_delay(ROBOTS_AGENT) or 0) if rp is not None else 0.0

    def sitemaps_from_robots(self, url: str) -> list[str]:
        rp, _ = self._robots_for(url)
        return list(rp.site_maps() or []) if rp is not None else []

    # ---- public API ------------------------------------------------------------------------------

    def fetch(self, url: str) -> Page:
        """GET `url` if robots.txt allows it. Never raises: failures come back as Page(status=0, error=...)."""
        if url in self.pages:
            return self.pages[url]
        if not self.allowed(url):
            page = Page(url=url, status=0, robots_blocked=True, error="disallowed by robots.txt")
        else:
            page = self._get(url, self.crawl_delay(url))
        self.pages[url] = page
        return page

    def cached_page(self, url: str) -> Page | None:
        """The cached page for `url`, or None. Never touches the network."""
        resp = self.net.cached("GET", url)
        if resp is None:
            return None
        ctype = resp.headers.get("content-type", "")
        return Page(url=url, status=resp.status_code, text=decode_body(resp.content, ctype), content_type=ctype,
                    fetched_at=_iso(resp.fetched_at), from_cache=True, final_url=resp.url)

    def jsonld_branches(self, url: str) -> list[dict]:
        page = self.fetch(url)
        return extract_jsonld_branches(page.text, url) if page.ok else []

    def sitemap_urls(self, site_url: str, pattern: re.Pattern = LINK_KEYWORDS, limit: int = 60,
                     max_sitemaps: int = 6) -> list[str]:
        """URLs from /sitemap.xml (and `Sitemap:` lines of robots.txt; indexes followed) matching `pattern`."""
        parts = urlsplit(site_url)
        origin = f"{parts.scheme}://{parts.netloc}"
        queue = [*dict.fromkeys([*self.sitemaps_from_robots(origin), f"{origin}/sitemap.xml"])]
        seen: set[str] = set()
        urls: list[str] = []
        while queue and len(seen) < max_sitemaps:
            sm = queue.pop(0)
            if sm in seen or not self.allowed(sm):
                continue
            seen.add(sm)
            page = self.fetch(sm)
            if page.status != 200:
                continue
            resp = self.net.cached("GET", sm)
            locs, is_index = _sitemap_locs(resp.content if resp is not None else page.text.encode())
            if is_index:
                queue.extend(locs)
            else:
                urls.extend(u for u in locs if pattern.search(u))
        return list(dict.fromkeys(urls))[:limit]

    def discover(self, site_url: str, limit: int = 40) -> list[str]:
        """Candidate branch/contact pages: keyword links on the home page, then matching sitemap URLs."""
        home = self.fetch(site_url)
        found = relevant_links(home.text, site_url, limit) if home.ok else []
        for u in self.sitemap_urls(site_url, limit=limit):
            if u not in found:
                found.append(u)
        return found[:limit]


__all__ = [
    "USER_AGENT", "Page", "SiteFetcher", "decode_body", "extract_jsonld_branches", "jsonld_blocks", "page_links",
    "relevant_links", "visible_text",
]
