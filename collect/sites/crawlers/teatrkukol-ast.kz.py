"""teatrkukol-ast.kz: ГККП «Театр кукол» акимата города Астаны (manual target node/2349675581 «Театр кукол»).
WordPress-официалка; страница контактов даёт адрес и телефон, часов работы нет."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://teatrkukol-ast.kz/ru/kontakty/"
_NAME = re.compile(r"(?P<v>ГККП \"Театр кукол\" акимата города Астаны)")
_ADDR = re.compile(r"(?P<v>г\.Астана, проспект Республики 3)")
_PHONE = re.compile(r"(?P<v>\+7 \(7172\) 43-96-24)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    name, addr, phone = _NAME.search(text), _ADDR.search(text), _PHONE.search(text)
    if not (name and addr):
        return [], [URL], "name/address block not found."
    ev = [store.evidence("name", URL, name[0], page.fetched_at),
          store.evidence("address", URL, addr[0], page.fetched_at)]
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    b = store.make_branch("ГККП «Театр кукол» акимата города Астаны", ev, "html", 0.8, address=addr["v"],
                          phone=phone["v"] if phone else None, url=URL)
    notes = ("Официальный сайт театра; на контактах и по всему сайту нет ни графика работы, ни часов кассы — "
             "представления идут по афише (Календарь спектаклей), поэтому opening_hours не хранится. E-mail "
             "New@teatrkukol-ast.kz не входит в схему branch.")
    return [b], [URL], notes
