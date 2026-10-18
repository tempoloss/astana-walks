"""Kazakh / Russian / English wording of everything the core (retrieval, generation, follow-ups, profile) writes
for the user. The user interface has its own table in app/i18n.py on top of `t` below.

An entry is a tuple (kk, ru, en); `t(key, lang, **fields)` picks one and fills the {fields}. The Russian and English
wording is the original one (tests quote it); the Kazakh is literary, in short standard sentences. A test keeps the
three versions of one key to the same {fields}. Only primitives go in and out: this module sits below `models`.
"""

from __future__ import annotations

import re

from .i18n_attrs import ATTR_STRINGS
from .i18n_gov import GOV_STRINGS
from .i18n_sources import SOURCE_STRINGS

LANGS = ("kk", "ru", "en")  # the order of the language selector: Kazakh first
DEFAULT_LANG = "ru"
LANG_NAMES = {"kk": "Қаз", "ru": "Рус", "en": "Eng"}  # selector labels
LANG_SELF = {"kk": "қазақша", "ru": "русский", "en": "English"}  # a language in its own words
LLM_LANGUAGE = {
    "kk": "Kazakh (қазақша)",
    "ru": "Russian",
    "en": "English",
}  # what the model is told to write in

Entry = tuple[str, str, str]


def norm(lang: str | None) -> str:
    return lang if lang in LANGS else DEFAULT_LANG


def pick(entry: Entry, lang: str | None) -> str:
    return entry[LANGS.index(norm(lang))]


def t(key: str, lang: str | None, **fields: object) -> str:
    text = pick(STRINGS[key], lang)
    return text.format(**fields) if fields else text


def plural_ru(n: int, one: str, few: str, many: str) -> str:
    if 11 <= n % 100 <= 14 or n % 10 not in (1, 2, 3, 4):
        return many
    return one if n % 10 == 1 else few


def times(n: int, lang: str | None) -> str:
    """«2 раза» / «2 рет» / «2x»."""
    if norm(lang) == "ru":
        return f"{n} раз" if 11 <= n % 100 <= 14 or n % 10 not in (2, 3, 4) else f"{n} раза"
    return f"{n} рет" if norm(lang) == "kk" else f"{n}x"


def marks(n: int, lang: str | None) -> str:
    lang = norm(lang)
    if lang == "ru":
        return f"{n} {plural_ru(n, 'отметка', 'отметки', 'отметок')}"
    return f"{n} белгі" if lang == "kk" else f"{n} marks"


def points(n: int, lang: str | None) -> str:
    lang = norm(lang)
    if lang == "ru":
        return f"{n} {plural_ru(n, 'точка', 'точки', 'точек')}"
    return f"{n} нүкте" if lang == "kk" else f"{n}"


# ------------------------------------------------------------------ categories and tips

CATEGORY: dict[str, Entry] = {
    "cafe": ("кафе", "кафе", "cafe"),
    "restaurant": ("мейрамхана", "ресторан", "restaurant"),
    "fast_food": ("жылдам тамақ", "фастфуд", "fast food"),
    "bar_nightlife": ("бар / түнгі өмір", "бар / ночная жизнь", "bar / nightlife"),
    "museum_gallery": ("мұражай / галерея", "музей / галерея", "museum / gallery"),
    "attraction_landmark": ("көрікті жер", "достопримечательность", "landmark"),
    "viewpoint": ("шолу алаңы", "смотровая точка", "viewpoint"),
    "park_garden": ("саябақ / сквер", "парк / сквер", "park / garden"),
    "kids_playground": ("балалар алаңы", "детская площадка", "kids' playground"),
    "entertainment": ("ойын-сауық", "развлечения", "entertainment"),
    "mall": ("сауда орталығы", "торговый центр", "mall"),
    "culture_theatre_cinema": ("театр / кино", "театр / кино", "theatre / cinema"),
    "coworking_library": ("коворкинг / кітапхана", "коворкинг / библиотека", "coworking / library"),
    "public_toilet": ("дәретхана", "туалет", "public toilet"),
    "sport": ("спорт", "спорт", "sport"),
    "other": ("басқа", "другое", "other"),
}
TIP: dict[str, Entry] = {
    "cafe": (
        "Сусын алып, демалыңыз.",
        "Возьмите напиток и сделайте паузу.",
        "Grab a drink and take a break.",
    ),
    "restaurant": (
        "Тамақтануға жақсы орын.",
        "Отличное место, чтобы поесть.",
        "A good place to eat.",
    ),
    "fast_food": ("Жылдам тамақтану.", "Быстрый перекус.", "A quick bite."),
    "bar_nightlife": (
        "Кешкі демалыс және музыка.",
        "Вечерний отдых и музыка.",
        "Evening drinks and music.",
    ),
    "museum_gallery": (
        "Көрмені аралап шығыңыз.",
        "Осмотрите экспозицию.",
        "Walk through the exhibition.",
    ),
    "attraction_landmark": (
        "Айнала қарап, суретке түсіңіз.",
        "Осмотрите объект и сделайте фото.",
        "Look around and take photos.",
    ),
    "viewpoint": ("Көріністі тамашалаңыз.", "Полюбуйтесь видом.", "Enjoy the view."),
    "park_garden": (
        "Аумақта асықпай серуендеңіз.",
        "Неспешная прогулка по территории.",
        "A relaxed stroll around the grounds.",
    ),
    "kids_playground": (
        "Балаңызға ойнауға мүмкіндік беріңіз.",
        "Дайте ребёнку поиграть.",
        "Let the child play.",
    ),
    "entertainment": (
        "Ойын немесе аттракцион таңдаңыз.",
        "Выберите аттракцион или игру.",
        "Pick an attraction or a game.",
    ),
    "mall": (
        "Галереялар мен дүкендерді аралаңыз.",
        "Прогуляйтесь по галереям и магазинам.",
        "Stroll through the galleries and shops.",
    ),
    "culture_theatre_cinema": (
        "Афишаны орнында тексеріңіз.",
        "Проверьте афишу на месте.",
        "Check the programme on site.",
    ),
    "coworking_library": (
        "Жұмыс істеуге немесе оқуға тыныш орын.",
        "Спокойное место для работы или чтения.",
        "A calm place to work or read.",
    ),
    "sport": ("Белсенді демалыс.", "Активный отдых.", "Active leisure."),
    "public_toilet": (
        "Бар-жоғы мен тазалығын орнында тексеріңіз.",
        "Наличие и состояние уточняйте на месте.",
        "Check availability and condition on site.",
    ),
    "other": ("Айналаңызға қараңыз.", "Осмотритесь на месте.", "Look around."),
}


def category_name(category: str, lang: str | None) -> str:
    entry = CATEGORY.get(category)
    return pick(entry, lang) if entry else category


def tip(category: str, lang: str | None) -> str:
    entry = TIP.get(category)
    return pick(entry, lang) if entry else ""


# ------------------------------------------------------------------ holidays (names are keyed by the Russian one)

_HOLIDAYS: dict[str, tuple[str, str]] = {  # ru -> (kk, en)
    "Новый год": ("Жаңа жыл", "New Year"),
    "Рождество Христово": ("Рождество (православие)", "Orthodox Christmas"),
    "Международный женский день": ("Халықаралық әйелдер күні", "International Women's Day"),
    "Наурыз мейрамы": ("Наурыз мейрамы", "Nauryz"),
    "Праздник единства народа Казахстана": (
        "Қазақстан халқының бірлігі күні",
        "Day of Unity of the People of Kazakhstan",
    ),
    "День защитника Отечества": ("Отан қорғаушы күні", "Defender of the Fatherland Day"),
    "День Победы": ("Жеңіс күні", "Victory Day"),
    "Курбан айт": ("Құрбан айт", "Kurban Ait"),
    "День Столицы": ("Астана күні", "Capital Day"),
    "День Республики Казахстан": ("Республика күні", "Republic Day"),
}
_MOVED = (" (демалыс ауыстырылды)", " (перенос)", " (day moved)")


def holiday_name(ru_name: str, lang: str | None) -> str:
    """A public holiday of walks.holidays (named in Russian) in the answer language."""
    lang = norm(lang)
    if lang == "ru":
        return ru_name
    base, moved = (
        (ru_name[: -len(" (перенос)")], True)
        if ru_name.endswith(" (перенос)")
        else (ru_name, False)
    )
    names = _HOLIDAYS.get(base)
    out = base if names is None else names[0 if lang == "kk" else 1]
    return out + (_MOVED[0] if lang == "kk" else _MOVED[2]) if moved else out


# ------------------------------------------------------------------ plain labels

METHOD: dict[str, Entry] = {  # how a walking time was obtained
    "valhalla": ("Valhalla жаяу маршруты", "пеший маршрут Valhalla", "Valhalla walking route"),
    "straight": ("түзу сызық бойынша, бағалау", "по прямой, оценка", "straight line, estimate"),
    "estimate": (
        "көлік жылдамдығы бойынша бағалау",
        "оценка по скорости транспорта",
        "estimate from the speed of the transport",
    ),
    "mixed": (
        "ішінара түзу сызық бойынша, бағалау",
        "частично по прямой, оценка",
        "partly a straight line, estimate",
    ),
}
PADDING: dict[str, Entry] = {  # badge of a card that is not an exact match of the request
    "expanded": ("сәл алысырақ", "чуть дальше", "a bit farther"),
    "backfill": ("басқа санат", "другая категория", "another category"),
    "substituted": ("басқа санат", "другая категория", "another category"),
}


def method_label(method: str, lang: str | None) -> str:
    return pick(METHOD[method], lang)


def padding_label(padding: str, lang: str | None) -> str:
    return pick(PADDING[padding], lang)


PRIVATE_LINK: Entry = (
    "резервтік модель (жеке профиль)",
    "резервная модель (частный профиль)",
    "backup model (private profile)",
)
# a model name may hold colons of its own («openai:vendor-model:31b@PROFILE»): one followed by a name character belongs
# to the link, one followed by a space («…@PROFILE: ok») ends it
_LINK_SPEC = re.compile(r"\b([a-z][a-z0-9_-]*):((?:[\w./@-]|:(?=[\w./@-]))+)")


def public_text(text: str | None, lang: str | None = "ru") -> str:
    """`text` as the user may see it: every model link that is not Google's (`openai:<model>@<PROFILE>`, anything
    with a private profile) is replaced by one fixed label; `gemini:*` links stay. The real names live only in the
    environment and the debug logs, never on screen."""

    def replace(m: re.Match[str]) -> str:
        private = m.group(1) == "openai" or "@" in m.group(2)
        return pick(PRIVATE_LINK, lang) if private else m.group(0)

    return _LINK_SPEC.sub(replace, text or "")


def radius_text(declared_m: int, effective_m: int, lang: str | None) -> str:
    """The radius of the time budget and, when it was widened, the real one with the reason."""
    out = t("radius_declared", lang, m=declared_m)
    if effective_m > declared_m:
        out += t("radius_widened", lang, m=effective_m)
    return out


# ------------------------------------------------------------------ people's marks

SIGNAL: dict[str, Entry] = {  # button labels of the anonymous marks
    "was_open": ("болдым: ашық", "был: открыто", "was there: open"),
    "was_closed": ("болдым: жабық", "был: закрыто", "was there: closed"),
    "has_socket": ("розетка бар", "есть розетка", "has sockets"),
    "has_wifi": ("Wi‑Fi бар", "есть Wi‑Fi", "has Wi-Fi"),
    "noisy": ("шулы", "шумно", "noisy"),
    "quiet": ("тыныш", "тихо", "quiet"),
    "hours_differ": ("жұмыс уақыты басқа", "другие часы", "different hours"),
}
_ATTR = {  # reason code -> signal whose wording is used inside a sentence
    "people_socket": "has_socket",
    "people_wifi": "has_wifi",
    "people_quiet": "quiet",
    "people_noisy": "noisy",
}


def signal_label(signal: str, lang: str | None) -> str:
    return pick(SIGNAL[signal], lang)


def attr_label(code: str, lang: str | None) -> str:
    return pick(SIGNAL[_ATTR[code]], lang)


def source_label(demo: bool, lang: str | None) -> str:
    """The source of every attribute taken from marks; demo entries say so."""
    return t("people_source_demo" if demo else "people_source", lang)


def people_hours(hours: str, n_open: int, n_closed: int, last: str, lang: str | None) -> str:
    """The hours evidence of marks: «люди отмечали открыто (2 раза, последний 15.10)»."""
    if hours == "mixed":
        return t("people_mixed", lang, o=n_open, c=n_closed, last=last)
    n = n_open if hours == "open" else n_closed
    return t(
        "people_open" if hours == "open" else "people_closed", lang, n=times(n, lang), last=last
    )


def age_label(band: str, lang: str | None) -> str:
    """A child's age band of the profile: «4–7 лет» / «0–3 года» / «4–7 жас» / «4–7 years»."""
    shown = band.replace("-", "–")
    lang = norm(lang)
    if lang == "ru":
        return f"{shown} {'года' if band == '0-3' else 'лет'}"
    return f"{shown} жас" if lang == "kk" else f"{shown} years"


# ------------------------------------------------------------------ the texts

STRINGS: dict[str, Entry] = {
    "radius_declared": (
        "{m} м сіздің уақытыңыз бойынша",
        "{m} м по вашему времени",
        "{m} m for your time",
    ),
    "radius_widened": (
        "; {m} м-ге дейін кеңейтілді, себебі жақын жерде лайықты орын аз",
        "; расширено до {m} м, т.к. рядом мало подходящего",
        "; widened to {m} m because little suitable is nearby",
    ),
    # pipeline: a request for drugs, sex services or weapons (Result.refusal): no places are offered
    "refusal": (
        "Бұған көмектесе алмаймын: бұл тыйым салынған немесе қауіпті нәрсеге сұраныс. Серуендеуге, тамақтануға немесе демалуға жақын жерден орын таба аламын.",
        "С этим не помогу: это запрос на запрещённое или опасное. Могу подсказать, где рядом погулять, поесть или отдохнуть.",
        "I can't help with that: it is a request for something illegal or dangerous. I can suggest a place nearby to walk, eat or relax.",
    ),
    # generate: the fit sentence of the template
    "fit_head": ("Сұранысыңызға сай: ", "Подходит под запрос: ", "Fits your request: "),
    "fit_head_off": (
        "Сұралған санат емес, бірақ ",
        "Не совсем то, что вы просили, но ",
        "Not quite what you asked for, but ",
    ),
    "fit_none_off": (
        "Сұралған санат емес, бірақ ең жақын лайықты нұсқа.",
        "Другая категория, но ближайший подходящий вариант.",
        "Another category, but the closest suitable option.",
    ),
    "fit_none": (
        "Қол жетімділік радиусындағы ең жақын лайықты нұсқа.",
        "Ближайший подходящий вариант в радиусе доступности.",
        "The closest suitable option in range.",
    ),
    "fit_category": (
        "«{cat}» санаты — сіз сұрағандай",
        "категория «{cat}» — как вы просили",
        "category “{cat}” as requested",
    ),
    "fit_kids": ("балаларға лайықты", "подходит для детей", "suitable for children"),
    "fit_quiet": ("әдетте тыныш орын", "обычно спокойное место", "usually a calm place"),
    "fit_wifi": ("OSM-де Wi-Fi көрсетілген", "в OSM указан Wi-Fi", "Wi-Fi is listed in OSM"),
    "fit_socket": (
        "OSM-де розеткалар көрсетілген",
        "в OSM указаны розетки",
        "power sockets are listed in OSM",
    ),
    "fit_wheelchair": (
        "арбамен кіру мүмкіндігі белгіленген",
        "отмечена доступность для колясок",
        "wheelchair access is marked",
    ),
    "fit_free": ("OSM деректері бойынша тегін", "бесплатно по данным OSM", "free according to OSM"),
    "fit_night": (
        "OSM сағаттары бойынша осы уақытта ашық",
        "по часам OSM открыто в это время",
        "OSM hours say it is open at that time",
    ),
    "fit_keywords": ("{kws} сұрауына сәйкес келеді", "совпадает с {kws}", "matches {kws}"),
    "budget_over": (
        "Уақыт шектеулі болса да, одан қысқа нұсқа табылмады, сондықтан орын тізімде қалды: мұнда "
        "әдетте кемінде {lo} мин қажет, ал барып-қайтқаннан кейін уақыт одан аз қалады.",
        "Ничего короче в заданное время не нашлось, поэтому место оставлено: обычно здесь нужно от "
        "{lo} мин, а после дороги туда и обратно остаётся меньше.",
        "Nothing shorter fits the time limit, so it stays on the list: a visit usually takes at least "
        "{lo} min, more than is left after the walk there and back.",
    ),
    # weather, air, darkness
    "wx_feels": ("сезілуі {deg}°C", "ощущается как {deg}°C", "feels like {deg}°C"),
    "wx_heavy": (
        "қатты жауын-шашын ({p} мм/сағ)",
        "сильные осадки ({p} мм/ч)",
        "heavy precipitation ({p} mm/h)",
    ),
    "air_reason": (
        "ластанған ауа (PM2.5 {pm} мкг/м³)",
        "загрязнённый воздух (PM2.5 {pm} мкг/м³)",
        "polluted air (PM2.5 {pm} µg/m³)",
    ),
    "wx_bad": (
        "сыртта қолайсыз ауа райы ({what}) — ғимарат ішіндегі орын",
        "на улице непогода ({what}) — место в помещении",
        "bad weather outside ({what}) - an indoor place",
    ),
    "wx_air": (
        "ауа ластанған (PM2.5 {pm} мкг/м³) — ғимарат ішіндегі орын",
        "воздух загрязнён (PM2.5 {pm} мкг/м³) — место в помещении",
        "polluted air (PM2.5 {pm} µg/m³) - an indoor place",
    ),
    "wx_dark": (
        "күн батқаннан кейін — ғимарат ішіндегі орын",
        "после заката — место в помещении",
        "after sunset - an indoor place",
    ),
    "wx_outdoor_off": (
        "мұндай жағдайда саябақ, шолу алаңы және балалар алаңын ұсынбаймыз",
        "парки, смотровые точки и площадки в таких условиях не предлагаем",
        "parks, viewpoints and playgrounds are not offered in these conditions",
    ),
    # marks of people
    "people_source": ("адамдардың белгілері бойынша", "по отметкам людей", "by people's marks"),
    "people_source_demo": (
        "адамдардың белгілері бойынша (демо-деректер)",
        "по отметкам людей (демо-данные)",
        "by people's marks (demo data)",
    ),
    "people_mixed": (
        "адамдардың белгілері бір-біріне қайшы (ашық {o}, жабық {c}; соңғысы {last})",
        "отметки людей расходятся (открыто {o}, закрыто {c}; последняя {last})",
        "people's marks disagree (open {o}, closed {c}; latest {last})",
    ),
    "people_open": (
        "адамдар ашық деп белгіледі ({n}, соңғысы {last})",
        "люди отмечали открыто ({n}, последний {last})",
        "people marked it open ({n}, latest {last})",
    ),
    "people_closed": (
        "адамдар жабық деп белгіледі ({n}, соңғысы {last})",
        "люди отмечали закрыто ({n}, последний {last})",
        "people marked it closed ({n}, latest {last})",
    ),
    "people_sep": (" — ", " — ", " - "),
    "people_vs_osm": (
        "бұл OSM сағаттарымен сәйкес келмейді, сенімділік төмендетілді",
        "это расходится с часами OSM, уверенность снижена",
        "this disagrees with the OSM hours, confidence lowered",
    ),
    "people_not_hours": (
        "бұл жұмыс уақытының жазбасы емес",
        "это не запись о часах работы",
        "this is not an opening-hours record",
    ),
    # notes under a card
    "note_chain": (
        "Желі: жақын жерде тағы {n} филиал бар, ең жақыны көрсетілген.",
        "Сеть: ещё {n} рядом, показана ближайшая.",
        "Chain: {n} more branch(es) nearby, the nearest one is shown.",
    ),
    "note_weather_outdoor": (
        "Ашық аспан астындағы орын, ал ауа райы қолайсыз ({reason}): жылы киініңіз, далада болатын "
        "уақыт қысқартылды.",
        "Место на открытом воздухе, а погода неблагоприятная ({reason}): оденьтесь тепло, "
        "время на улице сокращено.",
        "Outdoor place in bad weather ({reason}): dress warmly, time outside is shortened.",
    ),
    "note_air_outdoor": (
        "Ашық аспан астындағы орын, ал ауа ластанған (PM2.5 {pm} мкг/м³): далада болатын уақыт "
        "қысқартылды.",
        "Место на открытом воздухе, а воздух загрязнён (PM2.5 {pm} мкг/м³): время на улице сокращено.",
        "Outdoor place while the air is polluted (PM2.5 {pm} µg/m³): time outside is shortened.",
    ),
    "note_outdoor_kept": (
        "Сіз сұрағандай ашық аспан астындағы орын; жағдай: {reason} — серуенді қысқарту жөн.",
        "Место на улице, как вы просили; условия: {reason} — прогулку лучше сократить.",
        "An outdoor place, as you asked; conditions: {reason} — better keep the walk short.",
    ),
    "note_dark_outdoor": (
        "Күн батқаннан кейін: ашық жерде қараңғы, жарықтандыру туралы деректер жоқ.",
        "После заката: на открытом месте темно, освещение в данных неизвестно.",
        "After sunset: dark outdoors, lighting is not in the data.",
    ),
    "note_holiday": (
        "Мемлекеттік мереке ({name}): жұмыс уақыты басқаша болуы мүмкін, алдын ала нақтылаңыз.",
        "Государственный праздник ({name}): часы работы могут отличаться, уточните.",
        "Public holiday ({name}): opening hours may differ, check before you go.",
    ),
    "note_hours_unknown": (
        "Жұмыс уақыты деректерде белгісіз — шықпас бұрын нақтылаңыз.",
        "Часы работы в данных неизвестны — уточните перед выходом.",
        "Opening hours are unknown in the data - check before you go.",
    ),
    "note_off_category": (
        "Санат сұрауыңыздан тыс: жақын жерде лайықты орын аз.",
        "Категория вне вашего запроса: подходящих мест рядом мало.",
        "Outside the requested categories: few matching places in range.",
    ),
    "note_off_category_weather": (
        "Санат сұрауыңыздан тыс: қолайсыз жағдайға байланысты ғимарат ішіндегі орын ұсынылды.",
        "Категория вне вашего запроса: из-за погоды, воздуха или темноты предложено место в помещении.",
        "Outside the requested categories: an indoor place is offered because of the weather, air or darkness.",
    ),
    "note_expanded": (
        "Мәлімделген радиустан алыс: жақын жерде мұндай орын жоқ.",
        "Дальше заявленного радиуса: ближе такого места нет.",
        "Farther than the declared radius: there is no such place closer.",
    ),
    "note_wifi": (
        "Wi-Fi/розеткалар деректерде расталмаған.",
        "Wi-Fi/розетки в данных не подтверждены.",
        "Wi-Fi/sockets not confirmed in the data.",
    ),
    "note_visited": (
        "Сіз мұнда бұрын болғаныңызды белгілегенсіз.",
        "Вы отмечали, что уже бывали здесь.",
        "You marked that you have been here before.",
    ),
    "note_wheelchair": (
        "Арбамен кіру мүмкіндігі деректерде көрсетілмеген.",
        "Доступность для колясок в данных не указана.",
        "Wheelchair access is not stated in the data.",
    ),
    "note_tight": (
        "Уақыт тығыз: мұнда әдетте кемінде {lo} мин қажет, ал барып-қайтқаннан кейін шамамен {left} мин "
        "қалады — орында болатын уақыт қысқартылады.",
        "Впритык по времени: обычно здесь нужно от {lo} мин, а после дороги туда и обратно "
        "остаётся около {left} мин — время на месте придётся сократить.",
        "A tight fit: a visit usually takes at least {lo} min, about {left} min "
        "are left after the walk there and back - the stay will be shortened.",
    ),
    # hours phrases that the collector wrote into a Russian description
    "hours_usual": ("Әдетте", "Обычно", "Usually"),
    "hours_247": ("тәулік бойы", "круглосуточно", "24/7"),
    "hours_tail_holiday": (
        "мереке күні жұмыс уақыты басқаша болуы мүмкін",
        "в праздник часы могут отличаться",
        "hours may differ on a public holiday",
    ),
    "hours_tail_unconfirmed": (
        "өзектілігі расталмаған",
        "актуальность не подтверждена",
        "not confirmed as current",
    ),
    "address": ("Мекенжайы: {a}.", "Адрес: {a}.", "Address: {a}."),
    # the reasons of a card: one true fact per sentence (walks/reasons.py)
    "fact_time": (
        "Бір осы орынның өзі {budget} мин уақытыңызға сыяды: барып-қайту жолы ~{rt} мин және орнында ~{stay} мин.",
        "Одно это место укладывается в ваши {budget} мин: дорога туда и обратно ~{rt} мин и ~{stay} мин на месте.",
        "This place alone fits your {budget} min: ~{rt} min there and back and ~{stay} min on site.",
    ),
    "fact_open_247": (
        "OSM деректері бойынша тәулік бойы жұмыс істейді.",
        "По данным OSM работает круглосуточно.",
        "Open 24/7 according to OSM.",
    ),
    "fact_open": (
        "OSM сағаттары бойынша осы уақытта ашық.",
        "По часам OSM в это время открыто.",
        "Open at this time according to the OSM hours.",
    ),
    "fact_nearest_open": (
        "Таңдалған {n} «{cat}» орнының ішінде түзу сызық бойынша OSM сағаттары бойынша ашық ең жақыны.",
        "Ближайшее по прямой из {n} подобранных мест «{cat}», открытое по часам OSM.",
        "The nearest in a straight line of the {n} selected “{cat}” places that is open by the OSM hours.",
    ),
    "fact_nearest": (
        "Таңдалған {n} «{cat}» орнының ішінде түзу сызық бойынша ең жақыны.",
        "Ближайшее по прямой из {n} подобранных мест «{cat}».",
        "The nearest in a straight line of the {n} selected “{cat}” places.",
    ),
    "fact_only": (
        "Таңдалғандар арасындағы «{cat}» санатының жалғыз орны.",
        "Единственное место «{cat}» среди подобранных.",
        "The only “{cat}” place among those selected.",
    ),
    "fact_wiki": (
        "Бұл орын туралы Уикипедияда мақала бар (айына ~{n} қаралым).",
        "О месте есть статья в Википедии (~{n} просмотров за месяц).",
        "The place has a Wikipedia article (~{n} views a month).",
    ),
    "fact_wiki_top": (
        "Таңдалған орындар арасында Уикипедиядағы ең көп оқылатын мақала (айына ~{n} қаралым).",
        "Самая читаемая в Википедии статья среди подобранных мест (~{n} просмотров за месяц).",
        "The most-read Wikipedia article among the selected places (~{n} views a month).",
    ),
    "fact_wiki_plain": (
        "Бұл орын туралы Уикипедияда мақала бар.",
        "О месте есть статья в Википедии.",
        "The place has a Wikipedia article.",
    ),
    "fact_outdoor": (
        "Сыртта үстелдер бар (OSM).",
        "Есть столики на улице (OSM).",
        "There are tables outside (OSM).",
    ),
    "fact_cuisine": ("Асханасы: {c}.", "Кухня: {c}.", "Cuisine: {c}."),
    "note_shared_coord": (
        "Бұл жазбаның координаттары Overture-дағы басқа жазбалармен бірдей: орналасуы шамамен, қашықтығы болжамды.",
        "Координаты этой записи совпадают с другими записями Overture: положение приблизительное, расстояние ориентировочное.",
        "This record shares its coordinates with other Overture records: the position is approximate, and so is the distance.",
    ),
    # dialogue follow-ups (followup.describe)
    "fu_head": (
        "Алдыңғы сұранысты нақтылау: ",
        "Уточнение прошлого запроса: ",
        "Refining the previous request: ",
    ),
    "fu_closer_cap": (
        "жақынырақ ({cap} м-ден артық емес)",
        "поближе (не дальше {cap} м)",
        "closer (within {cap} m)",
    ),
    "fu_closer_factor": (
        "жақынырақ (радиус ×{f})",
        "поближе (радиус ×{f})",
        "closer (radius ×{f})",
    ),
    "fu_more": (
        "бұрын көрсетілген орындарсыз ({n})",
        "без уже показанных мест ({n})",
        "without the {n} place(s) already shown",
    ),
    "fu_no_alcohol": ("алкогольсіз", "без алкоголя", "no alcohol"),
    "fu_budget_low": ("арзанырақ", "подешевле", "cheaper"),
    "fu_budget_medium": ("орташа бюджет", "средний бюджет", "mid-range"),
    "fu_budget_high": ("қымбатырақ", "подороже", "pricier"),
    "fu_kids_yes": ("баламен", "с ребёнком", "with a child"),
    "fu_kids_no": ("баласыз", "без ребёнка", "without a child"),
    "fu_quiet_yes": ("тыныштау", "потише", "quieter"),
    "fu_quiet_no": ("тыныштық керек емес", "тишина не нужна", "quiet not required"),
    "fu_wifi_yes": ("Wi‑Fi / розеткамен", "с Wi‑Fi / розеткой", "with Wi-Fi / sockets"),
    "fu_wifi_no": (
        "Wi‑Fi / розетка керек емес",
        "Wi‑Fi / розетка не нужны",
        "Wi-Fi / sockets not needed",
    ),
    "fu_minutes": (
        "{sign}{n} мин (қазір {total})",
        "{sign}{n} мин (теперь {total})",
        "{sign}{n} min (now {total})",
    ),
    "fu_mode": ("көлік: {mode}", "транспорт: {mode}", "transport: {mode}"),
    # profile
    "explain_with_kids": ("баламен жүресіз", "ходите с ребёнком", "you go with a child"),
    "explain_mobility": (
        "баспалдақсыз кіру керек",
        "нужен доступ без ступенек",
        "you need step-free access",
    ),
    "explain_quiet": (
        "тыныш орындарды жақсы көресіз",
        "любите тихие места",
        "you like quiet places",
    ),
    "explain_budget": (
        "қолжетімді нәрсе іздейсіз",
        "ищете недорогое",
        "you look for something affordable",
    ),
    "explain_halal": ("халал керек", "нужен халяль", "you need halal"),
    "explain_no_alcohol": ("алкогольсіз керек", "без алкоголя", "you want no alcohol"),
    "explain_walk_pace": (
        "өз қарқыныңызбен жүресіз",
        "ходите в своём темпе",
        "you walk at your own pace",
    ),
    "explain_cold_tolerance": ("суыққа сезімталсыз", "чувствительны к холоду", "you feel the cold"),
    "explain_age": ("{band} жас", "{band} лет", "{band} y.o."),
    "explain_wrap": (
        "Сіз {parts} деп белгілегенсіз — бұл ескерілді.",
        "Вы отмечали, что {parts} — это учтено.",
        "You told me that {parts} - taken into account.",
    ),
    "item_with_kids": ("баламен жүремін", "хожу с ребёнком", "I go with a child"),
    "item_mobility_stroller": ("арбамен жүремін", "хожу с коляской", "I use a stroller"),
    "item_mobility_wheelchair": (
        "арбамен кіру мүмкіндігі керек",
        "нужен доступ на коляске-кресле",
        "I need wheelchair access",
    ),
    "item_quiet": ("тыныш орындарды жақсы көремін", "люблю тихие места", "I like quiet places"),
    "item_budget_low": ("арзанды іздеймін", "ищу недорогое", "I look for something cheap"),
    "item_budget_medium": ("орташа бюджет", "средний бюджет", "mid-range budget"),
    "item_budget_high": ("бюджет шектелмеген", "бюджет не ограничен", "no budget limit"),
    "item_halal": ("халал керек", "нужен халяль", "I need halal"),
    "item_no_alcohol": ("алкогольсіз", "без алкоголя", "no alcohol"),
    "item_language": (
        "жауап тілі: {language}",
        "язык ответа: {language}",
        "answer language: {language}",
    ),
    "item_pace_slow": ("асықпай жүремін", "хожу неспешно", "I walk slowly"),
    "item_pace_fast": ("тез жүремін", "хожу быстро", "I walk fast"),
    "item_cold_low": (
        "тоңамын: ғимарат ішіндегі орын жақсы",
        "мёрзну: лучше помещения",
        "I feel the cold: indoors preferred",
    ),
    "item_cold_high": ("суықты оңай көтеремін", "холод переношу легко", "I handle the cold well"),
    "item_visited": ("болдым: {name} ({day})", "был: {name} ({day})", "been there: {name} ({day})"),
    "item_liked": ("ұнады: {cat} ×{n}", "понравилось: {cat} ×{n}", "liked: {cat} ×{n}"),
    "chip_with_kids": (
        "Есте сақтау: баламен?",
        "Запомнить: с ребёнком?",
        "Remember: with a child?",
    ),
    "chip_quiet": (
        "Есте сақтау: тыныш орын керек?",
        "Запомнить: люблю тихие места?",
        "Remember: I like quiet places?",
    ),
    "chip_stroller": (
        "Есте сақтау: арбамен жүремін?",
        "Запомнить: хожу с коляской?",
        "Remember: I use a stroller?",
    ),
    "chip_wheelchair": (
        "Есте сақтау: баспалдақсыз кіру керек?",
        "Запомнить: нужен доступ без ступенек?",
        "Remember: I need step-free access?",
    ),
    "chip_budget": (
        "Есте сақтау: арзанды іздеймін?",
        "Запомнить: ищу недорогое?",
        "Remember: I look for something cheap?",
    ),
    "chip_no_alcohol": (
        "Есте сақтау: алкогольсіз?",
        "Запомнить: без алкоголя?",
        "Remember: no alcohol?",
    ),
    "chip_halal": (
        "Есте сақтау: халал керек?",
        "Запомнить: нужен халяль?",
        "Remember: I need halal?",
    ),
    "chip_language": (
        "Тілді есте сақтау: {language}?",
        "Запомнить язык: {language}?",
        "Remember the language: {language}?",
    ),
    # LRT hint (transit)
    "lrt_hint": (
        "LRT: {a} → {b} (кестені тексеріңіз)",
        "LRT: {a} → {b} (проверьте расписание)",
        "LRT: {a} → {b} (check the timetable)",
    ),
    "lrt_car": (
        "«көлікпен» режимі: LRT кеңестері қажет емес",
        "режим «на машине»: подсказки LRT не нужны",
        "“by car” mode: no LRT hints needed",
    ),
    "lrt_none": (
        "деректерде LRT бекеттері жоқ",
        "в данных нет станций LRT",
        "no LRT stations in the data",
    ),
    "lrt_far": (
        "LRT бекеттері сіздің нүктеңізден {m} м-ден алыс",
        "станции LRT дальше {m} м от вашей точки",
        "LRT stations are farther than {m} m from your point",
    ),
    "lrt_near": (
        "ең жақын LRT бекеті «{name}» {m} м жерде; кеңестер: {n}",
        "ближайшая станция LRT «{name}» в {m} м; подсказок: {n}",
        "the nearest LRT station “{name}” is {m} m away; hints: {n}",
    ),
}
STRINGS.update(ATTR_STRINGS)  # the attribute checks and honest notes: walks/i18n_attrs.py
STRINGS.update(
    SOURCE_STRINGS
)  # where a fact comes from when it is not OSM's: walks/i18n_sources.py
STRINGS.update(GOV_STRINGS)  # state registries (ЦОН, sport register): walks/i18n_gov.py
