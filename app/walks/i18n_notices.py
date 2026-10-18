"""Wording of the notice lines of an answer (walks.dialog_extras, walks.dialog_asks): an official Kazhydromet notice
about Astana, the airport bus. An entry is a tuple (kk, ru, en) like walks.i18n.STRINGS; `tn` is this table's own
lookup. The official text of a storm warning is Russian only; the line says so in kk / en."""

from __future__ import annotations

from .i18n import Entry, pick

MONTHS_OF = {  # «18 октября»: the day of a notice
    "kk": ("қаңтардың", "ақпанның", "наурыздың", "сәуірдің", "мамырдың", "маусымның", "шілденің",
           "тамыздың", "қыркүйектің", "қазанның", "қарашаның", "желтоқсанның"),
    "ru": ("января", "февраля", "марта", "апреля", "мая", "июня", "июля", "августа", "сентября",
           "октября", "ноября", "декабря"),
    "en": ("January", "February", "March", "April", "May", "June", "July", "August", "September",
           "October", "November", "December"),
}  # fmt: skip

NOTICE_STRINGS: dict[str, Entry] = {
    # ---- weather: only what Kazhydromet says about Astana, short, with the link
    "wx_warn_storm": (
        "Астана үшін дауыл ескертуі (Қазгидромет, орыс тілінде): {text}",
        "Штормовое предупреждение для Астаны: {text}",
        "Storm warning for Astana (Kazhydromet, in Russian): {text}",
    ),
    "wx_warn_nmu": (
        "Астанада {day} НМУ — қолайсыз метеожағдайлар",
        "НМУ в Астане {day}",
        "NMU (smog alert) in Astana on {day}",
    ),
    "wx_src": ("Қазгидромет", "Казгидромет", "Kazhydromet"),
    # ---- the airport bus (facts of nn-airport.kz)
    "ap_last": (
        "Әуежайға соңғы автобус № {route} — {time}",
        "Последний автобус № {route} в аэропорт — {time}",
        "Last bus No. {route} to the airport — {time}",
    ),
    "ap_gone": (
        "Әуежайға соңғы № {route} автобус {time} кетті",
        "Последний автобус № {route} в аэропорт ушёл в {time}",
        "The last bus No. {route} to the airport left at {time}",
    ),
    "ap_first": (
        "Әуежайға автобустар {time} бастап жүреді (№ {route})",
        "Автобусы в аэропорт начинают ходить в {time} (№ {route})",
        "Buses to the airport start running at {time} (No. {route})",
    ),
    "ap_detail": (
        "Әуежай сайтының автобус беті, {date}",
        "страница автобусов на сайте аэропорта, {date}",
        "the bus page of the airport website, {date}",
    ),
    "ap_route": (
        "№ {route}: {first}–{last}, {headway} мин сайын",
        "№ {route}: {first}–{last}, каждые {headway} мин",
        "No. {route}: {first}–{last}, every {headway} min",
    ),
    "ap_answer": (
        "Әуежайға автобустар жүреді: {routes}. Жол ақысы: картамен {card} ₸, қолма-қол {cash} ₸.",
        "В аэропорт ходят автобусы: {routes}. Проезд: {card} ₸ по карте, {cash} ₸ наличными.",
        "Buses run to the airport: {routes}. Fare: {card} ₸ by card, {cash} ₸ in cash.",
    ),
    "ap_answer_nofare": (
        "Әуежайға автобустар жүреді: {routes}.",
        "В аэропорт ходят автобусы: {routes}.",
        "Buses run to the airport: {routes}.",
    ),
    "ap_only_airport": (
        "Менде тек әуежайға баратын автобустардың кестесі бар. ",
        "У меня есть расписание только автобусов в аэропорт. ",
        "I only have the timetable of the airport buses. ",
    ),
    "ap_none": (
        "Әуежайға баратын автобустардың кестесі менде жоқ — nn-airport.kz сайтын қараңыз.",
        "Расписания автобусов в аэропорт у меня нет — посмотрите на сайте аэропорта nn-airport.kz.",
        "I have no timetable of the airport buses; see the airport website, nn-airport.kz.",
    ),
}


def tn(key: str, lang: str | None, **fields: object) -> str:
    text = pick(NOTICE_STRINGS[key], lang)
    return text.format(**fields) if fields else text
