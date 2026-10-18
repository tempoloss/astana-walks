"""Street gazetteer of Astana from OpenAddresses KZ: address ALIASES and normalisation only, no coordinates.

Source: `data.openaddresses.io/cache/uploads/sergiyprotsiv/5f6b95/kz.csv.zip` (12 MB, `number,street,region,district,
x_point,y_point`; the manifest's attribution is «Комитет по правовой статистике и специальным учетам Генеральной
прокуратуры РК»). The rows with region «АСТАНА» are reduced to streets: folded key, printed spelling, number of address
points, districts. The snapshot is old (zip member dated 2017-01; the 2020s renames are missing) and its CRS is wrong
for most of the country, so the x/y columns are NOT used: coordinates of a state object come only from matching OSM
elements by name and address (`collect.gov.geocode`).

Usage (repo root): uv run python -m collect.gov.gazetteer [--out data/gazetteer/astana_streets.json]
"""

from __future__ import annotations

import csv
import io
import json
import sys
import zipfile
from collections import Counter, defaultdict
from datetime import UTC, datetime
from pathlib import Path

if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.gov.addr import street_key
from collect.net import default_net

ROOT = Path(__file__).resolve().parents[2]
OUT_PATH = ROOT / "data" / "gazetteer" / "astana_streets.json"
URL = "https://data.openaddresses.io/cache/uploads/sergiyprotsiv/5f6b95/kz.csv.zip"
REGION = "АСТАНА"
ATTRIBUTION = "Комитет по правовой статистике и специальным учетам Генеральной прокуратуры РК " \
              "(через OpenAddresses, openaddresses.io)"


def build(content: bytes, last_modified: str | None = None, retrieved_at: str | None = None) -> dict:
    with zipfile.ZipFile(io.BytesIO(content)) as z:
        member = next(n for n in z.namelist() if n.endswith(".csv"))
        rows = list(csv.DictReader(io.TextIOWrapper(z.open(member), encoding="utf-8")))
    astana = [r for r in rows if (r.get("region") or "").strip().upper() == REGION]
    by_key: dict[str, dict] = defaultdict(lambda: {"names": Counter(), "n": 0, "districts": Counter()})
    for r in astana:
        name = " ".join((r["street"] or "").split())
        key = street_key(name)
        if not key:
            continue
        g = by_key[key]
        g["names"][name] += 1
        g["n"] += 1
        g["districts"][(r.get("district") or "").strip()] += 1
    streets = [{
        "key": k, "name": g["names"].most_common(1)[0][0], "aliases": sorted(set(g["names"]) - {g["names"].most_common(1)[0][0]}),
        "addresses": g["n"], "districts": sorted(d for d in g["districts"] if d),
    } for k, g in sorted(by_key.items())]
    return {
        "source": "OpenAddresses KZ", "url": URL, "attribution": ATTRIBUTION,
        "license": "not stated by the source (OpenAddresses does not relicense the original data); state address "
                   "register, Закон №401-V ст. 1 п. 5; attribution required",
        "retrieved_at": retrieved_at or datetime.now(UTC).isoformat(timespec="seconds"),
        "file_last_modified": last_modified, "zip_member": member,
        "snapshot_note": "zip member dated 2017-01; later street renames are absent",
        "use": "address aliases / normalisation only; coordinates columns deliberately not stored",
        "rows_country": len(rows), "rows_astana": len(astana), "streets": len(streets), "coordinates": False,
        "items": streets,
    }


def load(path: Path = OUT_PATH) -> dict[str, dict]:
    """key -> street entry; empty when the gazetteer file is absent."""
    if not path.exists():
        return {}
    return {s["key"]: s for s in json.loads(path.read_text(encoding="utf-8"))["items"]}


def main(argv: list[str] | None = None) -> int:
    import argparse

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default=str(OUT_PATH))
    args = ap.parse_args(argv)
    resp = default_net().get(URL, timeout=300)
    cached = resp.from_cache
    payload = build(resp.content, resp.headers.get("last-modified"),
                    datetime.fromtimestamp(resp.fetched_at, UTC).isoformat(timespec="seconds"))
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    print(f"[gov.gazetteer] {payload['rows_astana']} Astana address rows -> {payload['streets']} street keys "
          f"({'cache' if cached else 'network'}) -> {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
