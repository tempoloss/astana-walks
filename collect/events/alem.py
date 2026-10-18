"""alem.ai/en/: the Museum of Singularity's own page (robots.txt absent: all allowed) — weekly hours, ticket price,
address and coordinates of a standing exhibition."""

from __future__ import annotations

import html as htmllib
import re

from collect.events import model
from collect.events.model import clean, ev
from collect.sites.fetch import visible_text
from collect.sites.hours import to_osm

SOURCE = "alem.ai"
URL = "https://alem.ai/en/"
TITLE = "Museum of Singularity"

_HOURS = re.compile(r"The Museum of Singularity is open:\s*(\d{1,2}:\d{2}\s*-\s*\d{1,2}:\d{2})\s+([A-Za-z]{3}\s*[–-]\s*[A-Za-z]{3})")
_PRICE = re.compile(r"Admission ticket\s*[—-]\s*₸\s*(\d[\d,]*)")
_PLACE = re.compile(r"(Mangilik El ave\.[^\[]*?)\s*\[\s*(\d{2}\.\d+),\s*(\d{2}\.\d+)\s*\]")


def parse(page_html: str, url: str, fetched_at: str) -> dict | None:
    text = clean(htmllib.unescape(visible_text(page_html)))
    hm, pm, am = _HOURS.search(text), _PRICE.search(text), _PLACE.search(text)
    if not hm or TITLE not in text:
        return None
    raw = f"{hm[1]} {hm[2]}"
    osm = to_osm(raw.replace("–", "-"))
    if not osm:
        return None
    lat, lon = (float(am[2]), float(am[3])) if am else (None, None)
    if not model.in_astana(lat, lon):
        lat = lon = None
        am = None
    evidence = [*ev("title", url, TITLE, fetched_at), *ev("when", url, hm[0], fetched_at)]
    address = clean(am[1]) if am else None
    evidence += ev("venue", url, TITLE, fetched_at)
    if am:
        evidence += ev(("address", "coords"), url, am[0], fetched_at)
    price_text = f"₸{pm[1]}" if pm else None
    if pm:
        evidence += ev("price", url, pm[0], fetched_at)
    return model.make_event(
        SOURCE, "museum-of-singularity", title=TITLE, kind="standing", url=url, fetched_at=fetched_at,
        category="museum", venue_=model.venue(TITLE, address=address, lat=lat, lon=lon),
        evidence_=evidence, hours_raw=raw, hours_osm=osm, price_text=price_text,
        price_from=int(pm[1].replace(",", "")) if pm else None)
