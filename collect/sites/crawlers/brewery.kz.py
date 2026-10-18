"""brewery.kz: one-page ресторан Brewery (Sat Group) in Astana; the 'Наши контакты' block holds address, hours, phones."""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.crawl_demo import _text_branch  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://brewery.kz"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    b = _text_branch(page, "Brewery", {
        "address": r"(?P<v>Астана, проспект Туран, 30 \(здание Fitness Palace\))",
        "hours": r"Режим работы: (?P<v>12:00-01:00, без выходных)",
        "phone": r"(?P<v>\+7 7172 56 77 11, \+7 702 888 11 59)",
    })
    notes = ("Single venue (the page header also links 'Все рестораны' to satgroup.kz). Hours cross midnight "
             "(12:00-01:00). No coordinates on the page.")
    return [b] if b else [], [URL], notes
