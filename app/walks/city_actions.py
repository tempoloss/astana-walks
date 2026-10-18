"""«Что с этим делать городу»: the city layer turned into short, checkable tasks.

Two kinds, never mixed:

* `supply` - from the demand groups that reached k: the district and the category where requests found no place of the
  requested kind inside the declared radius. It is a gap in the DATASET first; the task is to check the map and only
  then to count it as a gap of the city. Whether it is about people depends on the source of the requests (simulated
  or real) - the caller labels it.
* `hours` - from the place data alone: the categories where opening hours matter and are rarest, and the district
  holding most places of that category without hours. The task is to ask the owners for the hours.

Pure aggregation over `DemandRow` and `POI`; the district lookup is passed in, so the module has no files."""

from __future__ import annotations

from collections import Counter
from collections.abc import Callable, Iterable
from dataclasses import dataclass

from .demand import ANY_CATEGORY, OTHER, DemandRow
from .models import POI
from .retrieve import TRANSIT_CATEGORY

NO_DISTRICT = "вне границ районов"
MIN_CATEGORY_PLACES = (
    10  # a category with fewer places in total is too small for a «worst coverage» line
)
# Where opening hours decide whether a trip makes sense; a park or a playground has none to ask for.
HOURS_MATTER = (
    "cafe",
    "restaurant",
    "fast_food",
    "bar_nightlife",
    "museum_gallery",
    "entertainment",
    "mall",
    "culture_theatre_cinema",
    "coworking_library",
    "sport",
)
GENITIVE_PLURAL = {
    "cafe": "кафе",
    "restaurant": "ресторанов",
    "fast_food": "точек фастфуда",
    "bar_nightlife": "баров и мест ночной жизни",
    "museum_gallery": "музеев и галерей",
    "entertainment": "мест для развлечений",
    "mall": "торговых центров",
    "culture_theatre_cinema": "театров и кинотеатров",
    "coworking_library": "коворкингов и библиотек",
    "sport": "спортивных объектов",
}


@dataclass(frozen=True)
class CityAction:
    kind: str  # "supply" | "hours"
    district: str
    category: str
    count: int  # supply: requests without a place of the kind; hours: places without hours
    of: int  # supply: requests of the district for the category; hours: places of the category in the district
    share: float  # supply: count / of; hours: share of the places that HAVE hours in the district
    text: str


def supply_actions(
    rows: Iterable[DemandRow],
    district_for: Callable[[str], str | None],
    category_ru: Callable[[str], str],
    top: int = 5,
) -> list[CityAction]:
    """District x category with the most requests that found no place of the kind within the declared radius. Only
    rows that reached k are summed (the merged «прочее» rows have no location), so nothing below k is revealed."""
    acc: dict[tuple[str, str], list[int]] = {}
    for r in rows:
        if r.cell == OTHER or not r.category or r.category == ANY_CATEGORY:
            continue
        a = acc.setdefault((district_for(r.cell) or NO_DISTRICT, r.category), [0, 0])
        a[0] += r.no_requested_category_nearby
        a[1] += r.requests
    ranked = sorted(
        ((d, c, n, tot) for (d, c), (n, tot) in acc.items() if n > 0),
        key=lambda x: (-x[2], x[0], x[1]),
    )[:top]
    return [
        CityAction(
            "supply",
            d,
            c,
            n,
            tot,
            n / tot,
            f"{d}: {n} из {tot} запросов на «{category_ru(c)}» не нашли ни одного такого места в заданном "
            "радиусе. Проверить на карте, нет ли пропуска в данных; если места действительно нет — это "
            "кандидат на размещение.",
        )
        for d, c, n, tot in ranked
    ]


def hours_actions(
    pois: Iterable[POI],
    district_for: Callable[[float, float], str | None],
    category_ru: Callable[[str], str],
    top: int = 5,
) -> list[CityAction]:
    """For each of the `top` categories (among HOURS_MATTER, at least MIN_CATEGORY_PLACES places) with the lowest
    share of places that have opening hours: the district with the most places of it lacking hours."""
    total: Counter[str] = Counter()
    with_hours: Counter[str] = Counter()
    by_district: dict[str, Counter[str]] = {}
    districts_total: Counter[tuple[str, str]] = Counter()
    for p in pois:
        if p.category == TRANSIT_CATEGORY or p.category not in HOURS_MATTER:
            continue
        d = district_for(p.lat, p.lon) or NO_DISTRICT
        total[p.category] += 1
        districts_total[d, p.category] += 1
        if p.opening_hours:
            with_hours[p.category] += 1
        else:
            by_district.setdefault(p.category, Counter())[d] += 1
    worst = sorted(
        (c for c, n in total.items() if n >= MIN_CATEGORY_PLACES),
        key=lambda c: (with_hours[c] / total[c], -total[c], c),
    )[:top]
    out: list[CityAction] = []
    for c in worst:
        if not by_district.get(c):
            continue
        d, missing = sorted(by_district[c].items(), key=lambda kv: (-kv[1], kv[0]))[0]
        n_here = districts_total[d, c]
        share = (n_here - missing) / n_here
        out.append(
            CityAction(
                "hours",
                d,
                c,
                missing,
                n_here,
                share,
                f"Запросить часы работы у {missing} {GENITIVE_PLURAL.get(c, category_ru(c))} в районе {d}: "
                f"у {n_here - missing} из {n_here} они есть ({share:.0%}), по городу в целом "
                f"{with_hours[c] / total[c]:.0%}.",
            )
        )
    return out
