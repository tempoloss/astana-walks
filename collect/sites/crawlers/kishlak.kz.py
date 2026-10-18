"""kishlak.kz/astana-contact/: ресторан «Кишлак» в Астане — контакты текстом (Тел./Адрес/Время работы)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://kishlak.kz/astana-contact/"
RX = {
    "address": r"(?P<v>г\. Нур-Султан, пр\. Кабанбай батыра, 19/1, Круглая площадь)",
    "phone": r"Тел\.: (?P<v>\+7 \(702\) 203-57-77)",
    "hours": r"Время работы: (?P<v>с 11\.30 до 02\.00 \(без выходных\))",
}


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    ev, values = [], {}
    for field, rx in RX.items():
        m = re.search(rx, text)
        if m:
            ev.append(store.evidence({"hours": "opening_hours"}.get(field, field), URL, m[0], page.fetched_at))
            values[field] = m["v"]
    m = re.search(r"(?P<v>Кишлак \(Нур-Султан\))", page.text)
    if m:
        ev.append(store.evidence("name", URL, m[0], page.fetched_at))
    if not values:
        return [], [URL], "contacts block not found."
    b = store.make_branch("Кишлак", ev, "html", 0.8, address=values.get("address"), phone=values.get("phone"),
                          opening_hours_raw=values.get("hours"), url=URL)
    notes = ("Astana branch block on the contacts page; the same page also lists two Almaty addresses, which are not "
             "stored. Hours cross midnight (11:30-02:00).")
    return [b], [URL], notes
