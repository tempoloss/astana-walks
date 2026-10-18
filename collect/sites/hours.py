"""Human opening-hours text (ru / kk / en / it / pl) -> OSM `opening_hours`, or None when not deterministic.

`to_osm("Пн-Пт 9-18, сб 10-16")` -> "Mo-Fr 09:00-18:00; Sa 10:00-16:00". Anything unknown (unknown word, bare
number, breaks, months, "до 22:00" without a start, overlapping rules, 12h times without am/pm on both ends) gives
None: a wrong schedule is worse than no schedule. Every result is parsed back with `opening-hours-py` (the parser the
app uses), so a string this module returns is always accepted by the app.
"""

from __future__ import annotations

import re
import unicodedata
from collections.abc import Iterable
from datetime import datetime, timedelta

from opening_hours import OpeningHours, ParserError

OSM_DAYS = ("Mo", "Tu", "We", "Th", "Fr", "Sa", "Su")
_L = "a-zà-öø-ÿĀ-ſїіа-яәіңғүұқөһ"  # letters of ru/kk/en/it/pl words (text is lower-cased first)

_STEMS = (
    ("понедельник", 0), ("вторник", 1), ("сред", 2), ("четверг", 3), ("пятниц", 4), ("суббот", 5), ("воскресен", 6),
    ("дүйсенбі", 0), ("сейсенбі", 1), ("сәрсенбі", 2), ("бейсенбі", 3), ("жұма", 4), ("жексенбі", 6), ("сенбі", 5),
    ("monday", 0), ("tuesday", 1), ("wednesday", 2), ("thursday", 3), ("friday", 4), ("saturday", 5), ("sunday", 6),
    # Italian / Polish full day names (Wikivoyage `orari=` / `godziny=`; abbreviations live in _SHORT)
    ("luned", 0), ("marted", 1), ("mercoled", 2), ("gioved", 3), ("venerd", 4), ("sabato", 5), ("domenica", 6),
    ("poniedzial", 0), ("wtorek", 1), ("sroda", 2), ("czwartek", 3), ("piatek", 4), ("sobota", 5), ("niedziela", 6),
)
_SHORT = {
    "пн": 0, "пнд": 0, "mo": 0, "mon": 0, "дс": 0,
    "вт": 1, "tu": 1, "tue": 1, "tues": 1, "сс": 1,
    "ср": 2, "we": 2, "wed": 2,
    "чт": 3, "th": 3, "thu": 3, "thur": 3, "thurs": 3, "бс": 3,
    "пт": 4, "птн": 4, "fr": 4, "fri": 4, "жм": 4,
    "сб": 5, "sa": 5, "sat": 5,
    "вс": 6, "su": 6, "sun": 6, "жс": 6, "жк": 6,
    # Italian (lun mar mer gio ven sab dom) and Polish (pon pn wt śr sr czw pt sb sob nd)
    "lun": 0, "mar": 1, "mer": 2, "gio": 3, "ven": 4, "sab": 5, "dom": 6,
    "pon": 0, "pn": 0, "wt": 1, "śr": 2, "sr": 2, "czw": 3, "pt": 4, "sob": 5, "sb": 5, "nd": 6, "nz": 6,
}

_AP = r"(?:am|pm|a\.m\.|p\.m\.)"
_TOKEN = re.compile(
    rf"""
    (?P<allday>24\s*/\s*7|круглосуточн\w*|круглые\s+сутки|24\s*(?:часа|часов|час|ч|hours?|h)\b(?:\s+в\s+сутки)?
        |round\s+the\s+clock|тәулік\s*бойы|тәулігіне\s+24\s+сағат|24\s*сағат)
    |(?P<daily>ежедневно|ежедн\.?|каждый\s+день|без\s+выходных|daily|every\s*day|7\s*/\s*7
        |7\s*(?:days|дней)(?:\s+a\s+week|\s+в\s+неделю)?|күн\s+сайын|күнде\w*
        |tutti\s+i\s+giorni|codziennie|każdy\s+dzień)
    |(?P<weekdays>будн\w*|рабочи[ех]\s+дн\w*|weekdays?|жұмыс\s+күндері)
    |(?P<weekend>выходны[ехм]\w*|weekends?|демалыс\s+күндері)
    |(?P<off>выходной|вых\.?|закрыт\w*|closed|off|не\s+работа\w*|жабық|демалыс)
    |(?P<time>(?P<h1>\d{{1,2}})(?:[:.](?P<m1>\d{{2}}))?\s*(?P<ap1>{_AP})?\s*(?:-|to|until|till|до|по|дейін)\s*
        (?P<h2>\d{{1,2}})(?:[:.](?P<m2>\d{{2}}))?\s*(?P<ap2>{_AP})?(?![\d:]))
    |(?P<day>(?<![{_L}])(?:понедельник\w*|вторник\w*|сред[аыуе]\w*|четверг\w*|пятниц\w*|суббот\w*|воскресен\w*
        |дүйсенбі\w*|сейсенбі\w*|сәрсенбі\w*|бейсенбі\w*|жұма\w*|сенбі\w*|жексенбі\w*
        |(?:mon|tues?|wednes|thurs?|fri|satur|sun)day\w*
        |luned[ìi]|marted[ìi]|mercoled[ìi]|gioved[ìi]|venerd[ìi]|sabato|domenica
        |poniedziad?ek|wtorek|ś?rod[ae]|czwartek|pi[ąa]tek|sobot[ae]|niedziel[ae]
        |(?:пнд?|вт|ср|чт|птн?|сб|вс|дс|сс|бс|жм|жс|жк|mon?|tues?|wed|thu?r?s?|fri|sat|sun|tu|we|th|fr|sa|su
          |lun|mar|mer|gio|ven|sab|dom|pon|pn|wt|śr|czw|pt|sob|sb|nd)\.?
        (?![{_L}\d])))
    |(?P<word>[{_L}]+)
    |(?P<seg>[;|/\n•])
    |(?P<comma>,)
    |(?P<dash>-)
    |(?P<skip>[\s.:()"'«»]+)
    |(?P<junk>.)
    """,
    re.VERBOSE | re.IGNORECASE,
)

_IGNORE = frozenset({
    "с", "c", "со", "в", "на", "и", "до", "по", "ч", "час", "часа", "часов", "работаем", "работает", "работа", "режим",
    "работы", "график", "время", "часы", "открыто", "открыты", "открыт", "дни", "дн", "from", "to", "till", "until",
    "on", "at", "and", "open", "opens", "opening", "hours", "every", "h", "сағат", "бастап", "дейін", "жұмыс",
    "уақыты", "кесте", "без", "перерыва", "перерывов", "обеда", "break", "breaks", "through", "thru", "daily",
})
_CONNECT = frozenset({"по", "to", "through", "thru", "till", "until", "до", "дейін"})

_WEEKDAY_SET = frozenset(range(5))
_WEEKEND_SET = frozenset({5, 6})
_ALL = frozenset(range(7))
ALL_DAY_WEEK = "Mo-Su 00:00-24:00"  # what `_render` prints for every day all day; stored as "24/7"


def _day_index(tok: str) -> int | None:
    t = tok.rstrip(".")
    if t in _SHORT:
        return _SHORT[t]
    for stem, i in _STEMS:
        if t.startswith(stem):
            return i
    folded = unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()
    if folded != t and folded:  # Latin with diacritics ('śr' -> 'sr', 'piątek' -> 'piatek')
        if folded in _SHORT:
            return _SHORT[folded]
        for stem, i in _STEMS:
            if folded.startswith(stem):
                return i
    return None


SENTINEL = "sentinel"  # marker returned by _interval for 00:00-00:00; analyze() decides what it means


def _hhmm(h: str, m: str | None, ap: str | None) -> tuple[int, int] | None:
    hour, minute = int(h), int(m or 0)
    if minute > 59:
        return None
    if ap:
        if not 1 <= hour <= 12:
            return None
        hour = hour % 12 + (12 if ap.startswith("p") else 0)
    elif hour > 24 or (hour == 24 and minute):
        return None
    return hour, minute


def _interval(m: re.Match) -> str | None:
    ap1, ap2 = (m["ap1"] or "").lower() or None, (m["ap2"] or "").lower() or None
    if bool(ap1) != bool(ap2):  # "9-5pm", "10-10pm": 12h reading is a guess
        return None
    a, b = _hhmm(m["h1"], m["m1"], ap1), _hhmm(m["h2"], m["m2"], ap2)
    if a is None or b is None or a[0] == 24:
        return None
    start, end = a[0] * 60 + a[1], b[0] * 60 + b[1]
    if start == 0 and end == 0:  # "00:00-00:00": an export default for "no data" / "round the clock" alike
        return SENTINEL
    if start == 0 and end in (24 * 60, 23 * 60 + 59):
        return "00:00-24:00"
    if end == 0:
        end = 24 * 60
    if end == start:
        return None
    return f"{start // 60:02d}:{start % 60:02d}-{end // 60:02d}:{end % 60:02d}"


def _tokens(text: str) -> list[tuple[str, object]] | None:
    s = re.sub(r"<br\s*/?>|</?(?:p|li|div|tr)\b[^>]*>", ";", text.lower().replace("ё", "е").replace("\u00a0", " "))
    s = re.sub(r"[\u2010-\u2015\u2212]", "-", s)
    out: list[tuple[str, object]] = []
    for m in _TOKEN.finditer(s):
        kind = m.lastgroup if m.lastgroup not in ("h1", "m1", "ap1", "h2", "m2", "ap2") else "time"
        if m["time"]:
            kind = "time"
        if kind == "junk":
            return None
        if kind == "skip":
            continue
        if kind == "time":
            iv = _interval(m)
            if iv is None:
                return None
            out.append(("time", iv))
        elif kind == "day":
            idx = _day_index(m["day"])
            if idx is None:
                return None
            out.append(("day", idx))
        elif kind == "word":
            out.append(("word", m["word"]))
        else:
            out.append((kind, None))
    # "с пн по пт": a connector word between two days is a range dash; other filler words vanish
    resolved: list[tuple[str, object]] = []
    for i, (kind, val) in enumerate(out):
        if kind == "word":
            if (val in _CONNECT and resolved and resolved[-1][0] == "day"
                    and i + 1 < len(out) and out[i + 1][0] == "day"):
                resolved.append(("dash", None))
            elif val not in _IGNORE:
                return None
            continue
        resolved.append((kind, val))
    # a dash is a day range only between two days ("Вс — выходной", "10-22 — ежедневно" carry no range)
    return [
        t for k, t in enumerate(resolved)
        if t[0] != "dash" or (0 < k < len(resolved) - 1 and resolved[k - 1][0] == "day" and resolved[k + 1][0] == "day")
    ]


def _consume_days(items, i: int) -> tuple[frozenset[int] | None, int]:
    days: set[int] = set()
    n = len(items)
    while i < n:
        kind, val = items[i]
        if kind == "day":
            if i + 2 < n and items[i + 1][0] == "dash" and items[i + 2][0] == "day":
                a, b = val, items[i + 2][1]
                days.update(range(a, b + 1) if a <= b else [*range(a, 7), *range(0, b + 1)])
                i += 3
            else:
                days.add(val)
                i += 1
        elif kind in ("daily", "weekdays", "weekend"):
            days.update({"daily": _ALL, "weekdays": _WEEKDAY_SET, "weekend": _WEEKEND_SET}[kind])
            i += 1
        else:
            break
        if i + 1 < n and items[i][0] == "comma" and items[i + 1][0] in ("day", "daily", "weekdays", "weekend"):
            i += 1
    return (frozenset(days) if days else None), i


def _consume_times(items, i: int) -> tuple[list[str] | str | None, int]:
    """-> ([interval, ...] | "allday" | "off" | None, next index)."""
    n = len(items)
    if i < n and items[i][0] in ("allday", "off"):
        return ("allday" if items[i][0] == "allday" else "off"), i + 1
    times: list[str] = []
    while i < n and items[i][0] == "time":
        times.append(items[i][1])
        i += 1
        if i + 1 < n and items[i][0] == "comma" and items[i + 1][0] == "time":
            i += 1
    return (times or None), i


def _parse_segment(items) -> list[tuple[frozenset[int] | None, list[str] | str]] | None:
    rules: list[tuple[frozenset[int] | None, list[str] | str]] = []
    i, n = 0, len(items)
    while i < n:
        if items[i][0] == "comma":
            i += 1
            continue
        days, i = _consume_days(items, i)
        if days and i + 1 < n and items[i][0] == "comma" and items[i + 1][0] in ("time", "allday", "off"):
            i += 1  # "ПН-ВС, с 6:00 до 23:00"
        spec, i = _consume_times(items, i)
        if spec is None:
            return None
        if days is None:  # "10:00-22:00 ежедневно" / "круглосуточно, без выходных"
            j = i
            while j < n and items[j][0] == "comma":
                j += 1
            after, k = _consume_days(items, j)
            if after:
                days, i = after, k
        rules.append((days, spec))
    return rules


def _days_text(days: Iterable[int]) -> str:
    ds, parts, i = sorted(set(days)), [], 0
    while i < len(ds):
        j = i
        while j + 1 < len(ds) and ds[j + 1] == ds[j] + 1:
            j += 1
        if j - i >= 2:
            parts.append(f"{OSM_DAYS[ds[i]]}-{OSM_DAYS[ds[j]]}")
        else:
            parts.extend(OSM_DAYS[d] for d in ds[i:j + 1])
        i = j + 1
    return ",".join(parts)


def _intervals_ok(times: list[str]) -> bool:
    spans = []
    for t in times:
        a, b = t.split("-")
        start, end = int(a[:2]) * 60 + int(a[3:]), int(b[:2]) * 60 + int(b[3:])
        spans.append((start, end + 1440 if end <= start else end))
    spans.sort()
    return all(spans[k][1] <= spans[k + 1][0] for k in range(len(spans) - 1)) and (
        len(spans) == 1 or spans[-1][1] <= spans[0][0] + 1440)


def validate_osm(value: str | None) -> bool:
    """True when the app's opening-hours parser accepts the string."""
    if not value or not value.strip():
        return False
    try:
        OpeningHours(value)
    except (ParserError, ValueError):
        return False
    return True


_WEEK0 = datetime(2026, 6, 1)  # a Monday; no Kazakh public holiday that week


def same_schedule(a: str | None, b: str | None, step_min: int = 15) -> bool:
    """True when two OSM opening-hours strings open exactly the same minutes of a reference week (sampled every
    `step_min`). Unparseable input is never 'the same'."""
    if not validate_osm(a) or not validate_osm(b):
        return False
    oa, ob = OpeningHours(a), OpeningHours(b)
    for k in range(7 * 24 * 60 // step_min):
        t = _WEEK0 + timedelta(minutes=k * step_min)
        if oa.is_open(t) != ob.is_open(t):
            return False
    return True


def _render(rules) -> str | None:
    """Rules -> OSM text. Day sets may overlap only as 'general rule, then exception on a strict subset of its days'
    ("ежедневно 10-22; пт, сб 10-23"), which OSM reads the same way (the later rule wins)."""
    norm: list[tuple[frozenset[int], object]] = []
    for days, spec in rules:
        if days is None:
            if len(rules) > 1:
                return None
            days = _ALL
        if spec == "allday":
            spec = ["00:00-24:00"]
        if spec == "off" and days == _ALL:
            return None
        if spec != "off" and not _intervals_ok(spec):
            return None
        norm.append((days, spec if spec == "off" else tuple(spec)))
    overridden = False
    for k, (days, _) in enumerate(norm):
        for prev_days, _ in norm[:k]:
            if days & prev_days:
                if not days < prev_days:
                    return None
                overridden = True
    if not overridden:  # same hours on several days: "Mo 10-18; Tu 10-18" -> "Mo,Tu 10-18"
        merged: dict[object, set[int]] = {}
        for days, spec in norm:
            merged.setdefault(spec, set()).update(days)
        norm = [(frozenset(d), s) for s, d in merged.items()]
    return "; ".join(f"{_days_text(days)} {'off' if spec == 'off' else ','.join(spec)}" for days, spec in norm)


def analyze(text: str | None) -> tuple[str | None, list[str]]:
    """(OSM `opening_hours` or None, flags). Flags say why a readable schedule was *not* converted:

    * ``needs_days``: the text gives times but names no days ("с 18:00 до 06:00", "10:00-22:00"), so the schedule
      cannot be attached to a weekday. "круглосуточно" alone is a complete statement and is converted;
    * ``ambiguous_24h``: a ``00:00-00:00`` range with no "круглосуточно" / "24/7" in the same text.

    No flag and None: the text is not understood at all."""
    if not text or not text.strip() or len(text) > 400:
        return None, []
    toks = _tokens(text)
    if not toks:
        return None, []
    flags: list[str] = []
    if any(t == ("time", SENTINEL) for t in toks):
        if any(kind == "allday" for kind, _ in toks):  # the same text says "круглосуточно": the range restates it
            toks = [("allday", None) if t == ("time", SENTINEL) else t for t in toks]
            toks = [t for k, t in enumerate(toks) if not (t[0] == "allday" and k and toks[k - 1][0] == "allday")]
        else:
            flags.append("ambiguous_24h")
            toks = [("time", "00:00-24:00") if t == ("time", SENTINEL) else t for t in toks]
    rules: list[tuple[frozenset[int] | None, list[str] | str]] = []
    segment: list[tuple[str, object]] = []
    for tok in [*toks, ("seg", None)]:
        if tok[0] != "seg":
            segment.append(tok)
            continue
        if segment:
            parsed = _parse_segment(segment)
            if parsed is None:
                return None, flags
            rules.extend(parsed)
            segment = []
    if not rules:
        return None, flags
    if any(days is None and spec not in ("allday", "off") for days, spec in rules):
        flags.append("needs_days")
    if flags:
        return None, flags
    if len(rules) == 1 and rules[0][0] in (None, _ALL) and rules[0][1] == "allday":
        out = "24/7"
    else:
        out = _render(rules)
        if out is None:
            return None, []
        if out == ALL_DAY_WEEK:  # "Пн-Вс 00:00-23:59" says what "круглосуточно" says: one spelling for it
            out = "24/7"
    return (out if validate_osm(out) else None), []


def to_osm(text: str | None) -> str | None:
    """OSM `opening_hours` for a human schedule, or None when the text is not understood with certainty."""
    return analyze(text)[0]


def hours_flags(text: str | None) -> list[str]:
    """Why `text` was not converted (see `analyze`); [] when it converted or is not a schedule at all."""
    return analyze(text)[1]


# ---- schema.org openingHoursSpecification -----------------------------------------------------------------

_SCHEMA_DAYS = {"monday": 0, "tuesday": 1, "wednesday": 2, "thursday": 3, "friday": 4, "saturday": 5, "sunday": 6}


def spec_to_text(specs) -> str | None:
    """schema.org openingHoursSpecification (dict or list) -> "Mo-Fr 09:00-18:00; Sa 10:00-16:00" (an OSM string).

    None when a spec has a validity window, an unknown day or an unparsable time."""
    if isinstance(specs, dict):
        specs = [specs]
    per_day: dict[int, list[str]] = {}
    for sp in specs or []:
        if not isinstance(sp, dict) or sp.get("validFrom") or sp.get("validThrough"):
            return None
        days = sp.get("dayOfWeek")
        days = days if isinstance(days, list) else [days]
        idxs = []
        for d in days:
            idx = _SCHEMA_DAYS.get(str(d).rstrip("/").rsplit("/", 1)[-1].lower())
            if idx is None:
                return None
            idxs.append(idx)
        times = []
        for k in ("opens", "closes"):
            m = re.fullmatch(r"(\d{1,2}):(\d{2})(?::\d{2})?", str(sp.get(k) or "").strip())
            if not m:
                return None
            times.append(f"{int(m[1]):02d}:{m[2]}")
        iv = _interval(re.fullmatch(r"(?P<h1>\d+):(?P<m1>\d+)-(?P<h2>\d+):(?P<m2>\d+)(?P<ap1>)(?P<ap2>)",
                                    "-".join(times)))
        if iv is None or iv == SENTINEL:
            return None
        for d in idxs:
            per_day.setdefault(d, []).append(iv)
    if not per_day:
        return None
    groups: dict[tuple[str, ...], list[int]] = {}
    for d in sorted(per_day):
        groups.setdefault(tuple(sorted(per_day[d])), []).append(d)
    out = "; ".join(f"{_days_text(days)} {','.join(t)}" for t, days in groups.items())
    return out if validate_osm(out) else None
