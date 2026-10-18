"""abudhabiplaza.info/contacts: МФК Abu Dhabi Plaza — адрес в Астане и линия infodesk (часов нет)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://abudhabiplaza.info/contacts"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr = re.search(r"(?P<v>Астана ул\. Сыганак, дом 60/5)", text)
    phone = re.search(r"Общие вопросы (?P<v>\+7 \(7172\) 62 16 16)", text)
    name = re.search(r"(?P<v>Abu Dhabi Plaza)", text)
    if not addr or not phone:
        return [], [URL], "contacts block not found."
    ev = [store.evidence("address", URL, addr[0], page.fetched_at),
          store.evidence("phone", URL, phone[0], page.fetched_at)]
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    b = store.make_branch("ТЦ Abu Dhabi Plaza", ev, "html", 0.8, address=addr["v"], phone=phone["v"], url=URL)
    notes = ("The mall's visiting hours are not published on the site (same number is repeated for the commercial and "
             "marketing departments; the 'Общие вопросы' line is the mall helpdesk). Coordinates only appear inside a "
             "2GIS widget URL — not stored.")
    return [b], [URL], notes
