"""pinta.kz: the Astana tab of /restaurants server-renders one card per venue (title/ address/ phone/ weekly hours)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://pinta.kz/restaurants/astana"
_TITLE = re.compile(r'<h2 class="restaurant-card__title"[^>]*><!--\[-->(?P<v>[^<]+?)<!--\]--></h2>', re.DOTALL)
_HOURS = re.compile(r"(Вс-Чт ?: ?(?:с )?\d{1,2}:\d{2} (?:до|-) \d{1,2}:\d{2} Пт-Сб ?: ?(?:с )?\d{1,2}:\d{2} "
                    r"(?:до|-) \d{1,2}:\d{2})")
_PHONE = re.compile(r"\+7 \(\d{3}\) \d{3}-\d{2}-\d{2}")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    branches = []
    for m in _TITLE.finditer(page.text):
        name = store.norm_ws(m["v"])
        card = ""
        for i in (mm.start() for mm in re.finditer(re.escape(name + " "), text)):
            cand = text[i:i + 300]
            if _PHONE.search(cand) and _HOURS.search(cand):
                card = cand
                break
        if not card:
            continue
        pm, hm = _PHONE.search(card), _HOURS.search(card)
        address = store.norm_ws(card[len(name) + 1:pm.start()]) or None
        ev = [store.evidence("name", URL, name, page.fetched_at),
              store.evidence("phone", URL, pm[0], page.fetched_at),
              store.evidence("opening_hours", URL, hm[1], page.fetched_at)]
        if address:
            ev.append(store.evidence("address", URL, address, page.fetched_at))
        branches.append(store.make_branch(name, ev, "html", 0.8, address=address, phone=pm[0],
                                          opening_hours_raw=hm[1], url=URL))
    notes = ("Astana city tab of /restaurants (nur.pinta.kz redirects to pinta.kz/?city=astana); the Almaty/other "
             "tabs hold non-Astana venues and are skipped. The weekly schedule printed on each card ('Вс-Чт … "
             "Пт-Сб …') is the venue's hours. The site publishes no street coordinates for its venues.")
    return branches, [URL], notes
