"""qazaqconcert.kz: /ru/contacts prints the venue's full legal name, address and contact phones (no public
opening-hours block; the ticket-office schedule is rendered by a JS widget)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://qazaqconcert.kz/ru/contacts"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    vis = visible_text(page.text)
    ev, values = [], {}
    m = re.search(r'(?P<v>РГКП "Государственная академическая концертная организация "Қазақконцерт" '
                  r'имени Розы Баглановой")', vis)
    if m:
        ev.append(store.evidence("name", URL, m["v"], page.fetched_at))
        values["name"] = m["v"]
    m = re.search(r"(?P<v>г\. Астана, пр\.Мәңгілік ел, 10/1)", vis)
    if m:
        ev.append(store.evidence("address", URL, m[0], page.fetched_at))
        values["address"] = m["v"]
    m = re.search(r"(?P<v>Колл-центр \+7 706 730 6601)", vis)
    if m:
        ev.append(store.evidence("phone", URL, m[0], page.fetched_at))
        values["phone"] = "+7 706 730 6601"
    if not values.get("address") and not values.get("phone"):
        return [], [URL], f"{URL}: nothing parsed"
    notes = ("Contacts of the «Қазақконцерт» organisation (the ЦКЗ/ОКЗ «Қазақстан» concert hall). Phones listed per "
             "department (дирекция 70-53-02, аренда залов 70-52-41); stored is the колл-центр line +7 706 730 6601 "
             "(the visitor number). The page states no opening hours (the ticket-office schedule loads through a JS "
             "widget), so hours stay None — never inferred.")
    b = store.make_branch(values.get("name", "Қазақконцерт"), ev, "html", 0.8, address=values.get("address"),
                          phone=values.get("phone"), url=URL)
    return [b], [URL], notes
