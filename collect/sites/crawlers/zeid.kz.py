"""zeid.kz: hotel-restaurant complex ZEID; address + restaurant phone, no unambiguous hours statement."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://zeid.kz"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    t = visible_text(page.text)
    m_addr = re.search(r"(?P<v>г\. Астана,[\s\u200b]*ул\.[\s\u200b]*Агыбай батыра, 99)", t)
    m_ph = re.search(r"(?P<v>\+7 \(775\) 680-47-47) \(ресторан\)", t)
    if not m_addr:
        return [], [URL], "address line not found"
    addr = re.sub(r"[\s\u200b]+", " ", m_addr["v"])
    ev = [store.evidence("name", URL, "ZEID", page.fetched_at),
          store.evidence("address", URL, m_addr[0], page.fetched_at)]
    phone = None
    if m_ph:
        phone = m_ph["v"]
        ev.append(store.evidence("phone", URL, phone + " (ресторан)", page.fetched_at))
    b = store.make_branch("ZEID", ev, "html", 0.7, address=addr, phone=phone, url=URL)
    notes = ("«Гостиница 24/7» is the hotel and «Пн-Вт до 01:00 Ср-Вс круглосуточно» is printed under the hotel "
             "phone; no unambiguous restaurant hours — none stored.")
    return [b], [URL], notes
