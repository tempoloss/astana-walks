"""leprechaun.pub: single Irish pub in Астана — /kontakty/ prints address, phone and 'Ежедневно с 15:00 до 02:00'."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://leprechaun.pub/kontakty/"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    vis = visible_text(page.text)
    ev, values = [], {}
    m = re.search(r"(?P<v>г\. Астана, проспект Қабанбай батыра, 58Б корпус 2)", vis)
    if m:
        ev.append(store.evidence("address", URL, m[0], page.fetched_at))
        values["address"] = m["v"]
    m = re.search(r"(?P<v>ТЕЛЕФОН: \+7 \(771\) 046-88-22)", vis)
    if m:
        ev.append(store.evidence("phone", URL, m[0], page.fetched_at))
        values["phone"] = "+7 (771) 046-88-22"
    m = re.search(r"(?P<v>Ежедневно с 15:00 до 02:00)", vis)
    if m:
        ev.append(store.evidence("opening_hours", URL, m[0], page.fetched_at))
        values["hours"] = m["v"]
    t = re.search(r"<title[^>]*>([^<]+)</title>", page.text, re.I)
    if t and "Leprechaun" in t[1]:
        ev.append(store.evidence("name", URL, "Pub Leprechaun", page.fetched_at))
    if not values:
        return [], [URL], f"{URL}: nothing parsed"
    notes = ("The home page's 'Принимаем заказы ежедневно 15:00 до 00:00' is the order/delivery window; the contacts "
             "page states the venue schedule 15:00-02:00 daily, which is stored.")
    b = store.make_branch("The Leprechaun (Pub Leprechaun)", ev, "html", 0.8, address=values.get("address"),
                          phone=values.get("phone"), opening_hours_raw=values.get("hours"), url=URL)
    return [b], [URL], notes
