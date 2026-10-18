"""The demo preset (WALKS_DEMO_PIN=1, on in app/.env.demo): ONE definition of the conditions a demo scenario runs in,
shared by the UI, the CLI and `scripts/warm_cache.py`, so what the warm-up recorded is exactly what the stage asks.

The pin applies per request, and only to the requests that were recorded (`pins`): a scenario starter, one of
`presets.DEMO_REQUESTS`, or a follow-up of a dialogue that began with one of them. Every other request is answered like
an unpinned app: the real local time (or the one the user chose), the live weather, the configured router, the live
marks. A pinned request has
  * a fixed manual time: the scenario's own time (the night one) or 14:00 on PIN_DATE, a weekday, whatever the clock says;
  * a fixed manual weather: normal (10 °C, PM2.5 5) unless the scenario text is about cold or smog (-25 °C / PM2.5 80);
  * walking legs from the tracked data/walk_cache.json only (no network, no writes; a missing leg is the straight line);
  * the people's marks of the tracked seed, whatever visitors have marked since (their marks count for every other
    request).
A follow-up («а поближе?») keeps the conditions of the scenario the dialogue started from: pass that text as `base_text`.

Everything pinned is a manual, labelled demo condition (weather source «manual»), never presented as live data.
"""

from __future__ import annotations

import functools
import re
from collections.abc import Callable
from dataclasses import dataclass
from datetime import date, datetime, time

from .envcfg import demo_pin
from .feedback import SEED_PATH, FeedbackIndex, load_feedback
from .followup import FollowUp
from .models import Conversation, LLMStep, Result, StartHints, WeatherInfo
from .pipeline import recommend
from .presets import DEMO_REQUESTS, SCENARIOS
from .profile import Profile
from .walking import WalkingRouter, shipped_router
from .weather import manual_weather

PIN_DATE = date(
    2026, 10, 19
)  # a Monday: the day of the submission, opening hours are those of a working day
DEFAULT_TIME = time(14, 0)
_COLD = re.compile(r"холод|мороз|стужа|аяз|суық|\bcold\b|freez", re.IGNORECASE)
_SMOG = re.compile(r"смог|загрязн|\bsmog\b|pm\s?2[.,]?5", re.IGNORECASE)

__all__ = [
    "DEFAULT_TIME",
    "PIN_DATE",
    "PinSetup",
    "pinned",
    "pins",
    "recommend_pinned",
    "router",
    "setup_for",
    "when_for",
]


def pinned() -> bool:
    """True when WALKS_DEMO_PIN=1: the stand has a pin at all (which request it applies to is `pins`)."""
    return demo_pin()


def _recorded(text: str) -> bool:
    """Is `text` one of the requests the demo recorded (a scenario in any of its languages, or a DEMO_REQUESTS one)?"""
    return any(sc.matches(text) for sc in SCENARIOS) or any(text == r for r, _ in DEMO_REQUESTS)


def pins(text: str, base_text: str | None = None) -> bool:
    """Does this request run under the pinned conditions? Only with WALKS_DEMO_PIN=1, and only when it is a recorded
    request or a follow-up (`base_text`: the first message of its dialogue) of one."""
    return pinned() and _recorded(base_text or text)


def when_for(text: str, base_text: str | None = None) -> datetime:
    """The pinned moment of the scenario `base_text` (the dialogue's first message) or, for a new request, `text`."""
    probe = base_text or text
    own = next((sc.at for sc in SCENARIOS if sc.matches(probe)), None)
    return datetime.combine(PIN_DATE, own or DEFAULT_TIME)


def weather_for(text: str, base_text: str | None = None) -> WeatherInfo:
    probe = base_text or text
    if _COLD.search(probe):
        return manual_weather(-25.0)
    if _SMOG.search(probe):
        return manual_weather(10.0, pm25=80.0)
    return manual_weather(10.0, pm25=5.0)


@functools.cache
def _router() -> WalkingRouter:
    return shipped_router()


def router() -> WalkingRouter:
    """The pinned run's walking legs (data/walk_cache.json): also where the map takes the street lines from."""
    return _router()


@dataclass(frozen=True)
class PinSetup:
    """The pinned conditions of one request, as the keyword arguments `recommend` takes."""

    when: datetime
    weather: WeatherInfo
    router: WalkingRouter
    feedback: FeedbackIndex

    def describe(self) -> str:
        w = self.weather
        kind = "холод" if (w.apparent_c or 0) <= -15 else "смог" if w.air_bad else "обычная"
        return f"время {self.when:%d.%m %H:%M}, погода: {kind} (ручная), пешие отрезки из data/walk_cache.json"


def _marks() -> FeedbackIndex:
    """The people's marks a pinned request (a recorded scenario) is answered with: the tracked seed, always, because the
    recorded answers were made with it and the candidate list depends on it: one visitor's «был: закрыто» on a recorded
    place would otherwise change the candidates and the starter would leave its recording. Visitors' marks are still
    saved, shown on the city page and used by every request that is not a recorded scenario."""
    return load_feedback(SEED_PATH)


def setup_for(text: str, base_text: str | None = None) -> PinSetup:
    return PinSetup(
        when_for(text, base_text),
        weather_for(text, base_text),
        _router(),
        _marks(),
    )


def recommend_pinned(
    text: str,
    lat: float,
    lon: float,
    *,
    base_text: str | None = None,
    use_llm: bool = True,
    conversation: Conversation | None = None,
    profile: Profile | None = None,
    language: str | None = None,
    follow_up: tuple[FollowUp, LLMStep | None] | None = None,
    hints: StartHints | None = None,
    on_stage: Callable[[str], None] | None = None,
) -> Result:
    """`recommend` under the demo preset: the single code path of the warm-up script and of a pinned UI / CLI run."""
    s = setup_for(text, base_text)
    return recommend(
        text,
        lat,
        lon,
        s.when,
        use_llm=use_llm,
        weather=s.weather,
        router=s.router,
        conversation=conversation,
        profile=profile,
        feedback=s.feedback,
        language=language,
        follow_up=follow_up,
        hints=hints,
        on_stage=on_stage,
    )
