"""stumari.kz: single-page грузинский ресторан; the КОНТАКТЫ block holds hours, booking phone and address."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://stumari.kz"
_BLOCK = re.compile(r"КОНТАКТЫ (?P<hours>ПН-ВС \d{2}:\d{2} - \d{2}:\d{2}) Бронирование (?P<phone>\+7 708 838 32 15) "
                    r"Инстаграм @stumari_astana Адрес (?P<addr>010000, Республика Казахстан, г\. Астана ул\. Керей, "
                    r"Жанибек Хандар, 18)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    m = _BLOCK.search(text)
    if not m:
        return [], [URL], "contacts block not found."
    ev = [store.evidence("name", URL, "Стумари", page.fetched_at),
          store.evidence("address", URL, m[0][:300], page.fetched_at),
          store.evidence("phone", URL, m[0][:300], page.fetched_at),
          store.evidence("opening_hours", URL, m["hours"], page.fetched_at)]
    desc = re.search(r"(?P<v>Стумари - это щедрость, вкусы и веселье Грузии\.)", text)
    if desc:
        ev.append(store.evidence("description", URL, desc["v"], page.fetched_at))
    b = store.make_branch("Стумари", ev, "html", 0.8, address=m["addr"], phone=m["phone"],
                          opening_hours_raw=m["hours"], description=desc["v"] if desc else None, url=URL)
    notes = ("One venue; the Instagram handle is a social network (not crawled). Booking phone is the restaurant's "
             "own number as printed next to the address.")
    return [b], [URL], notes
