"""Crawl, join, de-duplicate, verify and write `data/events.json` (+ `data/events_stats.json`).

    uv run python -m collect.events                 # polite crawl of every source, then verify, then write
    uv run python -m collect.events --only sxodim.com,alem.ai
    uv run python -m collect.events --verify-only   # re-verify the shipped file against the HTTP cache (no network)

Every request goes through `collect.sites.fetch.SiteFetcher`: robots.txt of the host is read first (a disallowed or
unreachable-robots URL is never fetched), >= 1 s between requests to a host (more when robots.txt asks: inastana.kz
Crawl-delay 5), the shared User-Agent with a contact, a disk cache. Pages of an afisha go stale within hours, so a
cached page is reused only while younger than `--ttl-hours` (default 6): rerunning within that window makes no request
and writes the same file. A source that fails keeps its previous, still-current events (incremental); a source that
answers replaces its events.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.events import alem, inastana, model, qazaq, sxodim, telegram, youticket
from collect.events.dedupe import dedupe
from collect.events.verify import Verifier, verify_all
from collect.events.venues import VenueIndex, apply_join
from collect.net import NetError
from collect.sites.fetch import Page, SiteFetcher, _iso, decode_body

ROOT = Path(__file__).resolve().parents[2]
EVENTS_PATH = ROOT / "data" / "events.json"
STATS_PATH = ROOT / "data" / "events_stats.json"
POI_PATH = ROOT / "data" / "poi.enriched.json"
SCHEMA = 1
DEFAULT_TTL_H = 6.0
STANDING_MAX_AGE = timedelta(days=14)
MAX_DETAIL_PAGES = 40  # film pages of inastana.kz / posters / youticket events per run


class EventFetcher(SiteFetcher):
    """SiteFetcher whose cache reads expire after `ttl_s` (an afisha is stale within hours). The verifier reads the
    cache without a ttl (`cached_page`), so evidence is always checked against the page the event came from."""

    def __init__(self, ttl_s: float, **kw):
        super().__init__(**kw)
        self.ttl_s = ttl_s

    def _get(self, url: str, delay: float = 0.0) -> Page:
        resp = self.net.cached("GET", url, ttl=self.ttl_s)
        if resp is None:
            self._throttle(url.split("/")[2], delay)
            try:
                resp = self.net.get(url, timeout=30.0, ok_statuses=(200, 404, 410), cache_statuses=(200, 404, 410),
                                    max_retries=2)
            except NetError as exc:
                return Page(url=url, status=0, error=str(exc)[:300])
        ctype = resp.headers.get("content-type", "")
        return Page(url=url, status=resp.status_code, text=decode_body(resp.content, ctype), content_type=ctype,
                    fetched_at=_iso(resp.fetched_at), from_cache=resp.from_cache, final_url=resp.url)


class Result:
    """What one source produced: events, the sources (event `source` values) it owns, page counters, notes."""

    def __init__(self, owns: set[str]):
        self.owns = owns
        self.events: list[dict] = []
        self.ok = False
        self.pages = 0
        self.fetched_at = ""
        self.skipped: Counter = Counter()
        self.notes: list[str] = []
        self.robots = ""

    def note_page(self, page: Page, fetcher: SiteFetcher) -> bool:
        """Count a fetched page; False (and a note) when it is unusable."""
        self.robots = self.robots or fetcher.robots_status(page.url)
        if page.robots_blocked:
            self.notes.append(f"robots.txt disallows {page.url}")
            return False
        if not page.ok:
            self.notes.append(f"{page.url}: {'HTTP ' + str(page.status) if page.status else page.error[:80]}")
            return False
        self.pages += 1
        self.fetched_at = max(self.fetched_at, page.fetched_at)
        return True


def _page_dt(page: Page) -> datetime:
    return datetime.fromisoformat(page.fetched_at)


def crawl_sxodim(f: SiteFetcher, today: date, limit: int) -> Result:
    r = Result({sxodim.SOURCE})
    seen: dict[str, dict] = {}
    for url in sxodim.URLS:
        page = f.fetch(url)
        if not r.note_page(page, f):
            continue
        r.ok = True
        events, skipped = sxodim.parse(page.text, url, page.fetched_at, today)
        r.skipped.update(skipped)
        for e in events:
            seen.setdefault(e["id"], e)
    r.events = list(seen.values())
    return r


def crawl_inastana(f: SiteFetcher, today: date, limit: int) -> Result:
    r = Result({inastana.SOURCE})
    index = f.fetch(inastana.INDEX_URL)
    if not r.note_page(index, f):
        return r
    r.ok = True
    for _, _, url in inastana.film_links(index.text)[:limit]:
        page = f.fetch(url)
        if not r.note_page(page, f):
            r.skipped["page_failed"] += 1
            continue
        r.events += inastana.parse_detail(page.text, url, page.fetched_at, today, _page_dt(page))
    return r


def crawl_qazaq(f: SiteFetcher, today: date, limit: int) -> Result:
    r = Result({qazaq.SOURCE})
    listing = f.fetch(qazaq.LIST_URL)
    if not r.note_page(listing, f):
        return r
    r.ok = True
    contacts = f.fetch(qazaq.CONTACTS_URL)
    address = qazaq.contact_address(contacts.text) if r.note_page(contacts, f) else None
    for item in qazaq.poster_list(listing.text)[:limit]:
        url = qazaq.BASE + item["path"]
        page = f.fetch(url)
        detail = page.text if r.note_page(page, f) else None
        event = qazaq.make(item, detail, qazaq.LIST_URL, url, listing.fetched_at, listing.text, address,
                           qazaq.CONTACTS_URL, contacts.fetched_at or listing.fetched_at)
        if event:
            r.events.append(event)
    return r


def crawl_youticket(f: SiteFetcher, today: date, limit: int) -> Result:
    r = Result({youticket.SOURCE})
    sitemap = f.fetch(youticket.SITEMAP_URL)
    if not r.note_page(sitemap, f):
        return r
    r.ok = True
    for slug in youticket.slugs(sitemap.text)[:limit]:
        url = f"https://youticket.kz/events/{slug}"
        page = f.fetch(url)
        if not r.note_page(page, f):
            r.skipped["page_failed"] += 1
            continue
        event = youticket.parse(page.text, url, page.fetched_at)
        if event:
            r.events.append(event)
        else:
            r.skipped["not_astana_or_unparsed"] += 1
    return r


def crawl_alem(f: SiteFetcher, today: date, limit: int) -> Result:
    r = Result({alem.SOURCE})
    page = f.fetch(alem.URL)
    if r.note_page(page, f):
        r.ok = True
        if event := alem.parse(page.text, alem.URL, page.fetched_at):
            r.events.append(event)
    return r


def crawl_telegram(f: SiteFetcher, today: date, limit: int) -> Result:
    r = Result({f"t.me/{c}" for c in telegram.CHANNELS})
    for channel in telegram.CHANNELS:
        url = f"https://t.me/s/{channel}"
        page = f.fetch(url)
        if r.note_page(page, f):
            r.ok = True
            r.events += telegram.parse(page.text, url, page.fetched_at, today)
    return r


CRAWLERS = {
    sxodim.SOURCE: crawl_sxodim, inastana.SOURCE: crawl_inastana, qazaq.SOURCE: crawl_qazaq,
    youticket.SOURCE: crawl_youticket, alem.SOURCE: crawl_alem, "t.me": crawl_telegram,
}


def expired(e: dict, now: datetime) -> bool:
    """True when nothing of the event is left to attend (kept slightly past its end: the app filters exactly)."""
    grace = timedelta(hours=3)
    kind = e["kind"]
    if kind == "event":
        end = model.parse_iso(e.get("end")) or model.parse_iso(e["start"])
        return end + grace < now
    if kind == "run":
        return date.fromisoformat(e["date_to"]) < now.date()
    if kind == "sessions":
        return max(model.parse_iso(s) for s in e["sessions"]) + grace < now
    fetched = model.parse_iso(e["fetched_at"])
    return fetched is None or now - fetched > STANDING_MAX_AGE


def load_pois(path: Path = POI_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def load_events(path: Path = EVENTS_PATH) -> dict | None:
    return json.loads(path.read_text(encoding="utf-8")) if path.exists() else None


def build(results: dict[str, Result], previous: dict | None, pois: list[dict], verifier: Verifier, now: datetime) \
        -> tuple[dict, dict]:
    """(events document, stats) from the crawl results and the previous document."""
    index = VenueIndex(pois)
    fresh: list[dict] = []
    owned: set[str] = set()
    for r in results.values():
        if r.ok:
            owned |= r.owns
            fresh += r.events
    retained = [e for e in (previous or {}).get("events", []) if e["source"] not in owned]
    stats: dict = {"verify": Counter(), "dropped_expired": 0}
    candidates = []
    for e in fresh + retained:
        if expired(e, now):
            stats["dropped_expired"] += 1
        else:
            candidates.append(e)
    for e in candidates:
        apply_join(e, index)
    events, vstats = verify_all(candidates, verifier, index)
    events = dedupe(events)
    events.sort(key=lambda e: (e["source"], e["id"]))
    stats["verify"] = dict(sorted(vstats.items()))
    per_source: dict[str, dict] = {}
    for name, r in results.items():
        per_source[name] = {
            "ok": r.ok, "pages": r.pages, "fetched_at": r.fetched_at or None, "robots": r.robots or None,
            "skipped": dict(sorted(r.skipped.items())), "notes": r.notes[:10], "parsed": len(r.events),
        }
    by_src = Counter(e["source"] for e in events)
    for name, info in per_source.items():
        info["events_kept"] = sum(n for s, n in by_src.items() if s in results[name].owns)
    retained_ids = {e["id"] for e in retained}
    stats.update(
        sources=per_source, events=len(events), retained_from_previous=sum(e["id"] in retained_ids for e in events),
        kinds=dict(Counter(e["kind"] for e in events)),
        venue_joined=sum(e["venue"]["poi_id"] is not None for e in events),
        venue_joined_by_name=sum(e["venue"]["match"] == "name" for e in events),
        venue_joined_by_address=sum(e["venue"]["match"] == "address" for e in events),
        with_coordinates=sum(e["venue"]["lat"] is not None for e in events),
        coordinates_from_page=sum(e["venue"]["coords_source"] == "page" for e in events),
        without_coordinates=sum(e["venue"]["lat"] is None for e in events),
        merged_duplicates=sum(len(e["also_listed"]) for e in events),
    )
    times = [info["fetched_at"] for name, info in per_source.items() if info["fetched_at"] and results[name].ok]
    kept_old = [e["fetched_at"] for e in events if e["id"] in retained_ids]
    fetched = min([*times, *kept_old], default=None)
    doc = {"schema": SCHEMA, "tz": "UTC+05:00", "fetched_at": fetched,
           "sources": {
               **{n: v for n, v in (previous or {}).get("sources", {}).items() if n not in per_source},
               **{n: {"fetched_at": i["fetched_at"], "pages": i["pages"], "events": i["events_kept"]}
                  for n, i in per_source.items()}},
           "events": events}
    return doc, stats


def write_json(path: Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, ensure_ascii=False, indent=1, sort_keys=False) + "\n", encoding="utf-8")
    tmp.replace(path)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", help="comma-separated sources: " + ", ".join(CRAWLERS))
    ap.add_argument("--verify-only", action="store_true", help="re-verify data/events.json against the cache")
    ap.add_argument("--ttl-hours", type=float, default=DEFAULT_TTL_H, help="reuse cached pages younger than this")
    ap.add_argument("--limit", type=int, default=MAX_DETAIL_PAGES, help="detail pages per source")
    ap.add_argument("--out", type=Path, default=EVENTS_PATH)
    ap.add_argument("--stats", type=Path, default=STATS_PATH)
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    now = model.now_local()
    fetcher = EventFetcher(args.ttl_hours * 3600)
    pois = load_pois()
    previous = load_events(args.out)
    if args.verify_only:
        if previous is None:
            print(f"{args.out}: no such file", file=sys.stderr)
            return 1
        kept, vstats = verify_all(previous["events"], Verifier(fetcher), VenueIndex(pois))
        dropped = len(previous["events"]) - len(kept)
        print(f"verify-only: {len(kept)} of {len(previous['events'])} events verified, dropped {dropped}; "
              f"{dict(sorted(vstats.items()))}")
        return 1 if dropped or vstats["evidence_dropped"] else 0
    names = args.only.split(",") if args.only else list(CRAWLERS)
    unknown = [n for n in names if n not in CRAWLERS]
    if unknown:
        ap.error(f"unknown source(s) {unknown}; known: {', '.join(CRAWLERS)}")
    results: dict[str, Result] = {}
    for name in names:
        print(f"[events] {name} ...", file=sys.stderr, flush=True)
        try:
            results[name] = CRAWLERS[name](fetcher, now.date(), args.limit)
        except Exception as exc:  # one broken source must not lose the others  # noqa: BLE001
            results[name] = Result({name})
            results[name].notes.append(f"crashed: {type(exc).__name__}: {exc}"[:200])
    doc, stats = build(results, previous, pois, Verifier(fetcher), now)
    write_json(args.out, doc)
    write_json(args.stats, stats)
    print(json.dumps({k: stats[k] for k in ("events", "kinds", "venue_joined", "with_coordinates", "merged_duplicates")},
                     ensure_ascii=False))
    for name, info in stats["sources"].items():
        print(f"  {name}: ok={info['ok']} pages={info['pages']} parsed={info['parsed']} kept={info['events_kept']} "
              f"skipped={info['skipped']} {info['notes'][:2]}")
    print(f"  verify: {stats['verify']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
