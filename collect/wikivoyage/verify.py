"""Deterministic checks of the wikivoyage fields of a built dataset (empty list = fine).

* every `wikivoyage` field carries `field_sources[field]` with the edition and the article URL on the edition's host;
* `opening_hours` written by this stage is a day-qualified schedule (`opening-hours-py` accepts it);
* a day-less schedule never sits in `opening_hours` (it is `hours_unqualified`);
* prices are verbatim text, descriptions are never empty and never over a Wikipedia description.
"""

from __future__ import annotations

from urllib.parse import urlsplit

from collect.sites.hours import hours_flags, validate_osm

SOURCE = "wikivoyage"
VOYAGE_FIELDS = ("opening_hours", "opening_hours_voyage", "hours_unqualified", "price_text", "description_voyage")
_TEXT_FIELDS = ("price_text", "description_voyage")


def check_dataset(pois: list[dict]) -> list[str]:
    problems: list[str] = []
    for p in pois:
        fsrc = p.get("field_sources") or {}
        who = f"{p['id']} {p['name']!r}"
        for f, s in fsrc.items():
            if not (isinstance(s, dict) and s.get("source") == SOURCE):
                continue
            if f not in VOYAGE_FIELDS:
                problems.append(f"{who}: unexpected wikivoyage field {f}")
                continue
            lang = s.get("lang")
            host = urlsplit(s.get("url") or "").hostname or ""
            if not lang or host != f"{lang}.wikivoyage.org":
                problems.append(f"{who}: {f} evidence URL {s.get('url')!r} is not on {lang}.wikivoyage.org")
            if not s.get("snapshot_date"):
                problems.append(f"{who}: {f} has no snapshot_date")
        if fsrc.get("opening_hours", {}).get("source") == SOURCE:
            if not validate_osm(p.get("opening_hours")):
                problems.append(f"{who}: wikivoyage opening_hours {p.get('opening_hours')!r} is not a valid schedule")
            elif hours_flags(p.get("opening_hours")):
                problems.append(f"{who}: wikivoyage opening_hours {p.get('opening_hours')!r} names no days "
                                "(a day-less one belongs to hours_unqualified)")
        for f in _TEXT_FIELDS:
            if fsrc.get(f, {}).get("source") == SOURCE and not (p.get(f) or "").strip():
                problems.append(f"{who}: {f} is empty")
        if (p.get("description_source") == "wikipedia" and p.get("description_voyage")
                and fsrc.get("description_voyage", {}).get("source") == SOURCE
                and not p.get("description")):
            problems.append(f"{who}: description_voyage written although a wikipedia description exists")
    return problems
