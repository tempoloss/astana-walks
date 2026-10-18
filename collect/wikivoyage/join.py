"""Join Wikivoyage listings to dataset POIs: by Wikidata id first, then by coordinates (<= 150 m) with a name gate.

The name gate exists because a 150 m radius around a landmark is full of tenants (a cafe inside the Khan Shatyr
tent, a bar in the Palace of Independence). Rules, in order:

* `wdid` - the listing carries a Wikidata id and a POI of the dataset carries the same one: always the same object.
* `name` - name score >= 60 (`collect.names.name_score`, transliteration-insensitive) and within 150 m, and still >= 60
  once the boilerplate words are dropped from both sides («Республика Казахстан», «Национальный», «Государственный»,
  city names: `_BOILERPLATE_WORDS`). The token rule below ignores them too: two names that share only such words
  are not a pair.
* `coords+name` - a see/do listing and a POI of a compatible category within 40 m whose names share at least one
  content token (the alt/native name of the listing counts; `collect.names.skeleton` romanises both sides). This
  accepts translated pairs («Museo storico delle Forze Armate» -> «Государственный военно-исторический музей»: the kk
  names share «әскери-тарихи») that a plain score cut-off loses, and drops tenants (`Chan Szatyr` listing 3 m from
  the «Gold Mine Coaster» ride: no shared token, dropped). A shared token must name the venue: not a kind («mosque»,
  «museum»), not boilerplate, and not a word that venues of two or more other categories carry too (`expo`: a pub, a
  cafe and a hall carry it - it names the area, so «Expo 2017 buildings» is not the «SML EXPO Energy Hall»).
* `kind+near`   - a listing that only says what it is («Центральная мечеть», «Grand Mosque of Astana») and a POI of
  that kind within 40 m: the kind and the distance are the whole evidence, a shared word «мечеть» alone is not.
* a listing and a POI that carry different Wikidata ids are different venues, whatever the names say.
* eat/drink listings need the plain name score: eatery names are rarely translated, so a low score is a different
  venue nearby, not a translation.

Every radius pair is logged (`joined["radius_pairs"]`) for a human check; the log row records which rule accepted it.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from collect import venue_names as vn
from collect.names import name_score, skeleton
from collect.overpass_poi import haversine_m
from collect.wikivoyage.editions import Listing

MAX_RADIUS_M = 150.0
NAME_SCORE = 60.0
NEAR_RADIUS_M = 40.0
NEAR_MIN_TOKEN = 4  # a content token is at least this long after skeleton()

SEE_CATEGORIES = frozenset({
    "attraction_landmark", "museum_gallery", "park_garden", "sport", "culture_theatre_cinema",
    "coworking_library", "viewpoint", "mall",
})

_TOKEN = re.compile(r"[^\w]+", re.UNICODE)
_MIN_TOKEN = 3

# the rules, as they are recorded in the join log
RULES = {
    "wdid": "listing wikidata id = poi wikidata_id",
    "name": "name_score >= 60 within 150 m",
    "coords+name": "see/do listing, category-compatible poi within 40 m sharing a name token",
    "kind+near": "a listing that names only a kind of venue, a poi of that kind within 40 m",
    "false_pair_rule": "eat/drink listings need the name score; see/do pairs under 60 need <= 40 m, a see-family "
                       "category and a shared name token that names the venue (not a kind word, not boilerplate, "
                       "not a word venues of >= 2 other categories carry); different wikidata ids are never a pair",
}


@dataclass
class Pair:
    listing: Listing
    poi_id: str
    rule: str  # wdid | name | coords+name | kind+near
    distance_m: float
    score: float


# Words that name the country, the state, the city or the status of an institution rather than the place itself
# («Республика Казахстан», «Национальный», «Государственный», «Астана»). Two names that share only these are not the
# same object: the National Archives of the Republic of Kazakhstan are not the National Academic Library of it.
_BOILERPLATE_WORDS = (
    "republic republika republiki respublika respublikasy respublikasynyn республика республики республикасының "
    "repubblica "
    "kazakhstan kazakistan kazachstan kazachstanu kazakhstani казахстан казахстана қазақстан "
    "national nazionale narodowe narodowy национальный национальная национальное национального ұлттық "
    "state statale panstwowy państwowy государственный государственная государственное мемлекеттік "
    "astana астана"
).split()
_BOILERPLATE = frozenset(skeleton(w) for w in _BOILERPLATE_WORDS)


def _content(name: str) -> str:
    """The name without its boilerplate and kind words ('' when nothing distinctive is left)."""
    return " ".join(t for t in _TOKEN.split(name or "")
                    if t and skeleton(t) not in _BOILERPLATE and not vn.is_kind_word(t))


def _tokens(names: list[str], area_word=lambda tok: False) -> set[str]:
    out = set()
    for n in names:
        for t in _TOKEN.split(n or ""):
            s = skeleton(t)
            if (len(t) >= _MIN_TOKEN and len(s) >= NEAR_MIN_TOKEN - 1 and s not in _BOILERPLATE
                    and not vn.is_kind_word(t) and not area_word(s)):
                out.add(s)
    return out


def poi_names(p: dict) -> list[str]:
    """The names a POI answers to: its own, its languages, and those of the records merged into it."""
    return [p["name"], *p.get("names", {}).values(), *p.get("alt_names", [])]


def token_overlap(l: Listing, poi: dict, area_word=lambda tok: False) -> bool:
    """True when a content token of the listing (name or native alt name) is a token of the POI's names."""
    a = _tokens([l.name, l.alt], area_word)
    b = _tokens(poi_names(poi), area_word)
    return bool(a & b)


class Joiner:
    def __init__(self, pois: list[dict]):
        self.by_wdid = {p["wikidata_id"]: p for p in pois if p.get("wikidata_id")}
        self.pois = pois
        self._grid: dict[tuple[int, int], list[dict]] = {}
        # token -> categories whose POIs carry it: a word that venues of several categories carry names an area
        self._token_categories: dict[str, set[str]] = {}
        for p in pois:
            # a venue merged from several records (`collect.dedupe`) stands at each of their points
            for lat, lon in [(p["lat"], p["lon"]), *((m["lat"], m["lon"]) for m in p.get("merged_from") or ())]:
                self._grid.setdefault((round(lat / 0.005), round(lon / 0.005)), []).append((lat, lon, p))
            for tok in _tokens(poi_names(p)):
                self._token_categories.setdefault(tok, set()).add(p["category"])

    def near(self, lat: float, lon: float) -> list[tuple[float, dict]]:
        nearest: dict[str, tuple[float, dict]] = {}
        kx, ky = round(lat / 0.005), round(lon / 0.005)
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                for plat, plon, p in self._grid.get((kx + dx, ky + dy), []):
                    d = haversine_m(lat, lon, plat, plon)
                    if d <= MAX_RADIUS_M and (p["id"] not in nearest or d < nearest[p["id"]][0]):
                        nearest[p["id"]] = (d, p)
        return sorted(nearest.values(), key=lambda t: (t[0], t[1]["id"]))

    @staticmethod
    def _score(l: Listing, p: dict) -> float:
        """The plain name score of listing and POI, or 0 when it does not survive without boilerplate and kind words:
        a pair that matches only on «Республика Казахстан» / «Национальный» / «мечеть» / the city name is no pair.
        Two names that are nothing but a kind and its descriptors («Национальный музей Республики Казахстан» /
        «Muzeum Narodowe Republiki Kazachstanu») are the same name when kind and descriptors agree."""
        listing_names = [l.name, l.alt]
        theirs_names = poi_names(p)
        score = name_score(listing_names, theirs_names)
        if score < NAME_SCORE:
            return score
        content = name_score([_content(n) for n in listing_names], [_content(n) for n in theirs_names])
        if content >= NAME_SCORE:
            return score
        mine = [vn.parse(n) for n in listing_names if n]
        theirs = [vn.parse(n) for n in theirs_names if n]
        return score if any(vn.kind_only_equal(x, y) for x in mine for y in theirs) else 0.0

    def _area_word(self, category: str):
        return lambda tok: len(self._token_categories.get(tok, set()) - {category}) >= 2

    @staticmethod
    def _other_entity(l: Listing, p: dict) -> bool:
        """The listing and the POI carry different Wikidata ids: not the same venue, whatever the names say."""
        return bool(l.wikidata and p.get("wikidata_id") and l.wikidata != p["wikidata_id"])

    def best(self, l: Listing) -> Pair | None:
        if l.wikidata and (poi := self.by_wdid.get(l.wikidata)):
            return Pair(l, poi["id"], "wdid", 0.0, 100.0)
        if l.lat is None:
            return None
        nearby = [(d, p) for d, p in self.near(l.lat, l.lon) if not self._other_entity(l, p)]
        best: tuple[float, dict, float] | None = None
        for d, p in nearby:
            score = self._score(l, p)
            if score >= NAME_SCORE and (best is None or score > best[2]):
                best = (d, p, score)
        if best:
            d, p, score = best
            return Pair(l, p["id"], "name", round(d, 1), round(score))
        if l.section != "see":
            return None
        # low score is expected for translated names; keep only a close, category-compatible, token-sharing pair
        for d, p in nearby:
            if d > NEAR_RADIUS_M or p["category"] not in SEE_CATEGORIES:
                continue
            if token_overlap(l, p, self._area_word(p["category"])):
                return Pair(l, p["id"], "coords+name", round(d, 1), round(self._score(l, p)))
        # a listing that only says what it is («Центральная мечеть») and a POI of that kind next to it
        kinds = {k for n in (l.name, l.alt) if n for k in vn.parse(n).kinds if vn.parse(n).kind_only}
        if kinds:
            for d, p in nearby:
                if d <= NEAR_RADIUS_M and p["category"] in SEE_CATEGORIES and kinds & vn.kinds_of(
                        poi_names(p)):
                    return Pair(l, p["id"], "kind+near", round(d, 1), round(self._score(l, p)))
        return None
