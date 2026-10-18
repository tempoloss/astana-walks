"""aisha-bibi.com: hotel with an Aisha Bibi restaurant; LocalBusiness JSON-LD carries address/geo/phone/description."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "http://aisha-bibi.com/astana"
_ASTANA = re.compile(r"астана|51\.1\d+, ?71\.3\d+", re.IGNORECASE)


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    out = []
    for b in fetcher.jsonld_branches(URL):
        lat_ok = b.get("lat") is None or (50.98 <= (b.get("lat") or 0) <= 51.25 and 71.25 <= (b.get("lon") or 0) <= 71.65)
        if _ASTANA.search(str(b.get("address")) + " " + str(b.get("name"))) and lat_ok:
            b["url"] = URL
            out.append(b)
    notes = ("The POI is the restaurant of Aisha Bibi Hotel & Spa; the site publishes hotel-level facts only "
             "(JSON-LD: address, geo, phone, description) — no restaurant-specific hours or contacts, and the "
             "on-page clock widget is live time, not a schedule, so opening_hours stays None.")
    return out, [URL], notes
