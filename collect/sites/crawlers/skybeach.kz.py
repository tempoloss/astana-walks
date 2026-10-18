"""skybeach.kz: indoor beach club under Khan Shatyr; /ru/kontakty prints address, phones, e-mail and hours."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

HOME = "http://www.skybeach.kz"
URL = "https://skybeach.kz/ru/kontakty"
_TITLE = re.compile(r"<title[^>]*>\s*(Пляжный клуб - Sky Beach Club)\s*<", re.IGNORECASE)
_BLOCK = re.compile(r"Адрес (?P<addr>г\. Астана, пр\. Туран 37) Телефон (?P<phones>\+7 \(7172\) 577-787 \+7 701 883 9625) "
                    r"Email skybeach@khanshatyr\.com Часы работы (?P<hours>ежедневно с 10:00 до 21:00)")


def crawl(fetcher: SiteFetcher):
    home = fetcher.fetch(HOME)  # robots-checked entry; its <title> is the venue-name evidence
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [HOME, URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    m = _BLOCK.search(text)
    if not m:
        return [], [HOME, URL], "contacts block not found."
    tm = _TITLE.search(home.text) if home.ok else None
    if not tm:
        return [], [HOME, URL], "home title not found."
    ev = [store.evidence("name", HOME, tm[1], home.fetched_at),
          store.evidence("address", URL, m[0][:300], page.fetched_at),
          store.evidence("phone", URL, m[0][:300], page.fetched_at),
          store.evidence("opening_hours", URL, "Часы работы " + m["hours"], page.fetched_at)]
    b = store.make_branch("Sky Beach Club", ev, "html", 0.8, address=m["addr"], phone=m["phones"],
                          opening_hours_raw=m["hours"], url=URL)
    notes = ("The club sits inside Khan Shatyr (пр. Туран 37, e-mail @khanshatyr.com) — the same address the mall "
             "publishes; join.py should match it to the sport POI by name. The home page repeats the schedule "
             "('Наши двери открыты для вас ежедневно с 10:00 до 21:00').")
    return [b], [HOME, URL], notes
