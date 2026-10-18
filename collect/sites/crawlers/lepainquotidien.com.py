"""lepainquotidien.com: Le Pain Quotidien в ТРЦ «Хан Шатыр» (domain item из p6). Локация Астаны — страница
локатора /kz/en/locations/Khan Shatyr Mall/Turan-Avenue-37: per-day «Opening hours monday ...», плюс в инлайн-JSON
строки address/city/latitude/longitude (эскейп-форма внутри JS-строки)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://www.lepainquotidien.com/kz/en/locations/Khan%20Shatyr%20Mall/Turan-Avenue-37"
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_HOURS = re.compile(r"Opening hours ((?:(?:%s) \d\d:\d\d until \d\d:\d\d ?)+)" % "|".join(_DAYS))
_GEO = re.compile(r'latitude\\":(?P<lat>[\d.]+),\\"longitude\\":(?P<lon>[\d.]+)')
_ADDR = re.compile(r'address\\":\\"(?P<v>Turan Avenue 37)\\"')
_CITY = re.compile(r'city\\":\\"(?P<v>Astana)\\"')


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    hours = _HOURS.search(text)
    geo, addr = _GEO.search(page.text), _ADDR.search(page.text)
    ev = [store.evidence("name", URL, "Le Pain Quotidien", page.fetched_at)]
    raw = None
    if hours:
        raw = hours[1]
        ev.append(store.evidence("opening_hours", URL, hours[0], page.fetched_at))
    if addr:
        ev.append(store.evidence("address", URL, addr[0], page.fetched_at))
    if geo:
        ev.append(store.evidence("geo", URL, geo[0], page.fetched_at))
    lat, lon = (float(geo["lat"]), float(geo["lon"])) if geo else (None, None)
    if lat is not None and not (50.98 < lat < 51.25 and 71.25 < lon < 71.65):
        lat = lon = None
    b = store.make_branch("Le Pain Quotidien (Хан Шатыр)", ev, "html", 0.85,
                          address="Turan Avenue 37, Astana (Khan Shatyr Mall)" if addr else None,
                          lat=lat, lon=lon, opening_hours_raw=raw, url=URL)
    notes = ("One Astana location (Khan Shatyr, Turan Avenue 37; zip 010000). The page prints 'Welcome To'/'status "
             "OPEN'; phone is $undefined on the page, so none is stored. Per-day English schedule converts to a "
             "uniform Mo-Su 10:00-22:00. The .com brand site is corporate-owned (first-party); the KZ locale path "
             "(/kz/) hosts only this location.")
    return [b], [URL], notes
