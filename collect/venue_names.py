"""What a venue's name says: its identity words, its kind (museum / mosque / park ...) and its descriptors.

Shared by the duplicate merge (`collect.dedupe`) and the Wikivoyage join (`collect.wikivoyage.join`). Names come in
ru / kk / en / tr / it / pl and are compared after the transliteration of `collect.names` (`skeleton`), so «Ататюрк»,
«Ататүрік» and «Atatürk» meet. A name is split into

* **type words** - the kind of venue: «музей», «мұражай», «müzesi», «Museum» all are `museum`. They say nothing about
  *which* museum, so they never count as shared identity (two different mosques are both «мечеть»);
* **boilerplate** - the country, the city, the status («Республика Казахстан», «Астана», «Национальный»);
* **descriptors** - words that describe a venue instead of naming it («Центральная», «Historical», «Grand»), mapped to
  one concept across languages, so «Әскери-тарихи» = «Военно-исторический» = «Military History»;
* **identity words** - everything else (and the digits: «Евразия-2» is not «Евразия-3»).

Prefix lists below are compared against `skeleton()` of a word, which is why they look phonetic.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from rapidfuzz import fuzz

from collect.names import skeleton

# kind -> words (a prefix of the word, or the whole word when it starts with "="), in natural spelling; each is run
# through `skeleton()` when this module loads, so «мечеть», «mosque» and «meczet» compile like the names they match
TYPE_WORDS: dict[str, tuple[str, ...]] = {
    "museum": ("музей", "мұражай", "museum", "museo", "muzeum", "müzesi", "müze", "muzej", "musée"),
    "mosque": ("мечет", "мешіт", "mosque", "moschea", "meczet", "camii", "mescit", "masjid"),
    "cathedral": ("собор", "cathedral", "cattedrale", "katedr", "кафедраль", "кафедрал"),
    "church": ("храм", "церков", "church", "chiesa", "kościół", "kostel", "шіркеу", "=temple", "приход", "parish"),
    "synagogue": ("синагог", "synagog"),
    "monument": ("памятник", "ескерткіш", "monument", "pomnik", "heykel", "statue", "стела", "stella", "обелиск",
                 "obelisk"),
    "park": ("=парк", "=park", "parco", "parku", "parque", "саябақ", "саябағ", "=сквер", "=square", "=сад",
             "=garden", "=gardens"),
    "library": ("библиотек", "biblioteca", "library", "кітапхана", "kitapkhana", "kütüphane"),
    "theatre": ("театр", "theatre", "theater", "teatro", "=опера", "=opera"),
    "cinema": ("кинотеатр", "cinema", "=кино", "=cinemas"),
    "centre": ("=центр", "=center", "=centre", "=centro", "=zentrum"),
    "mall": ("=mall", "=тц", "=ттц", "=трц", "=трк", "=тд", "=тк", "торгов", "=рынок", "=market", "=базар",
             "=bazaar", "=bazar"),
}
# kinds whose building is one venue: two records of such a kind a few metres apart are the same place of worship
WORSHIP = {"mosque": "mosque", "synagogue": "synagogue", "cathedral": "christian", "church": "christian"}

# descriptors: concept -> word prefixes. `IDENTITY_CONCEPTS` still tell venues apart («Military museum» is not
# «Museum of the First President»); the others only describe.
CONCEPT_WORDS: dict[str, tuple[str, ...]] = {
    "military": ("воен", "әскери", "military", "militare", "wojsk", "armed"),
    "historical": ("историч", "тарихи", "tarihi", "history", "historic", "storic", "hystor"),
    "national": ("национальн", "ұлттық", "national", "nazional", "narodow"),
    "state": ("государствен", "мемлекеттік", "state", "statal", "państwow"),
    "central": ("центральн", "орталық", "central"),
    "grand": ("=grand", "больш", "велик", "great", "velik", "wielki", "=ulu", "=бас"),
    "old": ("старый", "старая", "=old", "eski"),
    "city": ("городск", "=city", "=capital", "столичн"),
}
IDENTITY_CONCEPTS = frozenset({"military"})
DESCRIPTOR_CONCEPTS = frozenset(CONCEPT_WORDS) - IDENTITY_CONCEPTS
# descriptors that every venue of its kind could carry; «central», «grand», «old», «city» single one out
WEAK_DESCRIPTORS = frozenset({"c:historical", "c:national", "c:state"})


def _compile(table: dict[str, tuple[str, ...]]) -> list[tuple[str, bool, str]]:
    out = []
    for key, words in table.items():
        for w in words:
            exact = w.startswith("=")
            out.append((key, exact, skeleton(w.lstrip("="))))
    return out


_TYPES = _compile(TYPE_WORDS)
_CONCEPTS = _compile(CONCEPT_WORDS)

# country / city / status words (the same set the Wikivoyage join always used)
_BOILERPLATE_WORDS = (
    "republic republika republiki respublika respublikasy respublikasynyn республика республики республикасының "
    "repubblica "
    "kazakhstan kazakistan kazachstan kazachstanu kazakhstani казахстан казахстана қазақстан "
    "astana астана of the di del della delle degli dei and"
).split()
BOILERPLATE = frozenset(skeleton(w) for w in _BOILERPLATE_WORDS)

_SPLIT = re.compile(r"[^\w]+|(?<=\d)(?=[^\W\d_])|(?<=[^\W\d_])(?=\d)|_", re.UNICODE)
_ADDRESS_NOISE = re.compile(r"[^\w]+|_", re.UNICODE)


def _lookup(table: list[tuple[str, bool, str]], sk: str) -> str | None:
    for key, exact, stem in table:
        if (sk == stem) if exact else sk.startswith(stem):
            return key
    return None


def _kind_of(sk: str) -> str | None:
    return _lookup(_TYPES, sk)


def _concept_of(sk: str) -> str | None:
    return _lookup(_CONCEPTS, sk)


@dataclass(frozen=True)
class NameParts:
    words: frozenset[str]  # identity words (skeletons) and concept tags «c:military»
    kinds: frozenset[str]  # venue kinds named («museum»)
    nums: frozenset[str]  # digits
    descriptors: frozenset[str]  # «c:national»: describe the venue, do not name it

    @property
    def identity(self) -> frozenset[str]:
        return self.words

    @property
    def descriptive_only(self) -> bool:
        """The name only says what kind of venue it is («Historical Museum Astana», «Национальный музей»): no
        identity word, no number, and no descriptor that picks one venue out («Central», «Old», «Grand»)."""
        return self.kind_only and self.descriptors <= WEAK_DESCRIPTORS

    @property
    def kind_only(self) -> bool:
        """No identity word and no number, whatever descriptors there are («Центральная мечеть»)."""
        return not self.words and not self.nums and bool(self.kinds)

    @property
    def all_words(self) -> frozenset[str]:
        return self.words | self.descriptors


def parse(name: str) -> NameParts:
    words: set[str] = set()
    kinds: set[str] = set()
    nums: set[str] = set()
    descriptors: set[str] = set()
    for raw in _SPLIT.split(name or ""):
        if not raw:
            continue
        if raw.isdigit():
            nums.add(raw.lstrip("0") or "0")
            continue
        sk = skeleton(raw)
        if not sk:
            continue
        if (kind := _kind_of(sk)) is not None:
            kinds.add(kind)
            continue
        if sk in BOILERPLATE:
            continue
        if (concept := _concept_of(sk)) is not None:
            (words if concept in IDENTITY_CONCEPTS else descriptors).add(f"c:{concept}")
            continue
        if len(sk) >= 3:
            words.add(sk)
    return NameParts(frozenset(words), frozenset(kinds), frozenset(nums), frozenset(descriptors))


def word_equal(a: str, b: str) -> bool:
    """Two words of the same name part: equal, or a spelling / declension variant of one another."""
    if a == b:
        return True
    if a.startswith("c:") or b.startswith("c:"):
        return False
    short, long_ = sorted((len(a), len(b)))
    if short < 4 or long_ - short > 2:  # «султан» is not «нурсултан»
        return False
    ratio = fuzz.ratio(a, b)
    return ratio >= 80 or (ratio >= 75 and a[:3] == b[:3])


def _uncovered(a: frozenset[str], b: frozenset[str]) -> list[str]:
    return [x for x in a if not any(word_equal(x, y) for y in b)]


def _covered(a: frozenset[str], b: frozenset[str]) -> bool:
    """Every word of `a` is in `b` - or all but one short word that nearly is («вей» / «way»), when two words agree."""
    missing = _uncovered(a, b)
    if not missing:
        return True
    if len(missing) > 1 or len(a) - 1 < 2:
        return False
    word = missing[0]
    return len(word) <= 4 and not word.startswith("c:") and max(fuzz.ratio(word, y) for y in b) >= 60


def same_name(a: NameParts, b: NameParts) -> bool:
    """True when both names speak of one venue: same numbers, and every word of the shorter name is in the longer
    (a word each side lacks - «Зенит» vs «Союз» - means two venues). At least one identity word must be shared:
    a common kind («музей») or a common descriptor («национальный») is not enough."""
    if a.nums != b.nums:
        return False
    wa, wb = a.all_words, b.all_words
    if not a.words or not b.words:
        return False
    shared = any(word_equal(x, y) for x in a.words for y in b.words)
    if shared and (_covered(wa, wb) or _covered(wb, wa)):
        return True
    # «Ата Тюрк» / «Ататюрк»: one name split in two words, the other not
    if min(len(a.words), len(b.words)) == 1 and max(len(a.words), len(b.words)) <= 2:
        ja, jb = "".join(sorted(a.words)), "".join(sorted(b.words))
        return len(ja) >= 5 and len(jb) >= 5 and fuzz.ratio(ja, jb) >= 85
    return False


def kind_only_equal(a: NameParts, b: NameParts) -> bool:
    """Both names only say what the venue is and say the same («Национальный музей Республики Казахстан» and
    «Muzeum Narodowe Republiki Kazachstanu»): the official name of such a venue is its kind plus its descriptors."""
    return a.kind_only and b.kind_only and a.kinds == b.kinds and a.descriptors == b.descriptors


def is_kind_word(word: str) -> bool:
    """True when the word names a kind of venue («музей», «mosque»)."""
    return _kind_of(skeleton(word)) is not None


def same_name_any(names_a: list[str], names_b: list[str]) -> bool:
    pa = [parse(n) for n in names_a if n]
    pb = [parse(n) for n in names_b if n]
    return any(same_name(x, y) for x in pa for y in pb)


def kinds_of(names: list[str]) -> frozenset[str]:
    return frozenset(k for n in names if n for k in parse(n).kinds)


def address_key(address: str | None) -> str | None:
    """A comparable form of a street address with a house number («Астана, проспект Республики 2» and
    «Астана, проспект Республики, 2»); None when there is no number, or the address is only the city."""
    if not address:
        return None
    parts = [skeleton(t) for t in _ADDRESS_NOISE.split(address) if t]
    parts = [p for p in parts if p and p not in BOILERPLATE]
    if not parts or not any(re.search(r"\d", p) for p in parts):
        return None
    return " ".join(sorted(parts))
