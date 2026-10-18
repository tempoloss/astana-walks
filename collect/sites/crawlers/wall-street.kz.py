"""wall-street.kz: ресторан «Wall Street» (Кабанбай батыра 60/20). Joomla-лендинг; https отдаёт self-signed cert,
краулим http. Часов работы на сайте нет — храним адрес и телефон."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://www.wall-street.kz/ru/kontakty"
_ADDR = re.compile(r"(?P<v>г\.Астана, Кабанбай батыра проспект, 60/20)")
_PHONE = re.compile(r"(?P<v>\+7 701 969 00 04)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr, phone = _ADDR.search(text), _PHONE.search(text)
    if not addr:
        return [], [URL], "address block not found."
    ev = [store.evidence("name", URL, "Wall Street", page.fetched_at),
          store.evidence("address", URL, addr[0], page.fetched_at)]
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    b = store.make_branch("Wall Street", ev, "html", 0.7, address=addr["v"],
                          phone=phone["v"] if phone else None, url=URL)
    notes = ("Contacts page gives address and two phones (+7 701 969 00 04 booking, +7 700 555 23 23 partnerships); "
             "no opening-hours statement anywhere on the site, so none is stored. The name evidence is the restaurant "
             "brand repeated in the page text ('Найти проезд до Wall Street Restaurant').")
    return [b], [URL], notes
