"""white.kz/contacts: holding WHITE ENTERPRISE lists its restaurants as `contacts__item` cards.

Astana branches only (city line «г. Астана» / address anchor); several <time> tags per card are the real
weekly schedule (the datetime attribute is a template default) and are joined with ';'.
"""
from __future__ import annotations

import html as htmllib
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://white.kz/contacts/"
ASTANA = re.compile(r"астан|нур[-\s]?султ", re.IGNORECASE)
_ITEM = re.compile(r'<div class="contacts__name">(?P<name>[^<]+)</div>\s*<div class="contacts__info">'
                   r'(?P<body>.*?)</div>\s*</div>', re.DOTALL)
_TEL = re.compile(r'<a href="tel:[^"]+">(?P<phone>[^<]+)</a>')
_TIME = re.compile(r"<time[^>]*>(?P<hours>[^<]+)</time>")
_ANCH = re.compile(r'<a(?![^>]*?(?:tel:|instagram\.com))[^>]*>(?P<addr>[^<]{4,})</a>')


def norm(s: str) -> str:
    return re.sub(r"\s+", " ", htmllib.unescape(s)).replace("\u200b", "").strip()


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    out = []
    for m in _ITEM.finditer(page.text):
        body = m["body"]
        head = norm(re.sub(r"<[^>]+>", " ", body[: body.find("<a") if "<a" in body else 120]))
        times = [t["hours"] for t in _TIME.finditer(body)]
        tels = [t["phone"] for t in _TEL.finditer(body) if t["phone"].strip()]
        addrs_raw = [a["addr"] for a in _ANCH.finditer(body) if not norm(a["addr"]).startswith("@")]
        addrs = [norm(a) for a in addrs_raw]
        addr = ", ".join(addrs)
        if head and head.lower() not in addr.lower():
            addr = f"{head} {addr}".strip()
        if not ASTANA.search(f"{head} {addr}"):
            continue
        ev = [store.evidence("name", URL, f'<div class="contacts__name">{m["name"]}</div>', page.fetched_at)]
        for t in tels:
            ev.append(store.evidence("phone", URL, t, page.fetched_at))
        if addrs_raw:
            ev.append(store.evidence("address", URL, f">{addrs_raw[0]}<", page.fetched_at))
        for t in times:
            ev.append(store.evidence("opening_hours", URL, t, page.fetched_at))
        out.append(store.make_branch(m["name"].strip(), ev, "html", 0.8, address=addr or None,
                                     phone=tels[0] if tels else None,
                                     opening_hours_raw="; ".join(times) or None, url=URL))
    notes = ("The page lists 13 branches; the 3 outside Астана (ЛЕТО café ALMATY, GASTERIA DUBAI, ЛАПША ALMATY) "
             "are skipped by the city line. Day-less schedules («12:00-02:00») stay in opening_hours_raw with "
             "hours_flags needs_days.")
    return out, [URL], notes
