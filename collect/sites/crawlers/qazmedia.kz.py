"""qazmedia.kz: ТОО «Управляющая компания «Қазмедиа орталығы» (manual target «Казмедиа центр», entertainment).
На страницах сайта — JSON-LD Organization с названием и описанием телерадиокомплекса; публичных часов посещения
и адреса в статике нет (график приёма граждан: среда 09:00-13:00 — это приёмная, не режим объекта)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://qazmedia.kz/ru/"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    branches = []
    for b in fetcher.jsonld_branches(URL):
        if "Қазмедиа орталығы" not in b["name"]:
            continue
        if not (b.get("description") or b.get("address") or b.get("phone")):
            continue
        b["confidence"] = 0.7
        branches.append(b)
    if not branches:
        return [], [URL], "Organization JSON-LD not found on the home page."
    notes = ("Только имя + описание из официального JSON-LD: адрес/координат/часов посещения сайт не публикует "
             "(на главной — 'День приема граждан: среда Время приема граждан: с 09:00 до 13:00', это приём "
             "гендиректора, не режим комплекса; телефоны — канцелярия/пиар-отдел). Концертный зал и выставки "
             "продаются через zakazbiletov.kz (агрегатор).")
    return branches, [URL], re.sub(r"\s+", " ", notes)
