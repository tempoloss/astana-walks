"""hcbarys.kz: Барыс Арена — /club/arena/contacts/ prints the arena address and its event-office phone; the arena
page gives the KZ name/description. The hockey-school office hours (09:00-18:00) are not the arena schedule."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

CONTACTS = "http://www.hcbarys.kz/club/arena/contacts/"
ARENA = "http://www.hcbarys.kz/club/arena/"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(CONTACTS)
    if not page.ok:
        return [], [CONTACTS], f"{CONTACTS}: status {page.status} {page.error}"
    vis = visible_text(page.text)
    ev, values = [], {}
    m = re.search(r"(?P<v>Астана қ\., Тұран даңғылы, 57)", vis)
    if m:
        ev.append(store.evidence("address", CONTACTS, m[0], page.fetched_at))
        values["address"] = m["v"]
    m = re.search(r"(?P<v>Телефон \+7 7172 61 34 41)", vis)
    if m:
        ev.append(store.evidence("phone", CONTACTS, m[0], page.fetched_at))
        values["phone"] = "+7 7172 61 34 41"
    ap = fetcher.fetch(ARENA)
    if ap.ok:
        av = visible_text(ap.text)
        m = re.search(r"(?P<v>Көпфункционалды Барыс Арена әртүрлі спорт түрлерінен сайыс өткізе алады\.)", av)
        if m:
            ev.append(store.evidence("name", ARENA, "Барыс Арена", ap.fetched_at))
            ev.append(store.evidence("description", ARENA, m[0], ap.fetched_at))
            values["description"] = m["v"]
    if not values.get("address"):
        return [], [CONTACTS], f"{CONTACTS}: address not parsed"
    notes = ("Барыс Арена (ice palace). Phone = the arena administration's event contact printed on the contacts "
             "page (info@mtexm.com — the operating company). No arena opening hours are published (game-day schedule "
             "only); the 09:00-18:00 block on /school/contacts/ belongs to the hockey school office, not the arena, "
             "so hours stay None. The club itself (ХК «Барыс») is the tenant, the POI is the arena.")
    b = store.make_branch("Барыс Арена", ev, "html", 0.8, address=values.get("address"), phone=values.get("phone"),
                          description=values.get("description"), url=CONTACTS)
    return [b], [CONTACTS, ARENA], notes
