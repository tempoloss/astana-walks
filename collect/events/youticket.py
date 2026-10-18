"""youticket.kz event pages (robots.txt: `Allow: /`, sitemap listed): the ticketing site of Astana venues.

The sitemap lists every event (`/events/<slug>`); a page gives the city, the venue, its address and coordinates, the
first session and the price; an `OPEN` page (a museum) gives its weekly schedule instead of a session. Only pages of
the city `astana` are kept. Dates come from the page text; the session end from the `SeoEndDate` field of the
page's embedded data.
"""

from __future__ import annotations

import html as htmllib
import json
import re
from datetime import date, datetime

from collect.events import model
from collect.events.model import clean, ev
from collect.sites.fetch import visible_text
from collect.sites.hours import to_osm

SOURCE = "youticket.kz"
SITEMAP_URL = "https://youticket.kz/sitemap.xml"

_PUSH = re.compile(r'self\.__next_f\.push\(\[1,("(?:[^"\\]|\\.)*")\]\)')
_SLUG = re.compile(r"https://youticket\.kz/events/([^<\"/]+)</loc>")
_M = "|".join(model.MONTHS_RU)
_WHEN = re.compile(rf"Дата\s+(\d{{1,2}})\s+({_M})\s+(\d{{4}})\s+Время\s+(\d{{1,2}}:\d{{2}})")
_VENUE = re.compile(r"Место проведения Площадка (.+?) Адрес (.+?) Открыть на карте")
_HOURS = re.compile(r"График работы (\S.{2,30}?\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2})")
_PRICE = re.compile(r"от\s+\d[\d ]*\s*₸")
_COORDS = re.compile(r"\?q=(-?\d+\.\d+),(-?\d+\.\d+)")


def slugs(sitemap_xml: str) -> list[str]:
    """Event slugs of the sitemap (the Russian URLs, no locale prefix)."""
    return sorted(set(_SLUG.findall(sitemap_xml)))


def embedded_data(page_html: str) -> dict | None:
    """The event object of the page's embedded Next.js data (`"data":{"Id":...}`); None when absent."""
    chunks = []
    for m in _PUSH.finditer(page_html):
        try:
            chunks.append(json.loads(m[1]))
        except ValueError:
            continue
    text = "".join(chunks)
    i = text.find('"data":{"Id":')
    if i < 0:
        return None
    try:
        obj, _ = json.JSONDecoder().raw_decode(text[i + len('"data":'):])
    except ValueError:
        return None
    return obj if isinstance(obj, dict) else None


def _city(data: dict) -> str:
    city = data.get("City")
    return str(city.get("Code", "")) if isinstance(city, dict) else ""


def parse(page_html: str, url: str, fetched_at: str) -> dict | None:
    data = embedded_data(page_html)
    if not data or _city(data) != "astana":
        return None
    text = clean(htmllib.unescape(visible_text(page_html)))
    title = clean(str(data.get("NameRu") or ""))
    vm = _VENUE.search(text)
    if not title or title not in text or not vm:
        return None
    name, address = clean(vm[1]), clean(vm[2])
    snippet_venue = vm[0]
    cm = _COORDS.search(page_html)
    lat, lon = (float(cm[1]), float(cm[2])) if cm and model.in_astana(float(cm[1]), float(cm[2])) else (None, None)
    evidence = [*ev("title", url, title, fetched_at), *ev(("venue", "address"), url, snippet_venue, fetched_at)]
    if lat is not None:
        evidence += ev("coords", url, cm[0], fetched_at)
    price = _PRICE.search(text)
    price_text = clean(price[0]) if price else None
    if price:
        evidence += ev("price", url, price[0], fetched_at)
    ven = model.venue(name, address=address, lat=lat, lon=lon)
    common = {"title": title, "url": url, "fetched_at": fetched_at, "venue_": ven, "price_text": price_text,
              "price_from": model.min_price(price_text) if price_text else None,
              "category": ", ".join(c for c in data.get("Categories", []) if isinstance(c, str)) or None}
    key = str(data.get("Code") or url.rsplit("/", 1)[-1])
    wm = _WHEN.search(text)
    if data.get("Type") == "OPEN":
        hm = _HOURS.search(text)
        raw = clean(hm[1]) if hm else None
        osm = to_osm(raw) if raw else None
        if not osm:
            return None
        evidence += ev("when", url, hm[0], fetched_at)
        return model.make_event(SOURCE, key, kind="standing", evidence_=evidence, hours_raw=raw, hours_osm=osm, **common)
    if not wm:
        return None
    start = model.local_dt(date(int(wm[3]), model.MONTHS_RU[wm[2]], int(wm[1])), wm[4])
    evidence += ev("when", url, wm[0], fetched_at)
    end = _end(data, start)
    if end:
        evidence += ev("when", url, f'"SeoEndDate":"{data["SeoEndDate"]}"', fetched_at)
    return model.make_event(SOURCE, key, kind="event", evidence_=evidence, start=start, end=end, **common)


def _end(data: dict, start: datetime) -> datetime | None:
    end = model.parse_iso(str(data.get("SeoEndDate") or ""))
    return end if end and end > start and (end - start).total_seconds() <= 12 * 3600 else None
