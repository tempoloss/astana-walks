"""lepimivarim.ru/pelmennye/: the network's own пельменная list; three Astana venues carry address + schedule."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://lepimivarim.ru/pelmennye/"
BLOCK = re.compile(r"<h2>(?P<name>[^<]{2,80})</h2>\s*<p>(?P<addr>Астана[^<]{3,120})<br>\s*(?P<hours>пн-вс\s*[^<]{3,40})<br>")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    branches = []
    for m in BLOCK.finditer(page.text):
        ev = [store.evidence("name", URL, f"<h2>{m['name']}</h2>", page.fetched_at),
              store.evidence("address", URL, m["addr"], page.fetched_at),
              store.evidence("opening_hours", URL, f"{m['addr']}<br> {m['hours']}", page.fetched_at)]
        branches.append(store.make_branch(m["name"].strip(), ev, "html", 0.8, address=m["addr"].strip(),
                                          opening_hours_raw=m["hours"].strip(), url=URL))
    notes = ("Only the three 'Астана,' blocks of the пельменные list were stored; Russian-city branches are out of "
             "scope. The menu link labelled «Астана» is a PDF (Меги пельменная), no hours text there. Coordinates are "
             "not published on the page.")
    return branches, [URL], notes
