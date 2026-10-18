"""starbucks.com.kz: /stores embeds the whole KZ store list as escaped Next.js JSON (name/address/weekly hours/geo)."""
from __future__ import annotations

import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://www.starbucks.com.kz/stores"
ASTANA_LAT, ASTANA_LON = (50.98, 51.25), (71.25, 71.65)
KZ_TZ = timezone(timedelta(hours=5))  # one time zone for the whole country since 2024-03-01
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_STORE = re.compile(r'\{\\"id\\":\\"\d+\\",\\"storeAddress\\":\\"(?P<addr>[^"]*?)\\".*?'
                    r'\\"name\\":\\"(?P<name>[^"]*?)\\".*?\\"weeklyWorkingHours\\":\{(?P<wh>.*?)\},'
                    r'\\"location\\":\{(?P<loc>[^}]*)\}', re.DOTALL)
_WT = re.compile(r'\\"(monday|tuesday|wednesday|thursday|friday|saturday|sunday)\\":\\"([\d:+-]+)\\"')
_LL = re.compile(r'\\"lon\\":(?P<lon>[\d.-]+),\\"lat\\":(?P<lat>[\d.-]+)')
# The visible list cards print ONE interval per store: today's. It must equal the JSON entry of today's weekday,
# otherwise the JSON is read wrongly (days shifted, other time zone) and the store's schedule is not stored.
_CARD = re.compile(r'<span class="text-\[24px\][^>]*>(?P<name>[^<]+)</span></div><div class="[^"]*">'
                   r'(?P<hours>\d\d:\d\d-\d\d:\d\d)</div>')


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    raw = page.text
    today = _DAYS[datetime.fromisoformat(page.fetched_at).astimezone(KZ_TZ).weekday()] if page.fetched_at else None
    cards: dict[str, set[str]] = {}
    for c in _CARD.finditer(raw):
        cards.setdefault(store.norm_ws(c["name"]), set()).add(c["hours"])
    branches, seen, unconfirmed = [], set(), []
    for m in _STORE.finditer(raw):
        mm = _LL.search(m["loc"])
        if not mm:
            continue
        lat, lon = float(mm["lat"]), float(mm["lon"])
        if not (ASTANA_LAT[0] <= lat <= ASTANA_LAT[1] and ASTANA_LON[0] <= lon <= ASTANA_LON[1]):
            continue
        name = json.loads('"' + m["name"] + '"')
        addr = json.loads('"' + m["addr"] + '"')
        key = f'{mm["lat"]},{mm["lon"]},{name}'
        if key in seen:  # 'Starbucks Europe City' is listed twice with identical coordinates
            continue
        seen.add(key)
        wt = dict(_WT.findall(m["wh"]))
        raw_hours = " ".join(f"{d} {wt[d]}" for d in _DAYS) if len(wt) == 7 else None
        shown = cards.get(store.norm_ws(name))
        if raw_hours and today and shown and shown != {wt[today]}:  # the card contradicts the JSON: keep no hours
            unconfirmed.append(f"{name}: card {sorted(shown)} vs JSON {today} {wt[today]}")
            raw_hours = None
        ev = [store.evidence("name", URL, '\\"name\\":\\"' + m["name"] + '\\"', page.fetched_at),
              store.evidence("address", URL, '\\"storeAddress\\":\\"' + m["addr"] + '\\"', page.fetched_at),
              store.evidence("geo", URL, mm[0], page.fetched_at)]
        if raw_hours:
            ev.append(store.evidence("opening_hours", URL, '\\"weeklyWorkingHours\\":{' + m["wh"] + "}",
                                     page.fetched_at))
        branches.append(store.make_branch(name, ev, "locator_json", 0.85, address=addr, lat=lat, lon=lon,
                                          opening_hours_raw=raw_hours, url=URL))
    notes = ("Store list = the escaped JSON array 'stores' embedded in the /stores page (Next.js RSC payload): "
             "name, storeAddress, weeklyWorkingHours per day and location lat/lon; per-store phones exist in the "
             "same payload but the chain uses one ordering line and they are not kept. Only outlets whose lat/lon "
             "fall in the Astana box are kept (Алматы/Шымкент skipped); one exact duplicate card ('Starbucks "
             "Europe City', same name and coordinates, two payload ids) is dropped. Names/addresses are as "
             "printed (Kazakh UI), including the site's own typo: 'Starbcuks Абу-Даби Плаза N' and "
             "'Starbcuks Абу-Даби Плаза' are two different names at the same point and both are kept. Weekly hours: "
             "'monday 08:00-22:00 ...' text converted by the framework rules. Cross-check: every store card of the list "
             "prints today's interval only (the fuzz run of 2026-10-17 compared that single value with the Mon-Fri "
             "JSON hours and saw a one-hour 'shift'; there is none: Saturday's JSON entry equals the card), so the "
             "crawler compares the card with the JSON entry of today's weekday (UTC+5) and stores no hours for a "
             "store where they differ." + (" Hours not stored: " + "; ".join(unconfirmed) + "." if unconfirmed else ""))
    return branches, [URL], notes
