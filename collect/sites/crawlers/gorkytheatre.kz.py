"""gorkytheatre.kz: /contacts prints the box-office phone, its weekly schedule and the address (KZ labels)."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://gorkytheatre.kz/contacts"
NAME = "Государственный Академический русский театр драмы им. М.Горького"


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    vis = visible_text(page.text)
    ev = []
    values = {}
    m = re.search(r"Касса: (?P<v>\+7 \(7172\) 57-23-75)", vis)
    if m:
        ev.append(store.evidence("phone", URL, m[0], page.fetched_at))
        values["phone"] = m["v"]
    m = re.search(r"(?P<v>Сейсенбі-жексенбі: 10:00-21:00)", vis)
    if m:
        ev.append(store.evidence("opening_hours", URL, m[0], page.fetched_at))
        values["hours"] = m["v"]
    m = re.search(r"(?P<v>Астана қ\., Желтоқсан к\.-сі 11, 13)", vis)
    if m:
        ev.append(store.evidence("address", URL, m[0], page.fetched_at))
        values["address"] = m["v"]
    t = re.search(r"<title[^>]*>([^<]+)</title>", page.text, re.I)
    if t and "Горького" in t[1]:
        ev.append(store.evidence("name", URL, t[1].strip(), page.fetched_at))
    if not ev:
        return [], [URL], f"{URL}: nothing parsed"
    notes = ("Hours are the box-office (Касса) schedule 'Сейсенбі-жексенбі' = Tue-Sun 10:00-21:00 with a lunch break "
             "14:00-15:00 (not encoded in OSM); performance times are per-show, not a facility schedule. Page mixes "
             "KZ/RU labels; KZ weekday names convert via the hours parser's kk stems.")
    b = store.make_branch(NAME, ev, "html", 0.8, address=values.get("address"), phone=values.get("phone"),
                          opening_hours_raw=values.get("hours"), url=URL)
    return [b], [URL], notes
