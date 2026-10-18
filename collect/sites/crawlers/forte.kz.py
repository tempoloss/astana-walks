"""forte.kz: ForteBank Kulanshi Art Space (manual target overture/e2157a69, галерея в головном офисе ForteBank,
ул. Достык 8/1). Отдельного сайта у арт-пространства нет; свежий пресс-релиз банка печатает режим работы и адрес."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://forte.kz/ru/news/forte-kulanshi-art-space-predstavyalet-vystavku-qazyna-araly"
_HOURS = re.compile(r"(?P<v>Режим работы: ежедневно с \d\d:\d\d до \d\d:\d\d)")
_ADDR = re.compile(r"(?P<v>Адрес: г\. Астана, ул\. Достык 8/1)")
_NAME = re.compile(r"(?P<v>Forte Kulanshi Art Space)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    hours, addr, name = _HOURS.search(text), _ADDR.search(text), _NAME.search(text)
    if not (hours and addr):
        return [], [URL], "hours/address lines not found (page changed)."
    ev = [store.evidence("address", URL, addr[0], page.fetched_at),
          store.evidence("opening_hours", URL, hours[0], page.fetched_at)]
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    b = store.make_branch("Forte Kulanshi Art Space", ev, "html", 0.75, address=addr[0].replace("Адрес: ", ""),
                          opening_hours_raw=hours[0].replace("Режим работы: ", ""), url=URL)
    notes = ("Часы заявлены в анонсе текущей выставки на официальном сайте ForteBank (оператора площадки): "
             "'ежедневно с 10:00 до 20:00'. Более ранний релиз той же площадки указывает 'с 9:00 ч. до 20:00 ч.' — "
             "взят свежий (okt-2026). Собственного домена у галереи нет (Instagram @forte.kulanshi.artspace — не "
             "хранится). Вход бесплатный — в анонсах, но без явной строки прайса в карточку не кладём.")
    return [b], [URL], notes
