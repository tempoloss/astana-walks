"""Harvest the live eGov RCA gazetteer (streets + buildings of Astana) to disk.

Closes the §23 direction #1 storage side: snapshot files (rca_streets.json ≤2024,
OpenAddresses 2017) get a live replacement with rename chains (`old_path_*`) and
fresh `modified`. Query shape proven in 21.10: {bool:{must:[{terms:{s_ats_id:[6
district ids]}}]}} against api/detailed/<idx>/v1 (the `filter` clause and `sort`
param are rejected by this old Elasticsearch; `page`/`size` work).

Resume-safe: every page is appended to <name>_pages.jsonl; the final json is
assembled from it, deduped by id. Old ES may cap from+size at 10 000 — that
condition is logged in the pages file, and the partial harvest stays valid.

Usage (repo root): uv run python collect/recon/round13/gazetteer_harvest.py
"""
import json, time, urllib.error, urllib.parse, urllib.request
from pathlib import Path

UA = {"User-Agent": "astana-walks-recon/1.0", "Accept": "*/*"}
ROOT = Path(__file__).resolve().parents[3]
AST = ["107989", "108584", "252205", "252235", "251449", "107193"]
def body():  # sort by id makes the from-windows stable (unsorted ES reuses overlapping
    # windows: the first harvest got raw 85256 but only 85058 unique - 198 rows duplicated,
    # 198 never seen; with sort the windows are a true partition)
    return json.dumps({"query": {"bool": {"must": [{"terms": {"s_ats_id": AST}}]}},
                       "sort": [{"id": "asc"}]}, ensure_ascii=False)


def harvest(idx: str, out_name: str, page_size: int = 1000, max_pages: int = 120) -> None:
    pages_path = Path(__file__).with_name(f"{out_name}_pages.jsonl")
    done = 0  # done = rows already harvested (the offset); `page` is IGNORED by this ES, `from` pages
    if pages_path.exists():
        for line in pages_path.open(encoding="utf-8"):
            r = json.loads(line)
            if isinstance(r, dict):  # {"cap": true}
                return
            done += len(r)
    total = None
    base = f"https://data.egov.kz/api/detailed/{idx}"
    probe = base + "?" + urllib.parse.urlencode({"source": body(), "page": 0, "size": 1})
    with urllib.request.urlopen(urllib.request.Request(probe, headers=UA), timeout=40) as x:
        if not (json.loads(x.read(200000)).get("totalCount")):
            base += "/v1"  # versioned dataset, §15.1 rule; s_geonims/s_buildings answer bare
    for k in range(done // page_size, done // page_size + max_pages):
        url = (base + "?" +
               urllib.parse.urlencode({"source": body(), "from": k * page_size, "size": page_size}))
        for att in range(4):
            try:
                with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=40) as x:
                    j = json.loads(x.read(9_000_000))
                break
            except urllib.error.HTTPError as e:
                if e.code in (400, 416):  # window cap: this harvest is complete up to here
                    pages_path.open("a", encoding="utf-8").write(json.dumps({"cap": k * page_size}) + "\n")
                    print(f"{idx}: window cap at {k * page_size}", flush=True)
                    return
                time.sleep(8 + 8 * att)
            except Exception:
                time.sleep(6 + 6 * att)
        else:
            print(f"{idx}: page {k} failed 4x, stop (resume later)", flush=True)
            return
        d = j.get("data") or []
        total = j.get("totalCount")
        if not d:
            if k == done // page_size and total and done == 0:
                raise RuntimeError(f"{idx}: empty first page but totalCount={total} - wrong form, not empty data")
            break  # offset beyond the end
        pages_path.open("a", encoding="utf-8").write(json.dumps(d, ensure_ascii=False) + "\n")
        if (k + 1) % 10 == 0:
            print(f"{idx}: {(k + 1) * page_size}/{total}", flush=True)
        if (k + 1) * page_size >= (total or 0):
            break
        time.sleep(0.2)
    rows, seen = [], set()
    if not pages_path.exists():
        print(f"{idx}: no pages harvested, skip assembly", flush=True)
        return
    for line in pages_path.open(encoding="utf-8"):
        r = json.loads(line)
        if isinstance(r, dict):
            continue
        for rec in r:
            if rec.get("id") not in seen:
                seen.add(rec.get("id"))
                rows.append(rec)
    proj = {"s_geonims": ["id", "name_kaz", "name_rus", "old_path_kaz", "old_path_rus", "s_ats_id", "modified", "rco"],
            "s_buildings": ["id", "number", "s_geonim_id", "s_ats_id", "s_ground_id", "modified"]}

    def keep(r):
        return {k: r[k] for k in proj.get(idx, r) if k in r and r[k] not in (None, "")}
    items = [keep(r) for r in rows]
    (ROOT / "data" / "gazetteer" / f"{out_name}.json").write_text(
        json.dumps({"source": f"data.egov.kz/api/detailed/{idx} (keyless, bare path - /v1 answers 0 for these two)",
                    "harvested": time.strftime("%Y-%m-%d"), "sort": "id asc (stable windows)",
                    "total_count_claim": total, "rows": len(items),
                    "note": "join fields only; full_path reconstructible via s_geonim_id -> s_geonims; canonical "
                            "street key is the NAME: 442 geonim names carry 2+ ids (1586 rows) - id-join splits one street",
                    "items": items}, ensure_ascii=False, separators=(",", ":")),
        encoding="utf-8")
    print(f"{idx}: {len(rows)} unique rows -> data/gazetteer/{out_name}.json (claimed {total})", flush=True)


if __name__ == "__main__":
    (ROOT / "data" / "gazetteer").mkdir(exist_ok=True)
    harvest("s_geonims", "egov_astana_geonims_live")
    harvest("s_buildings", "egov_astana_buildings_live", max_pages=900)
