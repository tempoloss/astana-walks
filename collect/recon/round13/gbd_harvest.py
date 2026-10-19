"""Harvest the GBD legal-entity register (data.egov.kz `gbd_ul`, v1) for one OKED class in Astana.

Why this shape (round 26, all measured 2026-10-19):
- the bare path `/api/detailed/gbd_ul` answers totalCount 0 - byList datasets need the explicit
  version `/v1` (998,841 rows);
- `bool/must` with 2+ clauses currently throws SearchPhaseExecutionException on the cluster's shard
  (stable across retries, on gbd_ul AND on kazposhta; the scout saw a live bool, the cluster
  degraded) - so every request is a single-field `match_phrase` on `okedru` and the city filter
  runs CLIENT-side over the returned rows; a multi-field `query_string` returns 0 (old ES);
- no coordinates and no hours in the register: this produces a LEADS file (name, BIN, address,
  status, director), geocoding/reconciliation is a separate step;
- pagination: pages are pulled with `"sort": ["bin"]` (unique, present in every row) over a from/size
  window - without a stable key the gazetteer_harvest warning bites (floating order loses rows);
  the header totalCount request needs no sort, and dedup by bin stays as a belt for page overlap.
  Old ES hard-caps from+size at 10 000: classes above the window warn and stop (all ours are below).
- the register never renamed the city: rows read «город Нур-Султан»; the postal prefix 010000 is
  NOT unique to it (Akmola oblast shares it: 154 891 rows vs 116 618 with «Астана»), so the keep
  test is prefix + no oblast word in either address field.

    uv run python collect/recon/round13/gbd_harvest.py "деятельность ломбардов" pawnshops
    uv run python collect/recon/round13/gbd_harvest.py "предоставление услуг парикмахерскими и салонами красоты" barbers
    # okedru is exact-phrase only: "деятельность парикмахерских" measures 0, the classifier wording above 1538
Legal: state open data (regime per V2500032813), license "not stated" on the portal - same track
as pharmacy/notaries in ATTRIBUTION.
"""
from __future__ import annotations
import json
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

HERE = Path(__file__).parent
BASE = "https://data.egov.kz/api/detailed/gbd_ul/v1?source="
UA = {"User-Agent": "astana-walks-gbd-harvest (research)"}


def ask(source: dict) -> dict:
    url = BASE + urllib.parse.quote(json.dumps(source, ensure_ascii=False))
    for attempt in range(4):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=120) as r:
                return json.loads(r.read().decode("utf-8", "replace"))
        except Exception as ex:  # the portal answers 5xx HTML pages too
            print(f"  attempt {attempt}: {str(ex)[:90]}", flush=True)
            time.sleep(8 * (attempt + 1))
    raise RuntimeError("gbd_ul unreachable after 4 attempts")


def is_astana(row: dict) -> bool:
    up = ((row.get("addressru") or "") + " " + (row.get("addresskz") or "")).upper()
    # the 010000 prefix ALONE leaks: the register carries a Шымкент row stamped "010000, город Шымкент"
    # (1 of 497 pawn rows, measured on the delivered slice) - require the city token as well
    return "010000" in up and ("АСТАНА" in up or "НУР-СУЛТАН" in up or "НҰР-СУЛТАН" in up) \
        and "ОБЛАСТЬ" not in up and "ОБЛЫС" not in up


def harvest(oked_phrase: str, slug: str, page: int = 100) -> None:
    out = HERE / f"gbd_{slug}_astana.jsonl"
    total = ask({"query": {"match_phrase": {"okedru": oked_phrase}}, "size": 1}).get("totalCount", 0)
    print(f"class {oked_phrase!r}: {total} legal entities nationwide", flush=True)
    cap = min(total, 10_000 - page)  # old ES hard-caps from+size at 10 000; a class larger than this needs
    if total > 10_000 - page:        # search_after - pawn/vets/barbers are far below, so warn and stop
        print(f"  WARNING total {total} exceeds the from/size window; harvested only the first {cap}")
    seen: set[str] = set()
    kept = 0
    out.unlink(missing_ok=True)
    for offset in range(0, cap + page, page):
        rows = ask({"query": {"match_phrase": {"okedru": oked_phrase}}, "sort": ["bin"], "from": offset,
                    "size": page}).get("data", [])
        if not rows:
            break
        for r in rows:
            key = r.get("bin") or r.get("id")
            if not key or key in seen:
                continue
            seen.add(str(key))
            if not is_astana(r) or "ликвид" in (r.get("statusru") or "").lower():
                continue  # another city, or a shut company - not a place to walk to
            kept += 1
            out.open("a", encoding="utf-8").write(json.dumps(r, ensure_ascii=False) + "\n")
        print(f"  paged {min(offset + page, total)}/{total}, kept {kept}", flush=True)
        time.sleep(1.2)  # the keyless window is polite or it closes
    print(f"wrote {out.name}: {kept} Astana rows")


if __name__ == "__main__":
    if len(sys.argv) != 3:
        sys.exit(__doc__)
    harvest(sys.argv[1], sys.argv[2])
