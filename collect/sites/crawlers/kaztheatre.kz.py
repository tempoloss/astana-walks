"""kaztheatre.kz/kk/page/bailanys-2: Казахский театр им. К. Куанышбаева — адрес, касса, приёмная."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://kaztheatre.kz/kk/page/bailanys-2"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr = re.search(r"(?P<v>Астана қаласы, Қалибек Қуанышбаев көшесі, 8/1)", text)
    phone = re.search(r"(?P<v>\+7 7172 24 83 23)", text)
    name = re.search(r"(?P<v>«Қалибек Қуанышбаев атындағы Қазақ ұлттық музыкалық драма театры» РМҚК)", text)
    if not addr:
        return [], [URL], "address not found."
    ev = [store.evidence("address", URL, addr[0], page.fetched_at)]
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    b = store.make_branch("Государственный Академический казахский музыкально-драматический театр им. К. Куанышбаева",
                          ev, "html", 0.8, address=addr["v"], phone=phone and phone["v"], url=URL)
    notes = ("The contacts page lists the ticket office (+7 7172 24 83 23, also +7 778 464 12 95) and reception "
             "(+7 7172 27 02 35); only the box-office number is stored. No visiting/box-office hours text on the "
             "site, so no opening_hours.")
    return [b], [URL], notes
