"""qazaqconcert.kz/posters: the concert organisation's own poster list (robots.txt: `Allow: /`).

The list gives date, hall and title; the poster page gives the start time; /contacts gives the street address of the
Astana hall. Posters of halls in other cities («(Алматы қаласы, ...)») are dropped. The hall is named in the site's
own navigation («"Qazaqstan" ОКЗ», kept in an HTML comment of every page): that name is the venue, the poster's
«Үлкен зал» / «Камералық зал» is the hall.
"""

from __future__ import annotations

import html as htmllib
import re
from datetime import date

from collect.events import model
from collect.events.model import clean, ev
from collect.sites.fetch import visible_text

SOURCE = "qazaqconcert.kz"
BASE = "https://qazaqconcert.kz"
LIST_URL = f"{BASE}/posters"
CONTACTS_URL = f"{BASE}/contacts"
VENUE_NAME = '"Qazaqstan" ОКЗ'

_ITEM = re.compile(r'<div class="afisha_item">(.*?)</div>\s*</div>', re.DOTALL)
_DATE = re.compile(r'<p class="afisha_date">(.*?)</p>', re.DOTALL)
_TITLE = re.compile(r'<a class="afisha_title" href="(/poster/[^"]+)">(.*?)</a>', re.DOTALL)
_DMY = re.compile(r"(\d{2})\.(\d{2})\.(\d{4})")
_TIME = re.compile(r"Күні:\s*(\d{2}\.\d{2}\.\d{4})\s+Уақыты:\s*(\d{1,2}:\d{2})")
_CONTACT_ADDR = re.compile(r'<a class="left_icon loc">([^<]+)</a>')
_OTHER_CITY = re.compile(r"\(([^)]*(?:қаласы|город|г\.)[^)]*)\)", re.IGNORECASE)


def venue_name_snippet(page_html: str) -> str | None:
    return VENUE_NAME if VENUE_NAME in page_html else None


def contact_address(contacts_html: str) -> str | None:
    m = _CONTACT_ADDR.search(contacts_html)
    return clean(htmllib.unescape(m[1])) if m else None


def poster_list(list_html: str) -> list[dict]:
    """[{date, hall, title, path, snippet}] of the Astana posters on the list page (`snippet`: the date line)."""
    out = []
    for m in _ITEM.finditer(list_html):
        d, t = _DATE.search(m[1]), _TITLE.search(m[1])
        if not (d and t):
            continue
        line = htmllib.unescape(re.sub(r"<[^>]+>", " ", d[1]))
        dmy = _DMY.search(line)
        hall = clean(_DMY.sub("", line).replace(".", " ", 1))
        if not dmy or _OTHER_CITY.search(hall):
            continue
        out.append({"date": date(int(dmy[3]), int(dmy[2]), int(dmy[1])), "hall": hall, "path": t[1],
                    "title": clean(htmllib.unescape(visible_text(t[2]))), "line": clean(line)})
    return out


def poster_time(poster_html: str) -> tuple[str, str] | None:
    """(«Күні: 22.10.2026 Уақыты: 19:00» verbatim, HH:MM) of a poster page."""
    m = _TIME.search(visible_text(poster_html))
    return (m[0], m[2]) if m else None


def make(item: dict, poster_html: str | None, list_url: str, poster_url: str, fetched_at: str, list_html: str,
         address: str | None, contacts_url: str, contacts_fetched_at: str) -> dict | None:
    """One event from a list entry (+ its poster page for the time)."""
    name_snippet = venue_name_snippet(list_html)
    if name_snippet is None:
        return None
    timed = poster_time(poster_html) if poster_html else None
    evidence = [*ev("title", list_url, item["title"], fetched_at), *ev("venue", list_url, name_snippet, fetched_at),
                *ev("venue", list_url, item["hall"], fetched_at)]
    if address:
        evidence += ev("address", contacts_url, address, contacts_fetched_at)
    ven = model.venue(VENUE_NAME.replace('"', ""), address=address, hall=item["hall"])
    key = item["path"].rsplit("/", 1)[-1]
    if timed:
        evidence += ev("when", poster_url, timed[0], fetched_at)
        return model.make_event(SOURCE, key, title=item["title"], kind="event", url=poster_url, fetched_at=fetched_at,
                                venue_=ven, evidence_=evidence, start=model.local_dt(item["date"], timed[1]))
    evidence += ev("when", list_url, item["line"].split(" ", 1)[0], fetched_at)
    return model.make_event(SOURCE, key, title=item["title"], kind="run", url=poster_url, fetched_at=fetched_at,
                            venue_=ven, evidence_=evidence, date_from=item["date"], date_to=item["date"])
