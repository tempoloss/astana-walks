"""inastana.kz/afisha: the only server-rendered source of cinema sessions in Astana (robots.txt: Crawl-delay 5).

The index lists films / shows; each page `/afisha/<id>/<slug>` lists, per cinema or venue, its address, the run
(«15 - 18 октября» or one date) and the session times (`title` of a session holds its price list). One event per
(film, venue). The sessions are the ones the page shows on the day it was fetched: a run is clamped to that day.
"""

from __future__ import annotations

import html as htmllib
import re
from datetime import date, datetime

from collect.events import model
from collect.events.model import clean, ev
from collect.sites.fetch import visible_text

SOURCE = "inastana.kz"
INDEX_URL = "https://www.inastana.kz/afisha"

_FILM = re.compile(r'<div class="(?:card|event)__title">\s*<a href="(https://www\.inastana\.kz/afisha/(\d+)/[^"#]+)">(.*?)</a>',
                   re.DOTALL)
_H1 = re.compile(r"<h1>(.*?)</h1>", re.DOTALL)
_BLOCK = '<div class="yt-video-actions event-info">'
_VENUE = re.compile(r'event-line__link">\s*<a href="[^"]*/catalog/index/(\d+)/[^"]*">(.*?)</a>', re.DOTALL)
_ADDRESS = re.compile(r'svg-map-placeholder"></use>\s*</svg>\s*</div>\s*<div[^>]*>\s*(.*?)\s*</div>', re.DOTALL)
_DATE = re.compile(r'event-line__date">\s*(.*?)\s*</div>', re.DOTALL)
_TIME = re.compile(r'<(?:span|a)\b([^>]*class="compact-schedule__time[^"]*"[^>]*)>\s*(\d{1,2}:\d{2})\s*</(?:span|a)>')
_TITLE_ATTR = re.compile(r'title="([^"]*)"')
_AMOUNT = re.compile(r"(?<!\d)(\d{1,3}(?:\s\d{3})+|\d+),(\d{2})(?!\d)")


def film_links(index_html: str) -> list[tuple[str, str, str]]:
    """[(film id, title, url)] of the index, order kept."""
    seen: dict[str, tuple[str, str, str]] = {}
    for m in _FILM.finditer(index_html):
        seen.setdefault(m[2], (m[2], clean(htmllib.unescape(visible_text(m[3]))), m[1]))
    return list(seen.values())


def _amounts(title_attr: str) -> list[int]:
    """Prices of a session: its `title` is «<id>\\n1 300,00, 1 500,00, ...»."""
    body = htmllib.unescape(title_attr).partition("\n")[2]
    return [int(re.sub(r"\s", "", m[1])) for m in _AMOUNT.finditer(body)]


def parse_detail(page_html: str, url: str, fetched_at: str, today: date, fetched_dt: datetime) -> list[dict]:
    """Events (one per venue block) of a film / show page."""
    h1 = _H1.search(page_html)
    title = clean(htmllib.unescape(visible_text(h1[1]))) if h1 else ""
    film_id = re.search(r"/afisha/(\d+)/", url)
    events = []
    for chunk in page_html.split(_BLOCK)[1:]:
        chunk = chunk.split('<div id="event-images">')[0]
        venue_m, addr_m, date_m = _VENUE.search(chunk), _ADDRESS.search(chunk), _DATE.search(chunk)
        times = [((t[1] if (t := _TITLE_ATTR.search(m[1])) else ""), m[2]) for m in _TIME.finditer(chunk)]
        if not (title and film_id and venue_m and date_m and times):
            continue
        name = clean(htmllib.unescape(visible_text(venue_m[2])))
        address = clean(htmllib.unescape(visible_text(addr_m[1]))) if addr_m else None
        date_text = clean(visible_text(date_m[1]))
        found = model.find_when(date_text, today)
        if found is None:
            continue
        when = found[0]
        day = min(max(fetched_dt.astimezone(model.TZ).date(), when.first), when.last)
        sessions = [model.local_dt(day, hhmm) for _, hhmm in times if model.valid_time(hhmm)]
        priced = [(min(a), t) for t, _ in times if (a := _amounts(t))]
        cheapest = min(priced, default=None)
        venue_snippet = f"{name} {address}" if address else name
        when_snippet = f"{date_text} " + " ".join(hhmm for _, hhmm in times)
        evidence = [*ev("title", url, title, fetched_at), *ev("venue", url, venue_snippet, fetched_at),
                    *ev("when", url, when_snippet, fetched_at)]
        if address:
            evidence += ev("address", url, venue_snippet, fetched_at)
        price_text = None
        if cheapest:
            price_text = clean(htmllib.unescape(cheapest[1]).partition("\n")[2])
            evidence += ev("price", url, price_text, fetched_at)
        events.append(model.make_event(
            SOURCE, f"{film_id[1]}:{venue_m[1]}", title=title, kind="sessions", url=url, fetched_at=fetched_at,
            venue_=model.venue(name, address=address), evidence_=evidence, date_from=when.first, date_to=when.last,
            sessions=sessions, price_text=price_text, price_from=cheapest[0] if cheapest else None))
    return events
