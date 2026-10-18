"""Wording of the state-object layer (ЦОН branches, the sport register): the hours line of a card, the weekday words the
query reader knows. An entry is a tuple (kk, ru, en), the same order as in walks.i18n.STRINGS. Honesty rule: a missing
schedule is «данных нет», never «закрыто» and never «нет часов»."""

from __future__ import annotations

LANGS = ("kk", "ru", "en")

GOV_STRINGS: dict[str, tuple[str, str, str]] = {
    "gov_day_open": ("{day}: {hours}", "{day}: {hours}", "{day}: {hours}"),
    "gov_day_closed": ("{day}: жабық", "{day}: закрыто", "{day}: closed"),
    "gov_unknown": (
        "жұмыс уақыты белгісіз (дереккөзде деректер жоқ)",
        "часы работы неизвестны (в источнике данных нет)",
        "opening hours unknown (the source has no data)",
    ),
    "gov_unqualified": (
        "кесте күндерсіз көрсетілген: {hours}",
        "график указан без дней недели: {hours}",
        "schedule given without days: {hours}",
    ),
    "gov_admin": (
        "әкімшілік жұмыс уақыты {hours} - бұл қабылдау бөлмесі, объектіге кіру уақыты емес",
        "график администрации {hours} - это часы приёмной, не часы работы объекта",
        "administration hours {hours} - the office, not the opening hours of the venue",
    ),
    "gov_source": ("дереккөз: {source}", "по данным {source}", "source: {source}"),
    "gov_holiday": (
        "мереке күні кесте өзгеше болуы мүмкін",
        "в праздник график может отличаться",
        "the schedule may differ on a public holiday",
    ),
    "gov_none": (
        "мемлекеттік объектілер табылмады",
        "государственных объектов не найдено",
        "no state objects found",
    ),
    "gov_unmapped": (
        "тағы {n} объектінің координаттары жоқ: картада және жиында жоқ",
        "ещё {n} объектов реестра без координат: в наборе и на карте их нет",
        "{n} more registry objects have no coordinates: not in the dataset or on the map",
    ),
    "gov_kind_cson": ("ХҚКО (ЦОН)", "ЦОН", "Public Service Centre"),
    "gov_kind_sport_facility": ("спорт объектісі", "спортивный объект", "sports facility"),
    # sources and the hours label: «по данным ЦОН (gov4c.kz)» (walks.models.STATE_REGISTRY)
    "src_state_registry": (
        "мемлекеттік органның деректері (gov4c.kz, data.egov.kz)",
        "данные госоргана РК (gov4c.kz, data.egov.kz)",
        "state body open data (gov4c.kz, data.egov.kz)",
    ),
    "src_gov": ("ХҚКО (gov4c.kz)", "ЦОН (gov4c.kz)", "Public Service Centre (gov4c.kz)"),
    "src_gov_sport": (
        "спорт нысандары тізілімі (data.egov.kz)",
        "реестр спортобъектов (data.egov.kz)",
        "sports facilities register (data.egov.kz)",
    ),
    "by_gov": (
        "ХҚКО (gov4c.kz) деректері бойынша",
        "по данным ЦОН (gov4c.kz)",
        "per the Public Service Centre (gov4c.kz)",
    ),
    "hours_state_open_gov": (
        "ХҚКО (gov4c.kz) деректері бойынша ашық",
        "открыто по данным ЦОН (gov4c.kz)",
        "open according to the Public Service Centre (gov4c.kz)",
    ),
    "fact_open_gov": (
        "ХҚКО (gov4c.kz) кестесі бойынша осы уақытта ашық.",
        "По графику ЦОН (gov4c.kz) в это время открыто.",
        "Open at this time according to the Public Service Centre schedule (gov4c.kz).",
    ),
    "fact_open_247_gov": (
        "ХҚКО (gov4c.kz) деректері бойынша тәулік бойы жұмыс істейді.",
        "По данным ЦОН (gov4c.kz) работает круглосуточно.",
        "Open 24/7 according to the Public Service Centre (gov4c.kz).",
    ),
    "fact_nearest_open_gov": (
        "Таңдалған {n} «{cat}» орнының ішінде түзу сызық бойынша ХҚКО (gov4c.kz) кестесі бойынша ашық ең жақыны.",
        "Ближайшее по прямой из {n} подобранных мест «{cat}», открытое по графику ЦОН (gov4c.kz).",
        "The nearest in a straight line of the {n} selected “{cat}” places that is open by the Public Service Centre schedule (gov4c.kz).",
    ),
    "people_vs_gov": (
        "бұл ХҚКО (gov4c.kz) кестесімен сәйкес келмейді, сенімділік төмендетілді",
        "это расходится с графиком ЦОН (gov4c.kz), уверенность снижена",
        "this disagrees with the Public Service Centre schedule (gov4c.kz), confidence lowered",
    ),
    "fit_night_gov": (
        "ХҚКО (gov4c.kz) кестесі бойынша осы уақытта ашық",
        "по графику ЦОН (gov4c.kz) открыто в это время",
        "the Public Service Centre schedule (gov4c.kz) says it is open at that time",
    ),
    # a state-service request: the one-sentence reply
    "gov_reply_open": (
        "{name}: {day} — {iv}. Дереккөз: {src}.",
        "{name}: {day} — {iv}. Источник: {src}.",
        "{name}: {day} — {iv}. Source: {src}.",
    ),
    "gov_reply_none": (
        "gov4c.kz деректері бойынша {day} бірде-бір ХҚКО жұмыс істемейді.",
        "По данным gov4c.kz {day} ни один ЦОН не работает.",
        "According to gov4c.kz no Public Service Centre is open {day}.",
    ),
    "gov_now": ("қазір", "сейчас", "right now"),
    "gov_today": ("бүгін", "сегодня", "today"),
    "gov_tomorrow": ("ертең", "завтра", "tomorrow"),
    # a sports object: the register's office week next to the venue's unknown hours
    "gov_admin_answer": (
        "Әкімшілік (қабылдау бөлмесі) жұмыс уақыты {hours} — data.egov.kz деректері; бұл объектінің өзінің жұмыс уақыты емес.",
        "График администрации (приёмной) {hours} — данные data.egov.kz; это не часы работы самого объекта.",
        "The administration's office hours are {hours} (data.egov.kz); that is not the opening hours of the venue itself.",
    ),
}

SOURCES = {"gov4c.kz": "gov4c.kz", "data.egov.kz": "data.egov.kz"}

# weekday index 0 = Monday: (short label kk, ru, en), then the stems the query reader accepts (any language)
WEEKDAY_SHORT: tuple[tuple[str, str, str], ...] = (
    ("дс", "пн", "Mon"),
    ("сс", "вт", "Tue"),
    ("ср", "ср", "Wed"),
    ("бс", "чт", "Thu"),
    ("жм", "пт", "Fri"),
    ("сб", "сб", "Sat"),
    ("жс", "вс", "Sun"),
)
WEEKDAY_ON: tuple[tuple[str, str, str], ...] = (
    ("дүйсенбіде", "в понедельник", "on Monday"),
    ("сейсенбіде", "во вторник", "on Tuesday"),
    ("сәрсенбіде", "в среду", "on Wednesday"),
    ("бейсенбіде", "в четверг", "on Thursday"),
    ("жұмада", "в пятницу", "on Friday"),
    ("сенбіде", "в субботу", "on Saturday"),
    ("жексенбіде", "в воскресенье", "on Sunday"),
)
WEEKDAY_STEMS: tuple[tuple[str, ...], ...] = (
    ("понедельник", "дүйсенбі", "monday", "mon"),
    ("вторник", "сейсенбі", "tuesday", "tue"),
    ("среда", "среду", "среды", "среде", "сәрсенбі", "wednesday", "wed"),
    ("четверг", "бейсенбі", "thursday", "thu"),
    ("пятниц", "жұма", "friday", "fri"),
    ("суббот", "сенбі", "saturday", "sat"),
    ("воскресень", "жексенбі", "sunday", "sun"),
)
TODAY_STEMS = ("сегодня", "бүгін", "today")
TOMORROW_STEMS = ("завтра", "ертең", "tomorrow")
KIND_STEMS: dict[str, tuple[str, ...]] = {
    "cson": (
        "цон",
        "центр обслуживания населения",
        "хқко",
        "халыққа қызмет көрсету орталығы",
        "public service cent",
    ),
    "sport_facility": ("спортивный комплекс", "спорткомплекс", "спорт кешені", "sports complex"),
}


def _pick(entry: tuple[str, str, str], lang: str | None) -> str:
    return entry[LANGS.index(lang) if lang in LANGS else 1]


def gt(key: str, lang: str | None, **fields: object) -> str:
    text = _pick(GOV_STRINGS[key], lang)
    return text.format(**fields) if fields else text


def weekday_label(index: int, lang: str | None) -> str:
    return _pick(WEEKDAY_SHORT[index], lang)


def weekday_on(index: int, lang: str | None) -> str:
    """«в субботу» / «сенбіде» / «on Saturday»."""
    return _pick(WEEKDAY_ON[index], lang)
