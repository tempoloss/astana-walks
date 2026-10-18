"""a-vm.kz: Astana Venue Management — оператор монумента «Байтерек» и Дворца Мира и Согласия. Каждая страница
объекта печатает сезонный график, адрес и телефон; OSM opening_hours не выражает сезонность -> raw остаётся."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

PAGES = [
    ("Байтерек", "https://a-vm.kz/objects/bayterek/", "Байтерек",
     re.compile(r"(?P<v>Адрес: бульвар Нуржол, 14)")),
    ("Дворец Мира и Согласия", "https://a-vm.kz/objects/peace/", "Мира и Согласия",
     re.compile(r"(?P<v>Адрес: Проспект Тауелсиздик, 57)")),
]
_HOURS = re.compile(r"(?P<v>1 июня – 31 августа – с \d\d:\d\d до \d\d:\d\d 1 сентября – 31 мая – с \d\d:\d\d до \d\d:\d\d)")
_PHONE = re.compile(r"(?P<v>\+7 \(7172\) \d\d-\d\d-\d\d|\+7 7172 \d\d\d \d\d\d)")


def crawl(fetcher: SiteFetcher):
    branches, pages = [], []
    for name, url, name_probe, addr_rx in PAGES:
        pages.append(url)
        page = fetcher.fetch(url)
        if not page.ok:
            continue
        text = visible_text(page.text)
        hours, addr, phone = _HOURS.search(text), addr_rx.search(text), _PHONE.search(text)
        if not (hours or addr):
            continue
        nm = re.search(re.escape(name_probe), text)
        ev = [store.evidence("name", url, name_probe, page.fetched_at)] if nm else []
        if addr:
            ev.append(store.evidence("address", url, addr[0], page.fetched_at))
        if hours:
            ev.append(store.evidence("opening_hours", url, hours[0], page.fetched_at))
        if phone:
            ev.append(store.evidence("phone", url, phone[0], page.fetched_at))
        branches.append(store.make_branch(name, ev, "html", 0.85,
                                          address=addr[0].replace("Адрес: ", "") if addr else None,
                                          phone=phone[0] if phone else None,
                                          opening_hours_raw=hours["v"] if hours else None, url=url))
    notes = ("Seasonal schedules (summer/winter ranges) cannot be expressed in opening_hours from this phrasing, so "
             "opening_hours_osm stays None and the verbatim text is kept (no days named at all: needs_days). Price "
             "lists (Байтерек 2500 ₸ и т. п.) are on the same pages but do not belong to the branch schema. The first "
             "phone is the venue's public number; «по коммерческим вопросам» numbers not stored. The museum inside the "
             "Пирамида has its own operator (astana-piramida.kz, crawled separately).")
    return branches, pages, notes
