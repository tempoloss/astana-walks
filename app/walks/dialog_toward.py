"""«В сторону Мангилик Ел по пути хочу кофе»: a request toward a street or a place the person does not have saved. The
target is read from the words (`read_toward`), found by the address geocoder of the stand (`TurnEnv.geocode`, a local
gazetteer: nothing leaves the server) and searched along the way to it, like «по пути домой» but toward that point.
When it cannot be found the reply says so and the search is made near the start."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass

from .bookmarks import Ref
from .dialog_strings import s
from .districts import load_districts
from .models import Bookmark

_AREAS = {  # the words of an area (a river or a district) -> the district it is searched toward
    "Есиль": (
        "есиль",
        "есил",
        "есіл",
        "есилю",
        "есиля",
        "есилем",
        "esil",
        "yesil",
        "ишим",
        "ишиму",
        "ишима",
        "ishim",
    ),
    "Нура": ("нура", "нуру", "нуры", "nura"),
    "Сарыарка": ("сарыарка", "сарыарку", "сарыарки", "saryarka"),
    "Байконур": ("байконур", "байконура", "байконуру", "baikonur", "baikonyr"),
    "Алматы": ("алматы",),  # only with «район»: bare, it is the city
}
_AREA_WORD = re.compile(
    r"\b(?:район\w*|ауданы\w*|district|реки|өзені|набережн\w*)\b", re.IGNORECASE
)
Geocode = Callable[[str], tuple[float, float, str] | None]
MAX_TARGET_WORDS = 5
_ON_WAY = r"(?:по\s+пути|по\s+дороге|на\s+пути|on\s+the\s+way|on\s+my\s+way|along\s+the\s+way|жолда|жол\s+бойында)"
_TOWARD = (
    # «в сторону мангилик ел по пути хочу кофе»  /  «хочу кофе в сторону мангилик ел»
    r"(?:в|на|по)\s+сторон[уы]\s+(?P<t>[^,.;!?]+?)"
    r"|(?:по\s+(?:пути|дороге)\s+(?:в\s+сторону|к|в|на)\s+)(?P<t2>[^,.;!?]+?)"
    r"|(?:toward|towards|in\s+the\s+direction\s+of|heading\s+to)\s+(?P<t3>[^,.;!?]+?)"
    r"|(?P<t4>[^,.;!?]+?)\s+(?:жаққа|жағына|бағытына)\s+қарай"
)
_RX = re.compile(
    rf"(?:{_TOWARD})(?=\s+{_ON_WAY}|\s+(?:хочу|нужн\w*|ищу|найди\w*|где|покажи\w*|want|need|find|looking|i\s)|[,.;!?]|\s*$)",
    re.IGNORECASE,
)
_FILLER = re.compile(rf"\s*{_ON_WAY}\s*", re.IGNORECASE)


@dataclass(frozen=True)
class Toward:
    target: str  # the words naming the target («мангилик ел»)
    rest: str  # the message without the phrase («хочу кофе»)
    on_the_way: bool  # the person said «по пути»: a target that is not found is said so


def read_toward(text: str) -> Toward | None:
    """The target of «в сторону X» / «toward X» and the message without those words; None when there is none (or the
    target is longer than a place name)."""
    m = _RX.search(text)
    if m is None:
        return None
    target = next((m.group(g) for g in ("t", "t2", "t3", "t4") if m.group(g)), "").strip(" ,.")
    if not target or len(target.split()) > MAX_TARGET_WORDS:
        return None
    way = bool(_FILLER.search(text))
    rest = " ".join(_FILLER.sub(" ", f"{text[: m.start()]} {text[m.end() :]}").split()).strip(
        " ,.;:-"
    )
    return Toward(target=target, rest=rest, on_the_way=way)


def area_target(target: str) -> tuple[float, float, str] | None:
    """A river or a district named as the target («в сторону Есиля»): the centre of the DISTRICT of that name, never a
    street of the same name («улица Есил»). (lat, lon, label) or None for a target that is not one."""
    low = target.lower()
    marked = bool(_AREA_WORD.search(low))
    words = {w for w in re.findall(r"[^\W\d_]+", low) if not _AREA_WORD.fullmatch(w)}
    for name, spellings in _AREAS.items():
        if words and words <= set(spellings) and (marked or name != "Алматы"):
            district = next((d for d in load_districts() if d.name == name), None)
            if district is None:
                return None
            pts = [p for poly in district.polygons for p in poly[0]]
            if not pts:
                return None
            return (
                round(sum(p[1] for p in pts) / len(pts), 5),
                round(sum(p[0] for p in pts) / len(pts), 5),
                f"район {name}",
            )
    return None


def resolve_toward(
    found: Toward, geocode: Geocode | None, lang: str
) -> tuple[Ref | None, str, str]:
    """(the way to the target as a `Ref`, the sentence that says what was done, the message to search with).
    Found: along the way to it. Not found after a «по пути»: said, and the search is made near the start without the
    phrase. Not found without «по пути» («в сторону моря»): nothing is said and the message stays as it was."""
    hit = area_target(found.target) or (geocode(found.target) if geocode is not None else None)
    if hit is not None:
        lat, lon, label = hit
        name = label or found.target
        bookmark = Bookmark(name=name, kind="other", lat=lat, lon=lon)
        return (
            Ref(bookmark=bookmark, along=True, rest=found.rest),
            s("toward_on", lang, name=name),
            found.rest,
        )
    if found.on_the_way:
        return None, s("toward_missing", lang, name=found.target), found.rest
    return None, "", ""
