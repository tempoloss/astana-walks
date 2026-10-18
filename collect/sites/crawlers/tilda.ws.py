"""tilda.ws (linebrewexpo.tilda.ws): Line Brew Expo restaurant landing.

Partition p3 groups two POI sites under the tilda.ws domain; incognita.astana.tilda.ws is unreachable (HTTP 403
over http, self-signed cert over https) and contributes no facts.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://linebrewexpo.tilda.ws"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    t = visible_text(page.text)
    m_addr = re.search(r"(?P<v>Астана, Мангелик Ел 20/1)", t)
    m_ph = re.search(r"Бронь столов: (?P<v>\+7 701 016 07 77)", t)
    m_hours = re.search(r"(?P<v>открыт с 12:00 до 02:00)", t)
    m_desc = re.search(r'(?P<v>LINE BREW EXPO второй ресторан сети "Line Brew" в Астане)', t)
    if not m_addr:
        return [], [URL], "address line not found"
    ev = [store.evidence("name", URL, "LINE BREW EXPO", page.fetched_at),
          store.evidence("address", URL, m_addr[0], page.fetched_at)]
    if m_ph:
        ev.append(store.evidence("phone", URL, "Бронь столов: " + m_ph["v"], page.fetched_at))
    if m_hours:
        ev.append(store.evidence("opening_hours", URL, m_hours[0], page.fetched_at))
    if m_desc:
        ev.append(store.evidence("description", URL, m_desc[0], page.fetched_at))
    b = store.make_branch("Line Brew Expo", ev, "html", 0.75, address=m_addr["v"],
                          phone=m_ph["v"] if m_ph else None, opening_hours_raw=m_hours["v"] if m_hours else None,
                          description=m_desc["v"] if m_desc else None, url=URL)
    notes = ("Same page also says «Open daily 12a.m. - 12p.m.», contradicting «открыт с 12:00 до 02:00» — the "
             "Russian schedule is stored (weekday-unqualified). Incognita Karaoke "
             "(incognita.astana.tilda.ws, the second POI of the tilda.ws partition entry): HTTP 403 over http "
             "and TLS/robots failure over https on repeated probes — no facts.")
    return [b], [URL], notes
