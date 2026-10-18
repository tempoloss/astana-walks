"""nabrk.kz: Национальная академическая библиотека РК (domain item p6). Drupal: /ru/page/rezhim-raboty даёт
график работы, /ru/page/kak-nas-nayti-0 — адрес и телефоны."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

SCHEDULE = "https://nabrk.kz/ru/page/rezhim-raboty"
FIND = "https://nabrk.kz/ru/page/kak-nas-nayti-0"
_HOURS = re.compile(r"(?P<v>работает с \d\d\.\d\d до \d\d\.\d\d ч\., суббота-воскресенье с \d\d\.\d\d до \d\d\.\d\d часов)")
_ADDR = re.compile(r"(?P<v>010000, Республика Казахстан, г\.Астана, ул\. Достык 11)")
_PHONE = re.compile(r"(?P<v>\+7\(7172\) 472545, 472653)")
_NAME = re.compile(r"(?P<v>Национальная Академическая Библиотека Республики Казахстан)")


def crawl(fetcher: SiteFetcher):
    p_sched, p_find = fetcher.fetch(SCHEDULE), fetcher.fetch(FIND)
    pages = [SCHEDULE, FIND]
    if not (p_sched.ok and p_find.ok):
        return [], pages, "schedule/contacts page unavailable"
    sched, find = visible_text(p_sched.text), visible_text(p_find.text)
    hours, addr, phone, name_m = _HOURS.search(sched), _ADDR.search(find), _PHONE.search(find), _NAME.search(sched)
    if not (hours and addr and name_m):
        return [], pages, "expected hours/address block not found (page layout changed)"
    ev = [store.evidence("name", SCHEDULE, name_m[0], p_sched.fetched_at),
          store.evidence("opening_hours", SCHEDULE, hours[0], p_sched.fetched_at),
          store.evidence("address", FIND, addr[0], p_find.fetched_at)]
    if phone:
        ev.append(store.evidence("phone", FIND, phone[0], p_find.fetched_at))
    b = store.make_branch("Национальная академическая библиотека Республики Казахстан", ev, "html", 0.8,
                          address=addr["v"], phone=phone["v"] if phone else None,
                          opening_hours_raw=hours["v"], url=SCHEDULE)
    notes = ("Фраза графика не называет дней для будней ('работает с 09.00 до 20.00 ч., суббота-воскресенье ...') — "
             "hours_flags фиксирует причину неконвертации, raw сохранён дословно. Та же страница добавляет "
             "'Последняя пятница каждого месяца – санитарный день' и 'Государственные праздничные дни библиотека не "
             "работает' — исключения, не выразимые в OSM. Телефон — справочные номера библиотеки со страницы "
             "'Как нас найти'.")
    return [b], pages, notes
