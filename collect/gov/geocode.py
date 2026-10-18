"""Coordinates for state objects: matching only, never bulk geocoding, never the OpenAddresses points.

A record gets a position from an existing OSM element (`data/gov/osm_candidates.json`, fetched by `collect.gov.osm`) or
an existing POI of the dataset, by name AND address:

  ЦОН (`cson`) vs OSM elements, best rank first
    3 `osm_name_address`  the element says ЦОН/ХҚКО/«Центр обслуживания населения», its district (and №) fit the record,
                          and its house number + street are the record's;
    2 `osm_address`       same house + street and the element is ЦОН-like (the name does not name the district);
    1 `osm_address`       same house + street, an unnamed or other-named element (the building): the address is the
                          registry's, the building is OSM's;
    0 `osm_name`          ЦОН-like element WITHOUT any address tag whose district matches and where exactly one record
                          of the register names that district: position of OSM's own element, not address-verified.
  sport complexes vs dataset POIs: `poi_name_address` (the same house + street, and a name similarity >= 75 or a strict
    name match) or `poi_name` (strict name match: equal skeleton or whole tokens of the shorter name inside the longer;
    category sport / attraction / entertainment; the POI has no address or the register's street); a sport record not
    matched to a POI goes through the OSM address match like ЦОН rank 1.

Candidates farther than 150 m from each other are ambiguous: the record stays unmapped (with the reason), it is kept and
counted. A record without a house number is matched by name only (rank 0), else unmapped. Absence of a match is a fact
about our data, not about the world.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass

from collect.gov.addr import (
    Address,
    fold,
    make_address,
    parse_address,
    same_street,
    street_key,
)
from collect.gov.model import Geocode, GovRecord
from collect.names import skeleton
from collect.overpass_poi import haversine_m
from collect.sites.join import name_similarity, poi_names

AMBIGUOUS_M = 150.0
POI_NAME_ADDR = 75.0  # fuzzy name similarity that, together with the same house + street, attaches a record to a POI
POI_NAME_ONLY = 90.0  # strict name match (see `_strict_name`) that attaches without an address
NAME_ONLY_CATEGORIES = frozenset({"sport", "attraction_landmark", "entertainment"})  # a venue, never a shop / cafe
LICENSE_OSM = "ODbL 1.0, © OpenStreetMap contributors"
CSON_MARK = re.compile(r"цон|хқко|центр обслуживания населения|халыққа қызмет|public service cent", re.IGNORECASE)
# folded stems of the districts named in ЦОН names (fold: ы->и, ұ->у, ә->а ... see collect.gov.addr)
DISTRICTS = {"есиль": "есил", "нура": "нура", "алматы": "алмат", "байконыр": "байкон", "сарыарка": "сариарк",
             "сарайшык": "сараиш"}
_NUMBER = re.compile(r"№\s*(\d+)|номер\s+(\d+)", re.IGNORECASE)
_LEGAL = re.compile(r"\b(?:КГУ|ГККП|ГКП|ГУ|КГП|РГП|ТОО|АО|НАО|ГККП на ПХВ)\b|С/К|акимата (?:города|г\.)\s*Астан\w*",
                    re.IGNORECASE)
_QUOTED = re.compile(r"[«\"“]([^«»\"“”]{3,}?)[»\"”]")
_NAME_TAGS = ("name", "name:ru", "name:kk", "name:en", "alt_name", "official_name", "short_name", "operator", "brand")


def districts_of(text: str) -> set[str]:
    f = fold(text)
    return {d for d, stem in DISTRICTS.items() if stem in f}


def number_of(text: str) -> str | None:
    m = _NUMBER.search(text)
    return (m.group(1) or m.group(2)) if m else None


def venue_names(names: dict[str, str]) -> list[str]:
    """Name variants of a registry name: quoted parts, and the whole without legal forms / quotes."""
    out: list[str] = []
    for text in names.values():
        out += [q.strip() for q in _QUOTED.findall(text)]
        plain = " ".join(_LEGAL.sub(" ", re.sub(r"[«»\"“”]", " ", text)).split())
        out.append(plain)
    return [n for n in dict.fromkeys(out) if len(n) >= 4]


@dataclass
class Elem:
    """An OSM candidate prepared for matching."""

    ref: str
    lat: float
    lon: float
    names: list[str]
    address: Address
    has_address: bool
    marker: bool
    tags: dict[str, str]

    @classmethod
    def from_candidate(cls, d: dict) -> Elem:
        tags = d["tags"]
        names = [tags[k] for k in _NAME_TAGS if tags.get(k)]
        street, house = tags.get("addr:street"), tags.get("addr:housenumber")
        return cls(d["ref"], d["lat"], d["lon"], names, make_address(street or tags.get("addr:place"), house),
                   bool(street or house), bool(CSON_MARK.search(" ".join(names))), tags)

    @property
    def title(self) -> str:
        return self.names[0] if self.names else ""


def _rec_address(rec: GovRecord) -> Address:
    a = rec.address
    return Address(a.get("raw") or "", a.get("street") or "", a.get("house"), a.get("key") or "")


def _name_fits(rec: GovRecord, e: Elem) -> bool:
    """The element's name is this record's: ЦОН-like, the record's district (and №, and 'специализированный') present."""
    if not e.marker:
        return False
    text = " ".join(e.names)
    rd = districts_of(" ".join(rec.names.values()))
    if rd and not rd <= districts_of(text):
        return False
    rn, en = number_of(rec.names.get("ru", rec.name)), number_of(text)
    if rn and en and rn != en:
        return False
    spec = "специализирован" in fold(rec.names.get("ru", ""))
    return not spec or "специализирован" in fold(text) or "спец" in fold(text)


def _district_counts(records: list[GovRecord]) -> Counter:
    """Districts named by ЦОН records; the ps_centers display rows (extra.display) are cross-check material and
    must not make a gov4c district ambiguous, so they are not counted."""
    return Counter(d for r in records if r.kind == "cson" and not r.extra.get("display")
                   for d in districts_of(" ".join(r.names.values())))


def _spread_ok(points: list[tuple[float, float]]) -> bool:
    return all(haversine_m(*points[0], *p) <= AMBIGUOUS_M for p in points[1:])


def _osm_match(rec: GovRecord, elems: list[Elem], dcount: Counter,
               rca: dict | None = None) -> tuple[list[tuple[int, Elem]], str | None]:
    """[(rank, element)] of acceptable candidates and the reason when nothing is acceptable."""
    addr = _rec_address(rec)
    rd = districts_of(" ".join(rec.names.values()))
    out: list[tuple[int, Elem]] = []
    for e in elems:
        addr_ok = same_address_alias(addr, e.address, rca)
        name_ok = _name_fits(rec, e) if rec.kind == "cson" else False
        if addr_ok and name_ok:
            out.append((3, e))
        elif addr_ok and e.marker and rec.kind == "cson":
            out.append((2, e))
        elif addr_ok:
            out.append((1, e))
        elif (rec.kind == "cson" and name_ok and not e.has_address and rd and all(dcount[d] == 1 for d in rd)
              and number_of(" ".join(e.names)) is None):
            out.append((0, e))
    if out:
        return out, None
    if not addr.house:
        return [], "no house number in the register address; no OSM element named for it"
    return [], f"no OSM element with address {addr.street}, {addr.house} (or a ЦОН-named one)"


def geocode_osm(rec: GovRecord, elems: list[Elem], dcount: Counter, fetched_at: str | None = None,
                rca: dict | None = None) -> Geocode:
    cands, why = _osm_match(rec, elems, dcount, rca)
    if not cands:
        return Geocode("unmapped", reason=why)
    best = max(r for r, _ in cands)
    top = [e for r, e in cands if r == best]
    if not _spread_ok([(e.lat, e.lon) for e in top]):
        return Geocode("unmapped", candidates=len(top),
                       reason=f"{len(top)} OSM candidates of rank {best} farther than {int(AMBIGUOUS_M)} m apart: "
                              + ", ".join(e.ref for e in top))
    rec_no = number_of(rec.names.get("ru", rec.name))
    pick = sorted(top, key=lambda e: (not e.marker, bool(rec_no) and number_of(" ".join(e.names)) != rec_no,
                                      e.ref.startswith("node/"), e.ref))[0]
    method = {3: "osm_name_address", 2: "osm_address", 1: "osm_address", 0: "osm_name"}[best]
    return Geocode("matched_osm", pick.lat, pick.lon, method, pick.ref, pick.title or None, None, len(top),
                   license=LICENSE_OSM, fetched_at=fetched_at,
                   reason=None if best >= 2 else ("OSM element with the registry's house number and street; its name "
                                                  "(if any) is not matched" if best == 1
                                                  else "ЦОН-named element without an address tag"))


def _strict_name(variants: list[str], p: dict) -> float:
    """100: equal phonetic skeleton; 90: whole tokens of the shorter name all inside the longer one (one of them with
    4+ letters: «Алау» in «Ледовый дворец Алау»); else 0. Fuzzy ratios are too loose for a name alone («Барыс» ~ «Barista»)."""
    best = 0.0
    pnames = [set(skeleton(n).split()) for n in poi_names(p)]
    for v in variants:
        vt = set(skeleton(v).split())
        for t in filter(None, pnames):
            if vt and vt == t:
                return 100.0
            short, long_ = (vt, t) if len(vt) <= len(t) else (t, vt)
            if short and short <= long_ and any(len(x) >= 4 for x in short):
                best = 90.0
    return best


def geocode_poi(rec: GovRecord, pois: list[dict], rca: dict | None = None) -> Geocode | None:
    """A matching existing POI (see the module docstring), None when there is none; ambiguity -> unmapped."""
    addr = _rec_address(rec)
    variants = venue_names(rec.names)
    found: list[tuple[float, bool, dict]] = []
    for p in pois:
        strict = _strict_name(variants, p)
        loose = max((name_similarity(v, p) for v in variants), default=0.0)
        padr = parse_address(p["address"]) if p.get("address") else None
        if padr and padr.house and addr.house:
            if same_address_alias(addr, padr, rca) and max(strict, loose if loose >= POI_NAME_ADDR else 0.0) > 0:
                found.append((max(strict, loose), True, p))
        elif (strict >= POI_NAME_ONLY and p["category"] in NAME_ONLY_CATEGORIES
              and (padr is None or not padr.key
                   or any(same_street(a, addr.key) for a in _alias_keys(padr.key, rca)))):
            found.append((strict, False, p))
    if not found:
        return None
    strong = [f for f in found if f[1]] or found
    best = max(s for s, _, _ in strong)
    top = [f for f in strong if f[0] >= best - 5]
    sport = [f for f in top if f[2]["category"] == "sport"]
    top = sport or top
    if len({f[2]["id"] for f in top}) > 1 and not _spread_ok([(f[2]["lat"], f[2]["lon"]) for f in top]):
        return Geocode("unmapped", candidates=len(top), reason="several POIs of the dataset share the name: "
                       + ", ".join(f[2]["id"] for f in top))
    sim, with_addr, p = sorted(top, key=lambda f: (-f[0], f[2]["id"]))[0]
    return Geocode("matched_poi", p["lat"], p["lon"], "poi_name_address" if with_addr else "poi_name", p["id"],
                   p["name"], round(sim, 1), len(top))


def _rca_note(rec: GovRecord, streets: dict | None, rca: dict | None) -> str | None:
    """The gazetteer note of an unmapped record: which gazetteers hold its street."""
    if not rec.address.get("key"):
        return None
    parts = []
    if streets is not None:
        known = any(same_street(rec.address["key"], k) for k in streets)
        parts.append("street present in the 2017 OpenAddresses gazetteer" if known
                     else "street absent from the 2017 OpenAddresses gazetteer")
    if rca:
        street = rca_lookup(rec.address["key"], rca)
        parts.append(f"street in the RCA register: {street['ru']} / {street['kk']}" if street
                     else "street not in the RCA register (2026-10 snapshot)")
    return "; ".join(parts) or None


def _alias_keys(key: str, rca: dict | None) -> list[str]:
    """The street key of an address plus the register's current key when the address names the street by a former
    or inflected spelling (the RCA gazetteer's `former` names are indexed in `load_gazetteer`)."""
    if not key:
        return []
    out = [key]
    if rca:
        street = rca_lookup(key, rca)
        if street and street["key"] not in out:
            out.append(street["key"])
    return out


def same_address_alias(addr: Address, other: Address, rca: dict | None) -> bool:
    """`same_address` with the RCA alias layer on either side: the house must still match exactly."""
    if addr.house is None or addr.house != other.house:
        return False
    return any(same_street(k, other.key) for k in _alias_keys(addr.key, rca)) or any(
        same_street(addr.key, k) for k in _alias_keys(other.key, rca))


def geocode_all(records: list[GovRecord], candidates: dict, pois: list[dict], streets: dict | None = None,
                rca: dict | None = None) -> Counter:
    """Set `record.geocode` on every record; returns the counts by status / method. `rca` (collect.gov.rca
    gazetteer, key -> street) lets an address written with a former or inflected street name match the register's
    current spelling, and annotates the unmapped reasons; it has no coordinates and never creates a match alone."""
    elems = [Elem.from_candidate(d) for d in candidates.get("elements", [])]
    failed = {(t["key"], t["house"]) for t in candidates.get("address_targets", []) if t.get("status") != "ok"}
    dcount = _district_counts(records)
    counts: Counter = Counter()
    for rec in records:
        g = geocode_poi(rec, pois, rca) if rec.kind == "sport_facility" else None
        if g is None or g.status == "unmapped":
            osm_g = geocode_osm(rec, elems, dcount, candidates.get("fetched_at"), rca)
            g = osm_g if g is None or osm_g.status != "unmapped" else g
        if g.status == "unmapped" and (rec.address.get("key"), rec.address.get("house")) in failed:
            g.reason = "the OSM address query failed (mirror): this address was NOT checked; " + (g.reason or "")
        if g.status == "unmapped" and (note := _rca_note(rec, streets, rca)):
            g.reason = (g.reason or "") + "; " + note
        rec.geocode = g
        counts[g.status] += 1
        if g.method:
            counts[g.method] += 1
    return counts


# ---- the RCA street layer: aliases + kk forms ----------------------------------------------------------------------


def rca_lookup(key: str, rca: dict) -> dict | None:
    """The register street of a folded street key (a `street_key` of the gazetteer items, or any street text —
    it is folded again): exact key, else a same_street agreement (Джангильдина / Жангильдин)."""
    if not key or not rca:
        return None
    k0 = " ".join(street_key(key).split())
    if k0 in rca:
        return rca[k0]
    for k, street in rca.items():
        if same_street(k0, k):
            return street
    return None




def rca_address_kk(address: Address, rca: dict | None) -> str | None:
    """The kk spelling of the address's street when exactly one register street agrees with its key: «Тұран
    даңғылы» for «Проспект Туран, 22». None when the street is ambiguous in the register or absent."""
    if rca is None or not address.key:
        return None
    k0 = " ".join(street_key(address.key).split())
    agreeing = {k: s for k, s in rca.items() if k == k0 or same_street(k0, k)}
    if len(agreeing) != 1:
        return None
    street = next(iter(agreeing.values()))
    kk = street["kk"]
    return kk if kk and " ".join(street_key(kk).split()) == street["key"] else None

