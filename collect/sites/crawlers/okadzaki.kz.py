"""okadzaki.kz: /restaurants embeds the Astana pickup/delivery points JSON (name + today/days schedules)."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

URL = "https://okadzaki.kz/restaurants"
_DAYS = ("monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday")
_BLOCK = re.compile(r'\{"hash":"[0-9a-f]+","name":"(?P<name>Астана[^"]*)".*?'
                    r'"today":"(?P<today>[^"]*)","days":(?P<days>\[\[.*?\]\])', re.DOTALL)


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    i = page.text.find('"restaurants":[')
    if i < 0:
        return [], [URL], "embedded 'restaurants' JSON array not found"
    seg = page.text[i + len('"restaurants":'):]
    depth = 0
    arr = ""
    for j, ch in enumerate(seg):
        if ch == "[":
            depth += 1
        elif ch == "]":
            depth -= 1
            if depth == 0:
                arr = seg[: j + 1]
                break
    branches = []
    for m in _BLOCK.finditer(page.text):
        days = json.loads(m["days"])
        if len(days) != 7 or any(len(d) != 2 for d in days):
            continue
        if all(d == ["00:00", "00:00"] for d in days):
            raw_hours = "круглосуточно " + m["today"]
        else:
            raw_hours = " ".join(f"{d} {a[0]}-{a[1]}" for d, a in zip(_DAYS, days))
        name = m["name"]
        ev = [store.evidence("name", URL, '"name":"' + name + '"', page.fetched_at),
              store.evidence("opening_hours", URL, '"today":"' + m["today"] + '","days":' + m["days"],
                             page.fetched_at)]
        branches.append(store.make_branch(name, ev, "locator_json", 0.75,
                                          opening_hours_raw=raw_hours, url=URL))
    notes = ("Branch list = the escaped JSON 'restaurants' array embedded in /restaurants (order-menu backend): "
             "every entry is one Astana OKADZAKI point (name = printed 'Астана, <street>' address line, hence kept "
             "as the branch name; separate address field is empty in the payload). Weekly schedule is the "
             "'days' array (Mon..Sun pairs, matches the printed 'today' value), 'круглосуточно' points print "
             "00:00-00:00 pairs plus the word in their name. Phones are the shared order line, not per-branch — "
             "skipped. Entries of other cities (Алматы etc.) are not Astana and were skipped.")
    return branches, [URL], notes
