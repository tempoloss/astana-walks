"""saryarka.com: ТРЦ «Сарыарка» — /kontakty prints the mall address, phone and a per-zone ВРЕМЯ РАБОТЫ block.
The mall-wide schedule is the shops' one ('Магазины: 1,2,3 этажи 10:00 - 22:00'); other lines are tenants
(cinema, supermarket, wardrobes) and the parking note is the car park's."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://saryarka.com/kontakty"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    vis = visible_text(page.text)
    ev, values = [], {}
    m = re.search(r"(?P<v>город Астана, пр\. Туран, 24)", vis)
    if m:
        ev.append(store.evidence("address", URL, m[0], page.fetched_at))
        values["address"] = m["v"]
    m = re.search(r"(?P<v>Телефон: \+7 701 081 02 27)", vis)
    if m:
        ev.append(store.evidence("phone", URL, m[0], page.fetched_at))
        values["phone"] = "+7 701 081 02 27"
    m = re.search(r"(?P<v>Магазины: 1,2,3 этажи 10:00 - 22:00)", vis)
    if m:
        ev.append(store.evidence("opening_hours", URL, m[0], page.fetched_at))
        values["hours"] = m["v"]
    t = re.search(r"<title[^>]*>([^<]+)</title>", page.text, re.I)
    if t and "Сарыарка" in t[1]:
        ev.append(store.evidence("name", URL, "ТРЦ Сарыарка", page.fetched_at))
    if not values:
        return [], [URL], f"{URL}: nothing parsed"
    notes = ("Mall hours = 'Магазины: 1,2,3 этажи 10:00 - 22:00' (no weekday names → hours_flags needs_days, raw kept). "
             "Same block also lists tenant schedules (гардероб 11:00-21:00, кафе/бары/рестораны 10:00-24:00, кинотеатр "
             "10:00-03:00, супермаркет Вкусмарт 10:00-22:00) and a paid 24h underground car park — not stored for the "
             "mall itself.")
    b = store.make_branch("ТРЦ «Сарыарка»", ev, "html", 0.8, address=values.get("address"), phone=values.get("phone"),
                          opening_hours_raw=values.get("hours"), url=URL)
    return [b], [URL], notes
