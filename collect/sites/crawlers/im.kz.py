"""im.kz: Nuxt SSR site; each /restaurants/<slug> page prints one restaurant card: name, address (г. Астана …),
phone and 'Часы работы' block. Only pages whose address line starts with 'г. Астана' are stored."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

SITEMAP = "https://im.kz/sitemap.xml"
ADDR = re.compile(r"(?P<v>г\. Астана, [^+]{6,90}?)\s+\+7")
PHONE = re.compile(r"(?P<v>\+7 \(7\d\d\) \d{3}[ -]\d{2}[ -]\d{2})")
HOURS = re.compile(r"(?P<v>\d{2}:\d{2} — \d{2}:\d{2})")


def crawl(fetcher: SiteFetcher):
    sm = fetcher.fetch(SITEMAP)
    if not sm.ok:
        return [], [SITEMAP], f"{SITEMAP}: status {sm.status} {sm.error}"
    urls = [u for u in re.findall(r"<loc>([^<]+)</loc>", sm.text) if re.search(r"im\.kz/restaurants/", u)]
    branches, pages = [], [SITEMAP]
    for url in urls:
        page = fetcher.fetch(url)
        pages.append(url)
        if not page.ok:
            continue
        text = visible_text(page.text)
        addr = ADDR.search(text)
        if not addr:
            continue
        phone, hours = PHONE.search(text), HOURS.search(text)
        title = re.search(r"<title>(?P<v>[^<|]{2,80})", page.text)
        ev = [store.evidence("address", url, addr[0], page.fetched_at)]
        if phone:
            ev.append(store.evidence("phone", url, phone[0], page.fetched_at))
        if hours:
            ev.append(store.evidence("opening_hours", url, hours[0], page.fetched_at))
        if title:
            ev.append(store.evidence("name", url, f"<title>{title['v']}", page.fetched_at))
            name = title["v"].strip()
        else:
            name = url.rsplit("/", 1)[-1]
        branches.append(store.make_branch(name or url, ev, "html", 0.75, address=addr["v"].strip(),
                                          phone=phone and phone["v"], opening_hours_raw=hours and hours["v"], url=url))
    notes = ("Branch list = the sitemap's /restaurants/<slug> pages (own SSR); pages with an Almaty address are "
             "skipped. Hours lines ('07:00 — 01:00') name no days -> raw only (needs_days); a second line on the same "
             "card is the technical break (e.g. '04:00 — 05:00') and is not stored. Coordinates are rendered by a JS "
             "map only, no lat/lng in HTML.")
    return branches, pages, notes
