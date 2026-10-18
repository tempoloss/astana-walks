"""hardees.kz: same store-locator template as kfc.kz — collapse cards `store_collapse_card_<id>` with city cat-id
2410 (Астана), address in a `details-text` td, coords in a `data-lat/data-lng` row, and a weekly schedule table
`takeaway_store_<id>` ('С собой' — the venue hours, the same pick-up table the KFC crawler uses)."""
from __future__ import annotations

import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://www.hardees.kz/stores"
KZ_TZ = timezone(timedelta(hours=5))  # one time zone for the whole country since 2024-03-01
_RU_DAYS = ("понедельник", "вторник", "среда", "четверг", "пятница", "суббота", "воскресенье")
_TODAY_ROW = re.compile(r'font-weight-bold mainColor">([^<]+)</td>')  # the platform bolds today's row of the table
ASTANA = "2410"  # <option value="2410">Астана</option> of the city selector
_CARD = re.compile(r'id="store_collapse_card_(?P<id>\d+)"[^>]*data-cat-id="(?P<cat>\d+)"')
_TITLE = re.compile(r'<h5 class="card-title">([^<]+)</h5>')
_ADDR = re.compile(r'<td class="details-text">([^<]*Астана[^<]*)</td>')
_GEO = re.compile(r'data-lat="(?P<lat>[\d.]+)" data-lng="(?P<lng>[\d.]+)"')
_DAY = r"(?:понедельник|вторник|среда|четверг|пятница|суббота|воскресенье) \d{1,2}:\d{2} - \d{1,2}:\d{2}"
_WEEK = re.compile(rf"(?:{_DAY} ?){{7}}")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    t = page.text
    today = _RU_DAYS[datetime.fromisoformat(page.fetched_at).astimezone(KZ_TZ).weekday()] if page.fetched_at else None
    starts = [(m["id"], m["cat"], m.start()) for m in _CARD.finditer(t)]
    branches, notes_extra = [], []
    for i, (sid, cat, a) in enumerate(starts):
        if cat != ASTANA:
            continue
        b = starts[i + 1][2] if i + 1 < len(starts) else len(t)
        chunk = t[a:b]
        title, addr, geo = _TITLE.search(chunk), _ADDR.search(chunk), _GEO.search(chunk)
        if not title:
            notes_extra.append(f"store {sid}: no card title")
            continue
        lat, lon = (float(geo["lat"]), float(geo["lng"])) if geo else (None, None)
        if lat is not None and not (50.98 <= lat <= 51.25 and 71.25 <= lon <= 71.65):
            notes_extra.append(f"store {sid}: coords outside the Astana bbox, dropped")
            continue
        raw_addr = addr[1].strip() if addr else None
        ev = [store.evidence("name", URL, title[1], page.fetched_at)]
        if raw_addr and raw_addr.endswith("Астана"):
            ev.append(store.evidence("address", URL, raw_addr, page.fetched_at))
        else:
            raw_addr = None
        if geo and lat is not None:
            ev.append(store.evidence("geo", URL, geo.group(0), page.fetched_at))
        else:
            lat = lon = None
        weekly = None
        j = chunk.find(f'id="takeaway_store_{sid}"')
        if j >= 0:
            k = chunk.find("</table>", j)
            w = _WEEK.search(visible_text(re.sub(r"<svg[\s\S]*?</svg>", "", chunk[j:k if k > j else j + 20000])))
            bold = _TODAY_ROW.search(chunk[j:k if k > j else j + 20000])
            if bold and today and bold[1].strip() != today:  # the site's own "today" row disagrees with the weekday
                notes_extra.append(f"store {sid}: today's row is {bold[1].strip()!r}, expected {today!r}: hours skipped")
            elif w and len({x.split(" ")[0] for x in re.findall(_DAY, w.group(0))}) == 7:
                weekly = w.group(0).strip()
                ev.append(store.evidence("opening_hours", URL, weekly, page.fetched_at))
        branches.append(store.make_branch(title[1], ev, "html", 0.8, address=raw_addr, lat=lat, lon=lon,
                                          opening_hours_raw=weekly, url=URL))
    notes = ("Branch cards = collapse blocks of the city filter 2410 ('Астана') on /stores; OSM carried 7 Astana POIs, "
             "the site currently lists 12 outlets. Hours = the 7-day 'С собой' (self pick-up) table, which is the "
             "venue schedule; the 'Доставка' table is delivery hours and is not used (same convention as the kfc.kz "
             "crawler on this platform). The table lists the days Sunday first and labels every row by its day name, which is "
             "what is parsed (the homepage JSON of the same stores numbers the days 1..7 in that Sunday-first order, so "
             "'day 7' is Saturday, not Sunday: Mega Expo closes at 00:00 on Saturday and 22:45 on the other days); the "
             "row the platform bolds is today's, and the crawler checks it against the weekday of the fetch (UTC+5). "
             "The only phone on the page is the chain short number 7001 (tel:7001, not "
             "branch-specific) and is not stored. " + "; ".join(notes_extra))
    return branches, [URL], notes.strip()
