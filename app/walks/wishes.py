"""Post-ranking rules of the wishes a record can only partly confirm: the night (what is confirmed open comes first,
an errand open round the clock next), and the honest «no place found has it» for halal and the diets."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable

from .hours import is_24_7
from .models import Candidate

# unknown hours at 23:00-06:00 are as good as closed for these
UNLIKELY_AT_NIGHT = frozenset({"mall", "museum_gallery", "coworking_library"})


def open_first(ranked: list[Candidate], wished: frozenset[str] = frozenset()) -> list[Candidate]:
    """23:00-06:00: places whose opening hours the data confirm come before every place with unknown hours (a stable
    partition: the rank order holds inside each group): at 3 a.m. a night shift wants what is open, not what is
    nearest and probably closed. A kind the person named («погулять с собакой») keeps its place before everything
    else: the night orders the places of that kind, it never replaces them with a café that happens to be open."""
    return sorted(
        ranked,
        key=lambda c: (bool(wished) and c.poi.category not in wished, c.hours_state != "open"),
    )


def round_the_clock_first(
    ranked: list[Candidate], wished: frozenset[str] = frozenset()
) -> list[Candidate]:
    """An errand at night (a pharmacy, a food shop): what the data confirm open now comes first, a round-the-clock one
    before the rest of them, and one whose hours are unknown after both (its card says so). A stable partition, as
    `open_first`."""
    return sorted(
        ranked,
        key=lambda c: (
            bool(wished) and c.poi.category not in wished,
            c.hours_state != "open",
            not is_24_7(c.poi.opening_hours),
        ),
    )


def without_night_dead_ends(
    chosen: list[Candidate], wished: frozenset[str] = frozenset()
) -> list[Candidate]:
    """A mall, a museum or a library with unknown hours at 23:00-06:00 is closed in all likelihood: out, unless nothing
    else is left or the person named that kind (the card then says its hours are unknown)."""
    left = [
        c
        for c in chosen
        if c.hours_state == "open"
        or c.poi.category not in UNLIKELY_AT_NIGHT
        or c.poi.category in wished
    ]
    return left or chosen


def mark_unmet_wishes(top: list[Candidate]) -> list[Candidate]:
    """A wish the record can be checked for (halal, a diet): when no returned card carries the mark, each card's
    «unverified» becomes «none», and the card says that no place found has it, instead of leaving it to be assumed."""
    met = {r for c in top for r in c.reasons}
    out = []
    for c in top:
        reasons = []
        for r in c.reasons:
            if r == "halal_unverified" and "halal" not in met:
                r = "halal_none"
            elif r.startswith("diet_unverified:") and f"diet:{r.split(':', 1)[1]}" not in met:
                r = f"diet_none:{r.split(':', 1)[1]}"
            reasons.append(r)
        out.append(c.model_copy(update={"reasons": reasons}) if reasons != c.reasons else c)
    return out


def keep_requested_kinds(
    cands: list[Candidate], requested: list[str], top_n: int, rank: Callable[[Candidate], tuple]
) -> list[Candidate]:
    """The first `top_n` of `cands`, except that the best candidate of every requested category that has any
    stays in the list: «playground or museum» must not be answered with ten playgrounds only. It takes the
    place of the lowest-ranked entry of a category that is listed more than once."""
    top = cands[:top_n]
    for cat in requested:
        if any(c.poi.category == cat for c in top):
            continue
        best = next((c for c in cands if c.poi.category == cat), None)
        if best is None:
            continue
        counts = Counter(c.poi.category for c in top)
        for i in range(len(top) - 1, -1, -1):
            if counts[top[i].poi.category] > 1:
                top = sorted([*top[:i], *top[i + 1 :], best], key=rank)
                break
    return top
