"""astana-expo.com: ВК «Астана-Экспо КС» — footer address/phone; the site publishes no visiting hours."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://www.astana-expo.com"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    t = visible_text(page.text)
    m_addr = re.search(r"(?P<v>010000, Казахстан, город Астана, район Сарайшық, улица Жұмекен Нәжімеденов, "
                       r"дом 16Г)", t)
    m_phone = re.search(r"Тел:\s*(?P<v>8 7172 64 23 23)", t)
    m_desc = re.search(r"(?P<v>Astana Expo — организатор ключевых отраслевых выставок и конференций в Казахстане "
                       r"и Центральной Азии)", t)
    if not m_addr:
        return [], [URL], "footer address not found"
    ev = [store.evidence("name", URL, "«Астана-Экспо КС»", page.fetched_at),
          store.evidence("address", URL, m_addr[0], page.fetched_at)]
    if m_phone:
        ev.append(store.evidence("phone", URL, "Тел: " + m_phone["v"], page.fetched_at))
    if m_desc:
        ev.append(store.evidence("description", URL, m_desc[0], page.fetched_at))
    b = store.make_branch("Астана-Экспо КС", ev, "html", 0.75, address=m_addr["v"],
                          phone=m_phone["v"] if m_phone else None, description=m_desc["v"] if m_desc else None,
                          url=URL)
    return [b], [URL], ("Exhibition organiser/venue; only event dates are published, no visiting opening hours.")
