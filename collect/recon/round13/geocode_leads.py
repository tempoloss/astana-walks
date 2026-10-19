"""Geocode the GBD/kazpost LEADS through the shipped offline geocoder (app/web/geocode.py).

Extraction rules (all measured, 19.10):
- street-type words match as WHOLE tokens only («ул.», «улица», «көшесі»... with optional dot+space):
  a prefix match cut «УЛЫ дала» into «ЛЫ» (the smoke showed kind=place instead of the street);
  the regression set is exactly the streets that exposed it: Улы дала / Есенберлина / Айтматова /
  Кошкарбаева + «Абылай хана, д. 26/1» (must reach house);
- the register row is «010000, Г.АСТАНА, РАЙОН..., УЛ. X, д. N, оф. 26» - feed the geocoder the
  street+house tail ONLY (city/district/office tokens sink the fuzzy floor);
- three metrics, no blending: house-hit / street-centroid (approximate=True) / miss. Misses are a
  legitimate output (renamed streets - the real use of the s_geonims old_path_* chains), they stay
  in the leads file and are NEVER poured into the base.

    cd app && uv run python ../collect/recon/round13/geocode_leads.py
Writes gbd_leads_geocoded.jsonl next to this file.
"""
from __future__ import annotations
import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
sys.path.insert(0, str(ROOT / "app"))
from web import geocode  # the shipped offline geocoder (ODbL gazetteer)

TYPE = re.compile(
    r"(?:\b(?:ул|пр|просп|пер|бур|туп)\.\s*|\b(?:улица|проспект|бульвар|переулок|тупик|шоссе|"
    r"көшесі|көше|даңғылы|даңғыл)\s+)([^,;]+)",
    re.I,
)  # dotted abbreviations ONLY with the dot («ул.» never cuts «УЛЫ дала»), whole words by space (advisory)
HOUSE = re.compile(r"(?:\bд\.|\bдом\s+|\bзд\.)\s*([\w\-/]+)|(?:,\s*)(\d+[\w\-/]*)(?=\s*(?:[,;]|$))", re.I)
OFFICE = re.compile(r"[,;]\s*(?:оф|блок|н\s*\.?\s*п|эт|каб|пом)\b[^,;]*", re.I)


def lead_query(row: dict) -> str | None:
    txt = (row.get("addressru") or "") + " ;; " + (row.get("addresskz") or "")
    txt = OFFICE.sub("", txt)
    best = None
    for m in TYPE.finditer(txt):
        name = m.group(1).strip(" ,.")
        if len(name) < 3:
            continue
        tail = txt[m.end():m.end() + 40]
        h = HOUSE.search(tail) or HOUSE.search(txt)
        best = f"{name} {(h.group(1) or h.group(2))}".strip() if h else name
    if best:
        return best
    # no type word (the kazpost shape: bare «Ауэзова», the regression's «УЛЫ ДАЛА») - the measured
    # branch is the raw string; for long register rows the city/district prologue goes first
    head = (row.get("address") or "").strip(" ,.;")
    if head:
        return head
    body = re.split(r"РАЙОН[^,;]*[,;]", txt, maxsplit=1, flags=re.I)[-1]
    body = re.split(r";;", body, maxsplit=1)[0]
    body = re.sub(r"^\s*(?:\d{6},\s*)?(?:Г\.?\s*)?(?:АСТАНА|НУР-СУЛТАН|НҰР-СУЛТАН)[\w.\s,]*[,;]", "", body, flags=re.I)
    return body.strip(" ,.;") or None


def geocode_row(row: dict, raw: str | None = None) -> tuple[str | None, float | None, float | None]:
    # the kazpost branch is the measured one: feed the SHORT address string to search() as is (43/52
    # street-centroids came that way); the type-regex is only for the long register rows
    q = raw if raw is not None else lead_query(row)
    if not q:
        return None, None, None
    hits = geocode.search(q)
    if not hits:
        return "miss", None, None
    top = hits[0]
    kind = top.get("kind")
    if kind in ("house", "street"):
        return kind, top["lat"], top["lon"]
    return "miss", None, None


def main() -> None:
    reg = [
        ("УЛЫ ДАЛА", "Улы дала"), ("ул. УЛЫ ДАЛА, д. 4", "Улы дала 4"),
        ("ул. Есенберлина, д. 10", "Есенберлина 10"), ("ул. Айтматова", "Айтматова"),
        ("ул. Кошкарбаева, 5", "Кошкарбаева 5"),
        ("УЛ. АБЫЛАЙ ХАНА, д. 26/1, оф. 26", "Абылай хана 26/1"),
    ]
    for raw, want in reg:
        got = lead_query({"addressru": raw})
        assert got and all(w in got.lower() for w in want.lower().split()), (raw, want, got)
    print("extraction regression: ok", flush=True)

    from collections import Counter
    stats = Counter()
    out = HERE / "gbd_leads_geocoded.jsonl"
    out.unlink(missing_ok=True)
    for f, cls in (
        ("gbd_pawnshops_astana.jsonl", "pawnshop"),
        ("gbd_barbers_astana.jsonl", "barber"),
        ("gbd_vets_astana.jsonl", "vet"),
        ("kazposhta_astana.jsonl", "post_office"),
    ):
        p = HERE / f
        if not p.exists():
            continue
        for line in p.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if cls == "post_office":
                row = {"addressru": row.get("address"), "addresskz": "", "name": row.get("name"),
                       "bin": row.get("nomber") or row.get("id")}
            kind, lat, lon = geocode_row(row, raw=(row.get("address") if cls == "post_office" else None))
            stats[(cls, kind)] += 1
            rec = {
                "class": cls,
                "name": row.get("nameru") or row.get("name"),
                "bin": row.get("bin"),
                "address": row.get("addressru") or row.get("address"),
                "query": (row.get("address") if cls == "post_office" else lead_query(row)),
                "kind": kind,
                "approximate": kind == "street",
                "lat": lat,
                "lon": lon,
            }
            out.open("a", encoding="utf-8").write(json.dumps(rec, ensure_ascii=False) + "\n")
    for (cls, kind), n in sorted(stats.items(), key=lambda kv: (kv[0][0], str(kv[0][1]))):
        print(f"{cls:12} {str(kind):8} {n}")
    h = sum(v for (c, k), v in stats.items() if k == "house")
    s = sum(v for (c, k), v in stats.items() if k == "street")
    m = sum(v for (c, k), v in stats.items() if k != "house" and k != "street")
    print(f"TOTAL house={h} street_approx={s} miss={m}")


if __name__ == "__main__":
    main()
