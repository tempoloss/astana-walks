"""The «Данные» page: where the facts come from (one card per source: what it gives, how much of it is in the base,
its licence and the links to the source and to the licence), how complete they are (coverage counted live from the
dataset the assistant uses, by field, category and district) and how honest the answers measured (the offline
evaluation of app/eval/results, read as it is). Numbers and links only; the wording is the page's (i18n)."""

from __future__ import annotations

import json
from collections import Counter
from functools import cache
from pathlib import Path
from urllib.parse import urlparse

from walks import mobility
from walks.districts import DEFAULT_PATH as DISTRICTS_PATH
from walks.districts import district_of, load_districts
from walks.events import load_snapshot
from walks.i18n import category_name
from walks.models import MUSEUM_REGISTER, OFFICIAL_SITE, POI, STATE_REGISTRY, WIKIVOYAGE
from walks.pipeline import get_pois
from walks.retrieve import TRANSIT_CATEGORY
from walks.walking import own_router

RESULTS = Path(__file__).resolve().parents[1] / "eval" / "results"
# (key on the page, summary file of app/eval/results); the held-out set written after the fixes is the honest one
EVAL_RUNS = (
    ("main", "summary_poi.enriched_offline.json"),
    ("holdout3", "summary_poi.enriched_holdout3_offline.json"),
    ("abstain", "summary_poi.enriched_abstain_offline.json"),
)
EVAL_KEYS = (
    "cases",
    "recs_total",
    "hallucinated_poi",
    "honest_unknown_rate",
    "constraint_ok_rate",
    "case_all_ok_rate",
    "honest_abstain_rate",
    "unknown_hours_rec_share",
)

CC0 = ("CC0 1.0", "https://creativecommons.org/publicdomain/zero/1.0/")
CC_BY = ("CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/")
CC_BY_SA = ("CC BY-SA 4.0", "https://creativecommons.org/licenses/by-sa/4.0/")
ODBL = ("ODbL 1.0", "https://www.openstreetmap.org/copyright")
# the cards of the page, in the order shown: (id, group, unit of `count`, links to the source, licences).
# Addresses and licences are those of data/ATTRIBUTION.md and docs/licensing.md. `count` is filled from the data.
_CARDS: tuple[tuple[str, str, str | None, tuple[str, ...], tuple[tuple[str, str], ...]], ...] = (
    ("osm", "places", "places", ("https://www.openstreetmap.org",), (ODBL,)),
    (
        "overture",
        "places",
        "places",
        ("https://overturemaps.org", "https://docs.overturemaps.org/attribution/"),
        (
            ("CDLA-Permissive-2.0", "https://cdla.dev/permissive-2-0/"),
            ("Apache-2.0 · Foursquare", "https://opensource.foursquare.com/places-notice-txt/"),
            CC0,
        ),
    ),
    ("wikidata", "places", "places", ("https://www.wikidata.org",), (CC0,)),
    ("wikipedia", "places", "places", ("https://www.wikipedia.org",), (CC_BY_SA,)),
    ("wikivoyage", "places", "places", ("https://www.wikivoyage.org",), (CC_BY_SA,)),
    ("sites", "places", "places", (), ()),
    ("museums", "places", "places", ("https://e-museum.kz",), ()),
    (
        "gov",
        "places",
        "places",
        ("https://gov4c.kz", "https://data.egov.kz"),
        (("401-V", "https://adilet.zan.kz/rus/docs/Z1500000401"),),
    ),
    (
        "met",
        "weather",
        None,
        ("https://api.met.no",),
        (CC_BY, ("NLOD 2.0", "https://data.norge.no/nlod/en/2.0")),
    ),
    (
        "kazhydromet",
        "weather",
        None,
        ("https://www.kazhydromet.kz",),
        (("№ 267", "https://old.adilet.zan.kz/rus/docs/V2100023716"),),
    ),
    (
        "openmeteo",
        "weather",
        None,
        ("https://open-meteo.com",),
        (("CC BY 4.0", "https://open-meteo.com/en/licence"),),
    ),
    ("valhalla", "moving", None, (), (ODBL,)),  # the source links depend on whose router it is
    ("gtfs", "moving", "stops", ("https://zenodo.org/records/15769359",), (CC_BY,)),
    ("airport", "moving", None, ("https://nn-airport.kz",), ()),
    (
        "basemap",
        "moving",
        None,
        ("https://openfreemap.org",),
        (ODBL, ("OpenMapTiles", "https://openmaptiles.org/")),
    ),
    (
        "afisha",
        "city",
        "events",
        (
            "https://sxodim.com",
            "https://inastana.kz",
            "https://youticket.kz",
            "https://qazaqconcert.kz",
            "https://alem.ai",
        ),
        (),
    ),
    ("marks", "city", None, (), ()),
)
VALHALLA_OWN = ("https://github.com/valhalla/valhalla",)
VALHALLA_PUBLIC = (
    "https://github.com/valhalla/valhalla",
    "https://www.fossgis.de/arbeitsgruppen/osm-server/nutzungsbedingungen/",
)


def _pct(n: int, total: int) -> float:
    return round(100 * n / total, 1) if total else 0.0


def _official_domains(pois: list[POI]) -> int:
    hosts = {
        urlparse(fs.get("url") or "").hostname
        for p in pois
        for fs in p.field_sources.values()
        if fs.get("source") == OFFICIAL_SITE
    }
    return len(hosts - {None})


_DISTRICT_SUFFIX = {
    "kk": " ауданы",
    "en": " audany",
}  # «Нұра ауданы» -> «Нұра»: every district named the same way


def _district_labels(lang: str) -> dict[str, str]:
    """The district names the geometry module returns (Russian, without «район») -> the name in `lang`."""
    try:
        features = json.loads(DISTRICTS_PATH.read_text(encoding="utf-8")).get("features", [])
    except (OSError, ValueError):
        return {}
    out: dict[str, str] = {}
    for f in features:
        props = f.get("properties") or {}
        key = str(props.get("name:ru") or props.get("name") or "").removeprefix("район ").strip()
        if key:
            own = str(props.get(f"name:{lang}") or key) if lang != "ru" else key
            out[key] = own.removesuffix(_DISTRICT_SUFFIX.get(lang, "")).strip()
    return out


def _by_district(places: list[POI], lang: str) -> list[dict]:
    """Places and the share with known hours per district; places outside every district are left out."""
    districts = load_districts()
    labels = _district_labels(lang)
    rows: dict[str, list[int]] = {}
    for p in places:
        name = district_of(p.lat, p.lon, districts)
        if name:
            row = rows.setdefault(name, [0, 0])
            row[0] += 1
            row[1] += bool(p.opening_hours)
    return sorted(
        (
            {"label": labels.get(name, name), "places": n, "hours": _pct(h, n)}
            for name, (n, h) in rows.items()
        ),
        key=lambda r: (-r["places"], r["label"]),
    )


def _coverage(pois: list[POI], lang: str) -> dict:
    places = [p for p in pois if p.category != TRANSIT_CATEGORY]
    total = len(places)
    hours_by = Counter(p.hours_source() for p in places)
    by_cat: dict[str, list[int]] = {}
    for p in places:
        row = by_cat.setdefault(p.category, [0, 0])
        row[0] += 1
        row[1] += bool(p.opening_hours)
    return {
        "places": total,
        "hours": _pct(sum(bool(p.opening_hours) for p in places), total),
        "hours_osm": _pct(hours_by["osm"], total),
        "hours_site": _pct(
            sum(1 for p in places if p.opening_hours and p.hours_source() == OFFICIAL_SITE), total
        ),
        "phone": _pct(sum(bool(p.phone) for p in places), total),
        "website": _pct(sum(bool(p.website) for p in places), total),
        "address": _pct(sum(bool(p.address) for p in places), total),
        "description": _pct(sum(p.has_real_description() for p in places), total),
        "categories": sorted(
            (
                {"label": category_name(c, lang), "places": n, "hours": _pct(h, n)}
                for c, (n, h) in by_cat.items()
            ),
            key=lambda r: (-r["places"], r["label"]),
        ),
        "districts": _by_district(places, lang),
    }


def _with_field_from(pois: list[POI], source: str) -> int:
    """How many places carry at least one fact that was read from `source`."""
    return sum(
        1 for p in pois if any(fs.get("source") == source for fs in p.field_sources.values())
    )


def _sources(pois: list[POI]) -> dict:
    def has(source: str) -> int:
        return sum(1 for p in pois if source in (p.sources or [p.source]))

    dates = sorted(p.collected_at[:10] for p in pois if p.collected_at)
    return {
        "osm": has("osm"),
        "overture": has("overture"),
        "wikidata": has("wikidata"),
        "wikipedia": sum(1 for p in pois if p.wikipedia),
        "official_site": has(OFFICIAL_SITE),
        "official_domains": _official_domains(pois),
        "museum_register": _with_field_from(pois, MUSEUM_REGISTER),
        "state_registry": _with_field_from(pois, STATE_REGISTRY),
        "wikivoyage": _with_field_from(pois, WIKIVOYAGE),
        "stops": _stops(),
        "events": len(load_snapshot().events),
        "date_from": dates[0] if dates else None,
        "date_to": dates[-1] if dates else None,
    }


def _stops() -> int:
    """Bus stops of the GTFS file (they are not places of the base: the assistant only names the nearest one)."""
    try:
        stops = json.loads((mobility.DATA_DIR / "stops.json").read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return 0
    return len(stops) if isinstance(stops, list) else 0


def _cards(sources: dict) -> list[dict]:
    """One card per source: its count (None where the source is not a count of the base), its links and licences."""
    counts = {
        "osm": sources["osm"],
        "overture": sources["overture"],
        "wikidata": sources["wikidata"],
        "wikipedia": sources["wikipedia"],
        "wikivoyage": sources["wikivoyage"],
        "sites": sources["official_site"],
        "museums": sources["museum_register"],
        "gov": sources["state_registry"],
        "gtfs": sources["stops"],
        "afisha": sources["events"],
    }
    out = []
    for key, group, unit, links, licences in _CARDS:
        if key == "valhalla":
            links = VALHALLA_OWN if own_router() else VALHALLA_PUBLIC
        out.append(
            {
                "id": key,
                "group": group,
                "unit": unit,
                "count": counts.get(key) if unit else None,
                "links": list(links),
                "licences": [{"label": label, "url": url} for label, url in licences],
            }
        )
    return out


def _eval() -> dict:
    out: dict[str, dict] = {}
    for key, name in EVAL_RUNS:
        try:
            raw = json.loads((RESULTS / name).read_text(encoding="utf-8"))
        except (OSError, ValueError):
            continue
        row = {k: raw.get(k) for k in EVAL_KEYS}
        row["date"] = str((raw.get("header") or {}).get("generated_at", ""))[:10] or None
        out[key] = row
    return out


@cache
def _summary(lang: str) -> dict:
    pois = get_pois()
    return {
        "sources": _sources(pois),
        "coverage": _coverage(pois, lang),
        "eval": _eval(),
    }


def data_info(lang: str) -> dict:
    """The page's numbers; the cards are assembled per call because whose router it is depends on the environment."""
    summary = _summary(lang)
    return summary | {"cards": _cards(summary["sources"])}
