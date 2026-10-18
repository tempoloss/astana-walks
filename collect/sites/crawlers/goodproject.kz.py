"""goodproject.kz: each restaurant project page prints its own contacts footer
(«Контакты <phone> <address> Время работы: <hours> О нас») plus a one-sentence venue description."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

# (display name, project page) — Astana venues of the holding, per /contacts/
VENUES = [
    ("Selfie", "https://goodproject.kz/projects/selfie-astana/"),
    ("Eva Wine Cafe", "https://goodproject.kz/projects/eva-wine-cafe/"),
    ("На крыше", "https://goodproject.kz/projects/na-kryshe/"),
    ("Malena Bar", "https://goodproject.kz/projects/malena-bar/"),
    ("Lilou Bar", "https://goodproject.kz/projects/lilou-bar/"),
]
_FOOT = re.compile(
    r"Контакты (?P<phone>\+7[\d ()+-]{8,24}?)\s*(?P<addr>г\. Астана.{5,90}?)Время работы:\s*(?P<hours>[^О]{3,120}?)\s*О нас")


def crawl(fetcher: SiteFetcher):
    branches, pages, notes = [], [], []
    for name, url in VENUES:
        page = fetcher.fetch(url)
        pages.append(url)
        if not page.ok:
            notes.append(f"{url}: status {page.status} {page.error[:60]}")
            continue
        text = visible_text(page.text)
        m = _FOOT.search(text)
        if not m:
            notes.append(f"{url}: contacts footer not found")
            continue
        snip = m[0][:300]
        nmx = re.search(re.escape(name) + r"\s+г\. Астана", text, re.IGNORECASE)
        desc = re.search(re.escape(name) + r" г\. Астана (?P<v>[^.!?]{20,240}[.!?])", text, re.IGNORECASE)
        ev = [store.evidence("name", url, nmx[0] if nmx else name, page.fetched_at),
              store.evidence("phone", url, snip, page.fetched_at),
              store.evidence("address", url, snip, page.fetched_at),
              store.evidence("opening_hours", url, ("Время работы: " + m["hours"])[:300], page.fetched_at)]
        if desc:
            ev.append(store.evidence("description", url, desc[0][:300], page.fetched_at))
        branches.append(store.make_branch(name, ev, "html", 0.8, address=m["addr"], phone=m["phone"],
                                          opening_hours_raw=m["hours"], description=desc["v"] if desc else None,
                                          url=url))
    notes.append("The holding also runs «Две реки» (goodproject.kz/projects/2-reki/) in Усть-Каменогорск — not "
                 "Astana, skipped. «Soul kitchen» (a POI with this domain) is not listed on the site. Hours "
                 "evidence = the per-venue footer; /contacts/ repeats addresses/phones without hours.")
    return branches, pages, " ".join(notes)
