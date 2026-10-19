"""Wording of the «сегодня рядом» block (kk / ru / en): heading, one line per event, the stale-data note. Pure
functions over an `events.EventHit` / `events.NearbyEvents` (duck-typed: this module imports nothing from walks)."""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

LANGS = ("kk", "ru", "en")
LOCAL = timezone(timedelta(hours=5))  # Astana time

STRINGS: dict[str, tuple[str, str, str]] = {
    "heading": ("Бүгін жақын жерде", "Сегодня рядом", "Nearby today"),
    "heading_tomorrow": ("Ертең жақын жерде", "Завтра рядом", "Nearby tomorrow"),
    "heading_on": ("{date} жақын жерде", "{date} рядом", "Nearby on {date}"),
    "on_now": ("қазір жүріп жатыр", "идёт сейчас", "on now"),
    "open_now": ("қазір ашық", "сейчас открыто", "open now"),
    "until": ("{date} дейін", "до {date}", "until {date}"),
    "sessions": ("сеанстар: {times}", "сеансы: {times}", "sessions: {times}"),
    "price_from": ("{n} ₸-дан", "от {n} ₸", "from {n} ₸"),
    "source": ("дереккөз: {src}", "источник: {src}", "source: {src}"),
    "data_as_of": ("деректер {when} бойынша", "данные на {when}", "data as of {when}"),
    "stale": (
        "Афиша {when} күні жаңартылған — деректер ескіруі мүмкін, шықпас бұрын нақтылаңыз.",
        "Афиша обновлялась {when} — данные могли устареть, уточните перед выходом.",
        "The listings were last updated {when} and may be out of date: check before you go.",
    ),
    "m": ("{n} м", "{n} м", "{n} m"),
    "km": ("{n} км", "{n} км", "{n} km"),
}
MONTHS = {  # kk in full: «қар» is «snow», not «қараша»
    "kk": (
        "қаңтар", "ақпан", "наурыз", "сәуір", "мамыр", "маусым", "шілде", "тамыз", "қыркүйек", "қазан", "қараша",
        "желтоқсан",
    ),
    "ru": ("янв", "фев", "мар", "апр", "мая", "июн", "июл", "авг", "сен", "окт", "ноя", "дек"),
    "en": ("Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"),
}  # fmt: skip
# «29 қарашаға дейін»: the month of an «until» date in the dative
MONTHS_TO_KK = (
    "қаңтарға", "ақпанға", "наурызға", "сәуірге", "мамырға", "маусымға", "шілдеге", "тамызға", "қыркүйекке", "қазанға",
    "қарашаға", "желтоқсанға",
)  # fmt: skip
SOURCE_LABELS = {
    "sxodim.com": "Sxodim",
    "inastana.kz": "InAstana",
    "youticket.kz": "YouTicket",
    "qazaqconcert.kz": "Қазақконцерт",
    "alem.ai": "Alem.ai",
}


def _idx(lang: str) -> int:
    return LANGS.index(lang) if lang in LANGS else 1


def t(key: str, lang: str, **kw) -> str:
    return STRINGS[key][_idx(lang)].format(**kw)


def heading(lang: str, day: datetime | None = None, today: datetime | None = None) -> str:
    """«Сегодня рядом»; for another asked day «Завтра рядом» / «25 окт рядом»."""
    days = (day.date() - today.date()).days if day is not None and today is not None else 0
    if days <= 0:
        return t("heading", lang)
    return (
        t("heading_tomorrow", lang)
        if days == 1
        else t("heading_on", lang, date=fmt_date(day, lang))
    )


def source_label(source: str) -> str:
    """`t.me/<channel>` is shown as the channel (@name), never as an official body."""
    if source.startswith("t.me/"):
        return "@" + source.removeprefix("t.me/")
    return SOURCE_LABELS.get(source, source)


def fmt_date(day: datetime, lang: str) -> str:
    return f"{day.day} {MONTHS.get(lang, MONTHS['ru'])[day.month - 1]}"


def _until_date(day: datetime, lang: str) -> str:
    return f"{day.day} {MONTHS_TO_KK[day.month - 1]}" if lang == "kk" else fmt_date(day, lang)


def fmt_distance(m: int, lang: str) -> str:
    return (
        t("km", lang, n=f"{m / 1000:.1f}".replace(".", ",") if lang != "en" else f"{m / 1000:.1f}")
        if m >= 1000
        else t("m", lang, n=m)
    )


def when_part(hit, lang: str, today: datetime) -> str:
    if hit.kind == "run":
        return (
            t("until", lang, date=_until_date(datetime.fromisoformat(hit.until), lang))
            if hit.until
            else t("on_now", lang)
        )
    if hit.kind == "standing":
        return t("open_now", lang) if hit.ongoing else f"{hit.start[11:16]}"
    start = datetime.fromisoformat(hit.start)
    if hit.kind == "sessions":
        times = ", ".join(s[11:16] for s in hit.sessions)
        return t("sessions", lang, times=times)
    clock = start.strftime("%H:%M")
    if hit.ongoing:
        return t("on_now", lang) + (f" ({clock})" if start.date() == today.date() else "")
    return clock if start.date() == today.date() else f"{fmt_date(start, lang)} {clock}"


def venue_part(hit) -> str:
    """«Venue, address»."""
    return hit.venue + (f", {hit.address}" if hit.address else "")


def price_part(hit, lang: str) -> str:
    """«от 3 000 ₸», '' when the price is unknown."""
    return (
        t("price_from", lang, n=f"{hit.price_from:,}".replace(",", " ")) if hit.price_from else ""
    )


def event_text(hit, lang: str, today: datetime) -> str:
    """«19:30 · Title — Venue, address · от 3 000 ₸ · 450 м» (the source is a link beside it, not a word here)."""
    where = venue_part(hit)
    head = where if hit.title.casefold() == hit.venue.casefold() else f"{hit.title} — {where}"
    parts = [
        when_part(hit, lang, today),
        head,
        price_part(hit, lang),
        fmt_distance(hit.distance_m, lang),
    ]
    return " · ".join(p for p in parts if p)


def event_line(hit, lang: str, today: datetime) -> str:
    """One line: «19:30 · Title — Venue, address · от 3 000 ₸ · 450 м · источник: Sxodim»."""
    return f"{event_text(hit, lang, today)} · {t('source', lang, src=source_label(hit.source))}"


def stale_note(fetched_at: str, lang: str) -> str:
    day = datetime.fromisoformat(fetched_at).astimezone(LOCAL)
    return t("stale", lang, when=f"{fmt_date(day, lang)} {day.strftime('%H:%M')}")
