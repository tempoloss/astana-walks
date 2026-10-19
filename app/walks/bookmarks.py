"""The user's own named places («дом», «школа»), sent with one request from their device: never stored, never logged.

Two things come from them: a request that NAMES one («рядом с домом», «возле школы», «по пути домой», the bookmark's own
name) is searched there (`near`) or along the way to it (`along`); and late at night a request for food, coffee or a
drink prefers places that lie toward home (closer to home than the user is). Everything is geometry and words; no model
reads a bookmark."""

from __future__ import annotations

import re
from dataclasses import dataclass

from .models import Bookmark, Candidate, Intent
from .radius import haversine_m

LATE_FROM_H, LATE_TO_H = 22, 5  # the evening that turns into «по пути домой»
FOOD_KINDS = frozenset({"restaurant", "cafe", "fast_food", "bar_nightlife"})
AT_HOME_M = 300  # a user this close to the bookmark is «there»: nothing lies «toward» it
CLOSER_BY_M = (
    50  # a place counts as toward the bookmark when it is at least this much closer than the user
)
ALONG_SLACK = 0.25  # along the way: the detour is at most this share of the user's own way ...
ALONG_MIN_DETOUR_M = 300  # ... and never stricter than this
MIN_TOWARD = 2  # with fewer places toward the bookmark the others stay in the list, behind them
TOWARD_SHARE = (
    0.15  # «по пути»: the place covers at least this share of the way to the bookmark ...
)
LEAN_SLACK = 0.5  # ... and a late request leaning toward home accepts a detour of at most this share of the way
MIN_NAME_CHARS = 3

_KIND_WORDS = {
    "home": r"дом\w*|квартир\w*|home|house|үй\w*",
    "work": r"работ\w*|офис\w*|work|office|жұмыс\w*",
    "study": r"школ\w*|универ\w*|вуз\w*|колледж\w*|садик\w*|детск\w* сад\w*|институт\w*|school|university|college"
    r"|campus|мектеп\w*",
}
_NEAR = r"(?<!\w)(?:рядом с|возле|около|поближе к|неподалёку от|недалеко от|у|near|next to|close to|around|by|жанында|маңында)"
_ALONG = r"(?<!\w)(?:по пути|по дороге|на пути|по дороге к|on the way|on my way|along the way|en route|жолда|жол бойында)"
_OWN = r"(?:(?:мо\w+|my|the|менің)\s+)?"
_POSSESSIVE_NAME = re.compile(r"^(?:my|the|мой|моя|моё|мое|мои|менің)\s+", re.IGNORECASE)
_DIRECTION = {  # bare «домой» / «на работу» / «в школу»: the way TO the place
    "home": r"домой|home\b|үйге",
    "work": r"на работу|к работе|с работы|to work|жұмысқа",
    "study": r"в школу|в университет|в универ|в вуз|к школе|из школы|to school|to university|мектепке",
}


@dataclass(frozen=True)
class Ref:
    """A bookmark the message names: searched around it (`along` False) or along the way to it; `rest` is the message
    without the words that named it (they are not a wish for a place)."""

    bookmark: Bookmark
    along: bool
    rest: str


def _core(name: str) -> str:
    """The name without its possessive: «my hotel» is a place called «hotel», said «my hotel», «the hotel»."""
    return _POSSESSIVE_NAME.sub("", name.strip())


def _stem(name: str) -> str:
    low = name.lower().strip()
    return low[:-1] if len(low) >= 5 and low[-1] in "аяыиуюеоьй" else low


def _patterns(b: Bookmark) -> list[tuple[bool, str]]:
    """(along, regex) pairs of one bookmark, most specific first."""
    words = [_KIND_WORDS[b.kind]] if b.kind in _KIND_WORDS else []
    core = _core(b.name)
    if len(core) >= MIN_NAME_CHARS:
        words.append(re.escape(_stem(core)) + r"\w*")
    out: list[tuple[bool, str]] = []
    for w in words:
        out.append(
            (True, rf"{_ALONG}\s+(?:back\s+)?(?:домой|до|к|в|на|с|to|from)?\s*{_OWN}(?:{w})")
        )
        out.append((False, rf"{_NEAR}\s+{_OWN}(?:{w})"))
        out.append(
            (False, rf"(?:{w})\s+(?:жанында|маңында|қасында|жанынан)")
        )  # kk: «үйдің жанында»
    if b.kind in _DIRECTION:
        out.append((True, rf"(?:{_DIRECTION[b.kind]})"))
    if len(core) >= MIN_NAME_CHARS:
        own = (
            _OWN if core != b.name.strip() else ""
        )  # a name said with its «my» is found by that «my» too
        out.append((False, rf"\b{own}{re.escape(_stem(core))}\w*"))
    return out


def find_ref(text: str, bookmarks: list[Bookmark]) -> Ref | None:
    """The first bookmark the text names (an «along the way» phrase beats a «near» one), else None."""
    low = text.lower()
    best: tuple[int, bool, re.Match[str], Bookmark] | None = None
    for b in bookmarks:
        for along, rx in _patterns(b):
            m = re.search(rx, low)
            if m is None:
                continue
            rank = 0 if along else 1
            if best is None or rank < best[0]:
                best = (rank, along, m, b)
            break  # this bookmark's most specific pattern is enough
    if best is None:
        return None
    _, along, m, b = best
    rest = " ".join(f"{text[: m.start()]} {text[m.end() :]}".split()).strip(" ,.;:-")
    return Ref(bookmark=b, along=along, rest=rest)


def named_bookmark(text: str, bookmarks: list[Bookmark]) -> Bookmark | None:
    """The bookmark the text names anywhere («my hotel», «the hotel», «до дома»): by its name, or by the word of its kind.
    Only a question about the way to it asks this; a search around it is `find_ref`."""
    low = text.lower()
    for b in bookmarks:
        core = _core(b.name)
        words = [_KIND_WORDS[b.kind]] if b.kind in _KIND_WORDS else []
        if len(core) >= MIN_NAME_CHARS:
            words.append(re.escape(_stem(core)) + r"\w*")
        if any(re.search(rf"(?<!\w)(?:{w})", low) for w in words):
            return b
    return None


def home_bookmark(bookmarks: list[Bookmark]) -> Bookmark | None:
    return next((b for b in bookmarks if b.kind == "home"), None)


def is_late(hour: int) -> bool:
    return hour >= LATE_FROM_H or hour < LATE_TO_H


def late_home(
    intent: Intent, hour: int, user: tuple[float, float], bookmarks: list[Bookmark]
) -> Bookmark | None:
    """The home bookmark a late request for food, coffee or a drink leans toward (None: not late, no such request, no
    home, or the user is at home)."""
    home = home_bookmark(bookmarks)
    if home is None or not is_late(hour) or not FOOD_KINDS.intersection(intent.categories):
        return None
    return None if haversine_m(*user, home.lat, home.lon) < AT_HOME_M else home


def toward(
    user: tuple[float, float], target: Bookmark, lat: float, lon: float, *, along: bool
) -> bool:
    """Is the point toward `target` for a user at `user`. «Along the way» (the person asked for it): closer to the target
    than the user and a small detour (ALONG_SLACK) — a place passed at the start counts. A late request that only leans
    toward home: a real share of the way (TOWARD_SHARE) with a sane detour (LEAN_SLACK); a place next to the user with
    home 6 km away is not «по пути домой»."""
    own = haversine_m(*user, target.lat, target.lon)
    if own < AT_HOME_M:
        return False
    there = haversine_m(lat, lon, target.lat, target.lon)
    if own - there < (CLOSER_BY_M if along else max(CLOSER_BY_M, TOWARD_SHARE * own)):
        return False
    detour = haversine_m(*user, lat, lon) + there - own
    return detour <= max(ALONG_MIN_DETOUR_M, (ALONG_SLACK if along else LEAN_SLACK) * own)


def prefer_toward(
    cands: list[Candidate],
    user: tuple[float, float],
    target: Bookmark,
    *,
    along: bool,
    kinds: frozenset[str] = frozenset(),
) -> list[Candidate]:
    """The candidates with those toward `target` first (alone when there are enough of them); unchanged when none lies
    that way, so the answer never claims a way it does not have. The way only orders and narrows the kinds the person
    NAMED (`kinds`): a place of another kind that lies toward home never takes the place of one they asked for, it
    only follows them."""
    named = [c for c in cands if c.poi.category in kinds] if kinds else []
    if named:
        return [*_toward_first(named, user, target, along), *(c for c in cands if c not in named)]
    return _toward_first(cands, user, target, along)


def _toward_first(
    cands: list[Candidate], user: tuple[float, float], target: Bookmark, along: bool
) -> list[Candidate]:
    on = [c for c in cands if toward(user, target, c.poi.lat, c.poi.lon, along=along)]
    if not on:
        return cands
    if len(on) >= MIN_TOWARD:
        return on
    return [*on, *(c for c in cands if c not in on)]
