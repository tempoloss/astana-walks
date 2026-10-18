"""astana.asiapark.kz: ТРЦ Asia Park — the footer prints the actual address and phone, the header the schedule."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://astana.asiapark.kz/ru/"
# NB: the footer spells 'и'/'й' decomposed (U+0438 + U+0306); the class accepts both forms.
IJ = "[\u0438\u0439]\u0306?"
ADDR = re.compile(rf"(?P<v>Факт{IJ}ческ{IJ}{IJ} адрес\s*:\s*Республика Казахстан г\. Астана пр\. Кабанба{IJ} батыра 21)")
HOURS = re.compile(r"(?P<v>С 10:00 до 22:00)")
PHONE = re.compile(r"(?P<v>\+77052221008)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr, hours, phone = ADDR.search(text), HOURS.search(text), PHONE.search(text)
    name = re.search(r"(?P<v>ТРЦ Asia Park)", text)
    if not addr:
        return [], [URL], "footer address not found."
    ev = [store.evidence("address", URL, addr[0], page.fetched_at)]
    if hours:
        ev.append(store.evidence("opening_hours", URL, hours[0], page.fetched_at))
    if phone:
        ev.append(store.evidence("phone", URL, phone[0], page.fetched_at))
    if name:
        ev.append(store.evidence("name", URL, name[0], page.fetched_at))
    b = store.make_branch("ТРЦ Asia Park", ev, "html", 0.75,
                          address="г. Астана, пр. Кабанбай батыра, 21", phone=phone and phone["v"],
                          opening_hours_raw=hours and hours["v"], url=URL)
    notes = ("www.asiapark.kz (the POI's URL) redirects work to the city subdomain astana.asiapark.kz — the mall's own "
             "site. The footer also prints the legal address of ТОО «REM.KZ» (пр. Бухар Жырау 51/4) which is the "
             "operator, not the mall, so only the 'Фактический адрес' was stored; its text keeps a decomposed 'й' "
             "(и + U+0306) in the evidence snippet. 'С 10:00 до 22:00' names no days -> raw only (needs_days).")
    return [b], [URL], notes
