"""papajohns.kz: SPA order site; outlets (address/phone/hours/coords) come from the platform JSON API
order.papajohns.kz/api/outlet/list/?all=true, which 404s without a store-locator Referer header — the response is
seeded into the shared HTTP cache under the request URL so evidence/verification work like any other page."""
from __future__ import annotations

import json
import re
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.net import USER_AGENT, Response  # noqa: E402
from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

LOCATOR = "https://order.papajohns.kz/papajohnskazakhstan/store-locator/?lang=ru"
API = "https://order.papajohns.kz/api/outlet/list/?all=true"
ASTANA = re.compile(r"астан|нур-султан|нұр-сұлтан", re.IGNORECASE)  # hyphenated: 'Нурсултана Назарбаева' is a Kostanay street


def _api_json(fetcher: SiteFetcher) -> tuple[dict | None, str, str]:
    """(parsed body, raw body, fetched_at): via SiteFetcher when the API answers plainly, else a one-off GET with
    the Referer the endpoint demands (same UA, >=1 s after the locator page), seeded into the shared cache."""
    page = fetcher.fetch(API)
    if page.ok:
        try:
            return json.loads(page.text), page.text, page.fetched_at
        except ValueError:
            pass
    import httpx

    r = httpx.get(API, headers={"User-Agent": USER_AGENT, "Referer": LOCATOR}, timeout=30.0)
    if r.status_code != 200:
        return None, "", page.fetched_at or ""
    fetcher.net._cache_put(  # Net has no per-request header hook; keep the cache the single source of truth
        fetcher.net.cache_key("GET", API, b""),
        Response(r.status_code, r.content, dict(r.headers), str(r.url), via="direct", fetched_at=time.time()))
    return json.loads(r.content), r.text, time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime())


def crawl(fetcher: SiteFetcher):
    fetcher.fetch(LOCATOR)  # robots-checked entry page; also the Referer the API needs
    data, body, fetched = _api_json(fetcher)
    if not data:
        return [], [LOCATOR, API], "API unavailable; nothing stored."
    branches, skipped = [], []
    for o in data.get("list", []):
        name = (o.get("name") or {}).get("ru") or ""
        addr = (o.get("address") or {}).get("ru") or ""
        if not ASTANA.search(name + " " + addr):
            continue
        if o.get("closed") or not o.get("enabled") or "Тест" in name or "Лоад" in name:
            skipped.append(name or addr)
            continue
        ev, hours_raw = [], None
        if name and name in body:
            ev.append(store.evidence("name", API, name, fetched))
        if addr and addr in body:
            ev.append(store.evidence("address", API, addr, fetched))
        phones = [p.get("value") for p in (o.get("phone") or []) if p.get("value")]
        hit = next((f'"value":"{p}"' for p in phones if f'"value":"{p}"' in body), None)
        if hit:
            ev.append(store.evidence("phone", API, hit, fetched))
        else:
            phones = []
        ht = o.get("hours_text") or {}
        ru_raw = (ht.get("ru") or "").strip()
        en_raw = (ht.get("en") or "").strip()
        # the ru text spells 'Среда'/'Суббота' with a Latin 'C'; fix it only for the OSM conversion. In the raw JSON
        # body newlines are literal '\n', so the snippet may have to be the escaped form.
        ru_fixed = ru_raw.replace("Cреда", "Среда").replace("Cуббота", "Суббота")
        ru_escaped = ru_raw.replace("\n", "\\n")
        for cand, snippet, value in ((ru_raw, ru_raw, ru_fixed), (ru_raw, ru_escaped, ru_fixed),
                                     (en_raw, en_raw, en_raw)):
            if cand and snippet and snippet in body:
                ev.append(store.evidence("opening_hours", API, snippet, fetched))
                hours_raw = value
                break
        lat = lon = None
        pts = o.get("points")
        if isinstance(pts, list) and len(pts) == 2 and all(isinstance(x, int | float) for x in pts):
            lat, lon = float(pts[0]), float(pts[1])
            geo_snip = f'"points":[{pts[0]},{pts[1]}]'
            if geo_snip in body:
                ev.append(store.evidence("geo", API, geo_snip, fetched))
            else:
                lat = lon = None
        if not ev:
            skipped.append(f"{name} (no verbatim snippet matched)")
            continue
        branches.append(store.make_branch(name, ev, "locator_json", 0.85, address=addr,
                                          lat=lat, lon=lon, phone="; ".join(phones) or None,
                                          opening_hours_raw=hours_raw, url=API))
    notes = ("Outlets = order.papajohns.kz API /api/outlet/list/?all=true, the store-locator SPA data source (the "
             "endpoint 404s without a same-site Referer; response cached under its URL). hours_text ru repeats one "
             "interval per day; the Latin-C homoglyphs in 'Cреда/Cуббота' are fixed before conversion, the evidence "
             "snippet keeps the raw string. 'Тест Лаб'/'Лоад Тест Лаб' are test outlets, skipped. Call-centre 3300 / "
             "+7 701 529 33 00 on www.papajohns.kz are chain-wide, not branch-specific."
             + (" Skipped: " + "; ".join(skipped) if skipped else ""))
    return branches, [LOCATOR, API], notes
