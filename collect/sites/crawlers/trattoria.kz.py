"""trattoria.kz: пиццерия/доставка Trattoria in Astana; header carries city, phone and daily schedule."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://trattoria.kz"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    hours = re.search(r"(?P<v>Ежедневно для Вас с 10:00 до 22:00)", text)
    phone = re.search(r"(?P<v>\+7\(707\)988-78-87)", text)
    city = re.search(r"(?P<v>Астана Доставка ко времени)", text)
    title = re.search(r"(?P<v>Пиццерия Trattoria в Астане)", page.text)
    if not hours or not phone:
        return [], [URL], "header block not found."
    ev = [store.evidence("opening_hours", URL, hours[0], page.fetched_at),
          store.evidence("phone", URL, phone[0], page.fetched_at)]
    if city:
        ev.append(store.evidence("name", URL, city[0], page.fetched_at))
    if title:
        ev.append(store.evidence("name", URL, title[0], page.fetched_at))
    b = store.make_branch("Траттория (Trattoria.kz)", ev, "html", 0.75, phone=phone["v"],
                          opening_hours_raw=hours["v"], url=URL)
    notes = ("One delivery pizzeria; the site sells Astana delivery only ('Астана' city selector, no branch list, no "
             "street address). 'Ежедневно для Вас с 10:00 до 22:00' is delivery/order hours of the one kitchen; "
             "hours.to_osm does not convert this phrasing, so the schedule stays raw without a flag.")
    return [b], [URL], notes
