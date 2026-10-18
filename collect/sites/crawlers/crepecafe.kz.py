"""crepecafe.kz: Next.js contacts page embeds the `restaurants` array (name/address/lat/lng/phone per cafe) in a
self.__next_f script; the HTML shows no per-cafe opening hours, so hours stay None (never inferred)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://crepecafe.kz/rus/contacts"
_REST = re.compile(r'\\"restaurants\\":\[')


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    t = page.text
    m = _REST.search(t)
    if not m:
        return [], [URL], "restaurants payload not found in the page."
    try:  # the array is JSON with escaped quotes inside the streamed script; unescape a window and parse it
        rest, _ = json.JSONDecoder().raw_decode(
            t[m.end() - 1:m.end() + 200000].replace('\\"', '"').replace("\\/", "/"))
    except ValueError as exc:
        return [], [URL], f"restaurants JSON unparsable: {exc!r}"
    branches = []
    for r in rest:
        name, addr = (r.get("name") or "").strip(), (r.get("address") or "").strip()
        lat, lng = r.get("lat"), r.get("lng")
        phone = str(r.get("phone") or "").strip()
        if not name:
            continue
        if not (isinstance(lat, (int, float)) and isinstance(lng, (int, float))
                and 50.98 <= lat <= 51.25 and 71.25 <= lng <= 71.65):
            continue  # 'Усть-Каменогорск' / 'Балхаш' outlets of the chain are outside Astana
        ev = []
        sn = f'\\"name\\":\\"{r.get("name")}\\"'
        if sn in t:
            ev.append(store.evidence("name", URL, sn, page.fetched_at))
        sa = f'\\"address\\":\\"{r.get("address")}\\"'
        if sa in t and addr:
            ev.append(store.evidence("address", URL, sa, page.fetched_at))
        else:
            addr = None
        sp = f'\\"phone\\":\\"{phone}\\"'
        if re.fullmatch(r"\+7\d{9,11}", phone) and sp in t:
            ev.append(store.evidence("phone", URL, sp, page.fetched_at))
        else:
            phone = None
        sg = f'\\"lat\\":{lat},\\"lng\\":{lng}'
        if sg in t:
            ev.append(store.evidence("geo", URL, sg, page.fetched_at))
        else:
            lat = lng = None
        if not ev:
            continue
        branches.append(store.make_branch(f"CrepeCafe, {name}", ev, "locator_json", 0.85,
                                          address=addr or None, lat=lat, lon=lng, phone=phone, url=URL))
    notes = ("Data = the escaped `restaurants` JSON embedded in the Next.js stream of /rus/contacts: name, ru "
             "address, lat/lng, per-cafe phone (+7 700 037-02xx; a '$undefined' placeholder phone is dropped). The "
             "payload also lists non-Astana outlets ('Усть-Каменогорск', 'Балхаш') — dropped per the Astana-only "
             "rule. The page prints no opening hours for any cafe (only the chain contact +7 707 707 47 47), so "
             "opening_hours stays None — never inferred. ZWSP characters inside names/addresses are stripped in the "
             "stored values; snippets are the raw escaped JSON spans.")
    return branches, [URL], notes
