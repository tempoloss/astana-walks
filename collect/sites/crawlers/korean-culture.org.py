"""korean-culture.org: Корейский культурный центр в Астане (поддомен kaz.korean-culture.org).
Страница 'Наш адрес' даёт адрес и телефоны; часов работы на сайте нет."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "http://kaz.korean-culture.org/ru/10/contents/348"
HOME = "http://kaz.korean-culture.org/ru"
_ADDR = re.compile(r"(?P<v>г\. Астана , ул\. Иманова 13 , бизнес-центр «Нурсаулет-2», 1 этаж)")
_PHONE = re.compile(r"(?P<v>\+7 \(7172\) 901 - 113~5)")
_NAME = re.compile(r"(?P<v>Корейский культурный центр)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr, phone = _ADDR.search(text), _PHONE.search(text)
    if not addr:
        return [], [URL], "address line not found."
    ev = [store.evidence("address", URL, addr[0], page.fetched_at)]
    name = _NAME.search(text)
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    else:  # the org name occurs on the home page ("Корейский культурный центр сообщает…")
        home = fetcher.fetch(HOME)
        name = _NAME.search(visible_text(home.text)) if home.ok else None
        if name:
            ev.append(store.evidence("name", HOME, name[0], home.fetched_at))
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    b = store.make_branch("Корейский культурный центр (Korean Cultural Center)", ev, "html", 0.75,
                          address=re.sub(r"\s+", " ", addr["v"]),
                          phone=phone["v"] if phone else None, url=URL)
    notes = ("The 'Наш адрес' page prints the address with irregular spacing (kept verbatim in the snippet). "
             "No opening-hours statement on the site; film-showing/course times live in news posts only. "
             "Факс +7 (7172) 901 - 116 not stored.")
    return [b], [URL, HOME], notes
