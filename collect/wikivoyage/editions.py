"""Edition configuration and wikitext listing parser for the Wikivoyage stage.

Every edition ships a fetched snapshot (`snapshots/<lang>.wikitext` + `<lang>.meta.json`, licence CC BY-SA 4.0,
see `collect/wikivoyage/README.md`). The parser is pure: it reads the snapshot text and returns listings with
section routing, native-name aliases and Wikidata ids - no network, no wiki markup dependency.

Listing fields are aliases of the same three facts:
  * hours  - en/ru `hours`, it `orari`, pl `godziny`, he `שעות`
  * price  - en/ru `price`, it `prezzo`, pl `ceny`, he `מחיר`
  * description - en `content`, it `descrizione`, pl `opis`, ru `description`, he `תיאור`
Listings are taken from the see/do sections (and, for hours and prices only, from eat/drink); buy/sleep listings
never contribute anything.
"""

from __future__ import annotations

import html
import re
from dataclasses import dataclass, field

_QID = re.compile(r"^Q\d+$")
_COMMENT = re.compile(r"<!--.*?-->")


@dataclass(frozen=True)
class Edition:
    lang: str
    title: str
    listing_re: str  # template names that carry listings
    see_sections: frozenset[str]  # top-level sections whose listings describe sights and activities
    eat_sections: frozenset[str]  # top-level sections whose listings contribute hours and prices only
    k_name: str
    k_alt: str
    k_lat: str
    k_lon: str
    k_hours: str
    k_price: str
    k_desc: str
    k_wikidata: str | None
    license_note: str = "CC BY-SA 4.0"


EDITIONS: tuple[Edition, ...] = (
    Edition("en", "Astana", r"\{\{(?:see|do|eat|drink)\b",
            frozenset({"See", "Do"}), frozenset({"Eat", "Drink"}),
            "name", "alt", "lat", "long", "hours", "price", "content", "wikidata"),
    Edition("it", "Astana", r"\{\{(?:see|do|eat|drink)\b",
            frozenset({"Cosa vedere", "Cosa fare"}), frozenset({"Dove mangiare", "Come divertirsi"}),
            "nome", "alt", "lat", "long", "orari", "prezzo", "descrizione", "wikidata"),
    Edition("he", "אסטנה", r"\{\{(?:מוקדי|פעילויות|אוכל|שתייה)\b",
            frozenset({"מוקדי עניין", "פעילויות"}), frozenset({"אוכל", "שתייה וחיי לילה"}),
            "שם", "שם חלופי", "lat", "long", "שעות", "מחיר", "תיאור", "ויקינתונים"),
    Edition("pl", "Astana", r"\{\{zobacz\b",
            frozenset({"Warto zobaczyć"}), frozenset({"Gastronomia", "Co do picia"}),
            "name", "alt", "lat", "long", "godziny", "ceny", "opis", None),
    Edition("ru", "Астана", r"\{\{listing\b",
            frozenset({"Достопримечательности", "Чем заняться"}), frozenset({"Еда", "Ночная жизнь"}),
            "name", "alt", "lat", "long", "hours", "price", "description", "wdid"),
)

_BY_LANG = {e.lang: e for e in EDITIONS}
_HEADER = re.compile(r"^=+([^=].*?)=+\s*$", re.MULTILINE)


def edition_of(lang: str) -> Edition:
    return _BY_LANG[lang]


@dataclass
class Listing:
    edition: str
    section: str  # "see" | "eat"
    name: str
    alt: str
    lat: float | None
    lon: float | None
    wikidata: str | None
    hours: str | None
    price: str | None
    description: str | None


@dataclass
class Article:
    edition: str
    title: str
    pageid: int
    snapshot_date: str
    listings: list[Listing] = field(default_factory=list)


def _fields_of(body: str) -> dict[str, str]:
    return {k.strip(): " ".join(html.unescape(v.strip()).replace("\u00a0", " ").split())
            for k, v in re.findall(r"\|\s*([^=|\n]*?)\s*=\s*([^\n|]*)", body)}


def _top_section(text: str, pos: int) -> str:
    """Name of the top-level (`== X ==`) section the position is inside: a listing of a `=== Palaces ===` subsection
    belongs to `See`, never to the subsection."""
    top = ""
    top_level = 2
    for m in _HEADER.finditer(text):
        if m.start() >= pos:
            break
        level = len(m.group(0)) - len(m.group(0).lstrip("="))
        if level <= top_level:
            top, top_level = m.group(1).strip(), level
    return top


def parse_article(lang: str, text: str, title: str, pageid: int, snapshot_date: str) -> Article:
    ed = edition_of(lang)
    art = Article(lang, title, pageid, snapshot_date)
    for m in re.finditer(ed.listing_re + r"((?:[^{}]|\{\{[^}]*\}\})*)\}\}", text, re.S):
        f = _fields_of(m.group(1))
        section = _top_section(text, m.start())
        kind = "eat" if section in ed.eat_sections else ("see" if section in ed.see_sections else "other")
        if kind == "other":
            continue
        lat = _float(_COMMENT.sub("", f.get(ed.k_lat, "")))
        lon = _float(_COMMENT.sub("", f.get(ed.k_lon, "")))
        wd = (f.get(ed.k_wikidata) or "").strip() if ed.k_wikidata else ""
        art.listings.append(Listing(
            edition=lang, section=kind, name=f.get(ed.k_name, "") or "", alt=f.get(ed.k_alt, "") or "",
            lat=lat, lon=lon, wikidata=wd if _QID.match(wd) else None,
            hours=f.get(ed.k_hours, "") or None,
            price=f.get(ed.k_price, "") or None,
            description=f.get(ed.k_desc, "") or None))
    return art


def _float(text: str | None) -> float | None:
    text = (text or "").strip()
    try:
        return float(text)
    except ValueError:
        return None


def fields_of_interest(l: Listing) -> tuple[str, ...]:
    """Which dataset fields the listing may fill: eat/drink listings contribute hours and prices only."""
    if l.section == "eat":
        return tuple(f for f in ("hours", "price") if getattr(l, f))
    return tuple(f for f in ("hours", "price", "description") if getattr(l, f))
