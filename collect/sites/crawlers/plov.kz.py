"""plov.kz (RUMI): Astana points from the embedded foodpicasso order JSON of /rumi_astana."""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.crawlers._foodpicasso import branches_from  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://plov.kz/rumi_astana"


def crawl(fetcher: SiteFetcher):
    out, page, err = branches_from(fetcher, URL, "RUMI")
    if err:
        return [], [URL], err
    return out, [URL], ("The plov.kz city page for Astana embeds each restaurant as {name=address, lat, lng, "
                        "weekly days}; the uniform 10:00-00:00 schedule converts to Mo-Su 10:00-24:00. Phones are "
                        "absent from the payload.")
