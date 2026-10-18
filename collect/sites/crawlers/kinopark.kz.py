"""kinopark.kz: Next.js cinema network — branch list renders client-side, no static Astana facts.

Kept as a module so the record's note is reproducible: 0 branches.
"""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://www.kinopark.kz/ru"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    why = ("kinopark.kz renders the cinema/city list client-side (Next.js): /ru/company/cinemas and /ru/sitemap "
           "carry only cinema names («Kinopark 9 IMAX Saryarqa», «Kinopark 7 Keruencity», «Kinoplexx 7 "
           "Sary-arka»…) without addresses or opening hours; afisha.api.kinopark.kz exposes no public cinemas "
           "endpoint; the only JSON-LD blocks are Organization/BreadcrumbList. No first-party branch facts to "
           "store for the 4 Astana POIs.")
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}. " + why
    return [], [URL], why
