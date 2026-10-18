"""cheburek.me: Tilda one-pager of the ЧебурекМИ chain; the Astana addresses live in the city tooltip submenu
whose hook id is #submenu:detailsk1 (anchor label 'Астана'). No per-venue opening hours are published."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://cheburek.me"
HOOK = "detailsk1"  # #submenu:detailsk1 ← anchor <a href="#submenu:detailsk1">Астана</a>


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    t = page.text
    if not re.search(rf'href="#submenu:{HOOK}"[^>]*>Астана', t):
        return [], [URL], f"{URL}: no city submenu anchored to 'Астана' (layout changed)"
    i = t.find(f'data-tooltip-hook="#submenu:{HOOK}"')
    if i < 0:
        return [], [URL], f"{URL}: tooltip block not found"
    k = t.find("t_onReady(", i)
    block = t[i:k if k > 0 else i + 6000]
    addrs = re.findall(r'<span class="t978__link-inner[^"]*">([^<]+)</span>', block)
    vis = visible_text(t)
    name = re.search(r"ЧебурекМИ", vis)
    branches = []
    for a in addrs:
        a = re.sub(r"\s+", " ", a).strip()
        if not a or a not in vis:
            continue
        ev = [store.evidence("address", URL, a, page.fetched_at)]
        if name:
            ev.append(store.evidence("name", URL, "ЧебурекМИ", page.fetched_at))
        branches.append(store.make_branch(f"ЧебурекМИ, {a} (Астана)", ev, "html", 0.7, address=a, url=URL))
    notes = ("The Kazakhstan section's 'Астана' tooltip menu lists the two outlet addresses above; the page carries no "
             "per-venue opening hours or phones (city block only lists addresses), so those fields stay None — never "
             "inferred. The remaining tooltip menus are Russian/Belarusian/KZ cities outside Astana.")
    return branches, [URL], notes
