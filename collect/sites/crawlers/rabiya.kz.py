"""rabiya.kz: Uzbek/European restaurant; weekly schedule in the footer block, Тел./Моб./E-mail are empty."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://rabiya.kz/"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    t = visible_text(page.text)
    m_addr = re.search(r'(?P<v>г\.Астана Правый берег, ЖК "Highwill" ул\. А\.Байтурсынова)', t)
    m_hours = re.search(r"(?P<v>Время работы: вс-чт: 11\.00-01\.00; пт-сб: 11\.00-02\.00)", t)
    m_desc = re.search(r"(?P<v>Rabiya - ресторан узбекской и европейской кухни в Астане)", page.text)
    if not (m_addr and m_hours):
        return [], [URL], "address/hours lines not found"
    ev = [store.evidence("name", URL, "Rabiya", page.fetched_at),
          store.evidence("address", URL, m_addr[0], page.fetched_at),
          store.evidence("opening_hours", URL, m_hours[0], page.fetched_at)]
    desc = m_desc["v"] if m_desc else None
    if desc:
        ev.append(store.evidence("description", URL, desc, page.fetched_at))
    b = store.make_branch("Rabiya", ev, "html", 0.75, address=m_addr["v"], opening_hours_raw=m_hours["v"],
                          description=desc, url=URL)
    notes = ("The header line «Время работы : с 11.00 до 02.00» agrees with the weekly schedule; the address "
             "street carries no house number on the site.")
    return [b], [URL], notes
