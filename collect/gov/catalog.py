"""Catalogue of the datasets the Astana akimat publishes on data.egov.kz, enumerated keyless:

  /datasets/getdatasetsrecount?byGovAgencyId=<id>&status=PUBLISHED      -> {"totalCount": N}
  /datasets/getdatasetsre?page=1..&count=10&byGovAgencyId=<id>&...      -> {"listSize", "datasets": [...]} (10 per page)
  /datasets/getmeta?index=<slug>                                         -> schema (fields: label, type)
  /datasets/exportjson?index=<slug>&from=&count=100                      -> rows (row count; coordinate probe)

Output `collect/gov/catalog.json`: per dataset slug, title, row count, fields, `has_coordinates` (a Geoposition-like
field in the schema, or coordinate-looking values in the rows) - the evidence for the city layer («акимат публикует N
наборов, координат нет ни в одном»). The summary states what was measured, not what is true of the world: a dataset
without coordinates in the published rows.

Usage (repo root): uv run python -m collect.gov.catalog [--out collect/gov/catalog.json]
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.gov.sport import HOST, PAGE_SIZE, export_url
from collect.sites.fetch import SiteFetcher
from collect.sites.store import now_iso

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "collect" / "gov" / "catalog.json"
AGENCY_ID = "AVUvu_Wu99eXTcgzf9td"  # Астана қаласы әкімдігі
LIST_PAGE = 10
MAX_ROW_PAGES = 50  # 5000 rows: a larger dataset is reported as truncated
_QUERY = f"byGovAgencyId={AGENCY_ID}&categoryId=&statusType=&datasetSortSelect=&status=PUBLISHED"
COUNT_URL = f"{HOST}/datasets/getdatasetsrecount?byGovAgencyId={AGENCY_ID}&categoryId=&status=PUBLISHED"
_COORD_NAME = re.compile(r"geo|lat|lon|lng|coord|коорд|широт|долгот|геопоз|x_point|y_point", re.IGNORECASE)
_COORD_VALUE = re.compile(r"^\s*-?\d{1,3}\.\d{3,}\s*[,;]\s*-?\d{1,3}\.\d{3,}\s*$")


def list_url(page: int) -> str:
    return f"{HOST}/datasets/getdatasetsre?page={page}&count={LIST_PAGE}&{_QUERY}"


def _order(v) -> int | None:
    return int(v) if str(v).strip().isdigit() else None


def schema_fields(meta: dict) -> list[dict]:
    fields = meta.get("fields") or {}
    out = [{"key": k, "label": v.get("labelRu") or v.get("labelKk") or v.get("labelEn") or "", "type": v.get("type"),
            "order": v.get("orderNumber")} for k, v in fields.items()]
    return sorted(out, key=lambda f: (_order(f["order"]) is None, _order(f["order"]) or 0, f["key"]))


def schema_coordinate_fields(fields: list[dict]) -> list[str]:
    return [f["key"] for f in fields if (f["type"] or "").casefold().startswith("geo")
            or _COORD_NAME.search(f["key"]) or _COORD_NAME.search(f["label"] or "")]


def row_has_coordinates(rows: list[dict]) -> bool:
    for r in rows:
        for k, v in r.items():
            if isinstance(v, str) and _COORD_VALUE.match(v):
                return True
            if _COORD_NAME.search(k) and v not in (None, "", "-"):
                return True
    return False


def _row_key(row: dict) -> str:
    return str(row["id"]) if "id" in row else json.dumps(row, sort_keys=True, ensure_ascii=False)


def enumerate_datasets(f: SiteFetcher) -> tuple[int, list[dict]]:
    total_page = f.fetch(COUNT_URL)
    if not total_page.ok:
        raise RuntimeError(f"{COUNT_URL}: HTTP {total_page.status} {total_page.error}")
    total = int(json.loads(total_page.text)["totalCount"])
    items: list[dict] = []
    page = 1
    while len(items) < total:
        p = f.fetch(list_url(page))
        if not p.ok:
            raise RuntimeError(f"{p.url}: HTTP {p.status} {p.error}")
        batch = json.loads(p.text).get("datasets") or []
        if not batch:
            break
        items.extend(b for b in batch if b["id"] not in {i["id"] for i in items})
        page += 1
    return total, items


def count_rows(f: SiteFetcher, slug: str) -> tuple[int, bool, list[dict]]:
    """(row count, truncated, rows of the first page)."""
    seen: set[str] = set()
    first: list[dict] = []
    start = 0
    for n in range(MAX_ROW_PAGES):
        p = f.fetch(export_url(slug, start))
        if not p.ok:
            return len(seen), False, first
        batch = json.loads(p.text)
        if n == 0:
            first = batch
        fresh = [r for r in batch if _row_key(r) not in seen]
        seen.update(_row_key(r) for r in fresh)
        if len(batch) < PAGE_SIZE or not fresh:
            return len(seen), False, first
        start = 101 if start == 0 else start + PAGE_SIZE
    return len(seen), True, first


def describe(f: SiteFetcher, item: dict) -> dict:
    slug = item["apiUri"] or item["id"]
    meta_page = f.fetch(f"{HOST}/datasets/getmeta?index={slug}")
    meta = json.loads(meta_page.text) if meta_page.ok else {}
    fields = schema_fields(meta)
    rows, truncated, sample = count_rows(f, slug)
    schema_geo = schema_coordinate_fields(fields)
    value_geo = row_has_coordinates(sample)
    return {
        "slug": slug, "title": item.get("nameRu") or item.get("nameKk") or item.get("nameEn"),
        "row_count": rows, "row_count_truncated": truncated,
        "fields": [{k: v for k, v in fl.items() if k != "order"} for fl in fields],
        "has_coordinates": bool(schema_geo) or value_geo, "coordinate_fields": schema_geo,
        "coordinates_in_rows": value_geo,
        "owner": (meta.get("owner") or {}).get("fullnameRu"), "modified": meta.get("modifiedDate"),
        "url": f"{HOST}/datasets/view?index={slug}",
    }


def build_catalog(f: SiteFetcher | None = None) -> dict:
    f = f or SiteFetcher()
    total, items = enumerate_datasets(f)
    datasets = sorted((describe(f, i) for i in items), key=lambda d: d["slug"])
    return {
        "source": "data.egov.kz", "agency_id": AGENCY_ID, "agency": "Астана қаласы әкімдігі",
        "fetched_at": now_iso(), "robots": f.robots_status(HOST + "/"),
        "endpoints": ["/datasets/getdatasetsrecount", "/datasets/getdatasetsre", "/datasets/getmeta",
                      "/datasets/exportjson"],
        "licence": "открытые данные госоргана РК, Закон №401-V (ст. 1 п. 5)",
        "summary": {
            "published_datasets": total, "enumerated": len(datasets),
            "with_coordinates": sum(d["has_coordinates"] for d in datasets),
            "empty": sum(d["row_count"] == 0 for d in datasets),
            "rows_total": sum(d["row_count"] for d in datasets),
            "with_working_hours_field": sum(any("режим" in (fl["label"] or "").casefold()
                                                or "жұмыс уақыт" in (fl["label"] or "").casefold()
                                                for fl in d["fields"]) for d in datasets),
        },
        "datasets": datasets,
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args(argv)
    cat = build_catalog()
    Path(args.out).write_text(json.dumps(cat, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    s = cat["summary"]
    print(f"[gov.catalog] published {s['published_datasets']}, enumerated {s['enumerated']}, with coordinates "
          f"{s['with_coordinates']}, with a working-hours field {s['with_working_hours_field']}, rows {s['rows_total']} "
          f"-> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
