"""astanaopera.kz/contacts: theatre address + box-office phone; box-office hours are not visiting hours."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://astanaopera.kz/contacts"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    t = visible_text(page.text)
    m_addr = re.search(r"(?P<v>Қазақстан, Астана, Д\. Қонаев көшесі, 1)", t)
    m_phone = re.search(r"Телефон\s+(?P<v>\+7 \(7172\) 709 600)", t)
    if not m_addr:
        return [], [URL], "address line not found"
    ev = [store.evidence("name", URL, "«Астана Опера» мемлекеттік опера және балет театры", page.fetched_at),
          store.evidence("address", URL, m_addr[0], page.fetched_at)]
    phone = None
    if m_phone:
        phone = m_phone["v"]
        ev.append(store.evidence("phone", URL, "Телефон " + phone, page.fetched_at))
    b = store.make_branch("Астана Опера", ev, "html", 0.75, address=m_addr["v"], phone=phone, url=URL)
    notes = ("The page gives box-office hours («Кассаның жұмыс уақыты»: Жұмыс күндері 10:00—19:00, Демалыс "
             "күндері 10:00—18:00) — a ticket-office schedule, not the theatre's opening hours; not stored.")
    return [b], [URL], notes
