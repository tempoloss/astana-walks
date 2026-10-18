"""paul.kz: the SPA embeds its outlet list as escaped JSON ("organizations":[...]): only Almaty is published."""
from __future__ import annotations

import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://paul.kz/"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    has_astana = "Астан" in page.text
    notes = ("The embedded outlet JSON of paul.kz lists a single organization 'PAUL АLMALY' "
             "(Bostandyk District, Almaty) and the page contains no Astana mention at all; the brand is present in "
             "Astana (Ramstor) but the site publishes no Astana outlet facts, so no branches are stored.")
    return [], [URL], notes if not has_astana else "Astana string found — re-check crawler"
