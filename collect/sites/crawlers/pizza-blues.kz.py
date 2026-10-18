"""pizza-blues.kz: /kontactPB lists the Астана branch outlets with per-address delivery phones; no opening hours
are published on the site (the Astana menu pages only). astana.pizza-blues.kz does not resolve (DNS)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://www.pizza-blues.kz/kontactPB"
OUTLETS = [("ул. Сатпаева, 11 тел. +7 747 1 344 526", "ул. Сатпаева, 11", "+7 747 1 344 526"),
           ("ул. Керей Жанибек хандар, 22 тел. +7 747 1 205 280", "ул. Керей Жанибек хандар, 22", "+7 747 1 205 280")]


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    vis = visible_text(page.text)
    header = 'ФИЛИАЛ "ПИЦЦА БЛЮЗ" г.Астана'
    if header not in vis:
        return [], [URL], f"{URL}: Астана branch header not found"
    branches = []
    for snippet, addr, phone in OUTLETS:
        if snippet not in vis:
            continue
        ev = [store.evidence("name", URL, header, page.fetched_at),
              store.evidence("address", URL, addr, page.fetched_at),
              store.evidence("phone", URL, snippet, page.fetched_at)]
        branches.append(store.make_branch(f"Пицца Блюз, {addr}", ev, "html", 0.75, address=addr, phone=phone, url=URL))
    notes = ("Both phones are the branch's 'Телефоны доставки' lines printed next to each address in the Астана "
             "section. No opening hours anywhere on the site (menu/contact pages checked). The former central-office "
             "number 8 (7172) 344 526 duplicates the Сатпаева line and is not stored separately.")
    return branches, [URL], notes
