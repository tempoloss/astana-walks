"""nu.edu.kz (library.nu.edu.kz/location): NU Library branches with the Main Library weekly schedule."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://library.nu.edu.kz/location"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    t = visible_text(page.text)
    m_addr = re.search(r"(?P<v>Block 5 53 Kabanbay Batyr Avenue Astana, Republic of Kazakhstan, 010000)", t)
    if not m_addr:
        return [], [URL], "Main Library block not found"
    m_phone = re.search(r"(?P<v>Tel: \+7 \(7172\) 70-62-55)", t)
    m_hours = re.search(r"(?P<v>Mon–Fri: 8:30 AM – 7:45 PM Sat–Sun: 10:00 AM – 6:45 PM)", t)
    ev = [store.evidence("name", URL, "Main Library", page.fetched_at),
          store.evidence("address", URL, m_addr[0], page.fetched_at)]
    if m_phone:
        ev.append(store.evidence("phone", URL, m_phone[0], page.fetched_at))
    if m_hours:
        ev.append(store.evidence("opening_hours", URL, m_hours[0], page.fetched_at))
    out = [store.make_branch("Nazarbayev University Library — Main Library", ev, "html", 0.8,
                             address="Block 5, 53 Kabanbay Batyr Avenue, Astana, Republic of Kazakhstan, 010000",
                             phone="+7 (7172) 70-62-55" if m_phone else None,
                             opening_hours_raw=m_hours["v"] if m_hours else None, url=URL)]
    m2 = re.search(r"(?P<v>5/1 Kerey-Zhanibek Khans Street Astana 010000, Kazakhstan)", t)
    if m2:
        ev2 = [store.evidence("name", URL, "NUSOM Library", page.fetched_at),
               store.evidence("address", URL, m2[0], page.fetched_at),
               store.evidence("phone", URL, "Tel: +7 (7172) 70 46 40", page.fetched_at)]
        out.append(store.make_branch("Nazarbayev University Library — NUSOM Library", ev2, "html", 0.8,
                                     address="5/1 Kerey-Zhanibek Khans Street, Astana 010000, Kazakhstan",
                                     phone="+7 (7172) 70 46 40", url=URL))
    notes = ("Main Library schedule stored verbatim; the Balcony sub-schedule, the NUSOM «Sun: No service at the "
             "Information Desk» exception and the inventory/holiday caveat are not encoded.")
    return out, [URL], notes
