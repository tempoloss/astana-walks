"""yms.kz/rus/contacts: YouMe sushi — телефон сети и один адрес самовывоза в Астане (SSR-встроен в JSON)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://yms.kz/rus/contacts"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr = re.search(r"(?P<v>Амангельды Иманова улица, 16)", text)
    phone = re.search(r"(?P<v>\+7 707 707 47 47)", text)
    name = re.search(r"(?P<v>YouMe Sushi Иманова)", text)
    if not addr:
        return [], [URL], "address not found."
    ev = [store.evidence("address", URL, addr[0], page.fetched_at)]
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    b = store.make_branch("YouMe Sushi", ev, "html", 0.75, address=addr["v"], phone=phone and phone["v"], url=URL)
    notes = ("Single pickup point listed ('Адреса наших кафе' — one cafe, Иманова 16; the city selector defaults to "
             "Астана). The 'Loading...' Yandex-map block renders coordinates client-side, none in HTML. No working "
             "hours text on the contacts page -> no opening_hours.")
    return [b], [URL], notes
