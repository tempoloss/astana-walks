"""Keyless Elasticsearch window of data.egov.kz: `GET /api/detailed/<index>?source={ES-DSL}` (no apiKey, unlike
`api/v4` = 403). Verified live 2026-10-17: `ps_centers` (ЦОН display, 555 nationally, 11 Astana rows by
`Region ~ 710000000`), the address register of the Committee for Legal Statistics (RCA): `s_geonims` (4032 toponyms
in the city slice, 3016 of type 11 «УЛИЦА»), `s_buildings` (85 256 addressable buildings in Astana, no coordinates),
`d_geonims_types` (85 RU/KK type words), `s_pb` (premises; the real-estate register's `ar_code` joins `s_pb.rca`,
NOT `s_buildings.rca` — different 16-digit namespaces for the same building; verified on a 2026Q3 row).

Legal basis: open data of a state body, Law of the Republic of Kazakhstan №401-V «On access to information»
(art. 1 p. 5: open data = machine-readable data for free use, processing, re-publication; art. 7: free of charge;
art. 10 p. 5 and art. 17: publication on the open-data portal data.egov.kz). robots.txt of data.egov.kz is served
with HTTP 404 (RFC 9309: absent robots.txt = everything allowed; SiteFetcher records `absent`). The portal itself
documents `api/detailed` on https://data.egov.kz/pages/samples without an apiKey in any example.

What this stage stores:
  * `data/gov/facts/ps_centers.json` — the Astana rows of `ps_centers` as evidence-backed records: a **display, not
    a register** — only 2 of the 11 rows carry `geoposition`, both are flagged `IsMarkedToDelete: true`, and one of
    the two coordinates is ~4.3 km off the place its address names (Азиа парк: the point sits by «Нұр Әлем», the mall
    is at пр. Кабанбай батыра, 21 ≈ 51.128, 71.412). The rows are cross-check material for the gov4c.kz ЦОН records;
    their `geoposition` is kept in `extra`, never used for the map.
  * `data/gazetteer/rca_streets.json` — the street layer of the address register: street id, ru/kk spellings,
    former names from `old_path_*` (the renames of the 2010s–2020s), type, district; **no coordinates — the
    register has none** (see `collect.gov.rca.Streets` for the matching use).

Usage (repo root): uv run python -m collect.gov.rca
"""

from __future__ import annotations

import hashlib
import json
import re
import sys
from pathlib import Path
from urllib.parse import quote

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.gov.addr import parse_address, street_key
from collect.gov.model import Evidence, GovRecord
from collect.sites.fetch import SiteFetcher
from collect.sites.store import norm_ws, now_iso

ROOT = Path(__file__).resolve().parents[2]
FACTS_PATH = ROOT / "data" / "gov" / "facts" / "ps_centers.json"
GAZETTEER_PATH = ROOT / "data" / "gazetteer" / "rca_streets.json"
HOST = "https://data.egov.kz"
API = f"{HOST}/api/detailed"
SOURCE_HOST = "data.egov.kz"
PAGE = 1000
# The 6 districts-in-city of Astana (s_ats ids); `terms` over the ids is the exact city slice (`match астана`
# pulls «улица Астана» of other regions).
ASTANA_ATS = ("107989", "108584", "252205", "252235", "251449", "107193")
GEONIMS_SLICE: dict = {"query": {"terms": {"s_ats_id": list(ASTANA_ATS)}}}
DISTRICT_RU = {
    "107989": "Сарыарка",
    "108584": "Есиль",
    "252205": "Нұра",
    "252235": "Сарайшык",
    "251449": "Байконыр",
    "107193": "Алматы",
}
STREET_TYPE = 11  # УЛИЦА in d_geonims_types
LICENSE_NOTE = (
    "открытые данные госоргана РК, Закон №401-V (ст. 1 п. 5: свободное использование, обработка, "
    "повторная публикация)"
)


# ---- the keyless API -------------------------------------------------------------------------------------------------


def detailed_url(index: str, source: dict) -> str:
    """The ES-DSL query URL; the braces are quoted for the URL (curl needs --globoff, httpx does not)."""
    return f"{API}/{index}?source={quote(json.dumps(source, ensure_ascii=False))}"


def detailed(fetcher: SiteFetcher, index: str, source: dict) -> tuple[dict, str]:
    """One response of the keyless endpoint as (json, page url); a non-200 raises (the API has no partial answers)."""
    url = detailed_url(index, source)
    page = fetcher.fetch(url)
    if not page.ok:
        raise RuntimeError(f"{url}: HTTP {page.status} {page.error}")
    return json.loads(page.text), url


def fetch_all(
    fetcher: SiteFetcher, index: str, source: dict, cap: int = 20_000
) -> tuple[list[dict], list[str], int]:
    """All rows of a query, paged by `PAGE` (`size`/`from`); (rows, page urls, totalCount of the first page)."""
    rows: list[dict] = []
    pages: list[str] = []
    seen: set[str] = set()
    total = -1
    for start in range(0, cap, PAGE):
        payload, url = detailed(fetcher, index, {**source, "size": PAGE, "from": start})
        pages.append(url)
        total = payload.get("totalCount", total)
        batch = payload.get("data") or []
        fresh = [r for r in batch if str(r.get("_id") or r.get("id")) not in seen]
        seen.update(str(r.get("_id") or r.get("id")) for r in fresh)
        rows.extend(fresh)
        if len(batch) < PAGE or not fresh:
            break
    return rows, pages, total


# ---- ps_centers (ЦОН display) ----------------------------------------------------------------------------------------


def _json_pair(key: str, value: str) -> str:
    """The `"key": "value"` snippet as the verifier's re-serialised view of the page prints it."""
    return json.dumps({key: value}, ensure_ascii=False)[1:-1]


def build_ps_record(row: dict, page_url: str) -> GovRecord | None:
    name_ru, addr_ru = norm_ws(row.get("NameRus") or ""), norm_ws(row.get("AddressRus") or "")
    if not name_ru or not addr_ru:
        return None
    ev = [
        Evidence("name", page_url, _json_pair("NameRus", row["NameRus"]), None, "ru"),
        Evidence("address", page_url, _json_pair("AddressRus", row["AddressRus"]), None, "ru"),
    ]
    if row.get("PhoneNumber"):
        ev.append(
            Evidence("phone", page_url, _json_pair("PhoneNumber", row["PhoneNumber"]), None, "ru")
        )
    a = parse_address(addr_ru)
    rid = "gov/cson-pc/" + hashlib.sha1(f"ps|{name_ru}|{addr_ru}".encode()).hexdigest()[:10]
    return GovRecord(
        id=rid,
        kind="cson",
        source=SOURCE_HOST,
        url=page_url,
        name=name_ru,
        names={"ru": name_ru, **({"kk": norm_ws(row["NameKaz"])} if row.get("NameKaz") else {})},
        address={
            "raw": a.raw,
            "street": a.street,
            "house": a.house,
            "key": a.key,
            "by_lang": {
                "ru": addr_ru,
                **({"kk": norm_ws(row["AddressKaz"])} if row.get("AddressKaz") else {}),
            },
        },
        hours=None,
        evidence=ev,
        phone_raw=norm_ws(row.get("PhoneNumber") or "") or None,
        extra={
            "register": "ps_centers",
            "display": True,
            "marked_to_delete": row.get("IsMarkedToDelete") == "true",
            "geoposition": row.get("geoposition") or None,
            "tax_structure": norm_ws(row.get("TaxStructure") or "") or None,
            "modified": norm_ws(row.get("ModifiedDate") or "") or None,
        },
    )


def astana_ps_centers(fetcher: SiteFetcher) -> tuple[list[GovRecord], list[str], dict]:
    """The ЦОН display rows of Astana as records; never a coordinate source (see the module docstring)."""
    rows, pages, total = fetch_all(
        fetcher, "ps_centers", {"query": {"match_phrase": {"Region": "710000000"}}}
    )
    records = [r for row in rows if (r := build_ps_record(row, pages[0]))]
    stats = {
        "rows_national": total,
        "rows_astana": len(rows),
        "records": len(records),
        "with_geoposition": sum(1 for r in records if r.extra.get("geoposition")),
        "marked_to_delete": sum(1 for r in records if r.extra.get("marked_to_delete")),
    }
    return records, pages, stats


# ---- the street gazetteer --------------------------------------------------------------------------------------------

_FORMER = re.compile(r"(?:улица|көшесі|даңғылы|проспект|площадь|алаңы)\s+(.+?)$")


def _former_names(row: dict) -> list[str]:
    """Former spellings of a toponym from its `old_path_*` history: the segment after the type word, dropped when it
    is just the current name again."""
    out: list[str] = []
    current = {norm_ws(row.get("name_rus")), norm_ws(row.get("name_kaz"))}
    for key in ("old_path_rus", "old_path_kaz"):
        for seg in (row.get(key) or "").split(";"):
            m = _FORMER.search(" ".join(seg.split()))
            if not m:
                continue
            name = m.group(1).strip(" .")
            if name and name not in current:
                out.append(name)
    return sorted(dict.fromkeys(out))


def build_gazetteer(geonims: list[dict], types: list[dict], url: str) -> dict:
    """The compact street layer from the `s_geonims` city slice + the `d_geonims_types` dictionary."""
    items = []
    for r in geonims:
        if str(r.get("d_geonims_type_id")) != str(STREET_TYPE) or not norm_ws(r.get("name_rus")):
            continue
        key = " ".join(street_key(r["name_rus"]).split())
        if not key:  # «Набережная» alone: nothing left after the type words are folded away
            continue
        items.append(
            {
                "id": str(r.get("id") or r.get("_id")),
                "key": key,
                "ru": norm_ws(r["name_rus"]),
                "kk": norm_ws(r.get("name_kaz") or r["name_rus"]),
                "former": _former_names(r),
                "district": DISTRICT_RU.get(str(r.get("s_ats_id"))),
                "actual": str(r.get("actual")) not in ("0", "false", ""),
                "modified": (r.get("modified") or "")[:10] or None,
            }
        )
    type_words = {
        str(t.get("id")): {
            "ru": norm_ws(t.get("value_ru") or ""),
            "kk": norm_ws(t.get("value_kz") or ""),
            "short_ru": norm_ws(t.get("short_value_ru") or "") or None,
            "short_kk": norm_ws(t.get("short_value_kz") or "") or None,
        }
        for t in types
        if t.get("id") is not None
    }
    return {
        "source": "ИС «Адресный регистр» (RCA) Комитета по правовой статистике и специальным учетам Генеральной "
        "прокуратуры РК, через data.egov.kz /api/detailed/s_geonims (keyless)",
        "url": url,
        "attribution": "Комитет по правовой статистике и специальным учетам Генеральной прокуратуры РК",
        "license": LICENSE_NOTE,
        "retrieved_at": now_iso(),
        "snapshot_note": f"city slice s_ats {','.join(ASTANA_ATS)}; the register is live (max(modified) observed "
        "2026-10-15), unlike the OpenAddresses snapshot ≤2017",
        "use": "address aliases / normalisation only: old->new names, ru<->kk spellings; NO coordinates (the "
        "register has none)",
        "rows_total": len(geonims),
        "streets": len(items),
        "with_former_names": sum(1 for i in items if i["former"]),
        "type_words": type_words,
        "coordinates": False,
        "items": items,
    }


# ---- crawl -----------------------------------------------------------------------------------------------------------


def crawl(fetcher: SiteFetcher | None = None) -> tuple[dict, dict]:
    """(ps_centers facts payload, gazetteer payload). The only network-touching function of the stage."""
    f = fetcher or SiteFetcher()
    records, pages, pc_stats = astana_ps_centers(f)
    facts = {
        "source": SOURCE_HOST,
        "fetched_at": now_iso(),
        "pages": pages,
        "robots": f.robots_status(HOST + "/"),
        "stats": pc_stats,
        "records": [r.to_dict() for r in records],
        "notes": "ps_centers is a DISPLAY of ЦОН sectors: rows carry IsMarkedToDelete, only some have geoposition "
        "and one of those is ~4.3 km off its own address (Азиа парк). Cross-check of the gov4c.kz ЦОН "
        "records only; the geoposition values are kept in extra, never used for the map.",
    }
    geonims, gpages, _gtotal = fetch_all(f, "s_geonims", GEONIMS_SLICE)
    types, _tpages, _ttotal = fetch_all(f, "d_geonims_types", {"query": {"match_all": {}}}, cap=200)
    gazetteer = build_gazetteer(geonims, types, gpages[0])
    return facts, gazetteer


def load_gazetteer(path: Path = GAZETTEER_PATH) -> dict[str, dict]:
    """key -> street entry of the shipped gazetteer; empty when the file is absent (the gazetteer is optional).
    A former name indexes the same entry: `rca_lookup` then rewrites «Сатпаева» -> the register's «Қаныш Сәтбаев»."""
    if not path.exists():
        return {}
    items = json.loads(path.read_text(encoding="utf-8"))["items"]
    out: dict[str, dict] = {}
    for s in items:
        if s.get("key"):
            out.setdefault(s["key"], s)
    for s in items:
        for old in s.get("former") or []:
            k = " ".join(street_key(old).split())
            if k:
                out.setdefault(k, s)
    return out


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--facts", default=str(FACTS_PATH))
    ap.add_argument("--gazetteer", default=str(GAZETTEER_PATH))
    args = ap.parse_args(argv)
    facts, gazetteer = crawl()
    Path(args.facts).parent.mkdir(parents=True, exist_ok=True)
    Path(args.facts).write_text(
        json.dumps(facts, ensure_ascii=False, indent=1) + "\n", encoding="utf-8"
    )
    out = Path(args.gazetteer)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(gazetteer, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    s = facts["stats"]
    print(
        f"[gov.rca] ps_centers: {s['rows_astana']} Astana rows ({s['with_geoposition']} with geoposition, "
        f"{s['marked_to_delete']} marked to delete), national totalCount {s['rows_national']}; "
        f"gazetteer: {gazetteer['streets']} streets ({gazetteer['with_former_names']} with former names)"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
