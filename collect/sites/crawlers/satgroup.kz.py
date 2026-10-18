"""satgroup.kz: one-page group site with six Astana restaurant blocks (hours/phones in <p> of each <sections>)."""
from __future__ import annotations

import html as htmllib
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "http://satgroup.kz"
_SECTION = re.compile(r'<sections class="restourant.*?</sections>', re.DOTALL)
_BRANDS = {"grammy.kz": "GRAMMY", "brewery.kz": "BREWERY", "arnau-restaurant.kz": "ARNAU",
           "sundukastana.kz": "SUNDUK", "butchers.kz": "BUTCHER’S", "buno.kz": "BUNO"}


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(s)).strip()


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    bolds = set(re.findall(r"<b>([A-ZА-ЯЁ’'\s]+)</b>", page.text))
    out = []
    for sec in _SECTION.finditer(page.text):
        block = sec[0]
        site = re.search(r'<a href="http://([\w.-]+)/?(?:["?])', block)
        hours = re.search(r"Время работы:\s*(?P<v>[^<]+)", block)
        phone = re.search(r"Тел(?:ефон)?\.?:\s*(?P<v>[^<]+)</p>", block)
        seg = block[block.find("<p>"):block.find("</p>")]
        lines = [norm(x) for x in re.split(r"<br\s*>", seg)]
        addr_line = next((l for l in lines if re.search(r"Астан|Туран", l) and re.search(r"\d", l)), None)
        if not (site and hours and phone and addr_line):
            continue
        brand = _BRANDS.get(site[1].lower(), site[1])
        name_ev = next((b for b in bolds if b.strip().upper() == brand.upper()), brand)
        ev = [store.evidence("name", URL, name_ev, page.fetched_at),
              store.evidence("address", URL, addr_line, page.fetched_at),
              store.evidence("phone", URL, phone["v"], page.fetched_at),
              store.evidence("opening_hours", URL, hours["v"], page.fetched_at)]
        out.append(store.make_branch(brand, ev, "html", 0.75,
                                     address=re.sub(r"^Адрес:\s*", "", addr_line), phone=norm(phone["v"]),
                                     opening_hours_raw=norm(hours["v"]), url=URL))
    notes = ("Intro «сеть ресторанов в г. Астана» + six blocks (GRAMMY/BREWERY/ARNAU at пр. Туран 30 Fitness "
             "Palace; SUNDUK/BUTCHER’S/BUNO at ул. Жанибек и Керей ханов 14/2). The Fitness Palace address lines "
             "omit the city token; the intro places them in Astana. Cuisine lines are not stored.")
    return out, [URL], notes
