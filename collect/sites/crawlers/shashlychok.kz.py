"""shashlychok.kz: foodpicasso SPA; branch cards (name/lat/lng/days) live in an embedded JSON blob of /adresaiyrinf."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store
from collect.sites.fetch import SiteFetcher

URL = "https://shashlychok.kz/adresaiyrinf"
_STORE = re.compile(r'\{"hash":"[0-9a-f]+","name":')
_GEO = re.compile(r'"lat":"?(-?\d+(?:\.\d+)?)"?,"lng":"?(-?\d+(?:\.\d+)?)"?')
_DAYS = re.compile(r'"days":(\[\[.*?\]\])')


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [], f"{URL}: status {page.status} {page.error}"
    t = page.text
    dec = json.JSONDecoder()
    branches, seen = [], set()
    for m in _STORE.finditer(t):
        try:
            d, end = dec.raw_decode(t[m.start():])
        except ValueError:
            continue
        w = t[m.start():m.start() + end]  # verbatim source of this outlet object
        name = (d.get("name") or "").strip()
        if not name or not re.search(r"астана|нур[-\s]?султан", name, re.I):
            continue
        key = name.lower()
        if key in seen:
            continue
        seen.add(key)
        lat = lon = None
        geo_snip = None
        if gm := _GEO.search(w):
            lat, lon = float(gm[1]), float(gm[2])
            geo_snip = gm[0]
            if not (50.9 < lat < 51.4 and 71.0 < lon < 71.8):
                continue
        name_snip = name if name in w else f'"name":"{name}"'
        ev = [store.evidence("name", URL, name_snip, page.fetched_at),
              store.evidence("address", URL, name_snip, page.fetched_at)]
        if geo_snip:
            ev.append(store.evidence("geo", URL, geo_snip, page.fetched_at))
        raw = hours_snip = None
        if dm := _DAYS.search(w):
            try:
                days = json.loads(dm[1])
            except ValueError:
                days = []
            if len(days) == 7 and all(x == days[0] for x in days) and len(days[0]) == 2:
                raw = f"Ежедневно {days[0][0]}-{days[0][1]}"
                hours_snip = dm[0]
            ev_hours = store.evidence("opening_hours", URL, hours_snip, page.fetched_at) if raw else None
            if ev_hours:
                ev.append(ev_hours)
        branches.append(store.make_branch(f"Шашлычок, {name}", ev, "locator_json", 0.8,
                                          address=name, lat=lat, lon=lon, opening_hours_raw=raw, url=URL))
    notes = ("Branch list = the JSON store array embedded in the page template (foodpicasso platform): name, lat/lng "
             "and a 7-day [from,to] 'days' schedule per outlet; all seven days identical -> raw 'Ежедневно <from>-<"
             "end>'. Only outlets whose name says Астана are stored; Almaty/Shymkent outlets skipped. The page also "
             "prints legal requisites (ИП «UAKA food», ул. Абая 92/3) — a legal address, not a cafe; not stored. "
             "Phone numbers of the site are the chain delivery contact, not branch-specific.")
    if not branches:
        notes += f" No branches parsed (status {page.status})."
    return branches, [URL], notes
