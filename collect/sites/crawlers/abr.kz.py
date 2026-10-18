"""abr.kz: brand pages carry a city-tab card list; the 'Астана' tab holds Astana venues with address (item-title),
map coords toggle('lat, lon'), tel: phone and the 'Работаем <item-col-desc>' schedule."""
from __future__ import annotations

import html
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

RESTAURANTS = "https://abr.kz/restaurants"
CARD = re.compile(r'<div class="item-title">(?P<addr>[^<]+)</div>\s*'
                  r'<button @click="toggle\(\'(?P<lat>[\d.]+),\s*(?P<lng>[\d.]+)\'\)'
                  r'(?P<mid>.*?)href="tel:(?P<phone>[^"]+)"'
                  r'(?P<tail>.*?)item-col-desc">(?P<hours>[^<]+)</div>', re.DOTALL)
NAME = re.compile(r"Обратная связь (?P<n>[\wА-Яа-яЁё«»\.\-& ]+?) Назад")
BRAND = re.compile(r'href="(https://abr\.kz/restaurant/[a-z0-9_\-]+)"')
TAB_BTN = re.compile('''@click\\.prevent="tab = '(tab-\\d)'">Астана</a>''')
PANE_AT = '''x-show="tab === '{tab}'"'''
PANE_RE = re.compile('''x-show="tab === 'tab-\\d'"''')
LAT, LON = (50.98, 51.25), (71.25, 71.65)


def crawl(fetcher: SiteFetcher):
    listing = fetcher.fetch(RESTAURANTS)
    if not listing.ok:
        return [], [RESTAURANTS], f"{RESTAURANTS}: status {listing.status} {listing.error}"
    urls = list(dict.fromkeys(BRAND.findall(listing.text)))
    branches, pages = [], [RESTAURANTS]
    for url in urls:
        page = fetcher.fetch(url)
        pages.append(url)
        if not page.ok:
            continue
        name_m = NAME.search(visible_text(page.text))
        tabs = TAB_BTN.findall(page.text)
        if not name_m or not tabs:
            continue
        brand = html.unescape(name_m["n"]).strip()
        start = page.text.find(PANE_AT.format(tab=tabs[0]))
        nxt = [m.start() for m in PANE_RE.finditer(page.text) if m.start() > start]
        pane_txt = page.text[start:nxt[0]] if nxt else page.text[start:]
        for m in CARD.finditer(pane_txt):
            lat, lon = float(m["lat"]), float(m["lng"])
            if not (LAT[0] < lat < LAT[1] and LON[0] < lon < LON[1]):
                continue
            addr = html.unescape(m["addr"]).strip()
            hours = html.unescape(m["hours"]).strip()
            phone = m["phone"].strip()
            ev = [store.evidence("name", url, name_m[0], page.fetched_at),
                  store.evidence("address", url, f'<div class="item-title">{m["addr"]}</div>', page.fetched_at),
                  store.evidence("geo", url, f"toggle('{m['lat']}, {m['lng']}')", page.fetched_at),
                  store.evidence("phone", url, f'href="tel:{m["phone"]}"', page.fetched_at),
                  store.evidence("opening_hours", url, f'item-col-desc">{m["hours"]}<', page.fetched_at)]
            branches.append(store.make_branch(f"{brand} — {addr}", ev, "html", 0.8, address=addr, lat=lat, lon=lon,
                                              phone=phone, opening_hours_raw=hours, url=url))
    notes = ("One page per brand; each page tabs its venues by city — only the 'Астана' tab cards were used (tab id "
             "resolved dynamically, bounds-checked). Card fields: address = item-title, hours = 'Работаем "
             "<item-col-desc>' schedule, phone = tel: link, geo = yandex-map toggle('lat, lon'). abr.kz/contacts "
             "only carries Almaty head-office phones, so branch data comes from the brand pages.")
    return branches, pages, notes
