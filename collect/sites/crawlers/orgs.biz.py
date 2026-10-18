"""orgs.biz (costacoffeekz.orgs.biz): Costa Coffee Kazakhstan's own site built on the orgs.biz constructor; the
home page lists the Astana outlets twice (intro + FAQ). No opening hours; 2017-2018-era content."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://costacoffeekz.orgs.biz"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    vis = visible_text(page.text)
    m = re.search(r"(?P<v>Costa Coffee в Астане: .*?)(?:Costa Coffee в алматы|Частые вопросы|$)", vis, re.DOTALL)
    if not m:
        return [], [URL], f"{URL}: 'Costa Coffee в Астане' list not found"
    line = re.sub(r"\s+", " ", m["v"]).strip()
    body = line.split(":", 1)[1]
    outlets = [re.sub(r"[,]+$", "", x).strip() for x in body.split(" - ") if x.strip()]
    branches = []
    for o in outlets:
        if not o or o not in vis:
            continue
        ev = [store.evidence("name", URL, line[:300], page.fetched_at),
              store.evidence("address", URL, o, page.fetched_at)]
        branches.append(store.make_branch(f"Costa Coffee, {o}", ev, "html", 0.6, address=o, url=URL))
    notes = ("Outlets per the company's own list: ТРЦ Mega Astana, пр. Республики 7, Торговый центр Керуен, БЦ Москва, "
             "ТЦ Asia Park, Казмедиа Центр (ул. Кунаева 4) — mall/building names serve as the published location "
             "(only two carry street addresses). The site is a frozen 2017-2018 orgs.biz constructor page: no opening "
             "hours, no branch phones (the '20:00 до 22:00' occurrence is a dated 2017 tea-promo post, not a "
             "schedule). The canonical costacoffee.kz is unreachable, this is the only first-party source on hand.")
    return branches, [URL], notes
