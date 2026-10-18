"""uzbechka1.kz: LocalBusiness JSON-LD @graph on the home page — 4 Astana restaurants with address + openingHours.
The network-level object (no address) duplicates the same hours and is dropped; the single phone in the page is a
network line, not branch-specific."""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://uzbechka1.kz"


def crawl(fetcher: SiteFetcher):
    branches = [b for b in fetcher.jsonld_branches(URL) if (b.get("address") or "").find("Астан") >= 0
                or (b.get("address") or "").find("Астана") >= 0]
    notes = ("Branches = the schema.org @graph of the home page (4 restaurants in Астана, each with street address and "
             "'Mo-Su 11:00-23:00'). The graph's Organization/WebSite objects (hours without an address) are dropped as "
             "duplicates. The page's tel:+7 701 068 1888 is the network reservation line, not branch-specific, so no "
             "phone is stored.")
    return branches, [URL], notes
