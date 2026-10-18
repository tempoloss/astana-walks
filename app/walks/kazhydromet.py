"""Official Kazhydromet notices for Astana, read at run time (collect/SOURCES.md §14.1, verdict STORE with the mandatory
link to the source, Order of the Ministry of Ecology No. 267):

- the storm warning page kazhydromet.kz/ru/storm (its own feed `POST /ajax_storm.php`, region 20 = Astana): the notice
  carries the period of validity in its title («с 20 ч. 17 октября до 08 ч. 18 октября 2026 г.») and the text;
- the daily bulletin of unfavourable meteorological conditions (НМУ): one sentence for the next day, e.g.
  «18 октября неблагоприятные метеорологические условия ожидаются в городах …, Астана», published the day before.
  A city after «ночью» is at risk at night only (taken as 00:00-08:00 and 20:00-24:00 of that day).

Politeness: robots.txt of the host is read and obeyed (it has none today: the site answers with an HTML 404 page, which
counts as no restrictions), at most one request per second, the project User-Agent. The caller caches the result.
"""

from __future__ import annotations

import html
import json
import re
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from urllib.robotparser import RobotFileParser

from .hours import TZ
from .httpget import get_text
from .models import WeatherWarning

BASE = "https://www.kazhydromet.kz"
STORM_PAGE = f"{BASE}/ru/storm"
STORM_API = f"{BASE}/ajax_storm.php"
NMU_PAGE = f"{BASE}/ru/ecology/ezhednevnyy-byulleten-sostoyaniya-vozdushnogo-basseyna-nmu"
ROBOTS_URL = f"{BASE}/robots.txt"
ROBOTS_AGENT = "astana-walks"
ASTANA_REGION = 20
MIN_INTERVAL_S = 1.0
ROBOTS_TTL_S = 86400.0
UPCOMING = timedelta(hours=24)  # a notice that starts later than this is not shown yet
NIGHT_HOURS = ((0, 8), (20, 24))

_MONTHS = {
    name: number
    for number, name in enumerate(
        (
            "января",
            "февраля",
            "марта",
            "апреля",
            "мая",
            "июня",
            "июля",
            "августа",
            "сентября",
            "октября",
            "ноября",
            "декабря",
        ),
        1,
    )
}
_WS = re.compile(r"\s+")
_ASTANA = re.compile(r"Астан|Нур-Султан", re.IGNORECASE)
_WINDOW = re.compile(
    r"с\s+(\d{1,2})\s*ч\.?(?:\s*(\d{1,2})\s*мин\.?)?\s+(\d{1,2})\s+([а-я]+)(?:\s+(\d{4})\s*г\.?)?"
    r"\s+до\s+(\d{1,2})\s*ч\.?(?:\s*(\d{1,2})\s*мин\.?)?\s+(\d{1,2})\s+([а-я]+)\s+(\d{4})",
    re.IGNORECASE,
)
_NMU_DATE = re.compile(r"^(\d{1,2})\s+([а-я]+)", re.IGNORECASE)
_PUBLISHED = re.compile(r"Опубликовано\s+(\d{2})\.(\d{2})\.(\d{4})")
_NMU_BODY = re.compile(r'<div class="calendar_page_content">(.*?)</div>', re.DOTALL)
_NMU_TITLE = "Ежедневный бюллетень состояния воздушного бассейна (НМУ)"

Window = tuple[datetime, datetime]  # naive Astana time


@dataclass(frozen=True)
class Notice:
    kind: str  # "storm" | "nmu"
    title: str
    text: str
    source_url: str
    issued: str
    windows: tuple[Window, ...]
    attachment_url: str = ""


class RobotsDisallowed(PermissionError):
    pass


_robots: tuple[float, RobotFileParser | None] | None = None
_last_hit = 0.0


def reset() -> None:
    global _robots, _last_hit
    _robots = None
    _last_hit = 0.0


def _clean(text: str) -> str:
    return _WS.sub(" ", html.unescape(text).replace("\xa0", " ")).strip()


def _load_robots(timeout: float, opener, sleep) -> RobotFileParser | None:
    """The parsed robots.txt, None when the site has none (a non-robots body such as an HTML 404 page)."""
    global _robots
    if _robots is not None and time.monotonic() - _robots[0] < ROBOTS_TTL_S:
        return _robots[1]
    body = _throttled(ROBOTS_URL, timeout, opener, sleep)
    parser = None
    if re.search(r"^\s*user-agent\s*:", body, re.IGNORECASE | re.MULTILINE):
        parser = RobotFileParser()
        parser.parse(body.splitlines())
    _robots = (time.monotonic(), parser)
    return parser


def _throttled(
    url: str, timeout: float, opener, sleep, *, form: dict[str, str] | None = None
) -> str:
    global _last_hit
    wait = MIN_INTERVAL_S - (time.monotonic() - _last_hit)
    if wait > 0 and _last_hit:
        sleep(wait)
    _last_hit = time.monotonic()
    headers = {"Referer": STORM_PAGE, "X-Requested-With": "XMLHttpRequest"} if form else None
    return get_text(url, timeout, opener, form=form, headers=headers)


def _get(url: str, timeout: float, opener, sleep, *, form: dict[str, str] | None = None) -> str:
    parser = _load_robots(timeout, opener, sleep)
    if parser is not None and not parser.can_fetch(ROBOTS_AGENT, url):
        raise RobotsDisallowed(url)
    return _throttled(url, timeout, opener, sleep, form=form)


def _day(d: date) -> Window:
    start = datetime(d.year, d.month, d.day)
    return start, start + timedelta(days=1)


def _iso(when: datetime) -> str:
    return when.replace(tzinfo=TZ).isoformat(timespec="minutes")


# ---------------------------------------------------------------------------------------------------- storm


def parse_window(title: str, fallback: date | None = None) -> tuple[Window, ...]:
    """The period of validity named in the title of a storm warning; the whole `fallback` day when it names none."""
    m = _WINDOW.search(title)
    if m:
        s_month, e_month = _MONTHS.get(m[4].lower()), _MONTHS.get(m[9].lower())
        if s_month and e_month:
            e_year = int(m[10])
            s_year = int(m[5]) if m[5] else e_year - (1 if s_month > e_month else 0)
            try:
                start = datetime(s_year, s_month, int(m[3]), int(m[1]), int(m[2] or 0))
                end = datetime(e_year, e_month, int(m[8]), int(m[6]), int(m[7] or 0))
            except ValueError:
                start = end = None
            if start and end and end > start:
                return ((start, end),)
    return (_day(fallback),) if fallback else ()


def _for_astana(item: dict) -> bool:
    regions = item.get("regions") or []
    return (
        str(item.get("regionId")) == str(ASTANA_REGION)
        or any(str(r.get("id")) == str(ASTANA_REGION) for r in regions if isinstance(r, dict))
        or bool(_ASTANA.search(str(item.get("myRegions") or "")))
    )


def parse_storm(body: str) -> list[Notice]:
    """Storm warnings for Astana from the JSON of /ajax_storm.php (an empty list when there are none)."""
    out = []
    for item in json.loads(body).get("items") or []:
        if not _for_astana(item):
            continue
        title = _clean(str(item.get("name") or ""))
        issued = str(item.get("stormDate") or "")
        fallback = None
        with_date = re.fullmatch(r"(\d{2})\.(\d{2})\.(\d{4})", issued)
        if with_date:
            fallback = date(int(with_date[3]), int(with_date[2]), int(with_date[1]))
        attachment = str(item.get("attachment") or "")
        out.append(
            Notice(
                kind="storm",
                title=title,
                text=_clean(str(item.get("opis") or "")),
                source_url=STORM_PAGE,
                issued=issued,
                windows=parse_window(title, fallback),
                attachment_url=attachment if attachment.startswith(("http://", "https://")) else "",
            )
        )
    return out


# ---------------------------------------------------------------------------------------------------- НМУ


def parse_nmu(
    page: str, url: str = NMU_PAGE, today: date | None = None
) -> tuple[date | None, Notice | None]:
    """(the day the bulletin is about, its notice for Astana or None) from the bulletin page. The day is None when the
    page has no readable sentence; the notice is None when Astana is not in the list or no НМУ are expected."""
    body = _NMU_BODY.search(page)
    if body is None:
        return None, None
    text = _clean(re.sub(r"<[^>]+>", " ", body[1]))
    pub = _PUBLISHED.search(page)
    published = date(int(pub[3]), int(pub[2]), int(pub[1])) if pub else today
    m = _NMU_DATE.match(text)
    month = _MONTHS.get(m[2].lower()) if m else None
    if not (m and month and published):
        return None, None
    try:
        target = date(published.year, month, int(m[1]))
    except ValueError:
        return None, None
    if target < published - timedelta(days=30):  # a bulletin of December about January
        target = date(target.year + 1, target.month, target.day)
    head = text.partition("ночью")[0]
    if "не ожида" in text.lower() or not _ASTANA.search(text):
        return target, None
    start, end = _day(target)
    if _ASTANA.search(head):
        windows: tuple[Window, ...] = ((start, end),)
    else:  # only «ночью в городах …, Астана»
        windows = tuple(
            (start.replace(hour=a) if a < 24 else end, start.replace(hour=b) if b < 24 else end)
            for a, b in NIGHT_HOURS
        )
    notice = Notice(
        kind="nmu",
        title=_NMU_TITLE,
        text=text,
        source_url=url,
        issued=f"{pub[1]}.{pub[2]}.{pub[3]}" if pub else "",
        windows=windows,
    )
    return target, notice


# ---------------------------------------------------------------------------------------------------- feed


def fetch_notices(
    timeout: float,
    opener=urllib.request.urlopen,
    *,
    today: date,
    sleep=time.sleep,
) -> list[Notice]:
    """Every storm warning and НМУ notice for Astana that may concern today or tomorrow. Raises on a network error or
    when robots.txt forbids a page; an absent notice is an empty list."""
    notices = parse_storm(
        _get(
            STORM_API,
            timeout,
            opener,
            sleep,
            form={
                "date": "",
                "region": str(ASTANA_REGION),
                "year": "",
                "lang": "ru",
                "page": "1",
                "isInArchive": "0",
            },
        )
    )
    target, notice = parse_nmu(_get(NMU_PAGE, timeout, opener, sleep), NMU_PAGE, today)
    if notice is not None:
        notices.append(notice)
    if target is not None and target > today:  # the bulletin of today was published yesterday
        url = f"{NMU_PAGE}?date={today - timedelta(days=1):%Y-%m-%d}"
        target_y, notice_y = parse_nmu(_get(url, timeout, opener, sleep), url, today)
        if notice_y is not None and target_y == today:
            notices.append(notice_y)
    return notices


def warnings_at(notices: list[Notice], now: datetime) -> list[WeatherWarning]:
    """The notices in force at `now` (naive Astana time), and those that start within a day, active first."""
    out = []
    for n in notices:
        live = [w for w in n.windows if w[0] <= now < w[1]]
        later = sorted(w for w in n.windows if now < w[0] <= now + UPCOMING)
        chosen = live[0] if live else later[0] if later else None
        if chosen is None:
            continue
        out.append(
            WeatherWarning(
                kind=n.kind,  # type: ignore[arg-type]
                title=n.title,
                text=n.text,
                source_url=n.source_url,
                issued=n.issued,
                valid_from=_iso(chosen[0]),
                valid_to=_iso(chosen[1]),
                active=bool(live),
                attachment_url=n.attachment_url,
            )
        )
    out.sort(key=lambda w: (not w.active, w.kind != "storm", w.valid_from))
    return out
