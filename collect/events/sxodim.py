"""sxodim.com/astana/events/{today,week}: server-rendered event cards (robots.txt: `Disallow:` empty).

A card says «<price>, <date>[ в HH:MM], <venue>, <street>, <house>»; the parser stores that line as evidence, the
title, the link, and the facts split out of it. Cards without a date (restaurant offers) are skipped.
"""

from __future__ import annotations

import html as htmllib
import re
from datetime import date

from collect.events import model
from collect.events.model import clean, ev

SOURCE = "sxodim.com"
URLS = ("https://sxodim.com/astana/events/today", "https://sxodim.com/astana/events/week")

_CARD = re.compile(r'<div class="impression-card\b[^"]*"([^>]*)>(.*?)<div class="impression-card-info">\s*(.*?)\s*</div>',
                   re.DOTALL)
_ATTR = re.compile(r'data-(id|title|category)="([^"]*)"')
_LINK = re.compile(r'<a href="([^"]+)" class="impression-card-title">')
_STREET = re.compile(
    r"^(?:ул\.?|улица|пр\.?|просп\.?|проспект|пр-т|шоссе|мкр\.?|микрорайон|к\.|көш\.?|бульвар|б-р|наб\.?|пер\.?|"
    r"пл\.?|площадь|тракт)\s|(?:шоссе|даңғылы|көшесі|проспект)\b", re.IGNORECASE)
_CITY = re.compile(r"^(?:г\.\s*)?астана(?:\s+қаласы)?$", re.IGNORECASE)
_MEET = re.compile(r"^место сбора:\s*", re.IGNORECASE)


def split_venue(rest: str) -> tuple[str | None, str | None, str | None]:
    """(venue name, hall / detail, address) of «Venue, street, house[, floor ...]»; any may be None.

    The address starts at the first part that opens with a street word, else one part before the first part that
    is a house number («Рыба моей мечты, Бейбітшілік, 20/1»); what precedes it is the venue (first part) and its
    detail. «Астана қаласы» and «Место сбора:» are dropped."""
    parts = [p for p in (clean(x) for x in re.split(r",\s+", rest)) if p and not _CITY.match(p)]
    if not parts:
        return None, None, None
    start = next((i for i, p in enumerate(parts) if _STREET.search(p)), None)
    if start is None:
        house = next((i for i, p in enumerate(parts) if i >= 1 and re.match(r"\d", p)), None)
        start = max(house - 1, 0) if house is not None else len(parts)
    head, addr = parts[:start], parts[start:]
    head = [_MEET.sub("", h) for h in head]
    name = head[0] if head else None
    hall = ", ".join(head[1:]) or None
    return name, hall, ", ".join(addr) or None


def parse(page_html: str, url: str, fetched_at: str, today: date) -> tuple[list[dict], dict[str, int]]:
    """(events, counters) of one listing page."""
    events, skipped = [], {"no_date": 0, "no_venue": 0}
    for m in _CARD.finditer(page_html):
        attrs = dict(_ATTR.findall(m[1]))
        info_raw = htmllib.unescape(m[3])
        info = clean(info_raw)
        link = _LINK.search(m[2])
        title = clean(htmllib.unescape(attrs.get("title", "")))
        found = model.find_when(info, today)
        if not (title and attrs.get("id") and link):
            continue
        if found is None:
            skipped["no_date"] += 1
            continue
        when, a, b = found
        price_text = info[:a].strip(" ,") or None
        name, hall, address = split_venue(info[b:].lstrip(" ,"))
        if not name:
            skipped["no_venue"] += 1
            continue
        evidence = [
            *ev("title", url, title, fetched_at),
            *ev(("when", "venue", "address") if address else ("when", "venue"), url,
                htmllib.unescape(m[3]), fetched_at),
        ]
        if price_text:
            evidence += ev("price", url, htmllib.unescape(m[3]), fetched_at)
        kw: dict = {"title": title, "url": link[1], "fetched_at": fetched_at, "category": attrs.get("category"),
                    "venue_": model.venue(name, address=address, hall=hall), "evidence_": evidence,
                    "price_text": price_text, "price_from": model.min_price(price_text) if price_text else None}
        if when.is_range or when.time is None:
            event = model.make_event(SOURCE, attrs["id"], kind="run", date_from=when.first, date_to=when.last, **kw)
        else:
            event = model.make_event(SOURCE, attrs["id"], kind="event", start=model.local_dt(when.first, when.time),
                                     **kw)
        events.append(event)
    return events, skipped
