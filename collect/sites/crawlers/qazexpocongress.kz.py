"""qazexpocongress.kz: «Нұр Әлем» (сфера EXPO), оператор QazExpoCongress. /ru/nur-alem/ печатает график,
кассовый график, адрес и телефон — и предупреждение, что музей с декабря 2024 посетителей не принимает."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://qazexpocongress.kz/ru/nur-alem/"
_ADDR = re.compile(r"(?P<v>010000, г\. Астана, пр\. Мангилик Ел 55/\d+)")
_PHONE = re.compile(r"(?P<v>8 747 169 90 92)")
_HOURS = re.compile(r"График работы (?P<v>Вторник - Пятница с \d\d:\d\d до \d\d:\d\d) касса с \d\d:\d\d до \d\d:\d\d "
                    r"(?P<v2>Суббота - Воскресенье с \d\d:\d\d до \d\d:\d\d)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr, phone, hours = _ADDR.search(text), _PHONE.search(text), _HOURS.search(text)
    if not addr:
        return [], [URL], "address block not found."
    probe = "Нұр Әлем" if "Нұр Әлем" in text else "Музей энергии будущего"
    ev = [store.evidence("name", URL, probe, page.fetched_at),
          store.evidence("address", URL, addr[0], page.fetched_at)]
    raw = None
    if hours:
        raw = f"{hours['v']}; {hours['v2']}"
        ev.append(store.evidence("opening_hours", URL, hours[0], page.fetched_at))
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    b = store.make_branch("Нұр Әлем (Nur Alem, сфера EXPO)", ev, "html", 0.8, address=addr["v"],
                          phone=phone[0] if phone else None, opening_hours_raw=raw, url=URL)
    notes = ("The page still prints the working schedule (Вт-Пт 10-20, Сб-Вс 10-21, Пн — технический день) AND the "
             "notice 'С декабря 2024 года Музей энергии будущего завершил свою работу и прекратил прием посетителей' "
             "(здание занимает центр ИИ alem.ai). Hours are therefore stale-but-verbatim; join should weigh the "
             "closure notice. The cassa sub-schedule (10-19/10-20) and the Monday technical day sit inside the raw "
             "text but not in the OSM string.")
    return [b], [URL], notes
