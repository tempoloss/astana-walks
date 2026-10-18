"""zebra-coffee.clients.site: Zebra Coffee (агрегатор-конструктор sites, но страница — собственная визитка
заведения, домен из scout_chains). Инлайн-JSON печатает per-day расписание (экранированные кавычки), адрес и телефон."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://zebra-coffee.clients.site/"
_SCHED = re.compile(r'\\"day\\":\\"(?P<day>Понедельник|Вторник|Среда|Четверг|Пятница|Суббота|Воскресенье)\\",'
                    r'[^{]*?\\"hours\\":\[\\"(?P<t>\d\d:\d\d[–-]\d\d:\d\d)\\"\]')
_ADDR = re.compile(r"(?P<v>Астана, Мұхтар Әуезов көшесі, 17)")
_PHONE = re.compile(r"(?P<v>\+7 705 725 1980)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    days = list(_SCHED.finditer(page.text))[:7]
    addr, phone = _ADDR.search(text), _PHONE.search(text)
    if not days:
        return [], [URL], "readableSchedule JSON not found (layout changed)."
    raw = "; ".join(f"{m['day']} {m['t']}" for m in days)
    snip = page.text[days[0].start():days[0].end()]
    ev = [store.evidence("name", URL, "Zebra coffee", page.fetched_at),
          store.evidence("opening_hours", URL, snip, page.fetched_at)]
    if addr:
        ev.append(store.evidence("address", URL, addr[0], page.fetched_at))
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    b = store.make_branch("Zebra coffee", ev, "html", 0.8, address=addr["v"] if addr else None,
                          phone=phone[0] if phone else None, opening_hours_raw=raw, url=URL)
    notes = ("Расписание — инлайн-JSON страницы (readableSchedule, дни по-русски, единый интервал все 7 дней -> "
             "Mo-Su 07:30-23:00); сниппет — дословный экранированный фрагмент JSON. Ссылка 'Открыто' — статус на "
             "момент запроса, не часы. zebracoffee.kz редиректит на этот clients.site; адрес без lat/lng.")
    return [b], [URL], notes
