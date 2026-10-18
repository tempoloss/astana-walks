"""data.egov.kz: keyless-эндпоинты портала открытых данных (SOURCES.md §11). Реестры Управления спорта
(sporttyk_keshender_turaly_dere1, v14 — режим работы rrr/rrk) и Управления культуры (madeniet_uiymdary, v17 —
адрес/телефон) по г. Астане. Доказательства — дословные срезы JSON-ответа exportjson."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[3]))

from collect.sites import store  # noqa: E402
from collect.sites.fetch import SiteFetcher  # noqa: E402

DATASETS = [
    ("sporttyk_keshender_turaly_dere1", "v14"),
    ("madeniet_uiymdary", "v17"),
]
ASTANA = re.compile(r"астан|нур-султан|нұр-сұлтан", re.IGNORECASE)


def _version(fetcher: SiteFetcher, slug: str, fallback: str) -> str:
    page = fetcher.fetch(f"https://data.egov.kz/datasets/view?index={slug}")
    m = re.search(r"currentVersion\s*=\s*['\"](v\d+)['\"]", page.text) if page.ok else None
    return m[1] if m else fallback


def _raw_value_snippet(body: str, key: str, value: str) -> str | None:
    """A verbatim `"key":"value..."` slice of the JSON body for the given logical value (values may contain
    literal \\n escapes, so the slice comes from the raw body, not the decoded string)."""
    for m in re.finditer(r'"%s":"((?:[^"\\]|\\.)*)"' % re.escape(key), body):
        if value and value in json.loads('"%s"' % m.group(1)):
            return m.group(0)
    return None


def _clean(v: str | None) -> str | None:
    return re.sub(r"\s+", " ", v).strip(" ,;") or None if v else None


def crawl(fetcher: SiteFetcher):
    branches, pages = [], []
    for slug, fallback in DATASETS:
        ver = _version(fetcher, slug, fallback)
        url = f"https://data.egov.kz/datasets/exportjson?index={slug}&version={ver}&from=0&count=100"
        pages.append(url)
        page = fetcher.fetch(url)
        if not page.ok:
            continue
        rows = json.loads(page.text)
        for row in rows:
            if "nsksr" in row:  # sport registry
                name, addr, hours, phone = row.get("nsksr"), row.get("mr"), row.get("rrr"), row.get("ktr")
                keys = {"name": "nsksr", "address": "mr", "opening_hours": "rrr", "phone": "ktr"}
            else:  # culture registry (№729)
                name, addr = row.get("naimenovanieorganizatsiirus"), row.get("yuridichedkiiadress_na_rus")
                hours, phone = None, row.get("kontact_telrus")
                keys = {"name": "naimenovanieorganizatsiirus", "address": "yuridichedkiiadress_na_rus",
                        "phone": "kontact_telrus"}
            if not name or not ASTANA.search((addr or "") + (name or "") + (row.get("naimenovanieregionarus") or "")):
                continue
            addr_c = _clean(addr)
            if addr_c and "астан" not in addr_c.lower() and "нур" not in addr_c.lower():
                addr_c = "г. Астана, " + addr_c
            phone_c = _clean(phone)
            ev = []
            for field, value in (("name", _clean(name)), ("address", _clean(addr)), ("opening_hours", _clean(hours)),
                                 ("phone", phone_c)):
                if not value:
                    continue
                key = keys[field]
                snip = _raw_value_snippet(page.text, key, value if field != "address" else (addr or "").strip())
                if snip:
                    ev.append(store.evidence(field, url, snip[:300], page.fetched_at))
            if not ev:
                continue
            branches.append(store.make_branch(name, ev, "locator_json", 0.85, address=addr_c, phone=phone_c,
                                              opening_hours_raw=_clean(hours), url=url))
    notes = ("Реестры акимата Астаны с портала data.egov.kz (keyless exportjson, версия со страницы датасета). "
             "Спорт (№730, Упр. спорта, 7 строк): rrr='режим работы' — служебные часы учреждений без дней недели "
             "(needs_days), телефон — приёмная ('приемная: 31-85-05', без кода города — как в источнике). "
             "Культура (№729, Упр. культуры, 13 строк): адрес юридический без города (префикс добавлен в value, "
             "сниппет — исходный), телефоны локальные. Координат в обоих датасетах нет. Часы не выдумываются: "
             "это время работы администрации спортшкол, не график посещений секций.")
    return branches, pages, notes
