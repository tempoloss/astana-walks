"""Matching of free text against walks.lexicon_concepts / lexicon_data: normalisation, stems, typos, negation, language.

    m = match("кде паесть дешево и быстра")
    m.has("eat_generic"), m.has("cheap"), m.has("fast")   # True, True, True (the first one through a typo)

Steps: lowercase, ё→е, kazakh letters → their russian look-alikes (so «қайда» and «кайда» are the same word),
hyphens → spaces; the text is cut into clauses at punctuation and «но / а / but»; in every clause a stem matches
a word (prefix) or consecutive words. A word that matched nothing is compared with every stem of 4+ letters
through rapidfuzz (`partial_ratio` ≥ 85 aligned at the word start, or one edit for stems of 5+ letters), so
«паесть» finds «поесть». A hit with a negator («не», «без», «no», «without») within two words before it - or a
kk «емес» right after it - is negated: «без алкоголя» and «не хочу фастфуд» never add bars / fast food.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from functools import cache

from rapidfuzz import fuzz
from rapidfuzz.distance import OSA

from .lexicon_concepts import CONCEPTS
from .lexicon_data import (
    ANTONYM_PAIRS,
    DETERMINERS,
    DIRECT_PLACES,
    INFO_QUESTIONS,
    JOINS,
    KK_AMBIGUOUS,
    KK_BAR_JOINERS,
    KK_POSSESSIVE_ENDINGS,
    KK_POSTPOSITIONS,
    KK_QUESTION,
    KK_VISITED_AFTER,
    LANDMARK_ALIASES,
    LOCATIVE_BEFORE,
    NAME_LINKS,
    NEGATION_VOID,
    NEGATORS,
    PLACE_WORDS,
    POSTFIX_NEGATORS,
    VISITED_BEFORE,
    Concept,
)
from .safety import clean_text

FUZZY_RATIO = 85  # rapidfuzz ratio of the word's start and the stem that counts as a typo
# Shorter stems are matched exactly only: at 4-5 letters one edit lands on another ordinary word («келеди» ~ «кегл»).
FUZZY_MIN_STEM = 6
NEGATION_WINDOW = 2  # words before a hit in which a negator counts
_MAX_EXACT_LEN = 3  # a stem this short matches the whole word only
_KK_WITHOUT = ("сиз", "сыз")  # kk suffix «-сіз / -сыз»: «without»
_MIN_WITHOUT_LEN = 6
_ABLATIVE = (
    "дан",
    "ден",
    "тан",
    "тен",
    "нан",
    "нен",
)  # kk «-дан / -тен»: «from» (normalised letters)

_LETTERS = str.maketrans(
    {
        "ё": "е", "ә": "а", "ғ": "г", "қ": "к", "ң": "н", "ө": "о", "ұ": "у", "ү": "у", "һ": "х",
        "і": "и", "é": "e", "ö": "o", "ü": "u", "ç": "c", "ı": "i", "’": "", "'": "", "`": "",
    }
)  # fmt: skip
_KK_SPECIAL = re.compile(r"[әіңғүұқөһӘІҢҒҮҰҚӨҺ]")
_KK_FUNCTION = frozenset(
    [
        "маған",
        "бізге",
        "керек",
        "жақсы",
        "жақын",
        "қайда",
        "қандай",
        "және",
        "үшін",
        "болады",
        "барамын",
        "барғым",
        "келеді",
        "мен",
        "сен",
        "біз",
        "жоқ",
        "емес",
    ]
)
_EN_FUNCTION = frozenset(
    [
        "the",
        "a",
        "an",
        "i",
        "me",
        "my",
        "near",
        "with",
        "for",
        "to",
        "where",
        "want",
        "looking",
        "need",
        "some",
        "is",
        "are",
        "in",
        "at",
        "of",
        "and",
        "place",
        "something",
        "anything",
        "open",
        "on",
        "day",
        "what",
        "when",
        "can",
        "we",
        "you",
        "any",
        "nearby",
        "today",
        "tomorrow",
        "tonight",
        "please",
        "from",
        "do",
        "does",
        "there",
        "it",
        "how",
        "should",
    ]
)
_TOKEN = re.compile(
    r"\w+|[,;.!?:()\n]|[\U0001F300-\U0001FAFF]"
)  # an emoji is a word of its own («🍺»)
_CLAUSE_WORDS = frozenset({"но", "а", "зато", "хотя", "but", "however", "though"})
_PUNCT = frozenset(",;.!?:()\n")
_CYR = re.compile(r"[а-яёА-ЯЁ]")


def normalize(text: str) -> str:
    """Lowercase, ё→е, kk letters → ru look-alikes, hyphens → spaces, a few joined spellings (wi-fi → wifi)."""
    t = text.lower().translate(_LETTERS)
    t = re.sub(r"[-–—_/]", " ", t)
    for src, dst in JOINS.items():
        if src in t:
            t = t.replace(src, dst)
    return t


@dataclass(frozen=True)
class _Stem:
    words: tuple[tuple[str, bool], ...]  # (normalised word, whole word only)
    concept: str
    text: str  # as written in the lexicon, for notes
    lang: str


@dataclass(frozen=True)
class Hit:
    concept: str
    text: str  # what the user wrote
    stem: str  # the lexicon stem it matched
    fuzzy: bool  # matched through a typo
    negated: bool
    kk_only: bool  # a stem that exists only in the kazakh list
    location: bool = (
        False  # a place kind that names WHERE the user is («возле парка Момышулы»), not a wish
    )
    visited: bool = (
        False  # a place kind the user has just come from («только из мечети»): not a wish
    )
    joined: bool = False  # right after a conjunction («кафе немесе бар»): the kk «бар» is the bar, not «there is»


@dataclass
class Matches:
    hits: list[Hit]
    language: str
    active: dict[str, list[Hit]]  # concept -> positive hits (after `unless`)
    negated: dict[
        str, list[Hit]
    ]  # concept -> hits that were negated, for concepts with no positive hit
    located: dict[str, list[Hit]] = field(
        default_factory=dict
    )  # concept -> hits that only name a location
    visited: dict[str, list[Hit]] = field(
        default_factory=dict
    )  # concept -> hits that name a place the user has just left

    def has(self, name: str) -> bool:
        return name in self.active

    def is_negated(self, name: str) -> bool:
        return name in self.negated

    def typos(self) -> list[str]:
        return [f"{h.text}→{h.stem}" for hs in self.active.values() for h in hs if h.fuzzy]

    def flags(self) -> set[str]:
        """Every flag of the concepts the text mentions (and does not negate)."""
        return {f for name in self.active for f in _by_name()[name].flags}


def _compile_word(raw: str) -> tuple[str, bool]:
    exact = raw.endswith("=")
    word = normalize(raw.rstrip("=")).strip()
    return word, exact or len(word) <= _MAX_EXACT_LEN


@cache
def _stems() -> tuple[tuple[_Stem, ...], frozenset[str]]:
    """Every stem of the lexicon, and the (normalised) stems that exist in kk only."""
    out: list[_Stem] = []
    langs: dict[str, set[str]] = {}
    for c in CONCEPTS:
        for lang, raws in (("ru", c.ru), ("kk", c.kk), ("en", c.en)):
            for raw in raws:
                words = tuple(_compile_word(w) for w in raw.split())
                key = " ".join(w for w, _ in words)
                langs.setdefault(key, set()).add(lang)
                out.append(_Stem(words, c.name, raw, lang))
    ru_words = [s.words[0] for s in out if s.lang == "ru" and len(s.words) == 1]
    # a kazakh spelling that a russian stem also matches («розетка» ~ the stem «розетк») says nothing about the language
    kk_only = frozenset(
        k
        for k, ls in langs.items()
        if ls == {"kk"} and not any(_word_matches(k, w, whole) for w, whole in ru_words)
    )
    return tuple(out), kk_only


@cache
def _by_name() -> dict[str, Concept]:
    return {c.name: c for c in CONCEPTS}


@cache
def _unless_rank(name: str) -> int:
    """0 for a concept nothing cancels, else one more than the highest rank of the concepts that cancel it: the
    concepts are resolved in that order, so one that is cancelled itself (`wheelchair_on` by `kids`) no longer
    cancels another (`stroller`)."""
    return 1 + max((_unless_rank(u) for u in _by_name()[name].unless), default=-1)


@cache
def _index() -> tuple[dict[str, list[_Stem]], list[_Stem], list[_Stem], list[_Stem]]:
    """(exact single words, prefix single words, phrases, fuzzy candidates)."""
    exact: dict[str, list[_Stem]] = {}
    prefix: list[_Stem] = []
    phrases: list[_Stem] = []
    fuzzy: list[_Stem] = []
    for s in _stems()[0]:
        if len(s.words) > 1:
            phrases.append(s)
            continue
        word, whole = s.words[0]
        if whole:
            exact.setdefault(word, []).append(s)
        else:
            prefix.append(s)
            if len(word) >= FUZZY_MIN_STEM:
                fuzzy.append(s)
    return exact, prefix, phrases, fuzzy


def _word_matches(token: str, word: str, whole: bool) -> bool:
    return token == word if whole else token.startswith(word)


def _clauses(text: str) -> list[list[str]]:
    clauses: list[list[str]] = [[]]
    for raw in _TOKEN.findall(normalize(text)):
        if raw in _PUNCT or raw in _CLAUSE_WORDS:
            if clauses[-1]:
                clauses.append([])
            continue
        clauses[-1].append(raw)
    return [c for c in clauses if c]


def _is_negated(tokens: list[str], start: int, end: int, *, own_without: bool = False) -> bool:
    """`own_without`: the stem itself ends with «-сыз / -сіз» («баспалдақсыз», «шусыз»): the suffix is its meaning."""
    if (
        not own_without
        and len(tokens[start]) >= _MIN_WITHOUT_LEN
        and tokens[start].endswith(_KK_WITHOUT)
    ):
        return True  # kk «алкогольсіз» = «without alcohol»
    lo, words = start, 0  # «don't want a quiet place»: an article stands in the way of no negator
    while lo > 0 and words < NEGATION_WINDOW:
        lo -= 1
        words += tokens[lo] not in DETERMINERS
    for k in range(lo, start):
        if tokens[k] in NEGATORS:
            return not any(t in NEGATION_VOID for t in tokens[k + 1 : start])
    return end < len(tokens) and tokens[end] in POSTFIX_NEGATORS


def _single_hits(token: str) -> list[_Stem]:
    exact, prefix, _, _ = _index()
    found = [*exact.get(token, ()), *(s for s in prefix if token.startswith(s.words[0][0]))]
    return [
        s for s in found if not any(token.startswith(n) for n in _by_name()[s.concept].not_stems)
    ]


def _typo_score(stem: str, token: str) -> float:
    """How close `token` is to `stem` read as a typo of the word's start (0: not a typo of it). The first and the
    last letter of the stem must be intact (another ending is an inflection or another word: «маршрута» is not
    «маршрутка») and the rest may differ by one edit or by a rapidfuzz ratio of at least 85."""
    best = 0.0
    for shift in (0, -1, 1):
        head = token[: len(stem) + shift]
        if len(head) < len(stem) - 1 or head[0] != stem[0] or head[-1] != stem[-1]:
            continue
        ratio = fuzz.ratio(head, stem)
        if ratio >= FUZZY_RATIO or OSA.distance(head[:-1], stem[:-1], score_cutoff=1) <= 1:
            best = max(best, ratio)
    return best


_NEGATING_PREFIXES = ("не", "без")
_ANTONYMS = frozenset(
    pair
    for a, b in ANTONYM_PAIRS
    for pair in ((normalize(a), normalize(b)), (normalize(b), normalize(a)))
)


def _flips_meaning(stem: str, token: str) -> bool:
    """True when reading `token` as a typo of `stem` would turn it into its opposite: an antonym pair («надолго» /
    «недолго»), or a word that carries a negating prefix the stem lacks («небыстро» / «быстр»)."""
    if (token, stem) in _ANTONYMS or (token[: len(stem)], stem) in _ANTONYMS:
        return True
    return any(token.startswith(p) and not stem.startswith(p) for p in _NEGATING_PREFIXES)


def _fuzzy_hit(token: str) -> _Stem | None:
    """The stem a word is a typo of (None: nothing close). The best score wins, ties keep the lexicon order. A
    negator is never a typo, and neither is a word whose reading would flip the meaning (`_flips_meaning`)."""
    if len(token) < FUZZY_MIN_STEM - 1 or not token.isalpha() or token in NEGATORS:
        return None
    best, best_score = None, 0.0
    for s in _index()[3]:
        stem = s.words[0][0]
        if (
            len(stem) - 1 <= len(token) <= len(stem) + 3
            and not _flips_meaning(stem, token)
            and (score := _typo_score(stem, token)) > best_score
        ):
            best, best_score = s, score
    return best


@dataclass(frozen=True)
class _Names:
    """The words of the request written with a capital letter: its proper names («Момышулы», «Mega», «Park»)."""

    mid: frozenset[str]  # not at the start of a sentence; all-caps words included («ТЦ MEGA»)
    title: frozenset[
        str
    ]  # the same without all-caps words: «Парк», «Park», but not the abbreviation «ТЦ»
    anywhere: frozenset[str]  # a sentence start included («Момышулы паркі жанында»)


_WORD_OR_STOP = re.compile(r"\w+|[.!?\n]")
_LOCATIVES = tuple(tuple(normalize(p).split()) for p in LOCATIVE_BEFORE)
_POSTPOSITIONS = tuple(normalize(p) for p in KK_POSTPOSITIONS)
_POSSESSIVE = tuple(normalize(p) for p in KK_POSSESSIVE_ENDINGS)


def _names(text: str) -> _Names:
    mid: set[str] = set()
    title: set[str] = set()
    anywhere: set[str] = set()
    start = True
    for m in _WORD_OR_STOP.finditer(text):
        tok = m.group()
        if tok in ".!?\n":
            start = True
            continue
        if tok[0].isupper():
            norm = normalize(tok)
            anywhere.add(norm)
            if not start:
                mid.add(norm)
                if not (tok.isupper() and len(tok) > 1):
                    title.add(norm)
        start = False
    return _Names(frozenset(mid), frozenset(title), frozenset(anywhere))


def _after_locative(tokens: list[str], start: int) -> bool:
    """«возле парка», «рядом с музеем», «near the mall», «at a cafe»: a place kind right after a locative."""
    j = start
    while j > 0 and tokens[j - 1] in DETERMINERS:
        j -= 1
    return any(j >= len(ph) and tuple(tokens[j - len(ph) : j]) == ph for ph in _LOCATIVES)


def _is_location(tokens: list[str], start: int, end: int, names: _Names, *, kk: bool) -> bool:
    """True when the place kind only says where the user is: it is part of a proper name («Парк Горького», «Central
    Park», «парк Момышулы», «ТЦ Mega», kk «Момышулы паркі»), follows «near / возле / у / рядом с», or is followed by a
    kk postposition («жанында», «қасында», «жақын»). «хочу в парк», «погулять в парке» stay wishes."""
    if tokens[start] in names.title:
        return True
    j = end
    while j < len(tokens) and tokens[j] in NAME_LINKS:
        j += 1
    if j < len(tokens) and tokens[j] in names.mid:
        return True
    if end < len(tokens) and tokens[end].startswith(_POSTPOSITIONS):
        return True
    if (
        kk
        and start > 0
        and tokens[start - 1] in names.anywhere
        and tokens[end - 1].endswith(_POSSESSIVE)
    ):
        return True
    return _after_locative(tokens, start)


def _clause_hits(tokens: list[str], names: _Names, *, kk: bool) -> list[Hit]:
    _, _, phrases, _ = _index()
    hits: list[Hit] = []
    covered: set[int] = set()
    for i, tok in enumerate(tokens):
        for s in phrases:
            n = len(s.words)
            if i + n <= len(tokens) and all(
                _word_matches(tokens[i + k], w, whole) for k, (w, whole) in enumerate(s.words)
            ):
                hits.append(_hit(tokens, i, i + n, s, names, kk, fuzzy=False))
                covered.update(range(i, i + n))
        for s in _single_hits(tok):
            hits.append(_hit(tokens, i, i + 1, s, names, kk, fuzzy=False))
            covered.add(i)
    for i, tok in enumerate(tokens):
        if i not in covered and (s := _fuzzy_hit(tok)) is not None:
            hits.append(_hit(tokens, i, i + 1, s, names, kk, fuzzy=True))
    return hits


_VISITED = tuple(tuple(normalize(p).split()) for p in VISITED_BEFORE)


def _just_visited(tokens: list[str], start: int, end: int) -> bool:
    """«только из мечети», «вышел из музея», «just left the mall», kk «мешіттен шықтым»: the user has just BEEN at
    this kind of place, so it is the one thing that is not wanted."""
    j = start
    while j > 0 and tokens[j - 1] in DETERMINERS:
        j -= 1
    if any(j >= len(ph) and tuple(tokens[j - len(ph) : j]) == ph for ph in _VISITED):
        return True
    return (
        end < len(tokens) and tokens[end] in KK_VISITED_AFTER and tokens[start].endswith(_ABLATIVE)
    )


def _hit(
    tokens: list[str], start: int, end: int, s: _Stem, names: _Names, kk: bool, *, fuzzy: bool
) -> Hit:
    key = " ".join(w for w, _ in s.words)
    concept = _by_name()[s.concept]
    kind = bool(concept.categories) and concept.tier == "kind"
    own_without = key.endswith(_KK_WITHOUT)
    return Hit(
        concept=s.concept,
        text=" ".join(tokens[start:end]),
        stem=s.text.rstrip("="),
        fuzzy=fuzzy,
        negated=_is_negated(tokens, start, end, own_without=own_without),
        kk_only=key in _stems()[1],
        location=kind and _is_location(tokens, start, end, names, kk=kk),
        visited=kind and _just_visited(tokens, start, end),
        joined=start > 0
        and tokens[start - 1] in KK_BAR_JOINERS
        and not (end < len(tokens) and tokens[end] in KK_QUESTION),
    )


def detect_language(text: str, kk_only_hit: bool = False, *, any_hit: bool = True) -> str:
    """kk by its letters (әғқңөұүһі), its function words or a word only the kk lists know; else ru when there is
    Cyrillic (unless the text is plainly english around one russian word), else en. A Latin-only text that has
    neither an english function word nor a single lexicon hit (`any_hit` False) is gibberish, not english: ru."""
    if _KK_SPECIAL.search(text):
        return "kk"
    words = re.findall(r"\w+", text.lower())
    if kk_only_hit or any(w in _KK_FUNCTION for w in words):
        return "kk"
    cyr = [w for w in words if _CYR.search(w)]
    if cyr:
        english = sum(w in _EN_FUNCTION for w in words)
        return "en" if len(cyr) <= 1 and english >= 3 else "ru"
    if not re.search(r"[a-zA-Z]", text):
        return "ru"
    return "en" if any_hit or any(w in _EN_FUNCTION for w in words) else "ru"


def match(text: str) -> Matches:
    """Every concept the text mentions, with the words that triggered it (see the module docstring). Spans that
    are not natural language (pasted JSON, code, base64) are cut first (walks.safety.clean_text)."""
    text = clean_text(text)
    hits: list[Hit] = []
    names, kk = _names(text), detect_language(text) == "kk"
    for tokens in _clauses(text):
        hits += _clause_hits(tokens, names, kk=kk)
    language = detect_language(
        text, kk_only_hit=any(h.kk_only and not h.fuzzy for h in hits), any_hit=bool(hits)
    )
    if language == "kk":
        hits = [h for h in hits if h.text not in KK_AMBIGUOUS or h.joined]
    active: dict[str, list[Hit]] = {}
    negated: dict[str, list[Hit]] = {}
    located: dict[str, list[Hit]] = {}
    visited: dict[str, list[Hit]] = {}
    for h in hits:
        bucket = (
            visited if h.visited else located if h.location else negated if h.negated else active
        )
        bucket.setdefault(h.concept, []).append(h)
    for name in sorted(
        active, key=_unless_rank
    ):  # a concept that is itself cancelled cancels nothing
        if any(u in active for u in _by_name()[name].unless):
            del active[name]
    negated = {n: hs for n, hs in negated.items() if n not in active}
    located = {n: hs for n, hs in located.items() if n not in active}
    visited = {n: hs for n, hs in visited.items() if n not in active}
    return Matches(hits, language, active, negated, located, visited)


_ALIASES = tuple(
    (tuple(tuple(normalize(ph).split()) for ph in phrases), names)
    for phrases, names in LANDMARK_ALIASES
)
_NAMED_ALREADY = frozenset(
    {"хан", "khan"}
)  # «Хан Шатыр» is the name itself, not a description of a tent


def landmark_refs(text: str) -> list[str]:
    """The names of the well-known places a vague description points at («башня с шаром» -> Байтерек, «большой
    шатёр» -> Хан Шатыр, «sphere building» -> Nur Alem), in the order of the aliases; [] when none is described.
    A word of the description is read once: the first alias that matches takes it."""
    tokens = re.findall(r"\w+", normalize(clean_text(text)))
    taken: set[int] = set()
    out: list[str] = []
    for phrases, names in _ALIASES:
        for ph in phrases:
            n = len(ph)
            for i in range(len(tokens) - n + 1):
                span = range(i, i + n)
                if (
                    any(j in taken for j in span)
                    or not all(tokens[i + k].startswith(w) for k, w in enumerate(ph))
                    or (i > 0 and tokens[i - 1] in _NAMED_ALREADY)
                ):
                    continue
                taken.update(span)
                out += [x for x in names if x not in out]
    return out


_DIRECT = tuple(
    (tuple(tuple(normalize(ph).split()) for ph in phrases), names)
    for phrases, names in DIRECT_PLACES
)
_INFO = tuple(re.compile(rx) for rx in INFO_QUESTIONS)


_DURATION = re.compile(
    r"\b(?:\d+(?:[.,]\d+)?|an?|one|two|three|four|five|six|seven|eight|nine|ten|couple of|few|several|half an?)"
    r"\s+(?:hours?|hrs?)\b"
)


def without_durations(normalized: str) -> str:
    """The normalised text with the lengths of time in English hours dropped («2 hours before the flight», «in an
    hour»): they are a time budget, not the word «hours» of a question about opening hours."""
    return _DURATION.sub(" ", normalized)


def is_info_question(text: str) -> bool:
    """The text asks something ABOUT a place (hours, «стоит ли», «что это», «can we go in»), not for places."""
    t = without_durations(normalize(clean_text(text)))
    return any(rx.search(t) for rx in _INFO)


def named_places(text: str) -> list[tuple[tuple[str, ...], bool]]:
    """Well-known places the text names directly, in the order of the text: (their dataset names, located). `located`
    is True when the name only says where the user is («возле Хан Шатыра», «Хан Шатыр жанында»)."""
    tokens = re.findall(r"\w+", normalize(clean_text(text)))
    found: list[tuple[int, tuple[str, ...], bool]] = []
    for phrases, names in _DIRECT:
        for ph in phrases:
            n = len(ph)
            for i in range(len(tokens) - n + 1):
                if not all(tokens[i + k].startswith(w) for k, w in enumerate(ph)):
                    continue
                j = i
                while j > 0 and (tokens[j - 1] in DETERMINERS or tokens[j - 1] in PLACE_WORDS):
                    j -= 1
                after = tokens[i + n] if i + n < len(tokens) else ""
                located = _after_locative(tokens, j) or after.startswith(_POSTPOSITIONS)
                found.append((i, names, located))
    found.sort(key=lambda f: f[0])
    out: list[tuple[tuple[str, ...], bool]] = []
    for _, names, located in found:
        if all(names != n for n, _ in out):
            out.append((names, located))
    return out
