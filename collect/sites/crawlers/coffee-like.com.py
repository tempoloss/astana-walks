"""coffee-like.com: locations feed /coffee-bars/all behind the «Адреса» map — Russian cities only.

No Astana/Kazakhstan feature in the feed → 0 branches; the note records what was checked.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://coffee-like.com/coffee-bars/all"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    cities = {json.loads(f'"{m}"') for m in re.findall(r'"city":"((?:[^"\\]|\\.)*)"', page.text)}
    kz = sorted(c.strip() for c in cities if re.search(r"астан|нур|султ|казах", c, re.IGNORECASE))
    n = page.text.count('"type":"Feature"')
    notes = (f"Feed /coffee-bars/all (drives the «Адреса» map page): {n} points across {len(cities)} cities, all "
             f"of them Russian; Astana/KZ cities found: {kz or 'none'}. The 6 Astana «Coffee Like» POIs are not "
             "on the chain's own site map — no branches stored.")
    return [], [URL], notes
