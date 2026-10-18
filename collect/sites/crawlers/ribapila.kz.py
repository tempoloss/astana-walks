"""ribapila.kz: «Рыба Пила», морской ресторан (Sun Group) в Астане. Одна точка; адрес/часы/телефон в шапке лендинга."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://ribapila.kz"
_ADDR = re.compile(r"(?P<v>Проспект Туран 22, Астана)")
_HOURS = re.compile(r"Пн-Вс \| (?P<v>\d\d:\d\d - \d\d:\d\d)")
_PHONE = re.compile(r"(?P<v>\+7 \(705\) 605 22 22)")
_NAME = re.compile(r"(?P<v>РЫБА ПИЛА МОРСКОЙ РЕСТОРАН В АСТАНЕ)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr, hours, phone, name = _ADDR.search(text), _HOURS.search(text), _PHONE.search(text), _NAME.search(text)
    if not (addr and hours and name):
        return [], [URL], "header block (address/hours/name) not found."
    ev = [store.evidence("name", URL, name[0], page.fetched_at),
          store.evidence("address", URL, addr[0], page.fetched_at),
          store.evidence("opening_hours", URL, f"Пн-Вс | {hours['v']}", page.fetched_at)]
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    b = store.make_branch("Рыба Пила", ev, "html", 0.8, address=addr["v"], phone=phone["v"] if phone else None,
                          opening_hours_raw=f"Пн-Вс {hours['v']}", url=URL)
    notes = ("Header prints 'Пн-Вс | 12:00 - 00:00'; the vertical bar is stripped for the value only, the evidence "
             "snippet keeps it verbatim (00:00 closes -> 24:00). Phone is the restaurant's WhatsApp/booking number "
             "printed in the same block.")
    return [b], [URL], notes
