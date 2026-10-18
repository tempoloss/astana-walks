"""Post-ranking rules of the wishes a record can only partly confirm: the night (what is confirmed open comes first),
and the honest «no place found has it» for halal and the diets."""

from __future__ import annotations

from .models import Candidate

# unknown hours at 23:00-06:00 are as good as closed for these
UNLIKELY_AT_NIGHT = frozenset({"mall", "museum_gallery", "coworking_library"})


def open_first(ranked: list[Candidate]) -> list[Candidate]:
    """23:00-06:00: places whose opening hours the data confirm come before every place with unknown hours (a stable
    partition: the rank order holds inside each group), whatever their category: at 3 a.m. a night shift wants what
    is open, not what is nearest and probably closed."""
    return sorted(ranked, key=lambda c: c.hours_state != "open")


def without_night_dead_ends(chosen: list[Candidate]) -> list[Candidate]:
    """A mall, a museum or a library with unknown hours at 23:00-06:00 is closed in all likelihood: out, unless nothing
    else is left."""
    left = [c for c in chosen if c.hours_state == "open" or c.poi.category not in UNLIKELY_AT_NIGHT]
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
