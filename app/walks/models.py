"""Pydantic models shared by the pipeline stages."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator

from .i18n import radius_text, t

CATEGORIES = [
    "cafe",
    "restaurant",
    "fast_food",
    "bar_nightlife",
    "museum_gallery",
    "attraction_landmark",
    "viewpoint",
    "park_garden",
    "kids_playground",
    "entertainment",
    "mall",
    "culture_theatre_cinema",
    "coworking_library",
    "public_toilet",
    "pharmacy",
    "grocery",
    "money",
    "lodging",
    "clinic",
    "post",
    "sport",
    "other",
]
Category = Literal[
    "cafe",
    "restaurant",
    "fast_food",
    "bar_nightlife",
    "museum_gallery",
    "attraction_landmark",
    "viewpoint",
    "park_garden",
    "kids_playground",
    "entertainment",
    "mall",
    "culture_theatre_cinema",
    "coworking_library",
    "sport",
    "public_toilet",
    "pharmacy",
    "grocery",
    "money",
    "lodging",
    "clinic",
    "post",
    "other",
]
Mode = Literal["walk", "car", "transit"]
HoursState = Literal["open", "closed", "unknown"]
Confidence = Literal["high", "medium", "low"]
Language = Literal["ru", "kk", "en"]
Budget = Literal["any", "low", "medium", "high"]
WeatherHint = Literal["none", "cold", "rain", "heat", "smog"]
Refusal = Literal["none", "drugs", "sex", "weapons"]
Diet = Literal["vegetarian", "vegan", "gluten_free", "kosher"]
# How a card relates to the declared radius and the requested categories: "none" = requested kind inside the
# declared radius; "expanded" = requested kind, but found only after the radius was widened; "backfill" = another
# category added because too few requested ones were in range; "substituted" = an indoor place offered INSTEAD of the
# requested outdoor kind because of frost / heavy precipitation / smog (the shelter rule): not a supply shortage, but
# still not what was asked for, so the card says so.
Padding = Literal["none", "expanded", "backfill", "substituted"]

# Shipped dataset: OSM + Overture + Wikipedia + the businesses' own websites, built by `python -m collect.build`.
# data/poi.json stays as the OSM-only baseline the eval compares against.
DEFAULT_POI_PATH = Path(__file__).resolve().parents[2] / "data" / "poi.enriched.json"
OFFICIAL_SITE = "official_site"  # `sources` / `field_sources[<field>].source` of a fact read from the business's own site
STATE_REGISTRY = "state_registry"  # `sources` / `field_sources[<field>].source` of a fact of a state body's register
MUSEUM_REGISTER = "museum_register"  # `field_sources[<field>].source` of a fact of the e-museum.kz museum register
WIKIVOYAGE = "wikivoyage"  # `sources` / `field_sources[<field>].source` of a fact from the Wikivoyage guide (CC BY-SA)
GOV_SERVICE_TAG = "gov_service=cson"  # the tag of a ЦОН record (category `other`, see collect/gov)
# the suffix of the i18n keys that name whose hours a sentence is about (`hours_state_open_site`, `fact_open_gov`, ...);
# OSM's hours are the keys without a suffix, or `_osm` where there is one
HOURS_SUFFIX = {
    OFFICIAL_SITE: "site",
    STATE_REGISTRY: "gov",
    MUSEUM_REGISTER: "register",
    WIKIVOYAGE: "voyage",
}
# Why the hours of a card are not (only) the plain verdict of the opening-hours string:
# conflict = OSM and the website give different weekly schedules (OSM is kept, the card says so);
# split = at the request time one of them says open and the other closed (the state is unknown);
# unqualified = the website names hours without days («с 10:00 до 22:00»), which never decide open / closed.
HoursIssue = Literal["", "conflict", "split", "unqualified"]


class POI(BaseModel):
    """One record of data/poi.enriched.json (OSM, Overture, Wikipedia, official sites; see `sources`)."""

    model_config = ConfigDict(extra="ignore")

    id: str
    name: str
    names: dict[str, str] = Field(default_factory=dict)
    name_generated: bool = False
    lat: float
    lon: float
    category: str
    tags: list[str] = Field(default_factory=list)
    opening_hours: str | None = None
    website: str | None = None
    phone: str | None = None
    address: str | None = None
    address_kk: str | None = None  # kk spelling of `address`: the RCA register, see `collect/gov`
    wheelchair: str | None = None
    internet_access: str | None = None
    outdoor_seating: str | None = None
    description: str | None = None
    description_auto: str | None = None
    description_source: str | None = None
    source: str = "osm"
    collected_at: str | None = None
    sources: list[str] = Field(
        default_factory=list
    )  # data providers of the record: osm, overture, official_site, ...
    wikipedia: dict[str, dict[str, str]] = Field(
        default_factory=dict
    )  # lang -> {title, url, extract}
    popularity_pageviews: int | None = (
        None  # Wikimedia views of its articles, summed over languages, one month
    )
    # What the business's own website says (collect/sites). `opening_hours` is the OSM string, or the website's when
    # the record had none (then `field_sources.opening_hours.source` is "official_site").
    opening_hours_official: str | None = (
        None  # the website's day-qualified hours (OSM syntax) when OSM has its own
    )
    hours_conflict: bool = (
        False  # both exist and their weekly schedules differ; `opening_hours` stays OSM's
    )
    hours_unqualified: str | None = (
        None  # raw website hours without days: never drive open / closed
    )
    description_official: str | None = None  # the website's own description of the place
    price_text: str | None = (
        None  # the website's own price wording («вход — 1000 тг»); never parsed into a number
    )
    description_voyage: str | None = (
        None  # the Wikivoyage (collect/wikivoyage) description of the place: third-party CC BY-SA text
    )
    # What a state registry says (collect/gov, `sources` contains `state_registry`): the administration's office week of
    # a sports object (never `opening_hours`), a ЦОН schedule that differs from the hours the record already had, and
    # the match of the record (kind, method, url).
    admin_hours: dict[str, Any] | None = None
    opening_hours_state: str | None = None
    state_registry_match: dict[str, Any] | None = None
    field_sources: dict[str, dict[str, Any]] = Field(
        default_factory=dict
    )  # field -> {source, license, snapshot_date, url, snippet, ...}

    def tag_dict(self) -> dict[str, str]:
        out: dict[str, str] = {}
        for tag in self.tags:
            k, _, v = tag.partition("=")
            out[k] = v
        return out

    def is_state_service(self) -> bool:
        """A state service centre of the registry layer (ЦОН): a place for an explicit state-service request only,
        never a walking destination."""
        return GOV_SERVICE_TAG in self.tags

    def name_for(self, lang: str | None) -> str:
        """The name to show in `lang`: an English answer takes the record's English name (OSM `name:en`, else the title
        of its English Wikipedia article without the bracketed note), every other one the record's `name`."""
        if lang == "en":
            title = (self.wikipedia.get("en") or {}).get("title", "").split(" (")[0].strip()
            return self.names.get("name:en") or title or self.name
        return self.name

    def data_label(self, lang: str | None = "ru") -> str:
        """Where the record comes from, decided by code: 'OSM', 'OSM + Overture', 'OSM + официальный сайт', ..."""
        names = {
            "osm": "OSM",
            "overture": "Overture",
            OFFICIAL_SITE: t("src_official_site", lang),
            STATE_REGISTRY: t("src_state_registry", lang),
            MUSEUM_REGISTER: t("src_museum_register", lang),
            WIKIVOYAGE: t("src_wikivoyage", lang),
        }
        out = [names.get(s, s) for s in (self.sources or [self.source])]
        if self.description_source == "wikipedia" and "Wikipedia" not in out:
            out.append("Wikipedia")
        return " + ".join(out)

    def has_real_description(self) -> bool:
        """True for a human-written description (OSM tag, Wikipedia or the place's own website), False for one
        derived from tags."""
        return self.description_source in {"osm", "wikipedia"} or bool(self.description_official)

    def real_text(self) -> str:
        """The human-written descriptions of the record, joined: what a claim about the place may rest on."""
        parts = [
            self.description if self.description_source in {"osm", "wikipedia"} else "",
            self.description_official,
        ]
        return " ".join(p for p in parts if p)

    def _source_url(self, field: str) -> str | None:
        return self.field_sources.get(field, {}).get("url") or None

    def address_kk_source_url(self) -> str | None:
        """The page of the register the kk street spelling came from; None when there is no `address_kk`."""
        return self._source_url("address_kk") if self.address_kk else None

    def hours_source(self) -> str | None:
        """Where the hours of the card come from: the source of `opening_hours` (`osm` unless the record says
        otherwise), the source of the day-less text when hours name no days, None without any hours."""
        if self.opening_hours:
            return self.field_sources.get("opening_hours", {}).get("source") or "osm"
        if self.hours_unqualified:
            return self.field_sources.get("hours_unqualified", {}).get("source") or OFFICIAL_SITE
        return None

    def hours_source_url(self) -> str | None:
        """The page of the business's own website (or the register card) that the hours of the card (or the note
        beside them) were read from; None when the hours are OSM's alone."""
        if self.opening_hours:
            if self.hours_source() in (OFFICIAL_SITE, STATE_REGISTRY, MUSEUM_REGISTER, WIKIVOYAGE):
                return self._source_url("opening_hours")
            if self.hours_conflict and self.opening_hours_official:
                return self._source_url("opening_hours_official")
            return None
        return self._source_url("hours_unqualified") if self.hours_unqualified else None

    def wikivoyage_url(self) -> str | None:
        """The Wikivoyage article the first wikivoyage-sourced field of the record was read from."""
        for s in (self.field_sources or {}).values():
            if isinstance(s, dict) and s.get("source") == WIKIVOYAGE:
                return s.get("url") or None
        return None

    def official_description_credit(self, lang: str = "ru") -> tuple[str, str | None] | None:
        """Attribution for the website's description: (text, page url) or None."""
        if not self.description_official:
            return None
        return t("src_official_site", lang), self._source_url("description_official")

    def voyage_description_credit(self, lang: str = "ru") -> tuple[str, str | None] | None:
        """Attribution for the Wikivoyage description (third-party CC BY-SA text): (label, article url) or None."""
        if not self.description_voyage:
            return None
        return t("src_wikivoyage", lang), self._source_url("description_voyage")

    def wikipedia_credit(self, lang: str = "ru") -> tuple[str, str | None] | None:
        """Attribution for a Wikipedia-sourced description: (text, article url) or None."""
        if self.description_source != "wikipedia":
            return None
        art = self.wikipedia.get(lang) or next(iter(self.wikipedia.values()), {})
        return "Wikipedia, CC BY-SA 4.0", art.get("url")


def poi_path() -> Path:
    override = os.environ.get("POI_PATH")
    return Path(override) if override else DEFAULT_POI_PATH


def load_pois(path: str | Path | None = None) -> list[POI]:
    p = Path(path) if path else poi_path()
    return [POI.model_validate(r) for r in json.loads(p.read_text(encoding="utf-8"))]


class Intent(BaseModel):
    """Structured user request. Also used as the Gemini response schema."""

    time_budget_min: int = Field(
        60, description="Total time the user has, in minutes (travel + time on site)."
    )
    mode: Mode = Field("walk", description="How the user moves: walk, car or transit.")
    categories: list[Category] = Field(
        default_factory=list,
        description="POI categories the user explicitly or clearly implicitly wants. Empty if no preference.",
    )
    with_kids: bool = Field(False, description="User is with a child / children.")
    quiet: bool = Field(False, description="User wants a quiet, calm place.")
    needs_wifi_socket: bool = Field(
        False, description="User needs Wi-Fi and/or power sockets (e.g. to work)."
    )
    night: bool = Field(False, description="User wants a night-time / late-evening activity.")
    accessibility: bool = Field(False, description="User needs wheelchair / step-free access.")
    budget: Budget = Field(
        "any", description="Spending preference: any, low (cheap/free), medium, high."
    )
    language: Language = Field("ru", description="Language of the user's message; answer in it.")
    free_text_keywords: list[str] = Field(
        default_factory=list,
        description="Up to 8 short search keywords (lowercase, in the user's language) capturing the "
        "specific wish, e.g. 'арт', 'вид на город', 'настольные игры'. No place names of the user's location.",
    )
    # The fields below are read from the user's own words by the rule parser only: a model's value is ignored
    # (walks.intent.merge_intents), and they are not part of the draft shown to the model.
    weather_hint: WeatherHint = Field(
        "none",
        description="Rule-parser field, leave as default. Weather the user's own words state.",
    )
    exclude_categories: list[Category] = Field(
        default_factory=list,
        description="Rule-parser field, leave empty. Kinds the user has just visited.",
    )
    halal: bool = Field(False, description="Rule-parser field, leave false.")
    mode_explicit: bool = Field(False, description="Rule-parser field, leave false.")
    minor: bool = Field(
        False, description="Rule-parser field, leave false. The request names a minor."
    )
    refusal: Refusal = Field(
        "none",
        description="'none' unless the user asks for drugs, sex services or weapons (then drugs / sex / weapons).",
    )
    diets: list[Diet] = Field(
        default_factory=list,
        description="Rule-parser field, leave empty. Diets the user's own words state.",
    )
    landmark_refs: list[str] = Field(
        default_factory=list,
        description="Rule-parser field, leave empty. Landmarks a vague description points at.",
    )
    plan_order: list[Category] = Field(
        default_factory=list,
        description="Rule-parser field, leave empty. Stops in the order the user listed them.",
    )
    group_size: int = Field(
        0,
        description="Rule-parser field, leave 0. How many people the user says they are (0: not said).",
    )
    price_cap_kzt: int = Field(
        0, description="Rule-parser field, leave 0. A spending cap in tenge the user's words state."
    )
    pets: bool = Field(
        False, description="Rule-parser field, leave false. A dog / cat comes along."
    )
    info_about: list[str] = Field(
        default_factory=list,
        description="Rule-parser field, leave empty. The named place the user asks a question ABOUT.",
    )
    wished: list[Category] = Field(
        default_factory=list,
        description="Rule-parser field, leave empty. The kinds of place the user's own words NAME (a kind or an "
        "activity such as a stroll; not a default of a mood): a stated wish that no system default replaces.",
    )
    refused: list[Category] = Field(
        default_factory=list,
        description="Rule-parser field, leave empty. The kinds the user's own words rule out («не хочу в кафе»).",
    )
    local_food: bool = Field(
        False,
        description="Rule-parser field, leave false. The user asks for Kazakh / national food.",
    )
    time_stated: bool = Field(
        False,
        description="Rule-parser field, leave false. The user's words or a tap set the time budget (not a default).",
    )
    eat: bool = Field(
        False, description="Rule-parser field, leave false. Food is asked, not a coffee."
    )
    subkind: str = Field(
        "",
        description="Rule-parser field, leave empty. A kind inside a category: atm, dentist, doctor, "
        "kids_doctor, kazpost, play.",
    )
    sick: Literal["", "child", "adult"] = Field(
        "",
        description="Rule-parser field, leave empty. Somebody is ill (a fever, a cough, «заболел»): a clinic or a pharmacy "
        "is wanted for them (`child`: a child is the sick one, so a children's or general clinic comes before a dentist).",
    )
    work_needs: str = Field(
        "",
        description="Rule-parser field, leave empty. What a work wish names: wifi, socket or both.",
    )


class LLMAttempt(BaseModel):
    """One try of one model in the fallback chain."""

    model: str
    status: Literal["ok", "error", "skipped"]
    detail: str = ""  # error code / 'timeout' / why the model was skipped
    ms: int = 0


class LLMStep(BaseModel):
    """What happened in one LLM call (intent refinement or generation): chain, attempts, timing, cache."""

    chain: list[str]  # configured models, in order
    model: str | None = None  # the model whose answer was used (None: the whole chain failed)
    attempts: list[LLMAttempt] = Field(default_factory=list)
    ms: int = 0
    cached: bool = False

    def attempts_text(self) -> str:
        """'gemini-3.5-flash: 503 (1.2 s) → gemini-flash-latest: ok (3.1 s)'; 'из кэша' for a cache hit."""
        if self.cached:
            return f"из кэша ({self.model})"
        parts = []
        for a in self.attempts:
            what = {"ok": "ok", "skipped": f"пропущена ({a.detail})"}.get(a.status, a.detail)
            parts.append(
                f"{a.model}: {what}" + (f" ({a.ms / 1000:.1f} с)" if a.status != "skipped" else "")
            )
        return " → ".join(parts) or "—"


class IntentResult(BaseModel):
    intent: Intent  # the merged intent the pipeline uses
    parser: Literal["rules", "rules+llm"]
    note: str = ""  # adjustments applied / why the LLM was not used
    rules: Intent | None = None  # what the rule parser produced alone
    llm: Intent | None = None  # what the LLM returned alone (None: not called or failed)
    llm_step: LLMStep | None = None


class PeopleEvidence(BaseModel):
    """What anonymous marks of people (data/city_feedback.json) say about one place, inside the decay window.
    Never mixed into `hours_state` (that stays the OSM verdict); shown as its own evidence level."""

    hours: Literal["open", "closed", "mixed"] | None = None
    n_open: int = 0
    n_closed: int = 0
    last_hours_date: str | None = None  # ISO day of the newest «был: открыто / закрыто»
    confidence: Literal["medium", "low"] = (
        "low"  # of the hours verdict: contradiction or one mark = low
    )
    socket: int = 0  # marks «есть розетка»
    wifi: int = 0  # marks «есть Wi‑Fi»
    quiet: int = 0
    noisy: int = 0
    noise: Literal["quiet", "noisy", "mixed"] | None = None  # verdict of quiet vs noisy marks
    demo: bool = False  # every mark behind this evidence is a seeded demo entry


class StartHints(BaseModel):
    """What a person tapped next to the input box before a NEW search («сколько времени», «с кем»); never part of
    an LLM payload. The words of the message win over it (a time they state, a company they name)."""

    budget_min: int | None = Field(None, description="30, 60 or 120 minutes")
    company: Literal["solo", "pair", "kids"] | None = None


class Constraints(BaseModel):
    """What the dialogue (and a few profile flags) narrow on top of the Intent; never sent to the LLM."""

    radius_factor: float = (
        1.0  # < 1: a slow walking pace, or «а поближе?» when nothing was shown yet
    )
    radius_cap_m: int | None = (
        None  # «а поближе?»: not farther than this (closer than the last answer)
    )
    radius_floor_m: int | None = (
        None  # no time stated: search as wide as a 90-min outing reaches (walks.pipeline)
    )
    exclude_ids: list[str] = Field(default_factory=list)  # shown already: «ещё», «что-то другое»
    no_alcohol: bool = False
    avoid: list[Category] = Field(
        default_factory=list
    )  # the profile's «не показывать», unless the request names the kind: never retrieved, never backfilled


class Bookmark(BaseModel):
    """A place the user named on their own device («дом», «школа»): sent with one request, used for that request only,
    never stored, never logged. The coordinates are rounded to ~100 m on input."""

    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=40)
    kind: Literal["home", "work", "study", "other"] = "other"
    lat: float = Field(ge=-90, le=90)
    lon: float = Field(ge=-180, le=180)

    @model_validator(mode="after")
    def _round(self) -> Bookmark:
        self.lat, self.lon = round(self.lat, 3), round(self.lon, 3)
        return self


class Personal(BaseModel):
    """The part of a personal profile that retrieval reads. `about` (the user's own free text) is the one field that
    also reaches the model, in the intent and the generation prompts; the rest stays inside retrieval."""

    visited: list[str] = Field(default_factory=list)  # poi ids: ranked lower
    liked: dict[str, int] = Field(default_factory=dict)  # category -> how many times marked liked
    about: str = ""  # <= 500 chars, the user's own words; narrows only, never echoed into an answer
    kids_age_band: str | None = (
        None  # "0-3" | "4-7" | "8-12" | "13+": which places for a child rank first
    )
    vibe: dict[str, float] = Field(default_factory=dict)  # facet -> weight (walks.vibe)


class Conversation(BaseModel):
    """One dialogue, session only: the last request and what it showed. Never sent anywhere, never logged."""

    intent: Intent  # the intent the last answer was built from (profile flags included)
    private: bool = (
        False  # profile data entered the intent: such answers are never written to the request log
    )
    constraints: Constraints
    shown_ids: list[str] = Field(default_factory=list)
    farthest_m: int = 0  # farthest place the last answer offered: «поближе» goes closer than this
    nearest_m: int = 0  # walking metres of its nearest card, as shown: a «поближе» search reaches at least that far
    lat: float  # the last origin, already rounded
    lon: float
    turns: int = 1


class WeatherWarning(BaseModel):
    """An official Kazhydromet notice for Astana: a storm warning (ОЯ) or the daily bulletin of unfavourable
    meteorological conditions (НМУ, smog). `text` is the notice verbatim; the link `source_url` is mandatory
    wherever it is shown (Order of the Ministry of Ecology No. 267). `active` is False for a notice that is valid
    later (tomorrow's НМУ): it is shown but changes no ranking."""

    kind: Literal["storm", "nmu"]
    title: str
    text: str
    source_url: str
    issued: str = ""  # "17.10.2026", the date on the notice
    valid_from: str = ""  # ISO-8601 with the +05:00 offset of Astana
    valid_to: str = ""
    active: bool = False
    attachment_url: str = ""  # the PDF of a storm warning


class WeatherInfo(BaseModel):
    """Conditions for Astana (or a manual demo override): weather, air quality, sun times.

    `source` says where the weather part comes from: "metar" = the airport station observation (Kazhydromet METAR
    UACC, `observed_at` is its time), "met-no" = the MET Norway forecast (also when the observation is older than
    3 h: `obs_stale`), "manual" = a demo override. `forecast_used`: the forecast was read (it is the source of the
    precipitation also when `source` is "metar"). PM2.5 comes only from the Open-Meteo demo leg (`WALKS_AIR_DEMO`).
    Any part is None / empty when its request failed; a missing part never changes the ranking."""

    temperature_c: float | None = None
    apparent_c: float | None = None
    wind_kmh: float | None = None
    precipitation_mm: float | None = None
    pm25: float | None = None
    aqi: int | None = None
    force_dark: bool = False  # manual demo override: treat the request time as after sunset
    source: Literal["met-no", "manual", "metar"] = "met-no"
    forecast_used: bool = (
        False  # the MET Norway forecast supplied this answer's weather (or its precipitation)
    )
    fetched_at: str = ""
    observed_at: str = ""  # ISO-8601 (+05:00) of the airport observation found, used or stale
    obs_stale: bool = False  # that observation is older than 3 h: the forecast is used instead
    obs_raw: str = ""  # the METAR string verbatim
    wind_from_deg: int | None = (
        None  # where the wind of `wind_kmh` blows from; None: calm, variable or unknown
    )
    wind_gust_kmh: float | None = None  # the station's gust, only with an observation
    cloud_pct: float | None = (
        None  # sky cover 0..100 of the same source as the wind; None when unknown
    )
    precip_now: Literal["", "rain", "snow"] = (
        ""  # what falls at the station now (present-weather codes)
    )
    precip_level: int = 0  # 1 light / 2 moderate / 3 heavy, 0 with nothing falling
    visibility_m: int | None = (
        None  # the station's visibility (9999 = 10 km or more); None without a report
    )
    conditions: list[str] = Field(
        default_factory=list
    )  # adverse tokens of the observation / warnings
    warnings: list[WeatherWarning] = Field(
        default_factory=list
    )  # official Kazhydromet notices, active first
    adverse: bool = False  # freezing, heat, heavy precipitation, fog, storm warning, ...
    reason: str = ""
    air_bad: bool = False  # PM2.5 above the threshold, smoke / haze at the station, an НМУ
    air_reason: str = ""
    user_hint: str = ""  # cold / rain / heat / smog: the user's own words

    @property
    def warning(self) -> WeatherWarning | None:
        """The most relevant official notice (the first of `warnings`), None when there is none."""
        return self.warnings[0] if self.warnings else None

    @property
    def indoor_preferred(self) -> bool:
        return self.adverse or self.air_bad

    @property
    def indoor_reason(self) -> str:
        return ", ".join(r for r in (self.reason, self.air_reason) if r)


class Candidate(BaseModel):
    poi: POI
    distance_m: int
    walk_min: int
    travel_min: int
    hours_state: HoursState
    hours_note: str = ""
    hours_issue: HoursIssue = ""  # see `HoursIssue`
    score: float
    padding: Padding = "none"
    nearby_same: int = 0  # other points of the same chain/name + category within the cluster radius, collapsed into this card
    reasons: list[str] = Field(default_factory=list)  # machine codes, rendered in generate.py
    people: PeopleEvidence | None = None
    nearby_anon: int = 0  # other anonymous OSM records ("Детская площадка") of the same category this card stands for


class ClusterLog(BaseModel):
    """One collapsed chain: the card that represents it and the records merged into it."""

    kept_id: str
    kept_name: str
    merged: list[str]  # "name (id, 120 м, 94%)" of every collapsed record


class Filters(BaseModel):
    """What retrieval actually did - shown in the UI 'data used' panel."""

    mode: Mode
    speed_kmh: float
    time_budget_min: int
    travel_share: float
    radius_declared_m: int  # what the time budget (and the dialogue's narrowing) allows: the radius shown to the user
    radius_effective_m: (
        int  # the circle actually searched; larger than the declared one when it was widened
    )
    radius_factor: float = (
        1.0  # >1: nothing of the requested kind was in range, the radius was widened stepwise
    )
    categories_requested: list[str]
    categories_applied: list[str]
    categories_relaxed: bool
    night_mode: bool
    keywords: list[str]
    checked_at: str
    pois_total: int
    in_radius: int
    excluded_closed: int
    excluded_other: int
    candidates_returned: int
    hours_unknown: int
    excluded_min_stay: int = (
        0  # dropped: the category's minimum stay does not fit the budget left after the round trip
    )
    excluded_stay_kinds: list[str] = Field(
        default_factory=list
    )  # the categories those places were of: «на бар этого времени мало»
    excluded_outdoor: int = 0  # dropped in frost / smog while an indoor place was available: parks, viewpoints, playgrounds, outdoor landmarks
    clustered_away: int = (
        0  # same-chain duplicates collapsed into the nearest point of their cluster
    )
    merged: list[ClusterLog] = Field(
        default_factory=list
    )  # which records were merged into which card
    weather_adapted: bool = (
        False  # bad weather or air: walking radius capped; indoor first unless `outdoor_request`
    )
    outdoor_request: bool = False  # the request names an outdoor kind or brings a pet: it stays outdoors in bad weather / air
    air_bad: bool = False
    dark: bool = False  # request time is after sunset / before sunrise (outdoor places penalised)
    sunrise: str | None = None
    sunset: str | None = None
    sun_source: str | None = None
    holiday: str | None = None  # name of the public holiday on the request date, if any
    excluded_followup: int = 0  # dropped by the dialogue: shown already, no-alcohol
    shrink: float = 1.0  # < 1: the radius was narrowed («а поближе?», slow pace)
    people_marks: int = 0  # candidates that carry anonymous marks of people
    requested_nearby: int = 0  # places of the requested kinds inside the time-budget radius, whatever their hours (dataset fact)
    requested_nearby_with_hours: int = (
        0  # of them: places whose opening hours the data confirm (state open / closed)
    )
    # what the records of the places in range say (honest counts for «отмечено у N из M»): halal among the food places,
    # a step-free entrance among the places of the requested kinds; `excluded_alcohol`: left out by «без алкоголя»
    halal_marked: int = 0
    halal_checked: int = 0
    step_free_marked: int = 0
    step_free_checked: int = 0
    excluded_alcohol: int = 0
    excluded_avoid: int = 0  # left out by the profile's «не показывать»

    @property
    def radius_widened(self) -> bool:
        return self.radius_effective_m > self.radius_declared_m

    def radius_text(self, lang: str | None = "ru") -> str:
        """The radius for the header: the declared one, and, when it was widened, the real one with the reason."""
        return radius_text(self.radius_declared_m, self.radius_effective_m, lang)


class RetrievalResult(BaseModel):
    candidates: list[Candidate]
    filters: Filters


class Recommendation(BaseModel):
    poi: POI
    why: str
    time_on_site_min: int
    what_to_do: str
    confidence: Confidence
    generated_idea: bool
    notes: str = ""
    distance_m: int
    walk_min: int
    travel_min: int
    hours_state: HoursState
    hours_raw: str | None
    padding: Padding = "none"  # copied from the candidate: see `Padding`
    hours_note: str = (
        ""  # e.g. "праздник: День Победы" when an 'open' state was downgraded to unknown
    )
    hours_issue: HoursIssue = ""  # copied from the candidate: see `HoursIssue`
    text_source: Literal["llm", "template"]
    walk_method: Literal["valhalla", "straight", "estimate"] = "straight"
    lrt_hint: str | None = None
    people: PeopleEvidence | None = None
    unbacked_claims: list[str] = Field(
        default_factory=list
    )  # kinds of the claims dropped from the AI text of this card (walks.claims)

    @property
    def hours_source(self) -> str | None:
        """Where the hours behind `hours_state` come from: `osm`, `official_site` (also the website's hours
        without days) or None without any hours."""
        return self.poi.hours_source()

    @property
    def hours_source_url(self) -> str | None:
        """The page of the business's own website that the hours (or the website's note on them) were read from."""
        return self.poi.hours_source_url()


class RoutePlan(BaseModel):
    stops: list[str]  # poi ids in visiting order
    legs_m: list[int]  # user->1, 1->2, ...
    legs_min: list[int]
    walk_min_total: int  # outbound legs only
    return_min: int  # last stop -> user location
    stay_min: list[int]  # minutes on site per stop, possibly shrunk to fit the budget
    shrunk: bool = False
    legs_method: list[str] = Field(default_factory=list)  # per leg: valhalla / straight / estimate
    method: Literal["valhalla", "mixed", "straight", "estimate"] = "straight"
    on_site_min_total: int
    total_min: int  # outbound + on site + return
    budget_min: int
    fits: bool
    dropped: list[str] = Field(default_factory=list)  # ids removed so that the route fits


class Result(BaseModel):
    lat: float  # ALREADY ROUNDED
    lon: float
    when: datetime
    query: str
    intent: IntentResult
    retrieval: RetrievalResult
    recs: list[Recommendation]
    route: RoutePlan | None
    generation: Literal["llm", "template"]
    generation_note: str = ""
    llm_payload: dict | None = None  # exactly what was sent to the LLM in the generation step
    model: str | None = None  # the model that wrote the recommendation text
    generation_step: LLMStep | None = None  # attempt chain / timing / cache of the generation call
    generation_retry: Literal["", "live", "failed"] = (
        ""  # a recorded answer left no card with model text: "live" = the models were asked again and that answer is used, "failed" = they could not answer and the recorded one stays
    )
    lead_want: str = ""  # the model's «what you want» clause, after code's checks ('' = the template composes it)
    lead_text: str = (
        ""  # the model's own opening of the reply, after code's checks ('' = the template lead)
    )
    on_the_way: str = (
        ""  # the name of the bookmark the first place lies toward ('' = not on the way anywhere)
    )
    timings_ms: dict[str, int] = Field(
        default_factory=dict
    )  # intent / retrieve / generation / route / total
    weather: WeatherInfo | None = None
    walk_stats: dict[str, int] = Field(
        default_factory=dict
    )  # legs by method: valhalla / cache / straight / estimate
    lrt_note: str = ""  # why an LRT hint was or was not attached (data panel)
    constraints: Constraints = Field(default_factory=Constraints)
    continued: bool = False  # a follow-up of the previous request, not a new one
    follow_up_note: str = ""  # what the dialogue changed, shown to the user
    profile_applied: list[str] = Field(
        default_factory=list
    )  # codes of the profile flags that entered the intent
    private: bool = False  # profile data was involved: never written to the request log
    refusal: Refusal = "none"  # the request asks for something the assistant never helps with: no places are offered
    unbacked_claims_removed: int = 0  # AI sentences dropped: no field of the record backs them
