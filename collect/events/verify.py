"""Deterministic verifier of event fact-cards, in the manner of `collect.sites.verify`.

Every evidence snippet must be found (whitespace-normalised) in the cached page it names; every fact must be
covered by evidence of its field **and** be derivable from that snippet (title inside the title snippet, the time /
day numbers inside the `when` snippet, the address inside the address snippet, the coordinates equal to the numbers
of the coordinates snippet, ...). A fact that fails is dropped; an event that loses its title, time or venue is dropped
whole. Venue joins are re-checked with the same name / address rules that made them.

    uv run python -m collect.events --verify-only          # re-verify data/events.json against the cache
"""

from __future__ import annotations

import copy
import json
import re
from collections import Counter

from collect.events import model
from collect.events.venues import VenueIndex, address_key, addresses_agree, keys_agree, poi_name_keys, venue_keys
from collect.sites.fetch import Page, SiteFetcher
from collect.sites.store import norm_ws
from collect.sites.verify import page_variants

_QUOTES = re.compile(r"[«»\"“”„'`]")
_ZW = re.compile(r"[\u200b\u200c\u200d\ufeff]")
_FLOAT = re.compile(r"-?\d+\.\d+")
_ISO = re.compile(r"\d{4}-\d{2}-\d{2}t\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}")
_PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')


def norm(text: str) -> str:
    return norm_ws(_QUOTES.sub("", _ZW.sub("", text or ""))).casefold()


def page_text_views(page_text: str) -> list[str]:
    """`page_variants` plus the quote-unescaped source and the decoded Next.js data chunks (youticket)."""
    views = page_variants(Page(url="", status=200, text=page_text))
    views.append(norm_ws(page_text.replace('\\"', '"')))
    chunks = []
    for m in _PUSH.finditer(page_text):
        try:
            chunks.append(json.loads(m[1]))
        except ValueError:
            continue
    if chunks:
        views.append(norm_ws("".join(chunks)))
    return views


class Verifier:
    def __init__(self, fetcher: SiteFetcher, network: bool = False):
        self.fetcher, self.network = fetcher, network
        self._views: dict[str, list[str] | None] = {}

    def views(self, url: str) -> list[str] | None:
        if url not in self._views:
            page = self.fetcher.cached_page(url)
            if page is None and self.network:
                page = self.fetcher.fetch(url)
            self._views[url] = page_text_views(page.text) if page is not None and page.status == 200 else None
        return self._views[url]

    def snippet_found(self, url: str, snippet: str) -> bool:
        needle = norm_ws(snippet)
        return bool(needle) and any(needle in v for v in self.views(url) or [])


# ---- value-in-snippet checks ---------------------------------------------------------------------------------


def _snips(e: dict, *fields: str) -> list[str]:
    return [norm(x["snippet"]) for x in e["evidence"] if x["field"] in fields]


def _has_day(text: str, day: int) -> bool:
    return re.search(rf"(?<![\d:])0?{day}(?![\d:])", text) is not None


def _has_time(text: str, hhmm: str) -> bool:
    h, m = hhmm.split(":")
    return re.search(rf"(?<!\d)0?{int(h)}:{m}(?!\d)", text) is not None


def _when_ok(e: dict) -> bool:
    snips = _snips(e, "when")
    if not snips:
        return False
    joined = " ".join(snips)
    kind = e["kind"]
    if kind == "standing":
        return norm(e.get("hours_raw") or "") in joined
    if kind == "run":
        return all(_has_day(joined, model.parse_iso(e[k] + "T00:00:00").day) for k in ("date_from", "date_to"))
    if kind == "sessions":
        days = all(_has_day(joined, model.parse_iso(e[k] + "T00:00:00").day) for k in ("date_from", "date_to"))
        return days and all(_has_time(joined, model.parse_iso(s).strftime("%H:%M")) for s in e["sessions"])
    start = model.parse_iso(e["start"])
    if not (_has_day(joined, start.day) and _has_time(joined, start.strftime("%H:%M"))):
        return False
    if e.get("end"):
        end = model.parse_iso(e["end"])
        return any(model.parse_iso(m[0].upper()) == end for s in snips for m in _ISO.finditer(s))
    return True


def _coords_ok(e: dict) -> bool:
    nums = [float(x) for s in _snips(e, "coords") for x in _FLOAT.findall(s)]
    v = e["venue"]
    return any(abs(n - v["lat"]) < 1e-4 for n in nums) and any(abs(n - v["lon"]) < 1e-4 for n in nums)


def _fact_ok(e: dict, fact: str) -> bool:
    v = e["venue"]
    if fact == "title":
        return any(norm(e["title"]) in s for s in _snips(e, "title"))
    if fact == "when":
        return _when_ok(e)
    if fact == "venue":
        joined = " ".join(_snips(e, "venue"))
        return norm(v["name"]) in joined and (not v.get("hall") or norm(v["hall"]) in joined)
    if fact == "address":
        return any(norm(v["address"]) in s for s in _snips(e, "address"))
    if fact == "price":
        return any(norm(e["price_text"]) in s for s in _snips(e, "price"))
    if fact == "coords":
        return _coords_ok(e)
    raise KeyError(fact)


def _join_ok(e: dict, index: VenueIndex | None) -> bool:
    v = e["venue"]
    if not v.get("poi_id"):
        return True
    poi = index.by_id(v["poi_id"]) if index else None
    if poi is None:
        return index is None
    if v.get("match") == "name":
        ok = keys_agree(venue_keys(v["name"]), poi_name_keys(poi))
    else:
        ok = v.get("match") == "address" and addresses_agree(address_key(v.get("address")),
                                                             address_key(poi.get("address")))
    if v.get("coords_source") == "poi":
        ok = ok and abs(poi["lat"] - v["lat"]) < 1e-6 and abs(poi["lon"] - v["lon"]) < 1e-6
    return ok


def verify_event(event: dict, verifier: Verifier, index: VenueIndex | None = None) -> tuple[dict | None, Counter]:
    """(cleaned copy | None when dropped, counters). Pure with respect to the input."""
    stats: Counter = Counter()
    e = copy.deepcopy(event)
    errs = model.validate_event(e)
    if errs:
        stats["dropped_schema"] += 1
        return None, stats
    good = []
    for ev_ in e["evidence"]:
        stats["evidence_total"] += 1
        if verifier.views(ev_["url"]) is None:
            stats["evidence_page_not_cached"] += 1
        if verifier.snippet_found(ev_["url"], ev_["snippet"]):
            stats["evidence_ok"] += 1
            good.append(ev_)
        else:
            stats["evidence_dropped"] += 1
    e["evidence"] = good
    v = e["venue"]
    for fact in ("title", "when", "venue"):
        if not _fact_ok(e, fact):
            stats[f"dropped_{fact}"] += 1
            return None, stats
    if v.get("address") and not _fact_ok(e, "address"):
        stats["fact_dropped_address"] += 1
        v["address"] = None
    if e.get("price_text") and not _fact_ok(e, "price"):
        stats["fact_dropped_price"] += 1
        e["price_text"] = e["price_from"] = None
    if v.get("coords_source") == "page" and not _fact_ok(e, "coords"):
        stats["fact_dropped_coords"] += 1
        v.update(lat=None, lon=None, coords_source=None, poi_id=None, poi_name=None, match=None)
    if not _join_ok(e, index):
        stats["join_dropped"] += 1
        v.update(poi_id=None, poi_name=None, match=None)
        if v.get("coords_source") == "poi":
            v.update(lat=None, lon=None, coords_source=None)
    stats["events_ok"] += 1
    return e, stats


def verify_all(events: list[dict], verifier: Verifier, index: VenueIndex | None = None) -> tuple[list[dict], Counter]:
    total: Counter = Counter()
    kept = []
    for event in events:
        out, stats = verify_event(event, verifier, index)
        total.update(stats)
        if out is not None:
            kept.append(out)
    return kept, total
