"""fullers.kz: one page per venue (Kazakh default, ?locale=ru for Russian); address + phone + e-mail only,
the site states no opening hours, so hours stay None (never inferred)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

# (name, ru page) — Astana venues listed under the "Astana" menu group on https://fullers.kz/
VENUES = [
    ("Fuller's Pub", "https://fullers.kz/astana-fullers_pub?locale=ru"),
    ("Fuller's Botanical Garden", "https://fullers.kz/astana-botanical?locale=ru"),
    ("Fuller's Green Line", "https://fullers.kz/astana-green_line?locale=ru"),
    ("Fuller's La Vie", "https://fullers.kz/astana-astana-la_vie?locale=ru"),
]
_INFO = re.compile(r"(?P<addr>г\. Астана\s*[^\n+]{3,60}?|Астана,\s*[^\n+]{3,60}?)\s*(?P<phone>\+7[\d ]{9,15})")


def crawl(fetcher: SiteFetcher):
    branches, pages, notes = [], [], []
    for name, url in VENUES:
        page = fetcher.fetch(url)
        pages.append(url)
        if not page.ok:
            notes.append(f"{url}: status {page.status} {page.error[:60]}")
            continue
        text = visible_text(page.text)
        if name not in text:
            notes.append(f"{url}: venue name not found in page text")
            continue
        m = _INFO.search(text)
        if not m:
            notes.append(f"{url}: address/phone not found")
            continue
        ev = [store.evidence("name", url, name, page.fetched_at),
              store.evidence("address", url, m[0][:300], page.fetched_at),
              store.evidence("phone", url, m[0][:300], page.fetched_at)]
        branches.append(store.make_branch(name, ev, "html", 0.8, address=m["addr"].strip(),
                                          phone=m["phone"].strip(), url=url))
    notes.append("Site prints no opening hours for any venue (menu is a PDF; the address link goes to 2GIS, an "
                 "aggregator we must not crawl), so opening_hours stays None. Almaty venues (Pheasant Feather, "
                 "4YOU, Pub & Wine, Izumrud, Central Avenue) are not Astana — skipped.")
    return branches, pages, " ".join(notes)
