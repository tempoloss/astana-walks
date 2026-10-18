"""diplomathotel.kz: restaurant of the Diplomat hotel (POI «Байтерек», site calls it El Gaucho) — /restoran/
prints weekday/weekend breakfast times, /kontakty/ the Astana address and reservation phones."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

REST = "https://diplomathotel.kz/restoran/"
CONTACTS = "https://diplomathotel.kz/kontakty/"


def crawl(fetcher: SiteFetcher):
    rp, cp = fetcher.fetch(REST), fetcher.fetch(CONTACTS)
    if not rp.ok or not cp.ok:
        return [], [REST, CONTACTS], f"st rest={rp.status} cont={cp.status} {rp.error or cp.error}"
    rv, cv = visible_text(rp.text), visible_text(cp.text)
    ev, values = [], {}
    m = re.search(r"(?P<v>По будням: с 07:00 до 10:00)", rv)
    if m:
        ev.append(store.evidence("opening_hours", REST, m[0], rp.fetched_at))
        values["hours"] = m["v"]
    m = re.search(r"(?P<v>г\. Астана\.?\s*[\u200b\s]*[Уу]лица Динмухамед Конаев, 29/1)", cv)
    if m:
        ev.append(store.evidence("address", CONTACTS, m[0], cp.fetched_at))
        values["address"] = re.sub(r"\s+", " ", m["v"].replace("\u200b", " ")).strip()
    m = re.search(r"(?P<v>\+7 \(7172\) 476667)", cv)
    if m:
        ev.append(store.evidence("phone", CONTACTS, m[0], cp.fetched_at))
        values["phone"] = m["v"]
    m = re.search(r'(?P<v>Ресторан европей.{1,2}ой кухни "El Gaucho")', rv)
    if m:
        ev.append(store.evidence("name", REST, m[0], rp.fetched_at))
    if not values:
        return [], [REST, CONTACTS], "nothing parsed"
    notes = ("The hotel restaurant (POI «Байтерек»; the current site names it «El Gaucho» — naming conflict left to "
             "join). Only published schedule = breakfasts: 'По будням: с 07:00 до 10:00' (weekday breakfasts; the "
             "weekend line 08:00-11:00 is a separate rule not included in raw). Restaurant dinner/lunch hours are not "
             "stated. Address/phone are the hotel's reservation contacts from /kontakty/ (a ZWSP inside the printed "
             "address is whitespace-normalised in the stored value). The old /ru/bars path 404s.")
    b = store.make_branch("Ресторан отеля Diplomat (El Gaucho)", ev, "html", 0.7, address=values.get("address"),
                          phone=values.get("phone"), opening_hours_raw=values.get("hours"), url=REST)
    return [b], [REST, CONTACTS], notes
