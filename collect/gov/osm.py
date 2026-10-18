"""OSM candidates for the state objects: the only source of coordinates (the registers carry none).

Two Overpass queries through the polite layer (`collect.net`, mirror `maps.mail.ru`: overpass-api.de is unreachable from
this host; an answer cached under any endpoint wins), both inside the Astana admin area:

  1. every element whose name / operator / brand mentions ЦОН / ХҚКО / «Центр обслуживания населения» (+ amenity=
     public_service);
  2. every element whose `addr:street` looks like the street of a record and whose `addr:housenumber` is its house
     (buildings and POIs: the address query gives a building even when it carries no name).

The result is reduced to `data/gov/osm_candidates.json` (ref, centre, names, address, the few tags the matcher needs),
which `collect.gov.geocode` reads offline. The mirror returns the tags of some `way` elements double-encoded (UTF-8 bytes
read as cp1252: «Ð¦ÐžÐ» for «ЦОН»); `fix_mojibake` undoes that and the element is marked `encoding_repaired`.

Usage (repo root): uv run python -m collect.gov.osm [--facts data/gov/facts] [--out data/gov/osm_candidates.json]
"""

from __future__ import annotations

import json
import re
import sys
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect import overpass_poi as op
from collect.gov.addr import _FOLD
from collect.gov.model import GovRecord
from collect.net import Net, NetError, default_net

ROOT = Path(__file__).resolve().parents[2]
FACTS_DIR = ROOT / "data" / "gov" / "facts"
OUT_PATH = ROOT / "data" / "gov" / "osm_candidates.json"
MIRROR = "https://maps.mail.ru/osm/tools/overpass/api/interpreter"
TIMEOUT = 180
NAME_KEYS = "name|name:ru|name:kk|name:en|alt_name|official_name|short_name|operator|brand"
CSON_NAME_REGEX = ("ЦОН|ХҚКО|Центр обслуживания населения|Халыққа қызмет көрсету орталығы|Правительство для граждан|"
                   "Public Service Cent")
KEEP_TAGS = ("name", "name:ru", "name:kk", "name:en", "alt_name", "official_name", "short_name", "operator", "brand",
             "addr:street", "addr:housenumber", "addr:place", "amenity", "office", "government", "building",
             "healthcare", "leisure", "tourism")
_CP1252_C1 = {chr(c) for c in range(0x80, 0xA0)}
_CYR = re.compile(r"[А-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ]")
_MOJI = re.compile(r"[ÐÑÒÓ]")

# folded letter -> the spellings an OSM tag may use for it (OSM mixes Russian and Kazakh letters in one street name)
_VARIANTS: dict[str, set[str]] = {}
for _ch, _to in _FOLD.items():
    if _to:
        _VARIANTS.setdefault(_to, {_to}).add(chr(_ch))


def fix_mojibake(text: str) -> tuple[str, bool]:
    """(text, repaired). Double-encoded UTF-8 («Ð¦ÐžÐ») is read back as UTF-8; anything else is returned as is."""
    if not _MOJI.search(text) or _CYR.search(text):
        return text, False
    try:
        raw = b"".join(ch.encode("cp1252") if ch not in _CP1252_C1 else bytes([ord(ch)]) for ch in text)
        fixed = raw.decode("utf-8")
    except (UnicodeEncodeError, UnicodeDecodeError):
        return text, False
    return (fixed, True) if _CYR.search(fixed) else (text, False)


def street_regex(key: str) -> str | None:
    """Case-insensitive Overpass regex for a street key: the longest token, letters widened to their Kazakh/Russian
    variants; a long token loses its first letter (Джангильдина / Жангильдин)."""
    toks = sorted(key.split(), key=len, reverse=True)
    if not toks or len(toks[0]) < 4:
        return None
    tok = toks[0][1:] if len(toks[0]) > 6 else toks[0]
    parts = []
    for ch in tok:
        vs = sorted(_VARIANTS.get(ch, {ch}))
        parts.append(ch if len(vs) == 1 else "[" + "".join(vs) + "]")
    return "".join(parts)


def house_values(house: str) -> list[str]:
    """The spellings of a normalised house number OSM uses: «14а» -> 14а, 14А, 14a, 14A."""
    if not any(ch.isalpha() for ch in house):
        return [house]
    latin = house.replace("а", "a")
    return sorted({house, house.upper(), latin, latin.upper()})


def names_query(area_id: int) -> str:
    return (f"[out:json][timeout:120];\narea({area_id})->.a;\n(\n"
            f'  nwr(area.a)[~"^({NAME_KEYS})$"~"{CSON_NAME_REGEX}",i];\n  nwr(area.a)["amenity"="public_service"];\n'
            ");\nout center tags;\n")


def address_query(area_id: int, key: str, house_value: str) -> str:
    """One query: the elements whose `addr:housenumber` is exactly `house_value` and whose `addr:street` looks like
    the street `key`. The house number is an exact `key=value` filter (Overpass indexes it; a regex over every
    `addr:street` of the city times out), the street a regex on the few elements left."""
    rx = street_regex(key)
    clause = f'  nwr(area.a)["addr:housenumber"="{house_value}"]["addr:street"~"{rx}",i];' if rx else ""
    return f"[out:json][timeout:180];\narea({area_id})->.a;\n(\n{clause}\n);\nout center tags;\n"


def run(net: Net, query: str, max_retries: int = 5) -> tuple[dict, float]:
    """Cached answer under the mirror (or any endpoint of `overpass_poi.ENDPOINTS`), else one POST to the mirror."""
    for url in (MIRROR, *op.ENDPOINTS):
        if (hit := net.cached("POST", url, data={"data": query})) is not None:
            try:
                return hit.json(), hit.fetched_at
            except ValueError:
                pass
    resp = net.post(MIRROR, data={"data": query}, timeout=TIMEOUT, max_retries=max_retries)
    return resp.json(), resp.fetched_at


def reduce_element(el: dict) -> dict | None:
    ll = op.coords(el)
    if not ll or ll[0] is None:
        return None
    tags, repaired = {}, False
    for k in KEEP_TAGS:
        if k in (el.get("tags") or {}):
            tags[k], fixed = fix_mojibake(el["tags"][k])
            repaired |= fixed
    return {"ref": f"{el['type']}/{el['id']}", "lat": ll[0], "lon": ll[1], "tags": tags, "encoding_repaired": repaired}


def targets(records: list[GovRecord]) -> list[tuple[str, str]]:
    out: dict[tuple[str, str], None] = {}
    for r in records:
        if r.address.get("house") and r.address.get("key"):
            out[(r.address["key"], r.address["house"])] = None
    return list(out)


def load_records(facts_dir: Path = FACTS_DIR) -> list[GovRecord]:
    recs: list[GovRecord] = []
    for path in sorted(facts_dir.glob("*.json")):
        recs += [GovRecord.from_dict(d) for d in json.loads(path.read_text(encoding="utf-8"))["records"]]
    return recs


def collect(records: list[GovRecord], net: Net | None = None) -> dict:
    """Run the names query and one address query per distinct (street, house). A failed query is recorded as
    failed - the address was not asked, which is not the same as «OSM has nothing there»."""
    net = net or default_net()
    area_id, _ = op.resolve_area(net)
    elements: dict[str, dict] = {}
    fetched: list[float] = []
    queries = {"names": names_query(area_id), "address": []}

    def absorb(data: dict, at: float) -> int:
        fetched.append(at)
        for el in data.get("elements", []):
            if (red := reduce_element(el)) is not None:
                elements[red["ref"]] = red
        return len(data.get("elements", []))

    absorb(*run(net, queries["names"]))
    status = []
    for key, house in targets(records):
        if street_regex(key) is None:
            status.append({"key": key, "house": house, "status": "failed", "elements": 0,
                           "errors": ["street name too short for a safe regex: not queried"]})
            continue
        done = failed = found = 0
        errors: list[str] = []
        for value in house_values(house):  # one small query per spelling: a union of spellings times out on the mirror
            q = address_query(area_id, key, value)
            queries["address"].append(q)
            try:
                found += absorb(*run(net, q, max_retries=2))
                done += 1
            except (NetError, ValueError) as exc:
                failed += 1
                errors.append(str(exc)[:160])
                print(f"[gov.osm] {key} {value}: {exc!r}", file=sys.stderr)
        state = "ok" if not failed else ("partial" if done else "failed")
        status.append({"key": key, "house": house, "status": state, "elements": found, **({"errors": errors} if errors else {})})
    return {
        "source": "OpenStreetMap contributors (ODbL)", "endpoint": MIRROR, "area_id": area_id,
        "fetched_at": datetime.fromtimestamp(min(fetched), UTC).isoformat(timespec="seconds"),
        "queries": queries, "address_targets": status,
        "elements": sorted(elements.values(), key=lambda e: e["ref"]),
    }


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--facts", default=str(FACTS_DIR))
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args(argv)
    payload = collect(load_records(Path(args.facts)))
    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    fixed = sum(e["encoding_repaired"] for e in payload["elements"])
    failed = [t for t in payload["address_targets"] if t["status"] != "ok"]
    print(f"[gov.osm] {len(payload['elements'])} OSM elements ({fixed} with repaired encoding); "
          f"{len(payload['address_targets'])} address queries, {len(failed)} failed -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
