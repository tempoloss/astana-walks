"""coffeeboom.kz: the coffee-shop map (/coffeeshops/) loads all outlets from an internal JSON endpoint
/e/437/getCoffeeshops/ (name/address/lat/lng/phone/work_time per shop)."""
from __future__ import annotations

import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

ENTRY = "https://coffeeboom.kz/coffeeshops/?city=16"
API = "https://coffeeboom.kz/e/437/getCoffeeshops/?city=16"


def _kv(body: str, key: str, value) -> str | None:
    """Verbatim `"key": <json value>` span of the raw (\\u-escaped ASCII) body, or None."""
    sn = f'"{key}":{json.dumps(value)}'
    return sn if sn in body else None


def crawl(fetcher: SiteFetcher):
    fetcher.fetch(ENTRY)  # the page whose data-ajax attribute points at the API; also robots-checked
    page = fetcher.fetch(API)
    if not page.ok:
        return [], [ENTRY, API], f"{API}: status {page.status} {page.error}"
    try:
        data = json.loads(page.text)["data"]["coffeeshops"]
    except (ValueError, KeyError) as exc:
        return [], [ENTRY, API], f"unexpected API payload: {exc!r}"
    body = page.text
    branches = []
    for s in data.values():
        addr = (s.get("address") or "").strip()
        lat, lng = s.get("lat"), s.get("lng")
        try:
            lat, lng = float(lat), float(lng)
        except (TypeError, ValueError):
            continue
        if not (50.98 <= lat <= 51.25 and 71.25 <= lng <= 71.65):
            continue  # the endpoint answers with all cities; keep the Astana coordinate box only
        name = (s.get("name") or "").strip() or addr
        phone = (s.get("phone") or "").strip()
        wt = (s.get("work_time") or "").strip()
        ev = []
        if sn := _kv(body, "name", s.get("name")):
            ev.append(store.evidence("name", API, sn, page.fetched_at))
        sa = _kv(body, "address", s.get("address")) if addr else None
        if sa:
            ev.append(store.evidence("address", API, sa, page.fetched_at))
        else:
            addr = None
        sp = _kv(body, "phone", phone) if phone else None
        if sp:
            ev.append(store.evidence("phone", API, sp, page.fetched_at))
        else:
            phone = None
        # lat/lng are adjacent in the payload as "lng": "...", "lat": "..."
        sg = f'"lng":{json.dumps(s.get("lng"))},"lat":{json.dumps(s.get("lat"))}'
        if sg in body:
            ev.append(store.evidence("geo", API, sg, page.fetched_at))
        else:
            lat = lng = None
        swt = _kv(body, "work_time", wt) if wt else None
        if swt:
            ev.append(store.evidence("opening_hours", API, swt, page.fetched_at))
        else:
            wt = None
        if not ev:
            continue
        branches.append(store.make_branch(name, ev, "locator_json", 0.85, address=addr, lat=lat, lon=lng,
                                          phone=phone, opening_hours_raw=wt, url=API))
    notes = ("Data = JSON endpoint /e/437/getCoffeeshops/ (the map's data-ajax source, city=16 is Astana; the box "
             "lat 50.98-51.25 lon 71.25-71.65 re-checked per shop). work_time is already OSM-like 'Mon-Sun "
             "08:00-24:00'; converted with the framework rules (00:00 -> 24:00). Non-Astana cities present in the "
             "endpoint (Алматы etc.) skipped. The 'Желі офисі' contact on /about/contacts/ is the chain office, not "
             "a cafe; its phones are chain-wide and not stored per branch.")
    return branches, [ENTRY, API], notes
