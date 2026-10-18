"""edagoroda.kz: the home page embeds its venue map as JS objects {title, descr, lat, lng} — every object is one
«Еда Города» point with address and schedule in descr (parts split by '<br />')."""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

HOME = "https://www.edagoroda.kz"
LAT, LON = (50.98, 51.25), (71.25, 71.65)
OBJ = re.compile(r'\{title:"(?P<title>.*?)"\s*,descr:"(?P<descr>.*?)"\s*,lat:"(?P<lat>[\d.]+)"\s*,lng:"(?P<lng>[\d.]+)"')


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(HOME)
    if not page.ok:
        return [], [HOME], f"{HOME}: status {page.status} {page.error}"
    branches, seen = [], set()
    for m in OBJ.finditer(page.text):
        lat, lon = float(m["lat"]), float(m["lng"])
        if not (LAT[0] < lat < LAT[1] and LON[0] < lon < LON[1]):
            continue
        title = html.unescape(m["title"]).strip()
        parts = [html.unescape(p).strip() for p in m["descr"].split("&lt;br /&gt;")]
        parts = [p for p in parts if p]
        if len(parts) < 3:
            continue
        _, addr, hours = parts[0], parts[1], parts[2]
        if (title, addr) in seen:
            continue
        seen.add((title, addr))
        raw_obj = m[0][:300]
        ev = [store.evidence("name", HOME, f'title:"{m["title"]}"', page.fetched_at),
              store.evidence("address", HOME, f'descr:"{m["descr"][:220]}"', page.fetched_at),
              store.evidence("opening_hours", HOME, f'descr:"{m["descr"][:220]}"', page.fetched_at),
              store.evidence("geo", HOME, f'lat:"{m["lat"]}",lng:"{m["lng"]}"', page.fetched_at)]
        branches.append(store.make_branch(f"{title} — {addr}", ev, "html", 0.8, address=addr, lat=lat, lon=lon,
                                          opening_hours_raw=hours, url=HOME))
    notes = ("The company's own venue list is the 2GIS-style map initialisation on the home page (JS objects with "
             "title/descr/lat/lng; descr = name<br />address<br />schedule). Schedules 'с 10 до 22 часов' name no "
             "days, so hours stay raw (needs_days). The POI 'Лепим Варим' is not part of this list (only Еда Города "
             "cafes / grill-bar at Балкантау 187). Delivery 'ДОСТАВКА КРУГЛОСУТОЧНО' is a service, not venue hours; "
             "phone +7 705 100 21 33 is the chain order line, not branch-specific — not stored.")
    return branches, [HOME], notes
