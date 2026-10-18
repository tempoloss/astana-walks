"""po.qr-pib.kz: Президентский центр РК (для manual-цели «Назарбаев центр-2», ул. Бокейхана 1а).
Bitrix-подобный сайт; /ru/contacts печатает адрес, административный график и график экскурсий."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://po.qr-pib.kz/ru/contacts"
_ADDR = re.compile(r"(?P<v>г\. Астана, ул\. Бокейхана, 1а)")
_EXCURSION = re.compile(r"График проведения экскурсий: (?P<v>Вторник-воскресенье, с \d\d\.\d\d до \d\d\.\d\d ч\.)")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    text = visible_text(page.text)
    addr, exc = _ADDR.search(text), _EXCURSION.search(text)
    if not (addr and exc):
        return [], [URL], "contacts block not found."
    ev = [store.evidence("name", URL, "Президентский центр Республики Казахстан", page.fetched_at),
          store.evidence("address", URL, addr[0], page.fetched_at),
          store.evidence("opening_hours", URL, "График проведения экскурсий: " + exc["v"], page.fetched_at)]
    b = store.make_branch("Президентский центр Республики Казахстан (Назарбаев центр)", ev, "html", 0.8,
                          address=addr["v"], opening_hours_raw=exc["v"], url=URL)
    notes = ("Визитные часы для публики = график экскурсий (Вт-Вс, конвертируется в Tu-Su). Отдельно страницу "
             "печатает административный график 'Понедельник-пятница, с 09.00 до 18.30 ч.' — это офис, не посещение, "
             "в opening_hours не кладётся (в raw только экскурсионный). Телефонов блок контактов не даёт.")
    return [b], [URL], notes
