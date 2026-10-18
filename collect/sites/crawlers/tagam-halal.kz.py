"""tagam-halal.kz: сеть «Тагам» (manual target node/5966463390, fast_food). Tilda-сайт; страница /astana перечисляет
все астанинские заведения блоками «<адрес> Режим работы: Круглосуточно 24/7 Зал/Доставка/Самовывоз Номер службы
доставки: <phone>». Имя сети — с главной."""
from __future__ import annotations

import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher, visible_text  # noqa: E402

URL = "https://tagam-halal.kz/astana"
HOME = "https://tagam-halal.kz"
_ST = r"[\w''`\-.]{2,24}"
_BLOCK = re.compile(rf"(?P<addr>{_ST}+(?: {_ST}+){{0,3}}[, ]+\d{{1,3}}(?:/\d+[а-яa-z]*)?) "
                    r"Режим работы: (?P<hours>Круглосуточно 24/7) Зал/Доставка/Самовывоз "
                    r"Номер службы доставки: (?P<phone>[\d ]{10,18})")
_NAME = re.compile(r"(?P<v>Тагам)")


def _trim_addr(addr: str) -> str:
    """Drop leading navigation words: keep at most '<street> <number>' — street tokens ending in '.' (ул., пр.)
    or the last token before the number stay."""
    parts = addr.split()
    while len(parts) > 2 and not parts[0].endswith("."):
        parts.pop(0)
    return " ".join(parts).strip(" ,.")


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(URL)
    if not page.ok:
        return [], [URL], f"{URL}: status {page.status} {page.error}"
    name_ev = None
    name_page = fetcher.fetch(HOME)
    if name_page.ok and _NAME.search(visible_text(name_page.text)):
        name_ev = store.evidence("name", HOME, "Тагам", name_page.fetched_at)
    elif _NAME.search(visible_text(page.text)):
        name_ev = store.evidence("name", URL, "Тагам", page.fetched_at)
    branches, seen = [], set()
    for m in _BLOCK.finditer(visible_text(page.text)):
        addr = _trim_addr(m["addr"])
        if not addr or addr in seen:
            continue
        seen.add(addr)
        snip = f"{addr} Режим работы: {m['hours']}"
        ev = [store.evidence("address", URL, snip, page.fetched_at),
              store.evidence("opening_hours", URL, snip, page.fetched_at),
              store.evidence("phone", URL, "Номер службы доставки: " + m["phone"], page.fetched_at)]
        if name_ev:
            ev.append(name_ev)
        branches.append(store.make_branch(f"Тагам, {addr}", ev, "html", 0.8, address=f"Астана, {addr}",
                                          phone=re.sub(r"\s+", " ", m["phone"]).strip(),
                                          opening_hours_raw="Круглосуточно", url=URL))
    notes = ("Часы = собственная строка сети 'Режим работы: Круглосуточно 24/7' для каждого заведения; в raw "
             "оставлено 'Круглосуточно' (конвертируется в 24/7). Телефон — номер службы доставки конкретного "
             "заведения (не общий call-центр). Адреса напечатаны коротко ('Кенесары 8'), город добавлен префиксом; "
             f"на странице распознано заведений: {len(seen)}. 'Доставка Контакты KZ ENG' — навигация, из адреса "
             "вырезана.")
    return branches, [URL, HOME], notes
