"""Dataclasses of the state-object layer. Everything here is JSON-serialisable (`to_dict` / `from_dict`).

A `GovRecord` is one fact bundle about one state object (a ЦОН branch, a sport complex of register № 730). Every
stored field is backed by an `Evidence` snippet that the verifier finds verbatim in the cached source page.

Hours have a scope. `venue`: the schedule of the place a citizen walks into (a ЦОН branch window) - may become
`opening_hours` when day-qualified. `administration`: the office week of the managing body (register № 730 `rrr`/`rrk`
is the reception of the sports school, not the opening of the arena) - stored as `admin_hours`, never as
`opening_hours`.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any

SOURCE = "state_registry"
LICENSE_NOTE = "открытые данные госоргана РК, Закон №401-V (ст. 1 п. 5: свободное использование, обработка, " \
               "повторная публикация)"
SCOPES = ("venue", "administration")
KINDS = ("cson", "sport_facility")
GEO_STATUSES = ("matched_osm", "matched_poi", "unmapped")


@dataclass
class Evidence:
    field: str  # name | address | phone | opening_hours | admin_hours
    url: str  # the page the snippet is a verbatim substring of (= the cache key)
    snippet: str
    fetched_at: str | None = None
    lang: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {k: v for k, v in asdict(self).items() if v is not None}

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Evidence:
        return cls(d["field"], d["url"], d["snippet"], d.get("fetched_at"), d.get("lang"))


@dataclass
class Hours:
    raw: str  # the schedule as printed (ru segment), verbatim
    scope: str  # venue | administration
    opening_hours: str | None = None  # OSM syntax, day-qualified; only for scope == venue
    note: str | None = None  # a second schedule of the same place (e.g. «Выдача» next to «Прием»)
    flags: list[str] = field(default_factory=list)  # needs_days | ambiguous_24h | two_schedules

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Hours:
        return cls(d["raw"], d["scope"], d.get("opening_hours"), d.get("note"), list(d.get("flags") or []))


@dataclass
class Geocode:
    status: str  # matched_osm | matched_poi | unmapped
    lat: float | None = None
    lon: float | None = None
    method: str | None = None  # osm_name_address | osm_address | poi_address | poi_name
    ref: str | None = None  # osm node/way/relation id, or the POI id of the dataset
    ref_name: str | None = None
    name_score: float | None = None
    candidates: int = 0
    reason: str | None = None  # why unmapped (or what was ambiguous)
    license: str | None = None
    fetched_at: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Geocode:
        return cls(**{k: d.get(k) for k in cls.__dataclass_fields__ if k in d})


@dataclass
class GovRecord:
    id: str
    kind: str  # cson | sport_facility
    source: str  # gov4c.kz | data.egov.kz
    url: str  # the page / API URL the record comes from
    name: str
    names: dict[str, str]  # ru / kk / en as the source prints them
    address: dict[str, Any]  # {"raw", "street", "house", "key"} (collect.gov.addr.Address) + "by_lang"
    hours: Hours | None
    evidence: list[Evidence]
    phone_raw: str | None = None  # as printed; a bare local number is not turned into a POI `phone`
    extra: dict[str, Any] = field(default_factory=dict)
    fetched_at: str | None = None
    geocode: Geocode | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id, "kind": self.kind, "source": self.source, "url": self.url, "name": self.name,
            "names": self.names, "address": self.address, "phone_raw": self.phone_raw,
            "hours": self.hours.to_dict() if self.hours else None,
            "evidence": [e.to_dict() for e in self.evidence], "extra": self.extra, "fetched_at": self.fetched_at,
            "geocode": self.geocode.to_dict() if self.geocode else None,
        }

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> GovRecord:
        return cls(
            id=d["id"], kind=d["kind"], source=d["source"], url=d["url"], name=d["name"], names=dict(d["names"]),
            address=dict(d["address"]), hours=Hours.from_dict(d["hours"]) if d.get("hours") else None,
            evidence=[Evidence.from_dict(e) for e in d["evidence"]], phone_raw=d.get("phone_raw"),
            extra=dict(d.get("extra") or {}), fetched_at=d.get("fetched_at"),
            geocode=Geocode.from_dict(d["geocode"]) if d.get("geocode") else None)


def validate_record(r: GovRecord) -> list[str]:
    """Schema problems of a record (empty = fine): scope rules, evidence coverage."""
    errs: list[str] = []
    if r.kind not in KINDS:
        errs.append(f"{r.id}: kind {r.kind!r}")
    if not r.evidence:
        errs.append(f"{r.id}: no evidence")
    covered = {e.field for e in r.evidence}
    if "name" not in covered:
        errs.append(f"{r.id}: name without evidence")
    if r.address.get("raw") and "address" not in covered:
        errs.append(f"{r.id}: address without evidence")
    if r.phone_raw and "phone" not in covered:
        errs.append(f"{r.id}: phone without evidence")
    if r.hours:
        if r.hours.scope not in SCOPES:
            errs.append(f"{r.id}: hours scope {r.hours.scope!r}")
        need = "opening_hours" if r.hours.scope == "venue" else "admin_hours"
        if need not in covered:
            errs.append(f"{r.id}: hours ({r.hours.scope}) without {need} evidence")
        if r.hours.scope == "administration" and r.hours.opening_hours:
            errs.append(f"{r.id}: administration hours must not carry opening_hours")
    for e in r.evidence:
        if len(e.snippet) > 300:
            errs.append(f"{r.id}: snippet of {e.field} longer than 300 chars")
    return errs
