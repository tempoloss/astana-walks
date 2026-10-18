"""mtexm.com: ТОО «MTEX Management» — оператор стадиона «Астана Арена» (manual target wikidata/Q746559).
Карточка объекта /object/astana-arena печатает адрес и телефон; постоянного графика у стадиона нет (мероприятия)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://mtexm.com/object/astana-arena"
_NAME = re.compile(r"(?P<v>«Астана-Арена»)")
_ADDR = re.compile(r"(?P<v>Адрес: РК, Астана, пр\. Туран, 48)")
_PHONE = re.compile(r"(?P<v>Телефон: \+7 \(7172\) 70-26-87)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr, phone = _ADDR.search(text), _PHONE.search(text)
    name = _NAME.search(text)
    if not addr:
        return [], [URL], "address block not found."
    ev = [store.evidence("address", URL, addr[0], page.fetched_at)]
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    b = store.make_branch("Стадион «Астана Арена»", ev, "html", 0.85,
                          address=addr[0].replace("Адрес: ", ""), phone=phone[0].replace("Телефон: ", "")
                          if phone else None, url=URL)
    notes = ("Страница объекта оператора (MTEX Management): вместимость 30 000, поле 105×68 м. Фиксированного "
             "графика свободного входа сайт не публикует — стадион работает по расписанию матчей/мероприятий "
             "(Календарь), поэтому opening_hours нет. Телефон администрации оператора +7 (7172) 61-34-41 не храним — "
             "он управленческой компании, не арены.")
    return [b], [URL], notes
