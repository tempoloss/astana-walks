"""ferrum.kz: one cafe (Ferrum Cafe); /contacts/ prints address, booking phone and the cafe schedule.
The home-page 'Ежедневно с 11:00 до 22:00' is the Highvill-delivery schedule, not the cafe's."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://ferrum.kz/contacts/"
PATTERNS = {
    "address": r"Адрес: (?P<v>.+?) Режим работы Ferrum Cafe",
    "hours": r"Режим работы Ferrum Cafe: (?P<v>[^Р]+?) Режим работы доставки",
    "phone": r"Бронирование столиков: (?P<v>\+7 [0-9 ]+)",
}


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    vis = visible_text(page.text)
    ev, values = [], {}
    for field, rx in PATTERNS.items():
        m = re.search(rx, vis)
        if m:
            ev.append(store.evidence({"hours": "opening_hours"}.get(field, field), URL, m[0], page.fetched_at))
            values[field] = m["v"]
    name = "Ferrum Cafe"
    m = re.search(r"FERRUM CAFE", page.text)
    if m:
        ev.append(store.evidence("name", URL, page.text[m.start():m.start() + 11], page.fetched_at))
    if not values:
        return [], [URL], f"{URL}: no facts parsed"
    notes = ("Single cafe; the page is titled 'Завтраки в Астане' and the address (Кошкарбаева 8, ЖК Хайвил) is in "
             "Астана. The separate delivery schedule ('Ежедневно с 8:00 до 23:00' / home-page 11:00-22:00 'по ЖК "
             "Highvill') is delivery-only and not stored. 'Вскр-Чт c 8:00 до 24:00, Пт-Сб с 8:00 до 2:00' uses "
             "abbreviations ('Вскр', 'Чт' as range parts) the hours parser cannot decode deterministically, so "
             "opening_hours_osm stays None while raw is kept verbatim.")
    b = store.make_branch(name, ev, "html", 0.8, address=values.get("address").strip() if "address" in values else None,
                          phone=values.get("phone"), opening_hours_raw=values.get("hours"), url=URL)
    return [b], [URL], notes
