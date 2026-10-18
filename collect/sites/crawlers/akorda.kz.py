"""akorda.kz: официальный сайт Президента РК — резиденция «Ак орда» (P856 Wikidata Q413579).

Страница «График приёма граждан» (`/public/ru/executive_office/schedule`) — расписание приёма граждан
Администрацией Президента, а не часы посещения резиденции: по правилам этого репозитория административные /
приёмные часы никогда не становятся `opening_hours` заведения. Экскурсионного расписания Ак орды сайт не
публикует — веток нет, фактов нет, только вердикт.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.fetch import SiteFetcher  # noqa: E402

SCHEDULE = "https://akorda.kz/public/ru/executive_office/schedule"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(SCHEDULE)
    pages = [page.url] if page.ok else []
    notes = ("Резиденция «Ак орда»: сайт публикует только «График приёма граждан» Администрации — служебные часы "
             "приёма, не график посещения резиденции (экскурсии не публикуются) → веток и часов нет. "
             "Административные часы в opening_hours не попадают по правилам collect/sites.")
    return [], pages, notes
