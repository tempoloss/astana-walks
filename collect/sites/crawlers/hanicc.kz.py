"""hanicc.kz/hani_astana: Hani (hani.c.c) астана — часы хаба на шапке, описание из meta."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://hanicc.kz/hani_astana"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    hours = re.search(r"(?P<v>09:00−20:00)", text)
    desc = re.search(r'(?P<v><meta property="og:description" content="[^"]{20,300})', page.text)
    name = re.search(r"(?P<v><title>Доставка в Караганде от Hani)", page.text)
    if not hours:
        return [], [URL], "header schedule not found."
    ev = [store.evidence("opening_hours", URL, hours[0], page.fetched_at)]
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    description = None
    if desc:
        description = desc[0].split('content="', 1)[1]
        ev.append(store.evidence("description", URL, desc[0], page.fetched_at))
    b = store.make_branch("Hani Cakes and Coffee", ev, "html", 0.7, opening_hours_raw=hours["v"],
                          description=description, url=URL)
    notes = ("The Astana storefront of the Hani delivery service: '09:00−20:00' in the header is the hub's daily "
             "working time but names no days -> hours stay raw (needs_days). No street address or phone is rendered "
             "without login; delivery zones list only districts, not the venue address.")
    return [b], [URL], notes
