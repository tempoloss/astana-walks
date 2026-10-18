"""velotrek.kz/contacts: address + reception phone of the Saryarqa velodrome; no public opening hours."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://velotrek.kz/contacts/"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    t = visible_text(page.text)
    m_addr = re.search(r"(?P<v>Велотрек Сарыарқа, Қазақстан, Астана қаласы, Нұра ауданы, Қабанбай Батыр даңғылы, "
                       r"45а ғимарат)", t)
    m_phone = re.search(r"бөлмесінің телефоны\s+(?P<v>8 \(7172\) 707 173)", t)
    if not m_addr:
        return [], [URL], "address line not found"
    ev = [store.evidence("name", URL, "Сарыарқа", page.fetched_at),
          store.evidence("address", URL, m_addr[0], page.fetched_at)]
    phone = None
    if m_phone:
        phone = m_phone["v"]
        ev.append(store.evidence("phone", URL, "телефоны " + phone, page.fetched_at))
    b = store.make_branch("Велотрек «Сарыарқа»", ev, "html", 0.75, address=m_addr["v"], phone=phone, url=URL)
    notes = ("The visiting-hours page is the citizens' reception schedule of the director/vice-directors "
             "(каб. 201/312), not facility opening hours; «Екі аптада бір рет, дүйсенбі күні — санитарлық күн» "
             "refers to the fitness club. No public hours published.")
    return [b], [URL], notes
