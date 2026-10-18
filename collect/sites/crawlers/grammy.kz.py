"""grammy.kz: single-page караоке-ресторан; contacts block holds address, hours regime and phones."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://grammy.kz"
_BLOCK = re.compile(r"Адрес (?P<addr>Астана, проспект Туран, 30 \(здание Fitness Palace\)) "
                    r"РЕЖИМ РАБОТЫ: (?P<hours>с \d{2}:\d{2} до \d{2}:\d{2}) "
                    r"Контакты (?P<phones>\+7 \(7172\) 279-000 \+7 \(701\) 1000 703)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    m = _BLOCK.search(text)
    if not m:
        return [], [URL], "contacts block not found."
    ev = [store.evidence("name", URL, "Grammy — 2017", page.fetched_at),
          store.evidence("address", URL, m[0][:300], page.fetched_at),
          store.evidence("phone", URL, m[0][:300], page.fetched_at),
          store.evidence("opening_hours", URL, "РЕЖИМ РАБОТЫ: " + m["hours"], page.fetched_at)]
    b = store.make_branch("Grammy", ev, "html", 0.8, address=m["addr"], phone=m["phones"],
                          opening_hours_raw=m["hours"], url=URL)
    notes = ("The page states 'РЕЖИМ РАБОТЫ: с 18:00 до 06:00' without naming days; the schedule stays in "
             "opening_hours_raw, hours_flags marks it 'needs_days' (no day-less OSM conversion). No branch list — "
             "one venue only.")
    return [b], [URL], notes
