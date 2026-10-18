"""Does an official-site domain speak for a POI? The rule that keeps a chain's branch list from describing the
place the branch stands in (a Coffee BOOM inside the mall 'Mega Silk Way' is not the mall).

A site's facts may be attached to a POI only when

  * **brand agreement**: the POI's own website is on the domain, or the domain's brand (the first label of the
    domain: `coffeeboom.kz` -> "coffeeboom", `kfc-kazakhstan.kz` -> "kfc") is in the POI's name / brand keys
    (`names.name_key`: transliterated, spelling variants folded), or in the brand of its own website; and
  * **category compatibility**: the POI's category is one the domain's own POIs have; food places (cafe, restaurant,
    fast food, bar) are compatible with each other. A domain that has no POI of its own says nothing against a
    category.

Proximity alone (a branch 20 m from a POI with a similar name) never qualifies: the branch lists its address, not its
host. `collect.sites.join` applies the rule to every match; `collect.sites.verify.check_dataset` re-checks the
shipped dataset with the same functions.
"""

from __future__ import annotations

import re
from collections import defaultdict
from collections.abc import Iterable

from collect.names import is_generic_name, name_key
from collect.sites.domains import poi_domains

FOOD = frozenset({"cafe", "restaurant", "fast_food", "bar_nightlife"})
MIN_KEY = 3  # shorter keys ("im", "nu") are too ambiguous to prove a brand
SUBSTRING_KEY = 5  # a domain key this long may sit inside a longer POI name ("edagoroda" in "Гриль-бар «ЕдаГорода»")


def domain_keys(domain: str) -> set[str]:
    """Brand keys of a domain: its first label and the first word of that label ('kfc-kazakhstan' -> 'kfc')."""
    label = domain.lower().split(".")[0]
    if not label or is_generic_name(label.replace("-", " ")):
        return set()
    keys = {name_key(label), name_key(re.split(r"[-_]", label)[0])}
    return {k for k in keys if len(k) >= MIN_KEY}


def poi_keys(p: dict) -> set[str]:
    """Name / brand keys of a POI, plus the brand keys of the domains of its own website."""
    names = [p.get("name"), *(p.get("names") or {}).values(), p.get("brand")]
    keys = {name_key(n) for n in names if n}
    for d in poi_domains(p):
        keys |= domain_keys(d)
    return {k for k in keys if len(k) >= MIN_KEY}


def _keys_agree(domain_side: set[str], other: set[str]) -> bool:
    return any(a == b or a.startswith(b) or b.startswith(a) or (len(a) >= SUBSTRING_KEY and a in b)
               for a in domain_side for b in other)


def brand_agrees(domain: str, p: dict) -> bool:
    return domain in poi_domains(p) or _keys_agree(domain_keys(domain), poi_keys(p))


def same_brand(domain: str, other: str) -> bool:
    """Two domains of one brand: `kfc.kz` / `kfc-kazakhstan.kz`, `chabad.kz` / `chabadkz.org`."""
    return domain == other or _keys_agree(domain_keys(domain), domain_keys(other))


def own_categories(pois: Iterable[dict]) -> dict[str, set[str]]:
    """brand key -> categories of the POIs whose own website carries that brand key."""
    out: dict[str, set[str]] = defaultdict(set)
    for p in pois:
        for d in poi_domains(p):
            for k in domain_keys(d):
                out[k].add(p["category"])
    return out


def category_ok(domain: str, category: str, cats: dict[str, set[str]]) -> bool:
    own = set().union(*(cats.get(k, set()) for k in domain_keys(domain)))
    if not own or category in own:
        return True
    return category in FOOD and own <= FOOD


def speaks_for(domain: str, p: dict, cats: dict[str, set[str]]) -> bool:
    """True when the domain's facts may be attached to POI `p` (brand agreement and category compatibility)."""
    return brand_agrees(domain, p) and category_ok(domain, p["category"], cats)
