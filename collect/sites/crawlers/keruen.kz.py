"""keruen.kz: ТРЦ «Керуен» (manual target "Керуен", Достық 9). Static RU pages: /contacts carries the mall address,
the weekly schedule, the phone and Leaflet data-latitude/data-longitude attributes; /rezhim_raboty repeats
per-zone hours (supermarket/cinema — tenants, not the mall)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

CONTACTS = "https://www.keruen.kz/contacts"
REZHIM = "https://keruen.kz/rezhim_raboty"
_ADDR = re.compile(r"(?P<v>РК, г\. Астана, улица Достык, 9)")
_HOURS = re.compile(r"График работы ТРЦ (?P<v>с \d\d:\d\d до \d\d:\d\d , 7 дней в неделю)")
_PHONE = re.compile(r"(?P<v>\+7 \(7172\) 79-55-20)")
_GEO = re.compile(r'data-latitude="(?P<lat>[\d.]+)" data-longitude="(?P<lon>[\d.]+)"')
_NAME = re.compile(r"(?P<v>ТРЦ «Керуен»)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(CONTACTS)
    fetcher.fetch(REZHIM)
    if not page.ok:
        return [], [CONTACTS, REZHIM], f"{CONTACTS}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr, hours, phone, name = _ADDR.search(text), _HOURS.search(text), _PHONE.search(text), _NAME.search(text)
    geo = _GEO.search(page.text)
    if not (addr and hours and name):
        return [], [CONTACTS, REZHIM], "address/hours/name block not found on /contacts."
    ev = [store.evidence("name", CONTACTS, name[0], page.fetched_at),
          store.evidence("address", CONTACTS, addr[0], page.fetched_at),
          store.evidence("opening_hours", CONTACTS, hours[0], page.fetched_at)]
    lat = lon = None
    if geo:
        lat, lon = float(geo["lat"]), float(geo["lon"])
        ev.append(store.evidence("geo", CONTACTS, geo[0], page.fetched_at))
    if phone:
        ev.append(store.evidence("phone", CONTACTS, phone[0], page.fetched_at))
    b = store.make_branch("ТРЦ «Керуен»", ev, "html", 0.85, address=addr["v"], lat=lat, lon=lon,
                          phone=phone["v"] if phone else None, opening_hours_raw=hours["v"], url=CONTACTS)
    notes = ("One mall, one venue. /rezhim_raboty additionally lists per-tenant schedules (Galmart 09.00-23.00, "
             "кинотеатр 10.00-24.00, рестораны 10.00-24.00...) — tenant hours, not the mall's, and not stored. "
             "The mall schedule text names days only as '7 дней в неделю'; conversion follows hours.py rules, raw "
             "kept either way.")
    return [b], [CONTACTS, REZHIM], notes
