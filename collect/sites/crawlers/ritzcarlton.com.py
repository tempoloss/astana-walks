"""ritzcarlton.com: The Ritz-Carlton, Astana — dining page JSON-LD carries the hotel + each restaurant/bar
(address, phone, per-venue openingHours). Evidence snippets are the verbatim JSON-LD spans."""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://www.ritzcarlton.com/en/hotels/tserz-the-ritz-carlton-astana/dining/"


def crawl(fetcher: SiteFetcher):
    branches = [b for b in fetcher.jsonld_branches(URL) if "Astana" in (b.get("address") or "")]
    notes = ("Objects = the LocalBusiness/FoodEstablishment JSON-LD of the dining page (hotel, Mökki, Өzen, "
             "Selfie, terraces, Rooftop); the POI «Ozen» maps to «Өzen» (Mo-Su 09:00-24:00). 'Mökki Terrace'/'Rooftop' "
             "publish no openingHours (seasonal venues) — address/phone only. Addresses are the hotel's single "
             "location (16 Dostyk Street = пр. Достык 16); Mökki's 07:00-24:00 is the restaurant's schedule, the "
             "24/7 mentions on the overview page are spa/in-room dining for guests and are not used.")
    return branches, [URL], notes
