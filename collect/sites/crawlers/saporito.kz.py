"""saporito.kz: ресторан «Saporito» (ЖК «Туркестан», ул. Кошкарбаева 34). Статический сайт;
блок контактов даёт адрес, телефоны и время работы без дней недели."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://www.saporito.kz/%D0%BA%D0%BE%D0%BD%D1%82%D0%B0%D0%BA%D1%82%D1%8B.html"
_ADDR = re.compile(r"(?P<v>Ул\. Кошкарбаева, 34, ЖК \"Туркестан\")")
_PHONE = re.compile(r"Телефон: (?P<v>\+7\(7172\) 65-50-65)")
_HOURS = re.compile(r"(?P<v>Время работы: с \d\d:\d\d - \d\d:\d\d)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr, phone, hours = _ADDR.search(text), _PHONE.search(text), _HOURS.search(text)
    if not (addr and hours):
        return [], [URL], "contacts block not found."
    ev = [store.evidence("name", URL, "Saporito", page.fetched_at),
          store.evidence("address", URL, addr[0], page.fetched_at),
          store.evidence("opening_hours", URL, hours[0], page.fetched_at)]
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    b = store.make_branch("Saporito", ev, "html", 0.75, address=f"Астана, {addr['v']}",
                          phone=phone["v"] if phone else None,
                          opening_hours_raw=hours["v"].replace("Время работы: ", ""), url=URL)
    notes = ("'Время работы: с 08:00 - 02:00' names no days -> hours_flags needs_days, raw kept. The about page "
             "confirms 'Ежедневно с 08.00 утра' (breakfast) but the daily schedule itself is the contacts-page range. "
             "Second mobile phone +7(707) 555-02-99 (Моб.) also on the page; the landline is stored.")
    return [b], [URL], notes
