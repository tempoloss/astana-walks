"""eurotrans.kz: transport company; /contacts-2 prints address, phones and a work schedule; the company name is on
the home page (Joomla renders the contacts redirect without the site title)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402
HOME = "https://eurotrans.kz/ru/"  # the branded front page; the bare host 301-redirects here without the name
URL = "https://eurotrans.kz/contacts-2"
NAME = "Транспортная компания Eurotrans Group"
_ADDR = re.compile(r"Адрес: (?P<v>Z05H9D1, г\. Астана, ул\.Кунаева 23/1)")
_PHONE = re.compile(r"Телефон: (?P<v>\+7 \(708\) 425 38 03 \+7 \(7172\) 573 888)")
_HOURS = re.compile(r"График работы: (?P<v>Пн-Пт: с 9:00 до 18:00 Сб-Вс: выходной)")


def crawl(fetcher: SiteFetcher):
    home = fetcher.fetch(HOME)
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [HOME, URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    ev, vals = [], {}
    for field, rx in (("address", _ADDR), ("phone", _PHONE), ("hours", _HOURS)):
        if m := rx.search(text):
            key = "opening_hours" if field == "hours" else field
            ev.append(store.evidence(key, URL, m[0], page.fetched_at))
            vals[field] = m["v"]
    if home.ok and NAME in visible_text(home.text):
        ev.append(store.evidence("name", HOME, NAME, home.fetched_at))
    if not ev:
        return [], [HOME, URL], "no contacts found."
    b = store.make_branch("Eurotrans Group", ev, "html", 0.8, address=vals.get("address"),
                          phone=vals.get("phone"), opening_hours_raw=vals.get("hours"), url=URL)
    notes = ("POI «Eurotrans Group» is the office of a logistics company (transit_station category). Working "
             "schedule, not 24/7 cargo ops; site JSON-LD repeats the same address. The e-mail is JS-obfuscated on "
             "the page (no verbatim snippet, not stored).")
    return [b], [HOME, URL], notes
