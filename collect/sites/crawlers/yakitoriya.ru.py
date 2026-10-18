"""yakitoriya.ru: the RU chain's own page for its Astana restaurant (ТЦ «Абу-Даби Плаза»).

Coordinates come from the embedded RESTAURANT_ITEM_POINTS JSON; the schedule line has no weekday words, so the
raw stays weekday-unqualified (hours_flags needs_days).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://yakitoriya.ru/restaurants/nur-sultan-astana-tc-abu-dabi-plaza"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    t = visible_text(page.text)
    m_addr = re.search(r"(?P<v>г\. Астана, Сыганак, д\.16/5)", t)
    m_phone = re.search(r"Телефон:\s*(?P<v>8 \(7172\) 40-20-51)", t)
    m_hours = re.search(r"Часы работы:\s*(?P<v>с 10:00 до 22:00)", t)
    m_geo = re.search(r'\\u0022lat\\u0022: 51\.1219, \\u0022lon\\u0022: 71\.428', page.text)
    if not m_addr:
        return [], [URL], "address line not found"
    ev = [store.evidence("name", URL, "Якитория", page.fetched_at),
          store.evidence("address", URL, m_addr[0], page.fetched_at)]
    if m_phone:
        ev.append(store.evidence("phone", URL, "Телефон: " + m_phone["v"], page.fetched_at))
    if m_hours:
        ev.append(store.evidence("opening_hours", URL, "Часы работы: " + m_hours["v"], page.fetched_at))
    if m_geo:
        ev.append(store.evidence("geo", URL, m_geo[0], page.fetched_at))
    b = store.make_branch("Якитория (ТЦ «Абу-Даби Плаза»)", ev, "html", 0.8, address=m_addr["v"],
                          phone=m_phone["v"] if m_phone else None, lat=51.1219 if m_geo else None,
                          lon=71.428 if m_geo else None, opening_hours_raw=m_hours["v"] if m_hours else None,
                          url=URL)
    notes = ("The city selector of the delivery site lists «Астана (ТЦ \"Абу-Даби Плаза\")» as a restaurant of "
             "the network; «Бронь столов принимается ежедневно» is about bookings, not the schedule, so the "
             "10:00-22:00 line stays weekday-unqualified.")
    return [b], [URL], notes
