"""The buttons under an answer: deterministic, at most four that would CHANGE the request (plus «новый поиск»), each
one a phrase the rule parser reads offline. Which ones appear depends on what the request already says: no «без
алкоголя» for a museum, no «поближе» when everything is a minute away, no «с ребёнком» once the request has a child."""

from __future__ import annotations

from .dialog_strings import s
from .dialog_types import Chip, ShownPlace
from .models import Constraints, Intent
from .variety import priced_kinds
from .wishes import errand

MAX_REFINE_CHIPS = 4
MIN_FAR_M = 200  # «поближе» goes to 80% of the farthest shown place, never under 150 m: nearer than this it is moot
MAX_BUDGET_MIN = 240
DRINKS = frozenset({"restaurant", "bar_nightlife"})
QUIETABLE = frozenset(
    {"cafe", "coworking_library", "museum_gallery"}
)  # a park has no quiet tag to change the answer
WORKABLE = frozenset({"cafe", "coworking_library"})
START = ("food", "coffee", "walk", "kids_start", "museum", "unusual")


def chip(chip_id: str, lang: str, kind: str = "refine") -> Chip:
    return Chip(
        id=chip_id,
        label=s(f"c_{chip_id}", lang),
        send=s(f"q_{chip_id}", lang),
        kind=kind,  # type: ignore[arg-type]
    )


def reset_chip(lang: str) -> Chip:
    return chip("new", lang, "reset")


def start_chips(lang: str) -> list[Chip]:
    return [chip(i, lang, "start") for i in START]


def _applicable(intent: Intent, constraints: Constraints, shown: list[ShownPlace]) -> list[str]:
    cats = set(intent.categories)
    farthest = max((p.distance_m for p in shown), default=0)
    out: list[str] = []
    if shown:
        out.append("more")
    if shown and farthest >= MIN_FAR_M:
        out.append("closer")
    if (
        "other" in cats or errand(intent.wished or intent.categories)
    ):  # a state service point (ЦОН), an errand: a child, an hour more or cheaper change nothing there
        return out
    if intent.budget != "low" and priced_kinds(
        list(cats), "low"
    ):  # only food has a lever without prices
        out.append("cheaper")
    if not constraints.no_alcohol and cats & DRINKS:
        out.append("no_alcohol")
    if intent.time_budget_min < MAX_BUDGET_MIN:
        out.append("longer")
    if not intent.with_kids and not intent.minor and cats - {"bar_nightlife"}:
        out.append("kids")
    if not intent.quiet and cats & QUIETABLE:
        out.append("quiet")
    if not intent.needs_wifi_socket and cats & WORKABLE:
        out.append("wifi")
    return out


def refine_chips(
    intent: Intent, constraints: Constraints, shown: list[ShownPlace], lang: str
) -> list[Chip]:
    """Up to four refinements that change this request, then the «new search» button."""
    ids = _applicable(intent, constraints, shown)[:MAX_REFINE_CHIPS]
    return [*(chip(i, lang) for i in ids), reset_chip(lang)]
