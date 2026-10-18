"""foodpicasso order-platform sites (plov.kz, sushiman.kz, rafe.kz): branches from the embedded JSON.

The storefront HTML embeds `"restaurants":[{...}]` with per-point name (the address), lat/lng, `today` and a
7-entry weekly `days` array. Imported by the per-domain crawler modules of those sites.
"""

import html as htmllib
import json
import re

from collect.sites import store

ASTANA_LAT, ASTANA_LON = (50.98, 51.25), (71.25, 71.65)
_RES = re.compile(
    r'\{"hash":"\w+","name":"(?P<name>[^"]*?)".*?"lat":"(?P<lat>[\d.-]+)","lng":"(?P<lng>[\d.-]+)".*?'
    r'"today":"(?P<today>[^"]*)","days":(?P<days>\[\[.*?\]\])\}', re.DOTALL)


def branches_from(fetcher, url: str, brand: str):
    """(branches, page, error). Astana-only points; a uniform weekly `days` becomes «ежедневно a-b»."""
    page = fetcher.fetch(url)
    if not page.ok:
        return [], page, f"{url}: status {page.status} {page.error}"
    m = re.search(r'"restaurants":(\[.*?\]),"map"', page.text, re.DOTALL)
    if not m:
        return [], page, f"{url}: embedded restaurant JSON not found"
    out = []
    for mm in _RES.finditer(m[1]):
        lat, lon = float(mm["lat"]), float(mm["lng"])
        if not (ASTANA_LAT[0] < lat < ASTANA_LAT[1] and ASTANA_LON[0] < lon < ASTANA_LON[1]):
            continue
        name = htmllib.unescape(mm["name"]).strip()
        try:
            days = json.loads(mm["days"])
        except ValueError:
            days = []
        spans = {tuple(d) for d in days if isinstance(d, list) and len(d) == 2 and all(d)}
        raw = None
        ev = [store.evidence("name", url, f'"name":"{mm["name"]}"', page.fetched_at),
              store.evidence("address", url, f'"name":"{mm["name"]}"', page.fetched_at),
              store.evidence("geo", url, f'"lat":"{mm["lat"]}","lng":"{mm["lng"]}"', page.fetched_at)]
        if len(spans) == 1 and len(days) == 7:
            a, b = next(iter(spans))
            raw = f"ежедневно {a}-{b}"
            ev.append(store.evidence("opening_hours", url, f'"days":{mm["days"]}', page.fetched_at))
        out.append(store.make_branch(f"{brand} ({name})", ev, "locator_json", 0.85, address=name, lat=lat,
                                     lon=lon, opening_hours_raw=raw, url=url))
    return out, page, ""
