"""mastercoffee.kz: /contacts hides the branch block in escaped-JSON HTML; the Astana outlet is printed there."""
from __future__ import annotations

import html as htmllib
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://mastercoffee.kz/contacts"


def _decoded(page) -> str:
    """/contacts text view: the verifier's unicode-unescaped + entity-decoded variant, whitespace-normalised."""
    raw = page.text
    un = re.sub(r"\\u([0-9a-fA-F]{4})", lambda m: chr(int(m[1], 16)), raw).replace("\\/", "/")
    return store.norm_ws(htmllib.unescape(un))


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = _decoded(page)
    addr = re.search(r"(Фактический адрес: РК, г\. Астана, переулок(?:&nbsp;)? Жумабека Ташенова, дом 4/2, ВП 1\.)",
                     text)
    phone = re.search(r"(\+7 778 161 30 33)", text)
    hours = re.search(r"(Пн-Пт: 09:00-18:00, Сб: 10:00 - 16:00, Вс - выходной)", text)
    name = re.search(r"(MASTER COFFEE TRADE)", text)
    if not (addr and phone):
        return [], [URL], "Astana contacts block not found in the decoded page"
    ev = []
    if name:
        ev.append(store.evidence("name", URL, name[1], page.fetched_at))
    ev.append(store.evidence("address", URL, addr[1], page.fetched_at))
    ev.append(store.evidence("phone", URL, phone[1], page.fetched_at))
    if hours:
        ev.append(store.evidence("opening_hours", URL, hours[1], page.fetched_at))
    raw_hours = hours[1] if hours else None
    b = store.make_branch("Master Coffee (MASTER COFFEE TRADE, ИП)", ev, "html", 0.75,
                          address="РК, г. Астана, переулок Жумабека Ташенова, дом 4/2, ВП 1",
                          phone="+7 778 161 30 33", opening_hours_raw=raw_hours, url=URL)
    notes = ("Coffee roastery/coffee shop: /contacts prints (inside an escaped-JSON block) the Astana outlet of "
             "ИП \"MASTER COFFEE TRADE\": юридический адрес ул. Әлихан Бөкейхан 25 кв/офис 53 and фактический "
             "адрес переулок Жумабека Ташенова 4/2 ВП 1 (the physical one is stored), phone +7 778 161 30 33, "
             "график Пн-Пт 09:00-18:00, Сб 10:00-16:00, Вс выходной. This is the office/roastery, not the "
             "'Master Coffee Capital Park' cafe; the site lists no other Astana addresses.")
    return [b], [URL], notes
