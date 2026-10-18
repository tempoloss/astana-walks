"""qazaqgourmet.kz/contacts: ресторан Qazaq Gourmet — адрес и телефон в Астане (часов на сайте нет)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://qazaqgourmet.kz/contacts"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr = re.search(r"(?P<v>г\. Астана, Мангилик Ел, 29)", text)
    phone = re.search(r"(?P<v>\+7 708 988 88 88)", text)
    name = re.search(r"(?P<v>QAZAQ GOURMET)", text)
    if not addr or not phone:
        return [], [URL], "contacts block not found."
    ev = [store.evidence("address", URL, addr[0], page.fetched_at),
          store.evidence("phone", URL, phone[0], page.fetched_at)]
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    b = store.make_branch("Qazaq Gourmet", ev, "html", 0.8, address=addr["v"], phone=phone["v"], url=URL)
    notes = ("No opening hours anywhere on the site (only a 'ЗАБРОНИРОВАТЬ' link and a 2GIS pointer), so hours are "
             "not stored — not inferred.")
    return [b], [URL], notes
