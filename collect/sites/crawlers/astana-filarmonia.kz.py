"""astana-filarmonia.kz: ГККП «Государственная академическая филармония им. Е. Рахмадиева» (manual target
node/4916363251). Joomla-сайт; /ru/o-nas/kontakty печатает адреса трёх площадок и телефоны (часов нет — концерты
по афише)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://astana-filarmonia.kz/ru/o-nas/kontakty"
_NAME = re.compile(r"(?P<v>Еркеғали Рахмадиев атындағы мемлекеттік академиялық филармония)")
_ADDR = re.compile(r"(?P<v>город Астана, 010000, улица Кенесары 32 \(Концертный зал\))")
_PHONE = re.compile(r"(?P<v>Код города: 8 \(7172\) Приемная: 75-22-00 Касса: 75-23-83)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    name, addr, phone = _NAME.search(text), _ADDR.search(text), _PHONE.search(text)
    if not (name and addr):
        return [], [URL], "name/address block not found (layout changed)."
    ev = [store.evidence("name", URL, name[0], page.fetched_at),
          store.evidence("address", URL, addr[0], page.fetched_at)]
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    b = store.make_branch("Государственная академическая филармония имени Еркегали Рахмадиева", ev, "html", 0.8,
                          address=addr[0], phone="+7 7172 75-22-00" if phone else None, url=URL)
    notes = ("Концертный зал (Кенесары 32) — основная площадка; сайт перечисляет также Камерный зал (Абая 29) и "
             "Репетиционный (Бокейхана 25г) — отдельные адреса хранятся в notes, чтобы join не схватил их одним "
             "филиалом. Часов работы/кассы в HTML нет (афиша = события). Телефон — приёмная из блока 'Код города: "
             "8 (7172) Приемная: 75-22-00 Касса: 75-23-83'. E-mail скрыт JS-обфускацией.")
    return [b], [URL], notes
