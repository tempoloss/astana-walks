"""Join an event venue to a POI of `data/poi.enriched.json`.

The discipline is the one of `collect.sites.agree`: proximity alone never qualifies. A venue is joined to a POI only when

  * **name agreement**: a name key of the venue (`names.name_key`: transliterated, spelling variants folded; the
    «(…)» alias, the type suffix «, кинотеатр в городе Астана» and the venue as a whole are all tried) equals a name /
    brand key of the POI, or one contains the other (both >= 6 characters: «Хан Шатыр» inside «Chaplin Khan Shatyr»);
    several agreeing POIs are told apart by the address (same street and house), then by the page coordinates
    (nearest within 300 m with a clear margin), otherwise the venue stays unjoined; a POI more than 800 m from the
    coordinates the page itself gives is rejected (a branch of the same brand); or
  * **address agreement** (`match: "address"`, the venue name says nothing): exactly one POI of a venue-like category
    stands at the very same street + house number.

An unjoined venue keeps its address and gets no coordinates unless its own page gave them.
"""

from __future__ import annotations

import math
import re

from rapidfuzz import fuzz

from collect.names import is_generic_name, name_key, skeleton


def skeleton_tokens(text: str) -> set[str]:
    """Phonetic word skeletons of a title (generic venue-type words dropped) for cross-language title agreement."""
    return {t for t in skeleton(text).split() if len(t) >= 2}


ADDRESS_CATEGORIES = frozenset({
    "culture_theatre_cinema", "museum_gallery", "sport", "mall", "entertainment", "attraction_landmark",
    "park_garden", "coworking_library",
})
MIN_EQUAL, MIN_CONTAIN = 4, 6
FAR_M, NEAR_M = 800.0, 300.0
STREET_RATIO = 85

_SUFFIX = re.compile(r",?\s*(?:кинотеатр\s+)?в\s+городе\s+\S+\s*$", re.IGNORECASE)
_PAREN = re.compile(r"\(([^()]*)\)")
_STREET_WORDS = re.compile(
    r"\b(?:ул|улица|пр|просп|проспект|пр-т|шоссе|ш|мкр|микрорайон|к|көш|көшесі|даңғылы|даңғ|бульвар|б-р|наб|"
    r"набережная|пер|переулок|площадь|пл|тракт|район|г|город|астана|қаласы)\b\.?", re.IGNORECASE)
_HOUSE = re.compile(r"(?:^|[\s,])(\d+[а-яa-z]?(?:/\d+[а-яa-z]?)?)(?=[\s,]|$)", re.IGNORECASE)


def name_variants(name: str) -> list[str]:
    """The venue name as a whole, without the city-type suffix, and each «(alias)» on its own."""
    base = _SUFFIX.sub("", name or "").strip()
    variants = [base, *(m[1].strip() for m in _PAREN.finditer(base)), _PAREN.sub("", base).strip()]
    return [v for v in dict.fromkeys(variants) if v]


Key = tuple[str, ...]  # the words of a name, each through `name_key`
_WORD = re.compile(r"[^\W_]+")
# words that only say what kind of place it is: a name made of them alone identifies nothing
TYPE_WORDS = frozenset(name_key(w) for w in (
    "bar", "pub", "grill", "cafe", "coffee", "restaurant", "lounge", "club", "pizza", "burger", "sushi", "shop",
    "бар", "паб", "гриль", "кафе", "кофе", "кофейня", "ресторан", "клуб", "пицца", "пиццерия", "суши", "бургер",
    "шаурма", "столовая", "магазин", "музей", "театр", "кинотеатр", "парк", "центр", "дворец", "мечеть",
    "галерея", "арена", "зал", "библиотека",
))


def name_key_words(name: str) -> Key:
    return tuple(k for w in _WORD.findall(name or "") if (k := name_key(w)))


def venue_keys(name: str) -> set[Key]:
    keys: set[Key] = set()
    for v in name_variants(name):
        if is_generic_name(v):
            continue
        k = name_key_words(v)
        if len("".join(k)) >= MIN_EQUAL:
            keys.add(k)
    return keys


def poi_name_keys(p: dict) -> set[Key]:
    names = [p.get("name"), *(p.get("names") or {}).values(), p.get("brand")]
    return {k for n in names if n and not is_generic_name(n) and len("".join(k := name_key_words(n))) >= MIN_EQUAL}


def _inside(short: Key, long_: Key) -> bool:
    """`short` spells a run of whole words of `long_` (the word breaks may differ: «The Bus» / «TheBus»)."""
    target = "".join(short)
    return any("".join(long_[i:j]) == target for i in range(len(long_)) for j in range(i + 1, len(long_) + 1))


def keys_agree(a: set[Key], b: set[Key]) -> bool:
    """Equal names (spelling variants folded), or the shorter name is a run of whole words of the longer one
    («Хан Шатыр» in «Chaplin Khan Shatyr»; «Централ» is not in «Центральная мечеть») and is not made of type words."""
    for x in a:
        for y in b:
            if "".join(x) == "".join(y):
                return True
            short, long_ = sorted((x, y), key=lambda k: len("".join(k)))
            if len("".join(short)) >= MIN_CONTAIN and not all(w in TYPE_WORDS for w in short) and _inside(short, long_):
                return True
    return False


def address_key(address: str | None) -> tuple[str, str] | None:
    """(street key, house) of a free-text address; None when it has no house number or no street."""
    if not address:
        return None
    text = _STREET_WORDS.sub(" ", address.casefold())
    m = _HOUSE.search(text)
    if not m:
        return None
    street = name_key(text[: m.start()])
    return (street, m[1].casefold()) if len(street) >= 3 else None


def addresses_agree(a: tuple[str, str] | None, b: tuple[str, str] | None) -> bool:
    """Same house and the same street (spelling variants «Республики» / «Республика», «батыра» / «батыр» tolerated)."""
    if not a or not b or a[1] != b[1]:
        return False
    return a[0] == b[0] or (min(len(a[0]), len(b[0])) >= 6 and fuzz.ratio(a[0], b[0]) >= STREET_RATIO)


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = p2 - p1, math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * 6371000.0 * math.asin(math.sqrt(a))


class VenueIndex:
    def __init__(self, pois: list[dict]):
        self.pois = [p for p in pois if p.get("lat") is not None and p.get("lon") is not None]
        self._keys = [poi_name_keys(p) for p in self.pois]
        self._by_house: dict[str, list[tuple[tuple[str, str], int]]] = {}
        for i, p in enumerate(self.pois):
            if (ak := address_key(p.get("address"))):
                self._by_house.setdefault(ak[1], []).append((ak, i))

    def _at(self, ak: tuple[str, str]) -> list[int]:
        return [i for other, i in self._by_house.get(ak[1], []) if addresses_agree(ak, other)]

    def by_id(self, poi_id: str) -> dict | None:
        """The POI with this id; for an id that `collect.dedupe` merged into another record, the absorbed record as it
        was (name, names, coordinates, address), so a join made before the merge still verifies."""
        hit = next((p for p in self.pois if p["id"] == poi_id), None)
        if hit is not None:
            return hit
        for p in self.pois:
            for m in p.get("merged_from") or ():
                if m["id"] == poi_id:
                    return {"id": m["id"], "name": m["name"], "names": m.get("names") or {},
                            "category": m["category"], "lat": m["lat"], "lon": m["lon"], "address": m.get("address"),
                            "merged_into": p["id"]}
        return None

    def join(self, name: str, address: str | None, lat: float | None = None, lon: float | None = None) -> dict | None:
        """{"poi": POI dict, "via": "name" | "address"} or None."""
        vkeys = venue_keys(name)
        cands = [i for i, k in enumerate(self._keys) if vkeys and keys_agree(vkeys, k)]
        if lat is not None:
            cands = [i for i in cands if haversine_m(lat, lon, self.pois[i]["lat"], self.pois[i]["lon"]) <= FAR_M]
        ak = address_key(address)
        if cands:
            pick = self._pick(cands, ak, lat, lon)
            return {"poi": self.pois[pick], "via": "name"} if pick is not None else None
        if ak:
            same = [i for i in self._at(ak) if self.pois[i]["category"] in ADDRESS_CATEGORIES]
            if lat is not None:
                same = [i for i in same if haversine_m(lat, lon, self.pois[i]["lat"], self.pois[i]["lon"]) <= NEAR_M]
            if len(same) == 1:
                return {"poi": self.pois[same[0]], "via": "address"}
        return None

    def _pick(self, cands: list[int], ak: tuple[str, str] | None, lat: float | None, lon: float | None) -> int | None:
        if len(cands) == 1:
            return cands[0]
        if ak:
            same = [i for i in cands if addresses_agree(address_key(self.pois[i].get("address")), ak)]
            if len(same) == 1:
                return same[0]
            house = [i for i in cands if (pk := address_key(self.pois[i].get("address"))) and pk[1] == ak[1]]
            if len(house) == 1:  # the same house number where the other candidates give no address
                return house[0]
        if lat is not None:
            ranked = sorted(cands, key=lambda i: haversine_m(lat, lon, self.pois[i]["lat"], self.pois[i]["lon"]))
            d = [haversine_m(lat, lon, self.pois[i]["lat"], self.pois[i]["lon"]) for i in ranked]
            if d[0] <= NEAR_M and d[1] > 2 * d[0] + 50:
                return ranked[0]
        return None


def apply_join(event: dict, index: VenueIndex) -> bool:
    """Fill `venue.poi_id/poi_name/match` and, when the page gave no coordinates, the POI's. True when joined."""
    v = event["venue"]
    v.update(poi_id=None, poi_name=None, match=None)
    if v.get("coords_source") == "poi":
        v.update(lat=None, lon=None, coords_source=None)
    hit = index.join(v["name"], v.get("address"), v.get("lat"), v.get("lon"))
    if hit is None:
        return False
    poi = hit["poi"]
    v.update(poi_id=poi["id"], poi_name=poi["name"], match=hit["via"])
    if v.get("lat") is None:
        v.update(lat=poi["lat"], lon=poi["lon"], coords_source="poi")
    return True
