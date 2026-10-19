"""The time a message names («завтра», «утром», «в воскресенье днём», «tomorrow morning», «lunch tomorrow», «ертең»,
«кешке», «жексенбіде»): the moment the request is about, the message without those words, and how the reply names the
moment. Rules only, offline. A search, a question about hours and a weather question all read the same words, so the
open-now check, the hours of a place and the forecast are for the time the person asked, not for the clock."""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from .dialog_strings import s
from .hours import to_local_naive
from .i18n_gov import weekday_on
from .lexicon import normalize
from .sun import sun_for

DEFAULT_HOUR = 12  # a day named with no part of it: the middle of the day
DAWN_TWILIGHT = timedelta(
    minutes=40
)  # after sunrise the sky stays dim this long: the city lights are still on
# (name, from hour, to hour, the hour a request for that part is answered for); the night wraps past midnight
_PARTS = (
    ("morning", 6, 11, 9),
    ("day", 11, 17, 13),
    ("evening", 17, 22, 19),
    ("night", 22, 6, 23),
)
_WEEKDAYS = tuple(
    re.compile(rx)
    for rx in (
        r"\bпонедельник\w*|\bдуйсенби\w*|\bmonday\b",
        r"\bвторник\w*|\bсейсенби\w*|\btuesday\b",
        r"\bсред(?:а|у|е|ы|ой)\b|\bсарсенби\w*|\bwednesday\b",
        r"\bчетверг\w*|\bбейсенби\w*|\bthursday\b",
        r"\bпятниц\w*|\bжума\w*|\bfriday\b",
        r"\bсуббот\w*|\bсенби\w*|\bsaturday\b",
        r"\bвоскресень\w*|\bжексенби\w*|\bsunday\b",
    )
)
_AFTER = re.compile(r"\bпослезавтра\b|\bday after tomorrow\b|\bбурсигуни\b")
_TOMORROW = re.compile(r"\bзавтра\b|\bзавтрашн\w*|\btomorrow\b|\bертен\w*")
_TODAY = re.compile(r"\bсегодня\b|\btoday\b|\bбугин\b")
_CLOCK = re.compile(r"(?<![\d:.])([01]?\d|2[0-3]):([0-5]\d)(?![\d:])")
_AMPM = re.compile(r"(?<![\d:.])(1[0-2]|[1-9])\s?(am|pm)\b")
_PART_WORDS = {
    "morning": re.compile(
        r"\bутром\b|\bс утра\b|\bутро\b|\bmorning\b|\bтанертен\w*|\bтан ертен\w*"
    ),
    "day": re.compile(
        r"\bднем\b|\bafternoon\b|\bmidday\b|\bnoon\b|\bтусте\b|\bтустен\b|\bкундиз\w*"
    ),
    "evening": re.compile(r"\bвечером\b|\bevening\b|\btonight\b|\bкешке\w*|\bкеште\b"),
    "night": re.compile(r"\bночью\b|\bat night\b|\bтунде\b|\bтунге\b"),
}
# a meal is also a kind of place: it names the hour only next to a day, and the word itself stays in the message
_MEALS = (
    (re.compile(r"\blunch\b|\bобед\w*|\bтуски ас\b"), 13),
    (re.compile(r"\bdinner\b|\bужин\w*|\bкешки ас\b"), 19),
)
_FILLER_ENDS = frozenset(
    {"в", "во", "на", "к", "on", "in", "at", "for", "by", "а", "и", "ну", "and", "то"}
)


@dataclass(frozen=True)
class AskedTime:
    moment: datetime  # the local naive time the request is about
    rest: str  # the message without the time words ('' when nothing else was said)
    days: int  # whole days from today: 0 today, 1 tomorrow, 2+ a weekday
    part: str  # morning / day / evening / night, or ''
    shifted: bool  # the moment is not the present one: the reply says it
    exact: bool  # a part of the day or a meal was said, not the day alone
    since: datetime  # the present moment the words were read against
    note: str = ""  # why the moment is not the plain reading («вечер уже прошёл»): a string key, '' when it is

    def day_label(self, lang: str) -> str:
        """«сегодня», «завтра», «в воскресенье»."""
        if self.days == 0:
            return s("w_today", lang)
        if self.days == 1:
            return s("w_tomorrow", lang)
        return weekday_on(self.moment.weekday(), lang)

    def label(self, lang: str) -> str:
        """«завтра днём, 13:00», «в воскресенье, 12:00», «сегодня вечером, 19:00»."""
        part = s(f"w_part_{self.part}", lang) if self.part else ""
        return f"{self.day_label(lang)} {part}".strip() + f", {self.moment:%H:%M}"


def _spans(norm: str, rxs: list[re.Pattern[str]]) -> list[tuple[int, int]]:
    return [m.span() for rx in rxs for m in rx.finditer(norm)]


def _cut(text: str, norm: str, spans: list[tuple[int, int]]) -> str:
    """`text` without the spans (positions in `norm`, the same ones in `text` when the normalisation kept the length),
    and without the little words that only joined them to the rest («в» of «в воскресенье», «on» of «on Sunday»)."""
    base = text if len(text) == len(norm) else norm
    pieces, last = [], 0
    for a, b in sorted(spans):
        if a >= last:
            pieces.append(base[last:a])
            last = b
    pieces.append(base[last:])
    words = "".join(pieces).split()
    while words and words[0].lower().strip(",;:") in _FILLER_ENDS:
        words.pop(0)
    while words and words[-1].lower().strip(",;:") in _FILLER_ENDS:
        words.pop()
    rest = " ".join(words).strip(" ,;:")
    return rest if any(ch.isalnum() for ch in rest) else ""  # «а завтра?» leaves only the «?»


def _day_offset(norm: str, now: datetime) -> int | None:
    """Days ahead of the day the message names («завтра» 1, «в субботу» the next such day; today 0), else None."""
    if _AFTER.search(norm):
        return 2
    if _TOMORROW.search(norm):
        return 1
    for weekday, rx in enumerate(_WEEKDAYS):
        if rx.search(norm):
            return (weekday - now.weekday()) % 7
    return 0 if _TODAY.search(norm) else None


def _in_part(hour: int, lo: int, hi: int) -> bool:
    return lo <= hour < hi if lo < hi else hour >= lo or hour < hi


SMALL_HOURS = 6  # before this hour the night still belongs to the evening that has just gone


def _part_today(now: datetime, part: str) -> tuple[datetime, str]:
    """(the moment, a note) of «вечером» with no day: now when the part is on, else its next turn (this evening,
    tomorrow morning). The note says so when the part of today is over («вечер уже прошёл») or, in the small hours,
    when «вечером» is taken as the coming evening. «Ночью» while it is still dark (after sunset, before sunrise and its
    twilight: 06:50 in October) is now, not 23:00."""
    lo, hi, anchor = next((lo, hi, a) for name, lo, hi, a in _PARTS if name == part)
    rise, sset, _ = sun_for(now.date())
    light = (datetime.combine(now.date(), rise) + DAWN_TWILIGHT).time() <= now.time() < sset
    if _in_part(now.hour, lo, hi) or (part == "night" and not light):
        return now, ""
    at = now.replace(hour=anchor % 24, minute=0, second=0, microsecond=0)
    if part == "night":
        return at, ""
    if now.hour < lo:
        return at, "small_hours" if part == "evening" and now.hour < SMALL_HOURS else ""
    return at + timedelta(days=1), f"passed_{part}"


def _clock(norm: str) -> tuple[int, int, tuple[int, int]] | None:
    """(hour, minute, span) of a clock time said in the message («в 19:00», «at 7 pm»), else None."""
    if m := _CLOCK.search(norm):
        return int(m.group(1)), int(m.group(2)), m.span()
    if m := _AMPM.search(norm):
        hour = int(m.group(1)) % 12 + (12 if m.group(2) == "pm" else 0)
        return hour, 0, m.span()
    return None


def read_when(text: str, now: datetime) -> AskedTime | None:
    """The time the message names, or None when it names none."""
    norm = normalize(text)
    now = to_local_naive(now)
    part = next((name for name, rx in _PART_WORDS.items() if rx.search(norm)), "")
    offset = _day_offset(norm, now)
    clock = _clock(norm)
    if offset is None and not part and clock is None:
        return None
    meal = next((h for rx, h in _MEALS if rx.search(norm)), None)
    if offset:  # a day ahead: the part of it, or a meal said next to it, or the middle of the day
        hour = next((a for name, _, _, a in _PARTS if name == part), meal or DEFAULT_HOUR)
        moment = (now + timedelta(days=offset)).replace(
            hour=hour % 24, minute=0, second=0, microsecond=0
        )
        note = ""
    else:
        moment, note = _part_today(now, part) if part else (now, "")
    spans = _spans(norm, [_AFTER, _TOMORROW, _TODAY, *_WEEKDAYS, *_PART_WORDS.values()])
    if clock is not None:  # «в 19:00»: that hour of the day named (today by default)
        hour, minute, span = clock
        spans.append(span)
        moment = (now + timedelta(days=offset or 0)).replace(
            hour=hour, minute=minute, second=0, microsecond=0
        )
        note = ""
        if not offset and moment <= now:  # the time has gone by: the same time tomorrow, said
            moment, note = moment + timedelta(days=1), "passed_clock"
    cut = _cut(text, norm, spans)
    return AskedTime(
        moment=moment,
        rest=cut,
        days=(moment.date() - now.date()).days,
        part=part,
        shifted=moment != now,
        exact=bool(part)
        or clock is not None
        or (offset is not None and offset > 0 and meal is not None),
        since=now,
        note=note,
    )


def stamp(reply: str, asked: AskedTime, lang: str) -> str:
    """The reply with the time it answers for in front of it («Завтра днём, 13:00. …»); unchanged for the present."""
    if not asked.shifted:
        return reply
    label = asked.label(lang)
    said = f"{s(f'w_note_{asked.note}', lang, t=f'{asked.moment:%H:%M}')} " if asked.note else ""
    return s("w_stamp", lang, when=label[:1].upper() + label[1:], reply=f"{said}{reply}")


# ------------------------------------------------------------------ «if it is not cold»

_NOT_COLD = re.compile(
    r"\bсуы[қк]\s+емес\s+болса\b|\bжылы\s+болса\b|\bесли\s+(?:на\s+улице\s+)?(?:не\s+(?:будет\s+)?холодно|тепло|будет\s+тепло|тепло\s+будет)\b|"
    r"\bесли\s+не\s+(?:слишком\s+)?(?:холодно|мороз)\b|\bif\s+(?:it(?:'s|\s+is|\s+isn'?t|\s+is\s+not)?\s+)?(?:not\s+)?(?:too\s+)?(?:cold|warm)(?:\s+enough)?\b|"
    r"\bif\s+it(?:'s|\s+is)\s+not\s+(?:too\s+)?cold\b|\bif\s+it\s+isn'?t\s+(?:too\s+)?cold\b|\bif\s+not\s+cold\b",
    re.IGNORECASE,
)
_NEGATIVE_COLD = re.compile(r"\bif\s+it(?:'s|\s+is)\s+cold\b|\bif\s+cold\b", re.IGNORECASE)
_OUTDOOR = re.compile(
    r"\b(?:в\s+)?парк\w*|\bсквер\w*|\bсаяба[қк]\w*|\bпрогулк\w*|\bпогуля\w*|\bгуля\w*|\bсеруен\w*|\bна\s+улице\b|\bоткрыт\w+\s+воздух\w*|"
    r"\bpark\w*|\bwalk\w*|\boutdoors?\b|\boutside\b|\bplayground\b",
    re.IGNORECASE,
)


def read_condition(text: str) -> tuple[str, bool] | None:
    """«суық емес болса саябаққа барайық», «если не холодно, пойдём в парк», «if it's not cold»: (the message without the
    condition, True), the person's wish for the street depends on the weather; None when there is no such condition."""
    if _NEGATIVE_COLD.search(text) or (m := _NOT_COLD.search(text)) is None:
        return None
    rest = " ".join(f"{text[: m.start()]} {text[m.end() :]}".split()).strip(" ,;:")
    return (rest, True) if any(ch.isalnum() for ch in rest) else None


def indoors(text: str, lang: str) -> str:
    """The message with its outdoor words replaced by «в помещении»: the street wish that the cold has cancelled."""
    rest = " ".join(_OUTDOOR.sub(" ", text).split()).strip(" ,;:")
    return f"{rest} {s('indoors', lang)}".strip()
