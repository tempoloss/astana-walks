"""tri-peskarya.kz: hotel complex «Три Пескаря»; index.htm gives address+cafe schedule, Контакты — phone."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://tri-peskarya.kz/index.htm"
CONTACTS = "http://tri-peskarya.kz/Контакты.htm"


def crawl(fetcher: SiteFetcher):
    home = fetcher.fetch(URL)
    if not home.ok:
        return [], [URL], f"{URL}: status {home.status} {home.error}"
    t = visible_text(home.text)
    m_addr = re.search(r"(?P<v>Казахстан, г\. Астана м-он Коктал 1 ул\. Енлик - Кебек 11/1)", t)
    m_hours = re.search(r"КАФЕ работает (?P<v>с 12:00 до 01:00)", t)
    if not m_addr:
        return [], [URL], "address line not found"
    ev = [store.evidence("name", URL, "Три Пескаря", home.fetched_at),
          store.evidence("address", URL, m_addr[0], home.fetched_at)]
    raw = m_hours["v"] if m_hours else None
    if m_hours:
        ev.append(store.evidence("opening_hours", URL, "КАФЕ работает " + raw, home.fetched_at))
    b = store.make_branch("Три Пескаря", ev, "html", 0.7, address=m_addr["v"], opening_hours_raw=raw, url=URL)
    pages = [URL]
    cont = fetcher.fetch(CONTACTS)
    if cont.ok:
        m_ph = re.search(r"(?P<v>\+7 \(7172\) 300 390)", visible_text(cont.text))
        if m_ph:
            b["phone"] = m_ph["v"]
            b["evidence"].append(store.evidence("phone", CONTACTS, m_ph["v"], cont.fetched_at))
        pages.append(CONTACTS)
    notes = ("The index also claims «Мы работаем круглосуточно!» (a slogan for the complex) while the cafe line "
             "says «ЛЕТНЕЕ И ЗИМНЕЕ КАФЕ работает с 12:00 до 01:00» — the explicit cafe schedule is stored "
             "weekday-unqualified (hours_flags needs_days), the slogan is not.")
    return [b], pages, notes
