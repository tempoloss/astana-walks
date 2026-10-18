"""eagilik.com: библиотека/кофе-бар Eagilik (Астана) — расписание и телефоны отдела кофе-бара."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://www.eagilik.com/index.php/ru/about-eagilik-ru/contact-us-ru"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    hours = re.search(r"(?P<v>Вт-Сб: 10:00-21:00 Вс: 14:00-21:00 Пн: выходной)", text)
    phone = re.search(r"(?P<v>Coffee Bar & Bookstore \| \+7-\(7172\)-20-19-83)", text)
    name = re.search(r"(?P<v>Eagilik, Astana)", text) or re.search(r"(?P<v>Кофе бар)", text)
    if not hours:
        return [], [URL], "schedule block not found."
    ev = [store.evidence("opening_hours", URL, hours[0], page.fetched_at)]
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    b = store.make_branch("Eagilik - Books & Coffee", ev, "html", 0.7, phone=phone["v"].split("| ")[-1] if phone else None,
                          opening_hours_raw=hours["v"], url=URL)
    notes = ("The contacts page prints 'Нажмите на карту, чтобы узнать, где мы находимся' — street address is not in "
             "the text, only inside a Google-Maps link ('Eagilik, Astana'), so no address is stored. Phone belongs to "
             "the coffee bar & bookstore department; the library department number (+7-(7172)-20-08-01) is a separate "
             "desk and not stored. Schedule converted to Tu-Sa 10:00-21:00; Su 14:00-21:00; Mo off.")
    return [b], [URL], notes
