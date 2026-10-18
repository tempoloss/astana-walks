"""City knowledge from people: anonymous one-tap marks on a place («был: открыто», «есть розетка», «тихо», ...).

The tracked data/city_feedback.json is the SEED: a JSON list of `{poi_id, signal, date, weekday, hour_bucket}`
(+ `"demo": true` on seeded demo entries). Marks are never written to it: the working copy is the git-ignored
app/.local/city_feedback.json, copied from the seed on first use, so clicking a mark on a fresh clone leaves every
tracked file untouched. There is NO user id, NO coordinates, NO session id and no time finer than a bucket of
hours: a mark cannot be tied to a person.

What a mark does:
  * «был: открыто / закрыто» become their own hours evidence level, `PeopleEvidence.hours`, distinct from the OSM
    `hours_state` (which keeps meaning "what the OSM hours say"). Marks older than WINDOW_DAYS are ignored, newer
    ones fade with half-life HALF_LIFE_DAYS, a mark from another part of the day than the request counts half,
    and marks that contradict each other lower the confidence of the verdict.
  * «есть розетка», «есть Wi‑Fi», «тихо / шумно» become usable attributes, always labelled «по отметкам людей».
  * «другие часы» (`hours_differ`) is a report for the city layer: the hours the card shows are not the place's real
    ones. It says nothing about open / closed at a moment, so it is no evidence for a card.

WALKS_FEEDBACK=<path> redirects the working file (used as it is, never seeded); `off` disables reading and writing.
With WALKS_DEMO_PIN=1 the working file is app/.local/city_feedback.demo.json, a separate copy of the seed, so the
demo's marks stay apart from the developer's own (`reseed` restores it). A pinned (recorded) request never reads it: it
is answered with the tracked seed itself (walks.demo_pin), the marks the recorded answers were made with.
"""

from __future__ import annotations

import contextlib
import json
import os
import shutil
import tempfile
from collections import defaultdict
from datetime import date, datetime
from pathlib import Path
from typing import Literal, get_args

from pydantic import BaseModel, ConfigDict, field_validator

from .envcfg import demo_pin
from .hours import TZ
from .i18n import people_hours, signal_label
from .models import PeopleEvidence

SEED_PATH = (
    Path(__file__).resolve().parents[2] / "data" / "city_feedback.json"
)  # tracked, read-only
LOCAL_PATH = Path(__file__).resolve().parents[1] / ".local" / "city_feedback.json"
DEMO_PATH = LOCAL_PATH.with_name("city_feedback.demo.json")  # WALKS_DEMO_PIN=1
WINDOW_DAYS = 30  # older marks are ignored
MAX_ENTRIES = 5000  # past this the oldest people's marks are dropped (seeded demo marks stay)
HALF_LIFE_DAYS = 14.0
OTHER_PART_OF_DAY_WEIGHT = 0.5  # a mark made in another part of the day says less about this hour
DOMINANT_RATIO = 2.0  # one side of a contradiction must outweigh the other this much to win

Signal = Literal[
    "was_open", "was_closed", "has_socket", "has_wifi", "noisy", "quiet", "hours_differ"
]
REPORT_ONLY = frozenset({"hours_differ"})  # stored and shown to the city, never evidence for a card
SIGNALS: dict[
    str, str
] = {  # signal -> Russian button label (UI: walks.i18n.signal_label in the user's language)
    s: signal_label(s, "ru") for s in get_args(Signal)
}
WEEKDAYS = ("mon", "tue", "wed", "thu", "fri", "sat", "sun")
Weekday = Literal["mon", "tue", "wed", "thu", "fri", "sat", "sun"]
HourBucket = Literal["morning", "day", "evening", "night"]
BUCKET_RU = {"morning": "утром", "day": "днём", "evening": "вечером", "night": "ночью"}
ALLOWED_FIELDS = frozenset({"poi_id", "signal", "date", "weekday", "hour_bucket", "demo"})


def hour_bucket(hour: int) -> HourBucket:
    if 5 <= hour < 11:
        return "morning"
    if 11 <= hour < 17:
        return "day"
    if 17 <= hour < 22:
        return "evening"
    return "night"


class FeedbackEntry(BaseModel):
    """One mark. Deliberately nothing else: see the module docstring."""

    model_config = ConfigDict(extra="forbid")

    poi_id: str
    signal: Signal
    date: str  # ISO day, no time
    weekday: Weekday
    hour_bucket: HourBucket
    demo: bool = False

    @field_validator("date")
    @classmethod
    def _iso_day(cls, v: str) -> str:
        date.fromisoformat(v)
        return v

    def as_json(self) -> dict:
        out = self.model_dump()
        if not self.demo:
            del out["demo"]
        return out


def _trim(rows: list) -> list:
    """`rows` without its oldest non-demo entries beyond MAX_ENTRIES (the file is append-ordered)."""
    excess = len(rows) - MAX_ENTRIES
    kept: list = []
    for row in rows:
        if excess > 0 and not (isinstance(row, dict) and row.get("demo")):
            excess -= 1
            continue
        kept.append(row)
    return kept


def feedback_path() -> Path | None:
    """The working file of the marks: WALKS_FEEDBACK, else the demo copy (WALKS_DEMO_PIN), else the local file;
    None when WALKS_FEEDBACK=off."""
    v = os.environ.get("WALKS_FEEDBACK", "").strip()
    if v.lower() == "off":
        return None
    return Path(v) if v else DEMO_PATH if demo_pin() else LOCAL_PATH


def reseed(path: Path) -> None:
    """Make `path` a fresh copy of the tracked seed (atomically)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    shutil.copyfile(SEED_PATH, tmp)
    os.replace(tmp, path)


def _working_path() -> Path | None:
    """feedback_path(), seeded from the tracked file when it is one of our own working files and missing."""
    path = feedback_path()
    if path in (LOCAL_PATH, DEMO_PATH) and not path.exists():
        with contextlib.suppress(
            OSError
        ):  # read-only checkout: read_entries falls back to the seed
            reseed(path)
    return path


def read_entries(path: Path | None = None) -> list[FeedbackEntry]:
    """Every valid mark of the file; a missing or broken file, or a malformed entry, is skipped (never raises)."""
    path = path or _working_path()
    if path in (LOCAL_PATH, DEMO_PATH) and not path.exists():
        path = SEED_PATH  # a read-only checkout that could not be seeded: read the seed itself
    if path is None or not path.exists():
        return []
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return []
    out: list[FeedbackEntry] = []
    for item in raw if isinstance(raw, list) else []:
        try:
            out.append(FeedbackEntry.model_validate(item))
        except ValueError:
            continue
    return out


def add_feedback(
    poi_id: str, signal: str, when: datetime | None = None, path: Path | None = None
) -> FeedbackEntry:
    """Append one anonymous mark (day, weekday and part of the day of `when`, Astana time) to the shared file."""
    path = path or _working_path()
    if path is None:
        raise OSError("отметки отключены (WALKS_FEEDBACK=off)")
    local = when or datetime.now(TZ)
    if local.tzinfo is not None:
        local = local.astimezone(TZ)
    entry = FeedbackEntry(
        poi_id=poi_id,
        signal=signal,  # type: ignore[arg-type]
        date=local.date().isoformat(),
        weekday=WEEKDAYS[local.weekday()],  # type: ignore[arg-type]
        hour_bucket=hour_bucket(local.hour),
    )
    rows: list = []
    if path.exists():
        try:
            loaded = json.loads(path.read_text(encoding="utf-8"))
            rows = loaded if isinstance(loaded, list) else []
        except ValueError:
            rows = []
    rows.append(entry.as_json())
    rows = _trim(rows)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=path.parent, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(rows, fh, ensure_ascii=False, indent=1)
            fh.write("\n")
        os.replace(tmp, path)
    finally:
        Path(tmp).unlink(missing_ok=True)
    return entry


def _verdict(open_w: float, closed_w: float) -> tuple[Literal["open", "closed", "mixed"], bool]:
    """(verdict, contradicted): one side must outweigh the other DOMINANT_RATIO times to win a contradiction."""
    if not closed_w:
        return "open", False
    if not open_w:
        return "closed", False
    if open_w >= DOMINANT_RATIO * closed_w:
        return "open", True
    if closed_w >= DOMINANT_RATIO * open_w:
        return "closed", True
    return "mixed", True


class FeedbackIndex:
    """The marks of one file, grouped by place; `evidence` judges them at a moment."""

    def __init__(self, entries: list[FeedbackEntry] | None = None) -> None:
        self._by_poi: dict[str, list[FeedbackEntry]] = defaultdict(list)
        for e in entries or []:
            self._by_poi[e.poi_id].append(e)

    def __len__(self) -> int:
        return sum(len(v) for v in self._by_poi.values())

    def evidence(self, poi_id: str, when: datetime) -> PeopleEvidence | None:
        """What the marks of `poi_id` inside the window say at `when` (naive Astana time); None: no usable mark."""
        marks = self._by_poi.get(poi_id)
        if not marks:
            return None
        today, bucket = when.date(), hour_bucket(when.hour)
        open_w = closed_w = 0.0
        n_open = n_closed = 0
        last: dict[str, str] = {}
        sig_w: dict[str, float] = defaultdict(float)
        counts: dict[str, int] = defaultdict(int)
        used: list[FeedbackEntry] = []
        for e in marks:
            age = max(0, (today - date.fromisoformat(e.date)).days)
            if age > WINDOW_DAYS or e.signal in REPORT_ONLY:
                continue
            used.append(e)
            counts[e.signal] += 1
            w = 0.5 ** (age / HALF_LIFE_DAYS)
            sig_w[e.signal] += w
            last[e.signal] = max(last.get(e.signal, ""), e.date)
            if e.signal in ("was_open", "was_closed"):
                w *= 1.0 if e.hour_bucket == bucket else OTHER_PART_OF_DAY_WEIGHT
                if e.signal == "was_open":
                    open_w, n_open = open_w + w, n_open + 1
                else:
                    closed_w, n_closed = closed_w + w, n_closed + 1
        if not used:
            return None
        hours = confidence = last_hours = None
        if n_open or n_closed:
            hours, contradicted = _verdict(open_w, closed_w)
            confidence = "low" if contradicted or n_open + n_closed < 2 else "medium"
            dates = [last[s] for s in ("was_open", "was_closed") if s in last]
            if hours != "mixed":
                dates = [last["was_open" if hours == "open" else "was_closed"]]
            last_hours = max(dates)
        noise = None
        if counts["quiet"] or counts["noisy"]:
            noise, _ = _verdict(sig_w["quiet"], sig_w["noisy"])
            noise = {"open": "quiet", "closed": "noisy", "mixed": "mixed"}[noise]
        return PeopleEvidence(
            hours=hours,
            n_open=n_open,
            n_closed=n_closed,
            last_hours_date=last_hours,
            confidence=confidence or "low",  # type: ignore[arg-type]
            socket=counts["has_socket"],
            wifi=counts["has_wifi"],
            quiet=counts["quiet"],
            noisy=counts["noisy"],
            noise=noise,  # type: ignore[arg-type]
            demo=all(e.demo for e in used),
        )


def load_feedback(path: Path | None = None) -> FeedbackIndex:
    return FeedbackIndex(read_entries(path))


# ---------------------------------------------------------------- wording


def _day(iso: str) -> str:
    return date.fromisoformat(iso).strftime("%d.%m")


def hours_label(ev: PeopleEvidence, lang: str | None = "ru") -> str | None:
    """The people-evidence level of the hours: «люди отмечали открыто (2 раза, последний 15.10)», or None."""
    if ev.hours is None or ev.last_hours_date is None:
        return None
    return people_hours(ev.hours, ev.n_open, ev.n_closed, _day(ev.last_hours_date), lang)


def hours_evidence(state: str, ev: PeopleEvidence | None) -> Literal["osm", "people", "none"]:
    """Which level the card's hours stand on: OSM hours decided it, only people's marks did, or nothing."""
    if state in ("open", "closed"):
        return "osm"
    return "people" if ev is not None and ev.hours in ("open", "closed") else "none"
