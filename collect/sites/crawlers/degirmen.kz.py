"""degirmen.kz/filialy: address+phone pairs inside the «Астана» tab panel; the page has no opening hours."""
from __future__ import annotations

import html as htmllib
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://degirmen.kz/filialy/"
_TEXT = re.compile(r'class="brxe-text-basic">([^<]+)</div>')
_PHONE = re.compile(r"[+8][\d\s()\-–—+.]{8,24}")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    a = page.text.find('class="brxe-text-basic">Астана</span><i')
    b = page.text.find('class="brxe-text-basic">Конаев</span><i', a)
    if a < 0:
        return [], [URL], "Astana tab panel not found in HTML"
    items = [re.sub(r"\s+", " ", htmllib.unescape(t).replace("\xa0", " ")).strip()
             for t in _TEXT.findall(page.text[a:b if b > 0 else None])]
    out, i = [], 0
    while i + 1 < len(items):
        addr, phone = items[i], items[i + 1]
        if "астан" in addr.lower() and _PHONE.fullmatch(phone):
            ev = [store.evidence("name", URL, "Degirmen", page.fetched_at),
                  store.evidence("address", URL, addr, page.fetched_at),
                  store.evidence("phone", URL, phone, page.fetched_at)]
            out.append(store.make_branch("Degirmen", ev, "html", 0.7, address=addr, phone=phone, url=URL))
            i += 2
        else:
            i += 1
    notes = ("Only the Astana tab of the city tabs is used (7 points). No opening-hours text anywhere on the "
             "page — raw hours stay None. Points are unnamed; the chain name is used.")
    return out, [URL], notes
