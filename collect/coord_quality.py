"""Overture coordinate sanity checks (OSM records are never touched).

Overture's Meta-derived records sometimes carry a placeholder point instead of the venue's location: hundreds of
unrelated businesses share one pair of coordinates (the city centroid or a building of a data aggregator), or the
street in the address lies kilometres from the point ("Астана Азия Парк, Ұлы Дала 19" 7 km away at the airport).
Two rules, both on Overture records only:

* ``collapsed_point``: >= CLUSTER_MIN records share the same point (5 decimals, ~1 m) and their addresses do not
  agree (no street, or no single address holds more than SHARE_MAX of them). A mall or business centre also puts
  tenants on one point, but they share one address, so they stay. Measured on release 2026-09-23.1: with a
  threshold of 3 the rule also dropped a real mall (Сарыарка, 3 records on its point) and a theatre (Flamenco);
  the placeholder points are far larger (236, 158, 118, 40, 30, 24, ... records, top address share 1-6%), so
  CLUSTER_MIN is 8.
* ``address_far``: the street of the address has >= REF_MIN reference points (OSM POI addresses, Overture records
  outside any shared point) and the nearest one is more than FAR_M away from the record. A long avenue can end far
  from its mapped middle (the airport sits at the end of Кабанбай батыра), so this only nominates a record:
  `collect.build` stage `geocheck` geocodes the address with Nominatim (1 req/s, cached) and the record is
  suspect only when the geocoder puts the address more than FAR_M from the record, or finds nothing
  (`unverified`: kept but flagged).

`python -m collect.coord_quality` writes data/overture_geocheck.json (candidates and their Nominatim answers);
merge.py applies the verdicts.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path

try:
    from collect.names import name_key
    from collect.net import default_net
    from collect.overpass_poi import haversine_m, write_json
    from collect.overture_places import CONFIDENCE_CUTOFF
except ImportError:  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from collect.names import name_key
    from collect.net import default_net
    from collect.overpass_poi import haversine_m, write_json
    from collect.overture_places import CONFIDENCE_CUTOFF

DATA = Path(__file__).resolve().parents[1] / "data"
NOMINATIM = "https://nominatim.openstreetmap.org/search"
CLUSTER_MIN = 8
SHARE_MAX = 0.4
REF_MIN = 5
FAR_M = 2000.0
SELF_EPS = 1e-5  # a record is not its own reference
CLOSED = {"closed", "permanently_closed", "temporarily_closed"}

_TYPE = re.compile(
    r"(?<![\w])(?:улица|ул|көшесі|кошеси|көше|проспект|пр|даңғылы|данғылы|даңғыл|шоссе|бульвар|б-р|переулок|пер|"
    r"микрорайон|мкр|шағын\s*аудан|площадь|набережная|street|st|avenue|ave|road|rd|район|жилой|комплекс|жк|дом|д|кв|"
    r"офис|этаж|блок|корпус|зд|здание|строение)(?![\w])\.?", re.I)
_CITY = re.compile(
    r"(?<![\w])(?:астана|нур-?султан|nur-?sultan|astana|казахстан|kazakhstan|қазақстан|г|город|қала|республика|"
    r"область|kz|рк)(?![\w])", re.I)
_NUM = re.compile(r"[\d/\-]+[а-яa-z]?\b", re.I)
_HOUSE = re.compile(r"(\d+)\s*(?:[/\-]\s*\d+)?\s*[а-яa-z]?\s*$", re.I)


def street_keys(freeform: str | None) -> set[str]:
    """Normalised street names found in a free-form address (parts with a street word or a number)."""
    out = set()
    for part in re.split(r"[,;]", freeform or ""):
        if not re.search(r"\d", part) and not _TYPE.search(part):
            continue
        k = name_key(_CITY.sub(" ", _TYPE.sub(" ", _NUM.sub(" ", part))))
        if len(k) >= 4:
            out.add(k)
    return out


def address_key(ov: dict) -> tuple[str, str] | None:
    """(street, house number) of the first address that has both, else None."""
    for a in ov["addresses"]:
        text = a.get("freeform") or ""
        keys = street_keys(text)
        m = _HOUSE.search(text.strip())
        if keys and m:
            return sorted(keys)[0], m.group(1)
    return None


def point_key(ov: dict) -> tuple[float, float]:
    return round(ov["lat"], 5), round(ov["lon"], 5)


def collapsed_points(ovs: list[dict]) -> dict[str, dict]:
    """{overture id: evidence} for records on a point shared by >= CLUSTER_MIN records with disagreeing addresses."""
    groups: dict[tuple, list[dict]] = defaultdict(list)
    for ov in ovs:
        groups[point_key(ov)].append(ov)
    out = {}
    for pt, members in groups.items():
        if len(members) < CLUSTER_MIN:
            continue
        keys = Counter(k for ov in members if (k := address_key(ov)))
        top = keys.most_common(1)[0][1] / len(members) if keys else 0.0
        if top > SHARE_MAX:
            continue
        for ov in members:
            out[ov["id"]] = {"reason": "collapsed_point", "records_on_point": len(members),
                             "top_address_share": round(top, 2)}
    return out


def street_references(osm: list[dict], ovs: list[dict], skip_ids: set[str]) -> dict[str, list[tuple[float, float]]]:
    """street key -> points of OSM POI and (trusted) Overture records that carry that street in their address."""
    ref: dict[str, list[tuple[float, float]]] = defaultdict(list)
    for p in osm:
        for k in street_keys(p.get("address")):
            ref[k].append((p["lat"], p["lon"]))
    for ov in ovs:
        if ov["id"] in skip_ids or (ov["confidence"] or 0) < 0.5:
            continue
        for a in ov["addresses"]:
            for k in street_keys(a.get("freeform")):
                ref[k].append((ov["lat"], ov["lon"]))
    return ref


def far_from_street(ov: dict, ref: dict[str, list[tuple[float, float]]]) -> float | None:
    """Distance (m) to the nearest reference point of the record's best-known street, if that is > FAR_M."""
    nearest = []
    for a in ov["addresses"]:
        for k in street_keys(a.get("freeform")):
            pts = [q for q in ref.get(k, ()) if abs(q[0] - ov["lat"]) + abs(q[1] - ov["lon"]) > SELF_EPS]
            if len(pts) >= REF_MIN:
                nearest.append(min(haversine_m(ov["lat"], ov["lon"], *q) for q in pts))
    return min(nearest) if nearest and min(nearest) > FAR_M else None


def address_query(freeform: str) -> str:
    """The part of a free-form address that carries the street and house number (Overture prefixes it with a
    business or place name: "Дпд Казахстан, Ұлы Дала даңғылы 19")."""
    parts = [p.strip() for p in freeform.split(",") if p.strip()]
    with_number = [p for p in parts if re.search(r"\d", p)]
    return with_number[-1] if with_number else freeform


def nominatim_point(net, freeform: str) -> tuple[tuple[float, float] | None, float]:
    """(best hit or None, epoch seconds the answer was fetched - the cache time on reruns)."""
    resp = net.get(NOMINATIM, params={
        "q": f"{address_query(freeform)}, Астана", "format": "jsonv2", "limit": 1, "accept-language": "ru",
        "viewbox": "71.2,51.3,71.7,50.95", "bounded": 1,
    })
    data = resp.json()
    return ((float(data[0]["lat"]), float(data[0]["lon"])) if data else None), resp.fetched_at


def candidates(ovs: list[dict], osm: list[dict], cutoff: float) -> tuple[dict[str, dict], dict[str, dict]]:
    """(collapsed-point records, address_far nominees); nominees only among records that could enter the dataset."""
    usable = [o for o in ovs if o["name"] and o["operating_status"] not in CLOSED]
    collapsed = collapsed_points(usable)
    ref = street_references(osm, usable, set(collapsed))
    nominees = {}
    for ov in usable:
        if ov["id"] in collapsed or ov["category"] == "other" or (ov["confidence"] or 0) < cutoff:
            continue
        if (d := far_from_street(ov, ref)) is not None:
            nominees[ov["id"]] = {"reason": "address_far", "street_ref_distance_m": round(d)}
    return collapsed, nominees


def collect(data_dir: Path, cutoff: float) -> dict:
    net = default_net()
    ov_file = json.loads((data_dir / "overture_places.json").read_text(encoding="utf-8"))
    osm = json.loads((data_dir / "poi.osm.json").read_text(encoding="utf-8"))
    by_id = {o["id"]: o for o in ov_file["places"]}
    collapsed, nominees = candidates(ov_file["places"], osm, cutoff)
    checks, fetched = {}, 0.0
    for oid, ev in sorted(nominees.items()):
        ov = by_id[oid]
        text = next((a["freeform"] for a in ov["addresses"] if a.get("freeform")), None)
        hit, stamp = nominatim_point(net, text) if text else (None, 0.0)
        fetched = max(fetched, stamp)
        row = {**ev, "name": ov["name"], "category": ov["category"], "address": text,
               "nominatim": None if hit is None else {"lat": hit[0], "lon": hit[1]}}
        if hit is None:
            row["verdict"] = "unverified"
        else:
            row["distance_m"] = round(haversine_m(ov["lat"], ov["lon"], *hit))
            row["verdict"] = "address_far" if row["distance_m"] > FAR_M else "confirmed"
        checks[oid] = row
    snapshot = (datetime.fromtimestamp(fetched, timezone.utc).date().isoformat() if fetched
                else ov_file["meta"]["snapshot_date"])
    result = {
        "meta": {"snapshot_date": snapshot, "cutoff": cutoff, "release": ov_file["meta"]["release"],
                 "license": "ODbL-1.0 (Nominatim answers, © OpenStreetMap contributors)",
                 "params": {"cluster_min": CLUSTER_MIN, "share_max": SHARE_MAX, "ref_min": REF_MIN, "far_m": FAR_M},
                 "counts": {"collapsed_point_records": len(collapsed),
                            "collapsed_point_clusters": len({point_key(by_id[i]) for i in collapsed}),
                            "address_far_nominees": len(nominees),
                            "verdicts": dict(Counter(c["verdict"] for c in checks.values()))}},
        "collapsed_point": collapsed,
        "address_check": checks,
    }
    net.log_summary("geocheck")
    return result


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--data", default=str(DATA))
    parser.add_argument("--cutoff", type=float, default=CONFIDENCE_CUTOFF)
    args = parser.parse_args(argv)
    result = collect(Path(args.data), args.cutoff)
    write_json(Path(args.data) / "overture_geocheck.json", result)
    print(json.dumps(result["meta"]["counts"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
