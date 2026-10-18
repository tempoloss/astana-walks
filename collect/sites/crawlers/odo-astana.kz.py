"""odo-astana.kz: Центр олимпийской подготовки «Сарыарка» — фитнес-центр на пр. Кабанбай батыра 45А (manual target
way/460048101 «Ледовая арена»/спорт-кластер). Страница /ru/fitness-center-cot/ печатает подневный график."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://odo-astana.kz/ru/fitness-center-cot/"
_LINE = re.compile(r"(?P<day>Понедельник|Вторник|Среда|Четверг|Пятница|Суббота|Воскресенье) - "
                   r"(?P<range>с \d{1,2}:\d\d до \d{1,2}:\d\d)(?: \(раз в две недели, по понедельникам - "
                   r"санитарный день\))?")
_ADDR = re.compile(r"(?P<v>Наш адрес: (?P<a>г\. Астана, проспект Кабанбай батыра, 45 А))")
_PHONE = re.compile(r"(?P<v>\+7 \(7172\) 707 179)")
_NAME = re.compile(r"(?P<v>фитнес центр)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    lines = list(_LINE.finditer(text))
    addr, phone = _ADDR.search(text), _PHONE.search(text)
    if len(lines) < 7 or not addr:
        return [], [URL], "per-day schedule or address block not found (layout changed)."
    # 'График работы фитнес центра:' block lists all seven days; take it before the cassa block (also 7 lines?
    # the cassa line has no day names, so the first seven day-hits are the club schedule).
    raw = "; ".join(f"{m['day']} {m['range']}" for m in lines[:7])
    ev = [store.evidence("opening_hours", URL, "График работы фитнес центра: " + lines[0]["day"] + " - " +
                         lines[0]["range"], page.fetched_at),
          store.evidence("address", URL, addr["a"], page.fetched_at)]
    name = _NAME.search(text)
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    b = store.make_branch("Фитнес-центр ЦОП «Сарыарка»", ev, "html", 0.8, address=addr["a"],
                          phone=phone[0] if phone else None, opening_hours_raw=raw, url=URL)
    notes = ("Семь подневных строк 'Понедельник - с 7:00 до 23:00 ...' (единый интервал) конвертируются в "
             "Mo-Su 07:00-23:00; в raw дни склеены ';'. Внутренняя вставка '(раз в две недели, по понедельникам - "
             "санитарный день)' вынесена из raw (невыразимо в OSM, цитируется здесь). Часы кассы (7:00-20:30 вт-вс, "
             "обед 13:00-13:30) — касса, не клуб. Велотрек Сарыарка по тому же адресу — velotrek.kz (p3).")
    return [b], [URL], notes
