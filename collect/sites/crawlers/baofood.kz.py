"""baofood.kz: /restaurant page embeds a Restaurant JSON-LD per outlet (address incl. locality, telephone,
openingHours). Only the two Нур-Султан outlets are kept; the hours string 'Su-Th 10:00-23:00, Fr-Mo 10:00-23:00'
overlaps (Fr is in both) so to_osm stays None by design."""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://baofood.kz/restaurant"


def crawl(fetcher: SiteFetcher):
    branches = [b for b in fetcher.jsonld_branches(URL)
                if any(c in (b.get("address") or "") for c in ("Нур-Султан", "Астан"))]
    notes = ("Outlets = the JSON-LD Restaurant objects of /restaurant (the city tabs of the page); the 5 Алматы "
             "outlets are dropped (Astana-only rule). Both Astana outlets share the phone +7 (778) 744-74-95 as "
             "published. openingHours 'Su-Th 10:00-23:00, Fr-Mo 10:00-23:00' is kept verbatim in raw; overlapping "
             "ranges make the OSM conversion non-deterministic, so opening_hours_osm is None.")
    return branches, [URL], notes
