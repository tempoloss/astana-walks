"""ailand.kz: ЦСО «Ailand» (океанариум, экзотариум, «Джунгли», колесо обозрения). WordPress-страница
/ru/schedule-ru/ печатает расписание каждого объекта; в подвале — адрес и общие телефоны центра."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://ailand.kz/ru/schedule-ru/"
_ADDR = re.compile(r"(?P<v>г\. Астана, ул\. Шоссе Коргалжын 2)")
_PHONE = re.compile(r"(?P<v>\+7 708 757 55 55, \+7 7172 57 55 55)")
_SPACED = re.compile(r"(?P<name>ОКЕАНАРИУМ|ДЖУНГЛИ|ЭКЗОТАРИУМ) (?P<v>\d\d:\d\d — \d\d:\d\d)")
_WHEEL = re.compile(r"КОЛЕСО ОБОЗРЕНИЯ (?P<v1>\d\d:\d\d-\d\d:\d\d) ПН-ЧТ.*?(?P<v2>\d\d:\d\d-\d\d:\d\d) ПТ-ВС",
                    re.DOTALL)


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr, phone = _ADDR.search(text), _PHONE.search(text)

    def base_ev(name_snip: str, hours_snip: str) -> list[dict]:
        ev = [store.evidence("name", URL, name_snip, page.fetched_at),
              store.evidence("opening_hours", URL, hours_snip, page.fetched_at)]
        if addr:
            ev.append(store.evidence("address", URL, addr[0], page.fetched_at))
        if phone:
            ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
        return ev

    branches = []
    for m in _SPACED.finditer(text):
        branches.append(store.make_branch(
            f"{m['name'].capitalize()} (ЦСО Ailand)", base_ev(m["name"], f"{m['name']} {m['v']}"), "html", 0.8,
            address=addr["v"] if addr else None, phone=phone["v"] if phone else None,
            opening_hours_raw=m["v"], url=URL))
    w = _WHEEL.search(text)
    if w:
        ev = base_ev("КОЛЕСО ОБОЗРЕНИЯ", f"КОЛЕСО ОБОЗРЕНИЯ {w['v1']} ПН-ЧТ")
        ev.append(store.evidence("opening_hours", URL, f"{w['v2']} ПТ-ВС", page.fetched_at))
        branches.append(store.make_branch("Колесо обозрения (ЦСО Ailand)", ev, "html", 0.8,
                                          address=addr["v"] if addr else None,
                                          phone=phone["v"] if phone else None,
                                          opening_hours_raw=f"{w['v1']} ПН-ЧТ; {w['v2']} ПТ-ВС", url=URL))
    notes = ("Четыре объекта одного развлекательного центра, у каждого своя строка расписания; 'работает без выходных' "
             "— заголовок без дней, поэтому day-less строки остаются raw (Океанариум 10:00 — 21:00, Экзотариум "
             "10:00 — 20:00, Джунгли 12:00 — 20:00); Колесо обозрения даёт ПН-ЧТ/ПТ-ВС диапазоны и конвертируется "
             "(00:00 закрытие -> 24:00). Ограничение касс ('Билеты ... до 20:30') не хранится. Телефоны и адрес — "
             "общие номера/адрес центра из подвала той же страницы (не per-attraction). Парк аттракционов/Cosmo Arena "
             "без постоянного расписания.")
    return branches, [URL], notes
