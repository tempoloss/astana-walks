"""Reference crawlers for four official sites; the pattern a per-domain crawl agent follows.

    fetcher = SiteFetcher()                      # robots.txt + 1 req/s + cache
    page = fetcher.fetch(url)                    # evidence url == this url
    text = visible_text(page.text)               # or page.text for attributes / JSON
    store.make_branch(name, [store.evidence(field, url, <verbatim slice of text>)], method, confidence, ...)
    store.save_facts(store.new_record(domain, robots_ok=..., pages=[...], branches=[...], notes=...))

Usage: uv run python -m collect.sites.crawl_demo [domain ...]   (kfc.kz greenmall.kz nmrk.kz khanshatyr.com)
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.sites import store
from collect.sites.domains import registrable_domain
from collect.sites.fetch import Page, SiteFetcher, visible_text

ASTANA_LAT, ASTANA_LON = (50.9, 51.4), (71.0, 71.8)
KFC_STORES = "https://kfc.kz/stores"
_CARD = re.compile(r'<div class="card h-100"[^>]*?\bdata-id="(?P<id>\d+)"\s+data-lat="(?P<lat>[\d.]+)"\s+'
                   r'data-lng="(?P<lng>[\d.]+)"\s+data-address="(?P<addr>[^"]*)"(?P<body>.*?)(?=<div class="card h-100"|\Z)',
                   re.DOTALL)
_ZW = re.compile(r"[\u200b\ufeff]")
_PLUS_CODE = re.compile(r"^[0-9A-Z]{4,8}\+[0-9A-Z]{2,}")
WEEKLY = re.compile(r"(?P<w>понедельник [\d:-]+ вторник [\d:-]+ среда [\d:-]+ четверг [\d:-]+ пятница [\d:-]+ "
                    r"суббота [\d:-]+ воскресенье [\d:-]+)")


def kfc(fetcher: SiteFetcher) -> tuple[list[dict], list[str], str]:
    """kfc.kz/stores: one card per branch with data-lat/data-lng/data-address and a weekly pick-up schedule."""
    page = fetcher.fetch(KFC_STORES)
    if not page.ok:
        return [], [], f"{KFC_STORES}: status {page.status} {page.error}"
    branches, seen = [], set()
    for m in _CARD.finditer(page.text):
        lat, lng = float(m["lat"]), float(m["lng"])
        title = re.search(r'class="card-title mainColor">([^<]+)<', m["body"])
        if m["id"] in seen or not title or not title[1].startswith("KFC Астана"):
            continue
        if not (ASTANA_LAT[0] < lat < ASTANA_LAT[1] and ASTANA_LON[0] < lng < ASTANA_LON[1]):
            continue
        seen.add(m["id"])
        card = page.text[m.start():m.end()]
        takeaway = re.search(rf'id="takeaway_store_{m["id"]}".*?</table>', m["body"], re.DOTALL)
        weekly = re.search(WEEKLY, visible_text(takeaway[0])) if takeaway else None
        geo_raw = re.search(r'data-lat="[\d.]+"\s+data-lng="[\d.]+"', card)[0]
        addr_raw = re.search(r'data-address="[^"]*"', card)[0]
        address = _ZW.sub("", m["addr"]).strip()
        ev = [store.evidence("name", KFC_STORES, title[1], page.fetched_at),
              store.evidence("geo", KFC_STORES, geo_raw, page.fetched_at)]
        if address and not _PLUS_CODE.match(address):
            ev.append(store.evidence("address", KFC_STORES, addr_raw, page.fetched_at))
        else:
            address = None
        if weekly:
            ev.append(store.evidence("opening_hours", KFC_STORES, weekly["w"], page.fetched_at))
        branches.append(store.make_branch(
            title[1], ev, "html", 0.8, address=address, lat=lat, lon=lng,
            opening_hours_raw=weekly["w"] if weekly else None, url=KFC_STORES))
    notes = ("Hours = the 'Еженедельные часы самовывоза' (weekly pick-up) table of each card, which equals the card's "
             "'Часы работы'; delivery hours ('Часы Доставки') are a different table and are not used. Phone on the "
             "page is the chain call-centre short number 7797 (not branch-specific) and is not stored.")
    return branches, [KFC_STORES], notes


def _text_branch(page: Page, name: str, patterns: dict[str, str], method: str = "html",
                 confidence: float = 0.75) -> dict | None:
    """One branch from a contacts page: each regex of `patterns` ({field: regex with group 'v'}) is matched against
    the page's visible text; the matched text is the evidence snippet and group 'v' the value."""
    text = visible_text(page.text)
    title = re.search(r"<title[^>]*>(.*?)</title>", page.text, re.DOTALL | re.IGNORECASE)
    ev, values = [], {}
    for field, rx in patterns.items():
        m = re.search(rx, text)
        if m:
            ev.append(store.evidence({"hours": "opening_hours"}.get(field, field), page.url, m[0], page.fetched_at))
            values[field] = m["v"]
    if title and name.lower() in re.sub(r"\s+", " ", title[1]).lower():
        ev.append(store.evidence("name", page.url, re.sub(r"\s+", " ", title[0]), page.fetched_at))
    elif re.search(re.escape(name), text):
        ev.append(store.evidence("name", page.url, name, page.fetched_at))
    if not values:
        return None
    return store.make_branch(name, ev, method, confidence, address=values.get("address"), phone=values.get("phone"),
                             opening_hours_raw=values.get("hours"), url=page.url)


def greenmall(fetcher: SiteFetcher):
    url = "https://greenmall.kz/ru/contacts"
    page = fetcher.fetch(url)
    b = _text_branch(page, "Green Mall", {
        "address": r"Адрес: (?:[^,]+, ){0,4}(?P<v>г\. Астана, ул\. Сыганак д\.17Б НП13)",
        "hours": r"График работы ТРЦ: (?P<v>[cс] \d{1,2}:\d{2} до \d{1,2}:\d{2})",
        "phone": r"Ресепшн: (?P<v>\+7\(771\)033-82-85)",
    }) if page.ok else None
    return [b] if b else [], [url], "Parking hours (круглосуточно) on the same page belong to the car park, not the mall."


def nmrk(fetcher: SiteFetcher):
    url = "https://nmrk.kz/ru/about-museum/contacts/"
    page = fetcher.fetch(url)
    b = _text_branch(page, "Национального музея", {
        "hours": r"Рабочее время Национального музея РК (?P<v>\d{2}:\d{2} - \d{2}:\d{2} Вт-Вс)",
        "phone": r"Ресепшн: (?P<v>\+7 7172 \(91-90-35\))",
        "address": r"(?P<v>г\. Астана, проспект Тауелсиздик 54)",
    }) if page.ok else None
    if b:
        b["name"] = "Национальный музей Республики Казахстан"
        b["evidence"] = [e for e in b["evidence"] if e["field"] != "name"] + [
            store.evidence("name", url, "Национального музея РК", page.fetched_at)]
    return [b] if b else [], [url], (
        "Page also says 'Последний вторник месяца санитарный день' (closed on the last Tuesday of the month) and "
        "'Касса: 10:00 - 17:00'; opening_hours_osm does not encode these exceptions.")


def khanshatyr(fetcher: SiteFetcher):
    url = "https://www.khanshatyr.com/ru/contacts"
    page = fetcher.fetch(url)
    b = _text_branch(page, "Хан Шатыр", {
        "address": r"(?P<v>г\. Астана, пр\. Туран 37)",
        "hours": r"(?P<v>ЕЖЕДНЕВНО: 10:00 — 22:00; Пт, Сб: 10:00 — 23:00)",
        "phone": r"(?P<v>\+7 \(717\) 257-26-26)",
    }) if page.ok else None
    if b and not any(e["field"] == "name" for e in b["evidence"]):
        b = None
    return [b] if b else [], [url], (
        "The page lists a second schedule (administration, Дс-Жм 10:00-18:00 with lunch break); it is not the mall's "
        "visiting hours and is not used.")


CRAWLERS = {"kfc.kz": kfc, "greenmall.kz": greenmall, "nmrk.kz": nmrk, "khanshatyr.com": khanshatyr}


def crawl(domain: str, fetcher: SiteFetcher, facts_dir: Path | None = None) -> dict:
    branches, pages, notes = CRAWLERS[domain](fetcher)
    mine = [p for u, p in fetcher.pages.items() if registrable_domain(u) == domain]
    robots_ok = not any(p.robots_blocked for p in mine)
    if not robots_ok:
        branches, notes = [], "robots.txt forbids (or is unreachable for) the pages needed; nothing stored"
    rec = store.new_record(domain, robots_ok=robots_ok, pages=[p.url for p in mine if p.ok], branches=branches,
                           notes=notes, fetched_at=max((p.fetched_at for p in mine if p.ok), default=None))
    store.save_facts(rec, facts_dir)
    return rec


def main(argv: list[str] | None = None) -> int:
    sys.stdout.reconfigure(encoding="utf-8")
    domains = (argv if argv is not None else sys.argv[1:]) or list(CRAWLERS)
    fetcher = SiteFetcher()
    for d in domains:
        rec = crawl(d, fetcher)
        hrs = sum(1 for b in rec["branches"] if b["opening_hours_osm"])
        print(f"[crawl_demo] {d}: robots_ok={rec['robots_ok']} branches={len(rec['branches'])} with_osm_hours={hrs}")
        for b in rec["branches"][:30]:
            print(f"    {b['name']} | {b['address']} | {b['phone']} | {b['lat']},{b['lon']} | "
                  f"{(b['opening_hours_raw'] or '')[:60]} -> {b['opening_hours_osm']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
