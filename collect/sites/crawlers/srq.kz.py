"""srq.kz: ТРЦ «Сарыарка» (ТРЦ на пр. Туран 24; домен из scout_chains). Статический сайт; главная модалка
«ВРЕМЯ РАБОТЫ» печатается в HTML (зоны ТЦ), блок контактов — адрес/телефон/почта."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://srq.kz/ru"
_ADDR = re.compile(r"(?P<v>Адрес: город Астана, пр\. Туран, 24)")
_PHONE = re.compile(r"(?P<v>Телефон: \+7 701 081 02 27)")
_HOURS = re.compile(r"(?P<v>Время работы: Магазины: 1,2,3 этажи \d\d:\d\d - \d\d:\d\d)")
_NAME = re.compile(r"(?P<v>SARYARQA)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr, phone, hours, name = _ADDR.search(text), _PHONE.search(text), _HOURS.search(text), _NAME.search(text)
    if not (addr and name):
        return [], [URL], "address/name block not found."
    ev = [store.evidence("name", URL, name[0], page.fetched_at),
          store.evidence("address", URL, addr[0], page.fetched_at)]
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    if hours:
        ev.append(store.evidence("opening_hours", URL, hours[0], page.fetched_at))
    b = store.make_branch("ТРЦ «Сарыарка»", ev, "html", 0.8, address=addr[0].replace("Адрес: ", ""),
                          phone=phone[0].replace("Телефон: ", "") if phone else None,
                          opening_hours_raw=hours[0].replace("Время работы: ", "") if hours else None, url=URL)
    notes = ("Молалка «ВРЕМЯ РАБОТЫ» даёт часы по зонам (Магазины 10:00-22:00, Кафе/бары 10:00-24:00, Кинотеатр "
             "10:00-03:00, паркинг круглосуточный); без дней недели -> opening_hours_raw хранит первую строку "
             "(зоны магазинов), OSM не выводится. Единой строки «ТРЦ с X до Y» на сайте нет. Это тот же ТРЦ, что "
             "saryarka.com (домен закреплён за p1).")
    return [b], [URL], notes
