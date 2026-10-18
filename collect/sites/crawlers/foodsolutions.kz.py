"""foodsolutions.kz: the Astana tab of /restaurants lists the outlets with printed addresses only."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://foodsolutions.kz/restaurants"
_TAB = re.compile(r'id="tab-c-1">(.*?)<div class="tabs__content[^"]*" id="tab-c-', re.DOTALL)
_OUTLET = re.compile(r"(?P<v>Адрес: .+? Тел\.)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    m = _TAB.search(page.text)  # the first city tab is 'Астана' (nav order Астана/Алматы/Костанай/...)
    if not m:
        return [], [URL], "Астана tab (tab-c-1) not found on /restaurants"
    seg = visible_text(m[1])
    branches = []
    for mm in _OUTLET.finditer(seg):
        addr = store.norm_ws(re.sub(r"^Адрес:\s*|\s*Тел\.$", "", mm["v"]))
        if not addr:
            continue
        branches.append(store.make_branch(
            f"Food Solutions ({addr})",
            [store.evidence("address", URL, mm["v"], page.fetched_at)],
            "html", 0.75, address=addr, url=URL))
    notes = ("The Astana tab of /restaurants publishes 7 outlets (Кабанбай батыра 26; Кабанбай Батыра 62 ТРЦ "
             "'Mega Silk Way'; Достык 9 ТРЦ 'Керуен'; пр. Богенбай батыра 49 'САБ'; пр. Сарыарка 9 'Д' Кенесары; "
             "Петрова 24Г 'Евразия'; район 'Байқоңыр', ул. Өндіріс 96 'Трасса М36'), each with an 'Адрес:' line; "
             "the 'Тел.:' field is printed empty everywhere and the page gives no opening hours for Astana, so "
             "only addresses are stored. Coordinates are not published. Tabs of the other cities (Алматы, "
             "Костанай, Актобе, Караганда, Атырау) are not Astana and were skipped.")
    return branches, [URL], notes
