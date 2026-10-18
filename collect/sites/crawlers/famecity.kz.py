"""famecity.kz: детский игровой центр Fame City (ТРЦ Хан Шатыр, 4 этаж) — часы, телефон, центр карты own-site."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://www.famecity.kz/"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    hours = re.search(r"(?P<v>Часы работы - ежедневно с 11:00 до 22:00)", text)
    phone = re.search(r"(?P<v>8 \(701\) 883 96 29)", text)
    desc = re.search(r'(?P<v><meta name="description" content="[^"]{20,220})', page.text)
    name = re.search(r"(?P<v>Fame City — удивительный мир развлечений)", text)
    if not hours:
        return [], [URL], "hours not found."
    ev = [store.evidence("opening_hours", URL, hours[0], page.fetched_at)]
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    description = None
    if desc:
        description = re.sub(r"<meta name=\"description\" content=\"", "", desc[0])
        ev.append(store.evidence("description", URL, desc[0], page.fetched_at))
    b = store.make_branch("Fame City Entertainment Centre", ev, "html", 0.75,
                          phone=phone and phone["v"], opening_hours_raw=hours["v"], description=description, url=URL)
    notes = ("No street address in the text: the meta description places the centre 'на 4-м этаже "
             "торгово-развлекательного центра «Хан Шатыр»'. The page's only coordinates are the centre of an "
             "embedded 2GIS firmsonmap widget (2GIS data, not the venue's own), so they are NOT stored; the "
             "record has hours/phone/description only (address empty).")
    return [b], [URL], notes
