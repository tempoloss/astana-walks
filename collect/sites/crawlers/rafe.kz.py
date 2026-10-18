"""rafe.kz: JSON branches (coordinates + weekly days) merged with phones from /contacts."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.crawlers._foodpicasso import branches_from  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://rafe.kz/"
CONTACTS = "https://rafe.kz/contacts"
_ITEM = re.compile(r"(?P<brand>Rafe Coffee & Food|La Maison de Rafe)\s*(?P<addr>улица [^Т]+?)\s*Телефон:\s*"
                   r"(?P<phone>\+\d{7,15})")


def crawl(fetcher: SiteFetcher):
    out, page, err = branches_from(fetcher, URL, "Rafe Coffee & Food")
    notes = ("The order JSON carries name(address)/lat/lng/weekly days for 3 Astana points (uniform "
             "10:00-22:20). ")
    cont = fetcher.fetch(CONTACTS)
    if cont.ok:
        t = visible_text(cont.text)
        for m in _ITEM.finditer(t):
            addr = re.sub(r"\s+", " ", m["addr"]).strip()
            num = re.search(r"(\d+[\w/.-]*)\s*$", addr)
            hit = None
            if num:
                n = num[1].rstrip("/.- ")
                hit = next((x for x in out if x["address"] and re.search(rf"(?<!\d){re.escape(n)}(?!\d)",
                                                                         x["address"])), None)
            if hit and not hit["phone"]:
                hit["phone"] = m["phone"]
                hit["evidence"].append(store.evidence("phone", CONTACTS, f"Телефон: {m['phone']}",
                                                      cont.fetched_at))
            elif not hit:
                ev = [store.evidence("name", CONTACTS, m["brand"], cont.fetched_at),
                      store.evidence("address", CONTACTS, m["addr"], cont.fetched_at),
                      store.evidence("phone", CONTACTS, f"Телефон: {m['phone']}", cont.fetched_at)]
                out.append(store.make_branch(m["brand"], ev, "html", 0.7, address=addr, phone=m["phone"],
                                             url=CONTACTS))
        notes += ("Contacts page lists 4 points with phones; Кунаева 12/2 has no JSON point and is stored "
                  "address/phone-only.")
    else:
        notes += f"Contacts page unavailable ({cont.status} {cont.error[:60]}): phones not merged."
    if err:
        return [], [URL], err
    return out, [URL, CONTACTS], notes
