"""sushiman.kz: Astana points from the embedded foodpicasso order JSON of the homepage."""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.crawlers._foodpicasso import branches_from  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://sushiman.kz/"


def crawl(fetcher: SiteFetcher):
    out, page, err = branches_from(fetcher, URL, "Sushiman")
    if err:
        return [], [URL], err
    return out, [URL], ("Homepage serves the Астана city (title «Sushiman Астана»); both points share the weekly "
                        "10:00-22:59 `days` array. Phones absent from the payload.")
