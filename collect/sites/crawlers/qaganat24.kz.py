"""qaganat24.kz: chain of canteens; /contacts embeds LocalBusiness JSON-LD per outlet (address, geo, hours)."""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://qaganat24.kz/contacts"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    out = []
    for b in fetcher.jsonld_branches(URL):
        lat, lon = b.get("lat"), b.get("lon")
        if not (lat and 50.98 <= lat <= 51.25 and 71.25 <= lon <= 71.65):
            continue  # Almaty/Karaganda outlets skipped
        if "Астана" not in (b.get("address") or ""):
            continue
        b["url"] = URL
        out.append(b)
    notes = ("Outlets = LocalBusiness JSON-LD on /contacts; only the 3 Астана ones kept (Достык 5, Тауелсиздик 8/1, "
             "Республики 34А). Phone +7-708-970-50-46 is the chain call-centre printed identically on every outlet "
             "(kept as stated). 'Открыто круглосуточно' on the page matches openingHours Mo-Su 00:00-23:59.")
    return out, [URL], notes
