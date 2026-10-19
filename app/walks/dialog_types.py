"""The data of the dialogue API (walks.dialog): what one turn says (`Turn`) and what the next turn needs
(`DialogState`). Pydantic models, JSON in and out; the contract is described in docs/dialog.md."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from .models import Conversation

Lang = Literal["ru", "kk", "en"]
TurnKind = Literal["places", "none_found", "place_answer", "clarify", "thanks", "bye", "refusal"]
ChipKind = Literal["start", "refine", "reset"]
Topic = Literal[
    "hours", "address", "route", "phone", "website", "toilet", "wifi", "wheelchair", "terrace",
    "takeaway", "price", "parking", "reserve", "about",
]  # fmt: skip
STATE_VERSION = 1


class Source(BaseModel):
    label: str
    url: str | None = None


class Stop(BaseModel):
    """The nearest bus stop to a place (GTFS stops, CC BY 4.0); shown in the card's details only."""

    name: str
    minutes: int  # on foot, straight line × 1.3 at 75 m/min
    distance_m: int
    text: str = ""  # «Остановка «Sarytogai» — 3 мин пешком»
    source: Source | None = None


class Signal(BaseModel):
    """One line under a card from a layer outside the place's own record. `osm_note`: an open OpenStreetMap note that
    the place may have closed or changed its hours (a suspicion, never a fact; `source` is the note itself).
    `state_registry`: the schedule line of a ЦОН card for the asked day («сб: 09:00-13:00; по данным gov4c.kz»;
    `source` is the operator's page, `date` the day of the snapshot)."""

    kind: Literal["osm_note", "state_registry"]
    text: str
    source: Source
    date: str | None = None  # the day the note was written / the snapshot was taken (YYYY-MM-DD)


class Hours(BaseModel):
    state: Literal["open", "closed", "unknown"]
    text: str  # plain words: «Сейчас открыто»
    raw: str | None = None  # the schedule as the record has it (OSM syntax)
    source: Source | None = None  # whose hours; None when there are none
    issue: Literal["", "conflict", "split", "unqualified"] = ""
    note: str = ""
    data_date: str | None = None
    today: list[tuple[float, float]] | None = (
        None  # open spans of the arrival day in hours [(8.0, 24.0)]; [] = closed all day; None = no schedule
    )
    soon: bool = False  # open, and the schedule closes within the hour after arrival


class PeopleMarks(BaseModel):
    hours: Literal["open", "closed", "mixed"] | None = None
    n_open: int = 0
    n_closed: int = 0
    last_date: str | None = None
    confidence: Literal["medium", "low"] = "low"
    socket: int = 0
    wifi: int = 0
    quiet: int = 0
    noisy: int = 0
    demo: bool = False
    text: str = ""


class Walk(BaseModel):
    minutes: int
    distance_m: int
    method: Literal["valhalla", "straight", "estimate"] = "straight"
    mode: Literal["walk", "car", "transit"] = "walk"
    text: str = ""


class Price(BaseModel):
    """The place's own price wording («вход — 1000 тг», never parsed into a number) and whose it is."""

    text: str
    source: Source | None = None
    date: str | None = None  # the day the wording was read from the source (YYYY-MM-DD)


class Place(BaseModel):
    id: str
    name: str
    kind: str  # the kind of place in the user's words: «кафе»
    category: str
    lat: float
    lon: float
    primary: bool = False
    why: str = ""
    what_to_do: str = ""
    ai_idea: bool = False
    stay_min: int = 0
    address: str | None = None
    phone: str | None = None
    website: str | None = None
    walk: Walk
    hours: Hours
    people: PeopleMarks | None = None
    caveat: str = ""
    note: str = ""
    text_source: Literal["llm", "template"] = "template"
    padding: Literal["none", "expanded", "backfill", "substituted"] = "none"
    lrt_hint: str | None = None
    sources: list[Source] = Field(default_factory=list)
    data_date: str | None = None
    signal: Signal | None = None
    stop: Stop | None = None
    price: Price | None = None


class Chip(BaseModel):
    id: str
    label: str  # what the button shows
    send: str  # the exact text to hand to `take_turn`
    kind: ChipKind


class PlaceAnswer(BaseModel):
    place_id: str
    name: str
    topic: str
    text: str
    known: bool = True  # False: the data has no such fact and `text` says so
    source: Source | None = None


class Route(BaseModel):
    stops: list[str]
    legs_min: list[int]
    legs_m: list[int]
    stay_min: list[int]
    walk_min_total: int
    return_min: int
    total_min: int
    budget_min: int
    fits: bool
    method: str = "straight"
    lighting: str = (
        ""  # one line about the street lights along the way, only when OpenStreetMap knows enough
    )
    kind: Literal["plan", "nearest"] = (
        "nearest"  # plan: the user listed stops in an order and the route runs through them; else the nearest-first loop
    )


class Meta(BaseModel):
    parser: Literal["rules", "rules+llm"] = "rules"
    generation: Literal["llm", "template"] | None = None
    model: str | None = None
    cached: bool = False
    generation_retry: Literal["", "live", "failed"] = ""  # see models.Result.generation_retry
    ms: int = 0
    continued: bool = False
    change: str = ""
    intent: dict | None = None
    note: str = ""
    radius_m: int | None = None


class Notice(BaseModel):
    """One extra line of the answer from a live or official source: a Kazhydromet warning or the station's adverse
    weather («weather»), the airport bus («airport»). `source` is the link the line stands on."""

    kind: Literal["weather", "airport"]
    text: str
    source: Source | None = None
    detail: str = ""  # attribution / date, for the details panel


class EventItem(BaseModel):
    title: str
    when: str  # «19:30», «идёт сейчас», «сеансы: 18:00, 20:30»
    venue: str  # the venue and its address
    distance_m: int = 0
    price: str = ""
    text: str  # the whole line in words, without the source
    source: Source  # the page of the event


class EventsBlock(BaseModel):
    """«Сегодня рядом»: at most two events with their source links (three for a question about the afisha); `note`
    says how far the afisha reaches and when it was last updated."""

    heading: str
    items: list[EventItem]
    note: str = ""


class Turn(BaseModel):
    kind: TurnKind
    notice: str = ""  # one honest remark under the reply («на бар этого времени мало»), often empty
    lang: Lang = "ru"
    reply: str
    places: list[Place] = Field(default_factory=list)
    answers: list[PlaceAnswer] = Field(default_factory=list)
    chips: list[Chip] = Field(default_factory=list)
    notices: list[Notice] = Field(default_factory=list)
    events: EventsBlock | None = None
    route: Route | None = None
    origin: tuple[float, float] = (0.0, 0.0)
    meta: Meta = Field(default_factory=Meta)


class ShownPlace(BaseModel):
    """A place of the last answer, as much of it as a later question needs."""

    id: str
    name: str
    kind: str = ""
    what: str = ""
    distance_m: int = 0
    minutes: int = 0
    mode: Literal["walk", "car", "transit"] = "walk"


class DialogState(BaseModel):
    version: int = STATE_VERSION
    lang: Lang = "ru"
    lat: float
    lon: float
    conversation: Conversation | None = None
    shown: list[ShownPlace] = Field(default_factory=list)
    focus_id: str | None = None
    asked: ShownPlace | None = (
        None  # a named place the last question was about, when it is not one of `shown`
    )
    turns: int = 0
    demo_base: str | None = (
        None  # the first message of the dialogue, kept only while WALKS_DEMO_PIN is on
    )
    bookmark: str = ""  # the name of the bookmark the dialogue searches around / along the way to (from the device)
    bookmark_mode: Literal["", "near", "along"] = ""
    told: str = ""  # the conditions line the last fresh answer said: the next one does not repeat it word for word

    def shown_has(self, place_id: str) -> bool:
        return any(p.id == place_id for p in self.shown)
