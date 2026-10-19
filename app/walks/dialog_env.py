"""What one turn of the dialogue runs under (`TurnEnv`) and what it returns (`Outcome`); kept apart from walks.dialog,
which re-exports both."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field, replace
from datetime import datetime
from typing import Literal, NamedTuple

from .dialog_toward import Geocode
from .dialog_types import DialogState, Turn
from .dialog_when import AskedTime
from .feedback import FeedbackIndex
from .models import POI, Bookmark, Result, WeatherInfo
from .profile import Profile
from .walking import WalkingRouter


@dataclass
class TurnEnv:
    """What a turn runs under (a Python object, not JSON); every field is optional."""

    when: datetime | None = None
    weather: WeatherInfo | Callable[[], WeatherInfo] | None = (
        None  # a callable is asked only by an unpinned search
    )
    use_llm: bool = True
    router: WalkingRouter | None = None
    profile: Profile | None = None
    feedback: FeedbackIndex | None = None
    pois: list[POI] | None = None
    language: str | None = None  # the user fixed the language: answer in it whatever they write
    budget_min: int | None = None  # tapped next to the input box (30 / 60 / 120): a NEW search only
    company: Literal["solo", "pair", "kids"] | None = None  # tapped: with whom, a NEW search only
    bookmarks: list[Bookmark] = field(
        default_factory=list
    )  # the user's own named places, this request only
    on_stage: Callable[[str], None] | None = None  # parse / search / hours / write / route
    preface: str = (
        ""  # a sentence the reply of this turn starts with (the answer to «if it is not cold»)
    )
    asked_time: AskedTime | None = (
        None  # the time the message names (set by take_turn, never by the caller)
    )
    geocode: Geocode | None = (
        None  # the stand's address search: a place name -> (lat, lon, label), for «в сторону X по пути»
    )
    fresh_air: bool = False  # «парк, если не холодно» and it is cold: the nearest park goes second (set by take_turn)

    def said(self, line: str) -> TurnEnv:
        """This environment with `line` added to the sentences the reply starts with."""
        return replace(self, preface=f"{self.preface} {line}".strip()) if line else self


class Outcome(NamedTuple):
    turn: Turn
    state: DialogState
    result: Result | None = None  # Python only: the pipeline's full result of a search turn
