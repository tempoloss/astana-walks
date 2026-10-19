"""Pour the geocoded GBD leads into data/poi.enriched.json as POIs of an existing category.

Input: gbd_leads_geocoded.jsonl (from geocode_leads.py). Only kind="house" rows are eligible:
a street centroid is kilometers of error in Astana and stays in the leads file until the owner
accepts approximate points. `miss` rows never enter the base (renamed streets - the s_geonims
old_path_* question, not a data hole).

Class -> category follows the shipped taxonomy (no new categories here):
    pawnshop -> money (the pawnbroker subtype lives there since round 25)
    barber / vet -> NOT poured: no beauty/vet category, owner basket (§24.15)
Dedup: category + distance <= 120 m + NAME-TOKEN overlap. Proximity alone is NOT duplication
(measured: of 416 pawn house-hits exactly ONE shares a name with a money record nearby, while
158 sit near some ATM of a different business - a pawnshop next to a bank is two places).
Provenance: source=state_registry - the shipped gov-register label («данные госоргана РК»);
data_label() prints unknown source keys RAW (models.py:192), so a bespoke "gbd_register" would
render as itself; gov_hours cannot swallow these rows: kind_of() demands state_registry_match,
absent here (verified 402/402 kind=None). Register identity rides the tags (bin=, register=gbd_ul).

Names (the second review wave): legal wrappers and city tails are stripped to a fixed point; a
QUOTED brand wins - nested straight quotes («"Ломбард "Аванс""») break both a quote regex and
odd/even segment parity, so every split segment is a candidate unless it is a class word, a
legal form, a preposition-led tail («в городе Астана») or longer than a brand - the longest
survivor is the name. The dry output counts quote/strip/hint paths; a generic «Ломбард» is
street-localized («Ломбард (ул. …)») exactly like unnamed ATMs, and hint names are counted.

    cd <repo root> && uv run python collect/recon/round13/pour_leads.py [--dry] [--classes pawnshop,...]
"""
from __future__ import annotations
import argparse
import json
import math
import re
import time
from collections import Counter
from pathlib import Path

HERE = Path(__file__).parent
ROOT = HERE.parents[2]
BASE = ROOT / "data" / "poi.enriched.json"
LEADS = HERE / "gbd_leads_geocoded.jsonl"
LOG = HERE / "pour_leads_log.jsonl"
COLLECTED_AT = "2026-10-19T00:00:00+00:00"
DEDUP_M = 120
CATEGORY = {"pawnshop": "money"}
NAME_HINT = {"pawnshop": "Ломбард"}
CLASS_WORDS = {"ломбард", "ветеринарная клиника", "стоматология", "клиника", "ип", "тто"}

LEGAL_FORM = re.compile(
    r"^(?:(?:филиал|представительство)\s*(?:№|#\s*)?\S*\s+(?:ТОО|ИП)?\s+|"
    r"товарищество\s+с\s+ограниченной\s+ответственностью|товарищества\s+с\s+ограниченной\s+ответственностью|акционерное\s+общество|"
    r"коммандитное\s+товарищество|полное\s+товарищество|некоммерческое\s+партнёрство|"
    r"(?:\bТОО\b|\bИП\b|\bОсОО\b|\bКГП\b[^,]*|\bГКП\b[^,]*))", re.I)
PREP_TAIL = re.compile(r"^(?:в|на|по|о|при)\s", re.I)
CITY_TAIL = re.compile(r"^(?:в\s+)?(?:город[еa]?\s*\.?\s*$|(?:городе|город|район)\b)", re.I)
QUOTES = str.maketrans({"«": '"', "»": '"', "„": '"', "“": '"', "”": '"'})


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def clean_name(raw: str | None, cls: str, how: Counter) -> str:
    n = (raw or "").strip()
    norm = n.translate(QUOTES)
    if '"' in norm:
        segs = [x.strip() for x in norm.split('"') if x.strip()]
        cand = [
            x for x in segs
            if 3 <= len(x) <= 30 and x.lower() not in CLASS_WORDS
            and not LEGAL_FORM.search(x) and not PREP_TAIL.search(x) and not CITY_TAIL.search(x)
        ]
        if cand:
            how["quote"] += 1
            n = max(cand, key=len)
        else:
            n = norm
    else:
        n = norm
    while True:  # fixed point: wrappers can stack («Филиал ТОО …»)
        m = LEGAL_FORM.sub("", n.strip()).strip(' ,."«»')
        m = re.sub(r"\s*(?:\b(?:в|о)\s+)?(?:городе|город)\s+[А-Яа-яЁё\w'-]+\s*$", "", m).strip(" ,.")
        if m == n:
            break
        n = m
    n = re.sub(r"_+", " ", n).strip()  # the hygiene invariant: no underscore-handles in display names
    if not n or len(n) < 3 or n.lower() in CLASS_WORDS:
        how["hint"] += 1
        n = NAME_HINT[cls]
    else:
        how["strip"] += 1
    return n.strip(' "«».,')


def name_tokens(s: str | None) -> set[str]:
    s = (s or "").lower()
    words = "".join(c if c.isalnum() else " " for c in s).split()
    return {w for w in words if len(w) > 3} - {"ломбард", "tcpo", "ooo", "капитал"}


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--dry", action="store_true")
    ap.add_argument("--classes", default="pawnshop")
    args = ap.parse_args()
    classes = [c.strip() for c in args.classes.split(",") if c.strip()]

    base = json.loads(BASE.read_text(encoding="utf-8"))
    by_cat: dict[str, list[tuple[float, float, str]]] = {}
    bins: set[str] = set()
    for r in base:
        by_cat.setdefault(r["category"], []).append((r["lat"], r["lon"], r["name"]))
        for t in r.get("tags", []):
            if t.startswith("bin="):
                bins.add(t[4:])
    leads = [json.loads(l) for l in LEADS.read_text(encoding="utf-8").splitlines() if l.strip()]
    added, dup_near, dup_bin, skipped_class, not_house = [], 0, 0, 0, 0
    how: Counter = Counter()
    for row in leads:
        cls = row["class"]
        if cls not in classes or cls not in CATEGORY:
            skipped_class += 1
            continue
        if row["kind"] != "house":
            not_house += 1
            continue
        if str(row.get("bin")) in bins:
            dup_bin += 1
            continue
        cat = CATEGORY[cls]
        lt = name_tokens(row.get("name"))
        near = [m for m in by_cat.get(cat, []) if haversine_m(row["lat"], row["lon"], m[0], m[1]) <= DEDUP_M]
        if any(lt and lt & name_tokens(nm) for _, _, nm in near):
            dup_near += 1
            continue
        nm = clean_name(row.get("name"), cls, how)
        if nm == NAME_HINT[cls]:  # a generic word alone would lie about identity - the street localizes it
            street = re.search(r"(?:УЛ\.|ул\.|ПРОСП\.|пр\.|БУЛЬВАР|бульвар|ШОССЕ|шоссе)\s*([^,]+)", row.get("address") or "", re.I)
            if street:
                nm = f"{nm} ({street.group(1).strip()})"
        rec = {
            "id": f"gbd/{row['bin']}",
            "name": nm,
            "name_generated": False,
            "lat": row["lat"],
            "lon": row["lon"],
            "category": cat,
            "tags": [f"bin={row['bin']}", "source_class=" + cls, "register=gbd_ul"],
            "opening_hours": None,
            "hours_state": "unknown",
            "address": row.get("address"),
            "phone": None,
            "website": None,
            "description": None,
            "description_auto": None,
            "source": "state_registry",
            "collected_at": COLLECTED_AT,
            "sources": ["state_registry"],
            "field_sources": {
                "name": {"source": "state_registry", "license": "state open data (V2500032813), portal license not stated",
                         "snapshot_date": "2026-10-19"},
                "address": {"source": "state_registry", "license": "state open data (V2500032813), portal license not stated",
                            "snapshot_date": "2026-10-19"},
                "coordinates": {"source": "offline_geocoder(osm)", "license": "ODbL", "snapshot_date": "2026-10-19",
                                "approximate": False},
            },
        }
        added.append(rec)
        by_cat.setdefault(cat, []).append((rec["lat"], rec["lon"], rec["name"]))
    print(f"added={len(added)} dup_near={dup_near} dup_bin={dup_bin} not_house={not_house} other_classes={skipped_class}")
    print(f"name paths: {dict(how)}")
    LOG.open("a", encoding="utf-8").write(json.dumps({
        "at": time.strftime("%F %T"), "dry": args.dry, "classes": classes, "added": len(added),
        "dup_near": dup_near, "dup_bin": dup_bin, "not_house": not_house, "skipped_class": skipped_class,
        "names": dict(how)}) + "\n")
    if args.dry or not added:
        (HERE / "pour_preview.json").write_text(json.dumps(added[:40], ensure_ascii=False, indent=1), encoding="utf-8")
        print("DRY" if args.dry else "nothing to add", "- preview saved, base untouched")
        return
    BASE.with_suffix(".json.bak-pour").write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    base.extend(added)
    BASE.write_text(json.dumps(base, ensure_ascii=False), encoding="utf-8")
    print(f"base: {len(base)} records written (backup .bak-pour)")


if __name__ == "__main__":
    main()
