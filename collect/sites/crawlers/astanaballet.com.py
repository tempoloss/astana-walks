"""astanaballet.com/ru/pages/kontakty: театр «Астана Балет» — адрес и телефоны (часов нет)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://astanaballet.com/ru/pages/kontakty"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr = re.search(r"(?P<v>г\. Астана, проспект Ұлы дала, 43 \(бывший Ұлы дала, 9\))", text)
    phone = re.search(r"Касса (?P<v>\+7 7172 62-12-12)", text)
    name = re.search(r"(?P<v>Контакты - Театр Астана Балет)", page.text)
    if not addr:
        return [], [URL], "address not found."
    ev = [store.evidence("address", URL, addr[0], page.fetched_at)]
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    b = store.make_branch("Астана балет", ev, "html", 0.8, address="г. Астана, проспект Ұлы дала, 43",
                          phone=phone and " ".join(phone[0].split()), url=URL)
    notes = ("Contacts page: касса +7 7172 62-12-12, приемная/канцелярия/маркетинг numbers exist too, only the box "
             "office is stored. Performance schedule (афиша) is per-event, not opening hours -> no opening_hours. "
             "www.astanaballet.com robots.txt is for the wrong cert host; the bare https host was used.")
    return [b], [URL], notes
