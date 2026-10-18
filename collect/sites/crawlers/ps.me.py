"""ps.me (fassbier.ps.me): menu-page host of the FASS BIER bar; the page's JSON-LD Restaurant gives the locality
('Нур-Султан') and phone. Street address and hours are not published (menu SPA, visible DOM empty)."""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://fassbier.ps.me"


def crawl(fetcher: SiteFetcher):
    branches = [b for b in fetcher.jsonld_branches(URL) if b.get("name") == "FassBier"]
    notes = ("The venue's own page on the ps.me menu platform: JSON-LD Restaurant 'FassBier' with locality "
             "Нур-Султан and phone +77780507683; no street address and no opening hours in the HTML (menu is "
             "rendered client-side), so those stay None.")
    return branches, [URL], notes
