"""museumgold.kz: домен из Wikidata P856 Государственного музея золота и драгоценных металлов (Q4146879).

Домен припаркован: registrarian-заглушка «Новый сайт успешно создан и готов к работе» (robots.txt отвечает
`Allow: /`, но полезного содержимого нет). Музейных часов, цены или расписания на домене нет — веток нет.
"""

from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.fetch import SiteFetcher  # noqa: E402

HOME = "https://museumgold.kz/"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(HOME)
    pages = [page.url] if page.ok else []
    notes = ("Домен припаркован (заглушка регистратора «Новый сайт успешно создан и готов к работе», поддержка "
             "support@example.com) — сайта музея нет, часов и цен нет. P856 Q4146879 указывает на мёртвый домен.")
    return [], pages, notes
