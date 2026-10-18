"""Register № 730 «Перечень государственных спортивных объектов» of the Astana sports department on data.egov.kz
(`/datasets/exportjson?index=sporttyk_keshender_turaly_dere1&from=0&count=100`, keyless; `version=` is optional).

Trap: `rrr` / `rrk` («Режим работы», «08:30-18:00») is identical in all rows and sits next to `ktk` «приемная: …». It is
the office week of the managing body (the sports school's reception), not the hours of the arena a visitor walks
into. It is stored as `Hours(scope="administration")` = `admin_hours` on the POI, never as `opening_hours`. The head's
name (`fior`) is personal data and is not stored.

Usage (repo root): uv run python -m collect.gov.sport [--out data/gov/facts/data.egov.kz.json]
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.gov.addr import parse_address
from collect.gov.model import Evidence, GovRecord, Hours
from collect.sites.fetch import Page, SiteFetcher
from collect.sites.store import norm_ws, now_iso

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "data" / "gov" / "facts" / "data.egov.kz.json"
HOST = "https://data.egov.kz"
SLUG = "sporttyk_keshender_turaly_dere1"
PAGE_SIZE = 100
SOURCE_HOST = "data.egov.kz"


def export_url(slug: str, start: int, count: int = PAGE_SIZE) -> str:
    return f"{HOST}/datasets/exportjson?index={slug}&from={start}&count={count}"


def fetch_rows(fetcher: SiteFetcher, slug: str) -> list[tuple[dict, Page]]:
    """All rows of a dataset as (row, the page it came from), paged by 100. `from` is the 1-based number of the first
    row (0 and 1 are the same page), so the pages start at 0, 101, 201 ...; rows are de-duplicated by `id`. A short
    or empty page is the end; `[]` past the end is not an empty dataset."""
    out: list[tuple[dict, Page]] = []
    seen: set[str] = set()
    start = 0
    while True:
        page = fetcher.fetch(export_url(slug, start))
        if not page.ok:
            raise RuntimeError(f"{page.url}: HTTP {page.status} {page.error}")
        batch = json.loads(page.text)
        fresh = [r for r in batch if str(r.get("id")) not in seen]
        seen.update(str(r.get("id")) for r in fresh)
        out.extend((r, page) for r in fresh)
        if len(batch) < PAGE_SIZE or not fresh:
            return out
        start = 101 if start == 0 else start + PAGE_SIZE


def _json_pair(key: str, value: str) -> str:
    """The `"key": "value"` snippet as the verifier's re-serialised view of the page prints it."""
    return json.dumps({key: value}, ensure_ascii=False)[1:-1]


def build_record(row: dict, page: Page, slug: str = SLUG) -> GovRecord:
    name_ru, name_kk = norm_ws(row.get("nsksr") or ""), norm_ws(row.get("nsksk") or "")
    addr_ru = norm_ws(row.get("mr") or "")
    ev = [Evidence("name", page.url, _json_pair("nsksr", row["nsksr"]), page.fetched_at, "ru")]
    if row.get("nsksk"):
        ev.append(Evidence("name", page.url, _json_pair("nsksk", row["nsksk"]), page.fetched_at, "kk"))
    ev.append(Evidence("address", page.url, _json_pair("mr", row["mr"]), page.fetched_at, "ru"))
    a = parse_address(addr_ru)
    hours = None
    raw_hours = norm_ws(row.get("rrr") or "")
    if raw_hours and raw_hours != "-":
        hours = Hours(raw=raw_hours, scope="administration", opening_hours=None, flags=["administration_office_week"])
        ev.append(Evidence("admin_hours", page.url, _json_pair("rrr", row["rrr"]), page.fetched_at, "ru"))
    phone = norm_ws(row.get("ktr") or "") or None
    if phone:
        ev.append(Evidence("phone", page.url, _json_pair("ktr", row["ktr"]), page.fetched_at, "ru"))
    sports = norm_ws(row.get("vsr") or "")
    rid = "gov/sport/" + hashlib.sha1(f"sport|{slug}|{name_ru}|{addr_ru}".encode()).hexdigest()[:10]
    return GovRecord(
        id=rid, kind="sport_facility", source=SOURCE_HOST, url=page.url, name=name_ru,
        names={"ru": name_ru, **({"kk": name_kk} if name_kk else {})},
        address={"raw": a.raw, "street": a.street, "house": a.house, "key": a.key,
                 "by_lang": {"ru": addr_ru, **({"kk": norm_ws(row["mk"])} if row.get("mk") else {})}},
        hours=hours, evidence=ev, phone_raw=phone,
        extra={"dataset": slug, "register_no": 730, "row_id": str(row.get("id")),
               "sports": sports if sports and sports.strip("- ") else None},
        fetched_at=page.fetched_at)


def crawl(fetcher: SiteFetcher | None = None, slug: str = SLUG) -> dict:
    f = fetcher or SiteFetcher()
    pairs = fetch_rows(f, slug)
    pages = list(dict.fromkeys(p.url for _, p in pairs))
    records = [build_record(r, p, slug) for r, p in pairs]
    return {
        "source": SOURCE_HOST, "dataset": slug, "fetched_at": now_iso(), "pages": pages,
        "robots": f.robots_status(HOST + "/"), "records": [r.to_dict() for r in records],
        "notes": "rrr/rrk = office week of the administration (scope administration, admin_hours); "
                 "no coordinates in the register; head's name not stored.",
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args(argv)
    payload = crawl()
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[gov.sport] register №730: {len(payload['records'])} records -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
