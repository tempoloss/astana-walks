"""e-museum.kz: ГИС «Музеи Казахстана» — реестр музеев Министерства культуры РК (WordPress REST, keyless).

`GET /wp-json/wp/v2/museum?region=3952&lang=ru` отдаёт карточки региона «г. Астана»; фильтр региона возвращает и
«Алжир» (city Ақмол ауылы, Акмолинская область) — записи с city ≠ «Астана қаласы» отбрасываются. Часы в карточке
без дней недели («10:00 - 18:00») → raw + hours_flags needs_days, opening_hours_osm остаётся None; цена билета —
текстом в price_text (никогда не разбирается в число). Сниппеты — дословные подстроки сырого JSON-ответа
(escape-последовательности сохраняются, как в кэше). Сопоставление с POI: name + address (register-совпадение),
дубли-POI Военно-исторического музея разбирает join (адрес Республики, 2 есть у трёх из четырёх).
Факты сохраняются с `source_label="museum_register"` (store.new_record) — это реестр министерства,
а не собственные сайты музеев.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

REST_URL = "https://e-museum.kz/wp-json/wp/v2/museum?region=3952&lang=ru"
ASTANA_CITY = "Астана қаласы"
_CARD_URL = "https://e-museum.kz/ru/museum/{slug}/"
# The raw JSON keeps non-ASCII as \uXXXX escapes; a snippet must be a verbatim substring of the cached body, so
# fields are cut out of the raw text, never re-serialized from the parsed dict.
_STRING = {f: re.compile(rf'"{f}":"(?P<v>(?:[^"\\]|\\.)*)"') for f in
           ("work_hours", "ticket_price", "addressstreet", "addresscity", "site", "slug")}


def _verbatim(card: str, name: str) -> str | None:
    m = _STRING[name].search(card)
    return m.group(0) if m else None  # '"field":"value"' exactly as in the raw JSON


def _value(verbatim: str) -> str:
    return next(iter(json.loads("{" + verbatim + "}").values()))


def crawl(fetcher: SiteFetcher):
    page = fetcher.fetch(REST_URL)
    if not page.ok:
        return [], [REST_URL], f"REST {REST_URL} unavailable: {page.error or page.status}"
    body = page.text
    cards = ["{" + part for part in body.split('{"id":')[1:]]
    branches, notes_bits = [], []
    for card in cards:
        title_m = re.search(r'"title":\{"rendered":"((?:[^"\\]|\\.)*)"', card)
        slug_v = _verbatim(card, "slug")
        if not title_m or not slug_v:
            continue
        title = json.loads(f'"{title_m.group(1)}"')
        city_v = _verbatim(card, "addresscity")
        if city_v and _value(city_v) != ASTANA_CITY:
            notes_bits.append(f"{title}: city {_value(city_v)} — не Астана, отброшена")
            continue
        slug = _value(slug_v)
        ev = [store.evidence("name", REST_URL, f'"title":{{"rendered":"{title_m.group(1)}"}}', page.fetched_at)]
        addr_v = _verbatim(card, "addressstreet")
        address = _value(addr_v) if addr_v else None
        if addr_v:
            ev.append(store.evidence("address", REST_URL, addr_v, page.fetched_at))
        hours_v = _verbatim(card, "work_hours")
        hours = _value(hours_v) if hours_v else None
        if hours_v:
            ev.append(store.evidence("opening_hours", REST_URL, hours_v, page.fetched_at))
        price_v = _verbatim(card, "ticket_price")
        price = _value(price_v) if price_v else None
        if price_v:
            ev.append(store.evidence("price", REST_URL, price_v, page.fetched_at))
        site_v = _verbatim(card, "site")
        site = _value(site_v) if site_v else None
        branches.append(store.make_branch(
            title, ev, "html", 0.7, address=address,
            opening_hours_raw=hours, price_text=price, url=_CARD_URL.format(slug=slug)))
        notes_bits.append(f"{title}: site={site or '—'}, {hours or '—'}, {price or '—'}")
    notes = ("ГИС «Музеи Казахстана», WP REST region=3952 (keyless; robots закрывает только /wp-admin/). "
             "Часы карточек без дней недели → needs_days. Цена — текстом (price_text). Свои домены из поля site: "
             + "; ".join(notes_bits) + ". Сниппеты — сырой JSON с \\u-escape; card URL = /ru/museum/<slug>/.")
    return branches, [REST_URL], notes
