"""Kazakh / Russian / English wording of the web UI (app/web): labels, banners, panels, the city and data pages.
An entry is a tuple (kk, ru, en); `tr(key, lang, **fields)` picks one and fills the {fields}.
The texts the core writes into an answer live in walks/i18n.py. Russian is what the tests and the screenshots of the
case quote; the Kazakh is literary, in short standard sentences (a test keeps the {fields} of the three equal).
"""

from __future__ import annotations

from i18n_panels import PANEL
from walks.i18n import Entry, norm, pick
from walks.walking import own_router

HOURS_STATES = ("open", "unknown", "closed")
CONFIDENCE = ("high", "medium", "low")


def tr(key: str, lang: str | None, **fields: object) -> str:
    text = pick(
        OWN_ROUTER_WORDING[key] if key in OWN_ROUTER_WORDING and own_router() else UI[key], lang
    )
    return text.format(**fields) if fields else text


def places_count(n: int, lang: str | None) -> str:
    """«3 места» / «3 орын» / «3 places»."""
    lang = norm(lang)
    if lang == "ru":
        if 11 <= n % 100 <= 14 or n % 10 not in (1, 2, 3, 4):
            return f"{n} мест"
        return f"{n} место" if n % 10 == 1 else f"{n} места"
    if lang == "kk":
        return f"{n} орын"
    return f"{n} place" if n == 1 else f"{n} places"


UI: dict[str, Entry] = {
    # ---- first screen
    "title": ("🧭 Анық", "🧭 Анық", "🧭 Анық"),
    "subtitle": (
        "Астанада серуенге арналған көмекші",
        "помощник для прогулок по Астане",
        "walking assistant for Astana",
    ),
    "value": (
        "Астанада орын емес, орындар туралы мәлімет жетіспейді — біз не белгілі екенін де, не "
        "белгісіз екенін де ашық көрсетеміз.",
        "В Астане не хватает не мест, а сведений о них — мы честно показываем, что известно, а что нет.",
        "Astana does not lack places, it lacks information about them — so we show what is known and "
        "what is not.",
    ),
    "lang_label": ("Тіл", "Язык", "Language"),
    # ---- the honesty legend
    # ---- the badges of a card
    # ---- the numbers of a card
    "why": ("Неге:", "Почему:", "Why:"),
    "what": ("Не істеу керек:", "Что делать:", "What to do:"),
    "hours_osm": ("OSM сағаттары: `{h}`", "часы OSM: `{h}`", "OSM hours: `{h}`"),
    "description": ("Сипаттама:", "Описание:", "Description:"),
    "mode_walk": ("жаяу", "пешком", "on foot"),
    "mode_car": ("көлікпен", "на машине", "by car"),
    "mode_transit": ("қоғамдық көлікпен", "на транспорте", "by public transport"),
    # ---- the answer: header, route summary
    # ---- status chips
    "src_sim": ("симуляция", "симуляция", "simulation"),
    "wx_label": (
        "{t}°C (сезілуі), жауын-шашын {p} мм",
        "{t}°C (ощущается), осадки {p} мм",
        "{t}°C (feels like), precipitation {p} mm",
    ),
    # ---- the sidebar
    "wx_real": ("Нақты (MET Norway)", "Реальная (MET Norway)", "Real (MET Norway)"),
    "wx_sim": ("Симуляция", "Симуляция", "Simulation"),
    "wx_none": ("Ескермеу", "Не учитывать", "Ignore"),
    "footer": (
        "Орындар деректері: © OpenStreetMap contributors (ODbL) — https://www.openstreetmap.org/copyright, "
        "https://opendatacommons.org/licenses/odbl/1-0/; Overture Maps (Meta, Microsoft, PinMeTo — "
        "CDLA-Permissive-2.0; Foursquare — Apache-2.0, © Foursquare Labs, Inc.; AllThePlaces — CC0); "
        "Wikidata (CC0); Wikipedia (CC BY-SA 4.0, мақалаға сілтемемен) · жаяу маршруттар: Valhalla / FOSSGIS "
        "(valhalla1.openstreetmap.de) · ауа райы болжамы: Data from MET Norway (CC BY 4.0, NLOD 2.0), "
        "бақылаулар мен ескертулер: Қазгидромет (kazhydromet.kz) · "
        "ауа сапасы (қосылған кезде): Weather data by Open-Meteo.com (https://open-meteo.com, CC BY 4.0) · "
        "карта: OpenFreeMap © OpenMapTiles, деректер OpenStreetMap · картадағы қатені хабарлау: "
        "https://www.openstreetmap.org/fixthemap · мәтіндер: ЖИ (қосулы болса).",
        "Данные мест: © OpenStreetMap contributors (ODbL) — https://www.openstreetmap.org/copyright, "
        "https://opendatacommons.org/licenses/odbl/1-0/; Overture Maps (Meta, Microsoft, PinMeTo — "
        "CDLA-Permissive-2.0; Foursquare — Apache-2.0, © Foursquare Labs, Inc.; AllThePlaces — CC0); "
        "Wikidata (CC0); Wikipedia (CC BY-SA 4.0, со ссылкой на статью) · пешие маршруты: Valhalla / FOSSGIS "
        "(valhalla1.openstreetmap.de) · прогноз погоды: Data from MET Norway (CC BY 4.0, NLOD 2.0), "
        "наблюдения и предупреждения: Казгидромет (kazhydromet.kz) · "
        "качество воздуха (если включено): Weather data by Open-Meteo.com (https://open-meteo.com, CC BY 4.0) · "
        "карта: OpenFreeMap © OpenMapTiles, данные OpenStreetMap · ошибка на карте: "
        "https://www.openstreetmap.org/fixthemap · тексты: ИИ (если включён).",
        "Place data: © OpenStreetMap contributors (ODbL) — https://www.openstreetmap.org/copyright, "
        "https://opendatacommons.org/licenses/odbl/1-0/; Overture Maps (Meta, Microsoft, PinMeTo — "
        "CDLA-Permissive-2.0; Foursquare — Apache-2.0, © Foursquare Labs, Inc.; AllThePlaces — CC0); "
        "Wikidata (CC0); Wikipedia (CC BY-SA 4.0, linked to the article) · walking routes: Valhalla / FOSSGIS "
        "(valhalla1.openstreetmap.de) · weather forecast: Data from MET Norway (CC BY 4.0, NLOD 2.0), "
        "observations and warnings: Kazhydromet (kazhydromet.kz) · "
        "air quality (when switched on): Weather data by Open-Meteo.com (https://open-meteo.com, CC BY 4.0) · "
        "map: OpenFreeMap © OpenMapTiles, data OpenStreetMap · report a map error: "
        "https://www.openstreetmap.org/fixthemap · texts: AI (if on).",
    ),
    # ---- dialogue / memory
    "mem_dialogue": ("**Диалог:** {note}.", "**Диалог:** {note}.", "**Dialogue:** {note}."),
    "mem_dialogue_default": (
        "алдыңғы сұранысты нақтылау",
        "уточнение прошлого запроса",
        "a refinement of the previous request",
    ),
    "mem_constraints": (
        "**Диалог / профиль шектеулері:** радиус ×{f}{cap}; көрсетілгендер шығарылды: {n}; алкогольсіз: "
        "{alc}; осы ережелер бойынша алынып тасталды: {ex}.",
        "**Ограничения диалога / профиля:** радиус ×{f}{cap}; исключено показанных: {n}; без алкоголя: "
        "{alc}; отсеяно по этим правилам: {ex}.",
        "**Limits of the dialogue / profile:** radius ×{f}{cap}; shown places excluded: {n}; no alcohol: "
        "{alc}; dropped by these rules: {ex}.",
    ),
    "mem_cap": (", {m} м-ден артық емес", ", не дальше {m} м", ", not farther than {m} m"),
    "mem_profile": (
        "**Профиль:** ескерілді: {items}. Профиль сұраныстар журналына жазылмайды және белгілер деректеріне "
        "түспейді; ЖИ-ге тек жалаушалар барады.",
        "**Профиль:** учтено {items}. Профиль не пишется в журнал запросов и не попадает в данные отметок; "
        "в ИИ уходят только флаги.",
        "**Profile:** taken into account: {items}. The profile is not written to the request log and does "
        "not enter the marks data; only flags go to the AI.",
    ),
    "mem_marks": (
        "**Адамдардың белгілері:** {n} үміткерде анонимді белгілер бар (30 күннен ескілері ескерілмейді, "
        "жаңалары салмақты; қайшылықтар сенімділікті төмендетеді). Олар «OSM сағаттарын» өзгертпейді, "
        "бөлек деңгей ретінде көрсетіледі.",
        "**Отметки людей:** у {n} кандидатов есть анонимные отметки (старше 30 дней не учитываются, "
        "свежие весят больше; противоречия снижают уверенность). Они не меняют «часы по OSM», показаны "
        "отдельным уровнем.",
        "**Marks of people:** {n} candidates have anonymous marks (older than 30 days are ignored, fresh "
        "ones weigh more; contradictions lower the confidence). They do not change the “OSM hours” and "
        "are shown as a level of their own.",
    ),
    "profile_code_with_kids": ("баламен жүру", "с ребёнком", "with a child"),
    "profile_code_mobility": ("баспалдақсыз кіру", "доступ без ступенек", "step-free access"),
    "profile_code_quiet": ("тыныш орындар", "тишина", "quiet places"),
    "profile_code_budget": ("бюджет", "бюджет", "budget"),
    "profile_code_halal": ("халал", "халяль", "halal"),
    "profile_code_no_alcohol": ("алкогольсіз", "без алкоголя", "no alcohol"),
    "profile_code_walk_pace": ("жүріс қарқыны", "темп ходьбы", "walking pace"),
    "profile_code_cold_tolerance": (
        "суыққа төзімділік",
        "чувствительность к холоду",
        "cold tolerance",
    ),
    "profile_code_language": ("жауап тілі", "язык ответа", "answer language"),
    "fu_more": ("➕ Тағы", "➕ Ещё", "➕ More"),
    "mark_fail": (
        "Белгіні сақтау мүмкін болмады",
        "Не удалось сохранить отметку",
        "Could not save the mark",
    ),
    "profile_visit": ("✔ Болдым", "✔ Был здесь", "✔ I was here"),
    "profile_like": ("👍 Ұнады", "👍 Понравилось", "👍 I liked it"),
    "panel_empty": (
        "Әзірге ештеңе сақталмаған. Жауаптан кейін «Есте сақтау: …» түймелері пайда болады — тек басқанда сақталады.",
        "Пока ничего не сохранено. После ответа появятся кнопки «Запомнить: …» — сохраняется только по клику.",
        "Nothing is stored yet. After an answer the “Remember: …” buttons appear — it is saved only on a click.",
    ),
    "panel_edit": ("Қолмен өзгерту", "Изменить вручную", "Edit by hand"),
    "side_remember": (
        "Қалауларымды есте сақтау",
        "Запоминать мои предпочтения",
        "Remember my preferences",
    ),
    # ---- the city tab header
    # ---- the web page: header, banners, first screen
    "skip_to_input": ("Сұраныс өрісіне өту", "Перейти к полю запроса", "Skip to the request field"),
    "nav_label": ("Бөлімдер", "Разделы", "Sections"),
    "nav_assistant": ("Көмекші", "Ассистент", "Assistant"),
    "nav_city": ("Қала", "Город", "City"),
    "nav_data": ("Деректер", "Данные", "Data"),
    "nav_memory": ("Жад", "Память", "Memory"),
    "nav_menu": ("Мәзір", "Меню", "Menu"),
    "map_label": ("Астана картасы", "Карта Астаны", "Map of Astana"),
    "sheet_toggle": ("Панельді жылжыту", "Сдвинуть панель", "Move the panel"),
    "close": ("Жабу", "Закрыть", "Close"),
    "cancel": ("Болдырмау", "Отмена", "Cancel"),
    "map_offline_note": (
        "Интернет жоқ: карта негізсіз, нүктелер мен жол көрінеді",
        "Нет интернета: карта без подложки, точки и путь видны",
        "No internet: no base map, the points and the way are shown",
    ),
    "hello_title": ("Жақын жерде қайда барамыз?", "Куда пойти рядом?", "Where to go nearby?"),
    "hello_text": (
        "Не қалайтыныңызды және қанша уақытыңыз бар екенін жазыңыз. 3 орынға дейін ұсынып, жолды "
        "картада көрсетемін.",
        "Напишите, что хотите и сколько есть времени. Предложу до 3 мест и покажу путь на карте.",
        "Say what you want and how much time you have. I will suggest up to 3 places and show the way "
        "on the map.",
    ),
    "starters_label": ("Мысалы:", "Например:", "For example:"),
    "ask_placeholder": (
        "Мысалы: бір сағатқа тыныш кафе",
        "Например: тихое кафе на час",
        "E.g. a quiet café for an hour",
    ),
    "d_todo": ("Не істеуге болады", "Что сделать", "What to do"),
    "ask_label": ("Сұранысыңыз", "Ваш запрос", "Your request"),
    "send": ("Жіберу", "Отправить", "Send"),
    # ---- quick inputs beside the field
    "dur_30": ("30 мин", "30 мин", "30 min"),
    "dur_60": ("1 сағат", "1 час", "1 hour"),
    "dur_120": ("2 сағат", "2 часа", "2 hours"),
    "company_solo": ("Жалғыз", "Один", "Alone"),
    "company_pair": ("Екеуміз", "Вдвоём", "Two of us"),
    "company_kids": ("Балалармен", "С детьми", "With kids"),
    "when_other": ("Басқа уақыт / ауа райы", "Другое время / погода", "Other time / weather"),
    "when_time": ("Уақыт", "Время", "Time"),
    "when_weather": ("Ауа райы", "Погода", "Weather"),
    "when_now": ("Қазір", "Сейчас", "Now"),
    "when_at": ("Бүгін {t}", "Сегодня в {t}", "Today at {t}"),
    "when_note": (
        "Әдетте уақыт пен ауа райы өздігінен алынады. Мұнда оларды өзгертіп, басқа жағдайда не "
        "болатынын көруге болады.",
        "Обычно время и погода берутся сами. Здесь их можно поменять, чтобы посмотреть, что будет в "
        "другой ситуации.",
        "Normally the time and the weather are taken automatically. Here you can change them to see what "
        "another situation gives.",
    ),
    "wx_now": ("Қазіргідей", "Как сейчас", "As now"),
    "wx_frost": ("Аяз −25°", "Мороз −25°", "Frost −25°"),
    "wx_rain": ("Нөсер", "Ливень", "Downpour"),
    "wx_smog": ("Смог", "Смог", "Smog"),
    # ---- where the user is
    "loc_here": ("Сіз осындасыз: {name}", "Вы здесь: {name}", "You are here: {name}"),
    "loc_change": ("Өзгерту", "Изменить", "Change"),
    "loc_title": ("Сіз қайдасыз?", "Где вы?", "Where are you?"),
    "loc_mine": ("Менің орным", "Моё местоположение", "My location"),
    "loc_mine_wait": (
        "Орныңызды анықтап жатырмын…",
        "Определяю местоположение…",
        "Getting your location…",
    ),
    "loc_mine_fail": (
        "Орныңызды анықтау мүмкін болмады. Тізімнен немесе картадан таңдаңыз.",
        "Не удалось определить местоположение. Выберите место из списка или на карте.",
        "Could not get your location. Pick a place from the list or on the map.",
    ),
    "loc_pick_map": ("Картадан таңдау", "Выбрать на карте", "Pick on the map"),
    "loc_pick_hint": (
        "Картада өзіңіз тұрған жерді басыңыз.",
        "Нажмите на карте, где вы находитесь.",
        "Tap the map where you are.",
    ),
    "loc_point": ("картадағы нүкте", "точка на карте", "a point on the map"),
    "loc_privacy": (
        "Нүкте ~100 м-ге дейін дөңгелектенеді және сақталмайды.",
        "Точка округляется до ~100 м и нигде не сохраняется.",
        "The point is rounded to ~100 m and is not stored.",
    ),
    "you_marker": ("Сіз осындасыз", "Вы здесь", "You are here"),
    "rt_start": ("Бастау", "Старт", "Start"),
    # ---- the offline line above the answer
    "banner_offline": (
        "Интернетсіз: карта жеңілдетілген, тікелей деректер қолжетімсіз",
        "Без интернета: карта упрощена, живые данные недоступны",
        "Offline: the map is simplified, live data is unavailable",
    ),
    # ---- starter chips: short labels (the request they send is the scenario's full text)
    "starter_s0": ("Mega Silk Way жанында", "Рядом с Mega Silk Way", "Near Mega Silk Way"),
    "starter_s1": ("Тыныш, кофе, розетка", "Тихо, кофе, розетка", "Quiet, coffee, socket"),
    "starter_s2": ("Баламен", "С ребёнком", "With a child"),
    "starter_s3": ("Ұшуға 2 сағат", "2 часа до вылета", "2 h before flight"),
    "starter_s4": ("Түнгі ерекше", "Необычное ночью", "Unusual at night"),
    "starter_r0": ("Ұшуға 2 сағат, аяз", "До вылета, мороз", "Before flight, frost"),
    "starter_r1": ("Баламен қайда?", "С ребёнком, куда?", "Where with a child?"),
    "on_map_short": ("Карта", "Карта", "Map"),
    "open_yandex_short": ("Яндекс", "Яндекс", "Yandex"),
    "why_more": ("тағы", "ещё", "more"),
    "why_less": ("жасыру", "свернуть", "less"),
    "d_note": ("Ескертпе", "Примечание", "Note"),
    # ---- the answer
    "step_parse": ("Сұранысты талдап жатырмын", "Разбираю запрос", "Reading the request"),
    "step_search": (
        "Жақын орындарды іздеп, жұмыс уақытын тексеріп жатырмын",
        "Ищу места рядом и проверяю часы работы",
        "Looking for places nearby and checking their hours",
    ),
    "step_write": ("Жауап жазып жатырмын", "Пишу ответ", "Writing the answer"),
    "step_route": ("Жолды салып жатырмын", "Прокладываю путь", "Laying out the way"),
    "error_send": (
        "Жауап алу мүмкін болмады.",
        "Не удалось получить ответ.",
        "Could not get an answer.",
    ),
    "retry": ("Қайталау", "Повторить", "Try again"),
    "more_options": ("Тағы {n} нұсқа", "Ещё варианты ({n})", "More options ({n})"),
    "best_pick": ("Ең қолайлысы", "Лучший вариант", "Best pick"),
    "ai_idea": ("ЖИ идеясы", "Идея ИИ", "AI idea"),
    "ctx_indoor": (
        "{why}: алдымен ғимарат ішіндегі орындар",
        "{why}: сначала места в помещении",
        "{why}: indoor places first",
    ),
    "ctx_outdoor_kept": (
        "{why}: ашық аспан астындағы орын сұраныс бойынша қалдырылды, серуенді қысқарту жөн",
        "{why}: место на улице оставлено по вашему запросу, прогулку лучше сократить",
        "{why}: the outdoor place you asked for is kept, better keep the walk short",
    ),
    "ctx_dark": (
        "Қараңғы (күн батуы {t}): саябақтар тізімде төменірек",
        "Уже темно (закат в {t}): парки ниже в списке",
        "It is dark (sunset at {t}): parks are lower in the list",
    ),
    "ctx_dark_kept": (
        "Қараңғы (күн батуы {t}): ашық аспан астындағы орын сұраныс бойынша қалдырылды, жарықтандыру деректерде жоқ",
        "Уже темно (закат в {t}): место на улице оставлено по вашему запросу, освещение в данных неизвестно",
        "It is dark (sunset at {t}): the outdoor place you asked for is kept, lighting is not in the data",
    ),
    "ctx_holiday": (
        "{name}: жұмыс уақыты басқаша болуы мүмкін",
        "{name}: часы работы могут отличаться",
        "{name}: opening hours may differ",
    ),
    "ctx_time": (
        "Уақыт: {t} (қолмен қойылған)",
        "Время: {t} (задано вручную)",
        "Time: {t} (set by hand)",
    ),
    # ---- a place card
    "open_2gis": ("2GIS", "2ГИС", "2GIS"),
    "call": ("Қоңырау шалу", "Позвонить", "Call"),
    "details": ("Толығырақ", "Подробнее", "Details"),
    "km_short": ("км", "км", "km"),
    "d_address": ("Мекенжай", "Адрес", "Address"),
    "d_phone": ("Телефон", "Телефон", "Phone"),
    "d_website": ("Сайт", "Сайт", "Website"),
    "d_hours": ("Жұмыс уақыты", "Часы работы", "Opening hours"),
    "d_hours_none": ("Деректерде жоқ", "В данных нет", "Not in the data"),
    "d_status": ("Күй неге сүйенеді", "На чём основан статус", "What the status rests on"),
    "status_from": ("Дереккөз:", "Источник часов:", "Source of the hours:"),
    "data_on_date": ("{date} күнгі деректер", "данные на {date}", "data as of {date}"),
    "status_from_none": (
        "Жұмыс уақыты ешбір дереккөзде жоқ, сондықтан «белгісіз» деп жазамыз.",
        "Часов работы нет ни в одном источнике, поэтому пишем «неизвестно».",
        "No source has the opening hours, so we say “unknown”.",
    ),
    "d_hours_note": ("Ескерту", "Примечание", "Note"),
    "d_people": ("Тұрғындар белгілері", "Отметки жителей", "Residents' marks"),
    "demo_word": ("демо", "демо", "demo"),
    "d_stay": ("Орында", "На месте", "On site"),
    "stay_min": ("~{n} мин", "~{n} мин", "~{n} min"),
    "d_sources": ("Дереккөздер", "Источники", "Sources"),
    "d_date": ("Деректер күні", "Дата данных", "Data date"),
    "d_transit": ("Көлік", "Транспорт", "Transit"),
    "report_q": (
        "Осында болдыңыз ба? Жұмыс уақыты туралы хабарлаңыз:",
        "Были здесь? Сообщите о часах:",
        "Been here? Report on the hours:",
    ),
    "report_closed": ("Жабық", "Закрыто", "Closed"),
    "report_open": ("Ашық", "Открыто", "Open"),
    "report_other_hours": ("Уақыты басқа", "Другие часы", "Different hours"),
    "report_ok": ("Бәрі дұрыс", "Всё верно", "All correct"),
    "report_thanks": (
        "Рақмет! Белгі анонимді, ол «Қала» бетінде көрінеді.",
        "Спасибо! Отметка анонимна и видна на странице «Город».",
        "Thank you! The mark is anonymous and shows on the “City” page.",
    ),
    "report_done": (
        "Бұл орын туралы хабарладыңыз.",
        "Вы уже сообщили об этом месте.",
        "You have already reported this place.",
    ),
    "marks_q": ("Не байқадыңыз?", "Что заметили?", "What did you notice?"),
    "mine_q": ("Жеке профильге", "В личный профиль", "To your profile"),
    # ---- the route
    "rt_head": (
        "Маршрут: {total} мин, {budget} минуттан",
        "Маршрут: {total} мин из {budget}",
        "Route: {total} of {budget} min",
    ),
    "rt_fits": ("уақытыңызға сыяды", "успеваете", "fits your time"),
    "rt_over": ("уақытыңызға сыймайды", "не успеваете", "does not fit your time"),
    "rt_you": ("Сіз", "Вы", "You"),
    "rt_back": ("Кері", "Обратно", "Back"),
    "rt_walk": ("жолда {n} мин", "{n} мин в пути", "{n} min on the way"),
    "rt_stay": ("орнында ~{n} мин", "~{n} мин на месте", "~{n} min there"),
    "min_short": ("{n} мин", "{n} мин", "{n} min"),
    "qa_source": ("Дереккөз:", "Источник:", "Source:"),
    # ---- memory
    "mem_title": ("Мен сіз туралы не білемін", "Что я о вас знаю", "What I know about you"),
    "mem_dialog_note": (
        "Диалог тек осы бетте сақталады және бетті жапқанда өшеді.",
        "Диалог хранится только в этой вкладке и пропадает, когда вы её закрываете.",
        "The dialogue is kept only in this tab and is gone when you close it.",
    ),
    "mem_why": (
        "Әр сұраныста «баламен» немесе «тыныш» деп қайталамау үшін. Сақталғанның бәрі осы жерде "
        "көрінеді, кез келген жолды өшіруге болады. ЖИ-ге белгілеріңіз бен «Өзіңіз туралы айтыңыз» "
        "мәтіні барады, болған орындарыңыз бармайды.",
        "Чтобы не повторять «с ребёнком» или «тихо» в каждом запросе. Всё сохранённое видно здесь, "
        "любую строку можно стереть. В ИИ уходят ваши отметки и текст «Расскажите о себе», но не "
        "места, где вы были.",
        "So you do not repeat “with a child” or “quiet” in every request. Everything stored shows here "
        "and any line can be deleted. Your settings and the “Tell us about yourself” text go to the "
        "AI; the places you visited never do.",
    ),
    "mem_known": ("Сақталған", "Сохранено", "Stored"),
    "mem_forget_item": ("Ұмыту: {item}", "Забыть: {item}", "Forget: {item}"),
    "mem_forget_all": ("Бәрін ұмыту", "Забыть всё", "Forget everything"),
    "mem_off": (
        "Өшірулі: ештеңе оқылмайды және жазылмайды.",
        "Выключено: ничего не читается и не записывается.",
        "Off: nothing is read or written.",
    ),
    "mem_marks_note": (
        "Орындар туралы белгілер анонимді: тек орын, белгі, күн және тәулік бөлігі — атсыз, "
        "координатсыз.",
        "Отметки о местах анонимны: только место, отметка, день и часть суток — без имени и "
        "координат.",
        "Marks about places are anonymous: only the place, the mark, the day and the part of the day — "
        "no name, no coordinates.",
    ),
    # ---- the compact layout: legend, day strip, details
    "legend_title": ("Шартты белгілер", "Обозначения", "Legend"),
    "lg_walk": ("көшелермен жаяу жол", "путь пешком по улицам", "walking path along the streets"),
    "lg_straight": ("түзу сызық", "по прямой", "straight line"),
    "lg_open": ("ашық", "открыто", "open"),
    "lg_soon": ("жақында жабылады", "скоро закроется", "closing soon"),
    "lg_closed": ("жабық", "закрыто", "closed"),
    "lg_unknown": ("уақыты белгісіз", "часы неизвестны", "hours unknown"),
    "lg_sel": ("таңдалған орын", "выбранное место", "selected place"),
    "lg_other": ("басқа орындар", "другие места", "other places"),
    "lg_honest": (
        "Жұмыс уақыты белгілі орындар — {p} (барлығы {n}). Жоқ жерде «белгісіз» деп жазамыз.",
        "Часы известны у {p} из {n} мест. Где их нет, пишем «неизвестно».",
        "Hours are known for {p} of {n} places. Where they are not, we say “unknown”.",
    ),
    "h_today": ("бүгін", "сегодня", "today"),
    "h_now": ("қазір", "сейчас", "now"),
    "h_today_closed": ("бүгін жабық", "сегодня закрыто", "closed today"),
    "walk_street": ("көшелер бойымен", "по улицам", "along the streets"),
    "walk_straight": ("түзу сызықпен", "по прямой", "straight line"),
    "walk_estimate": ("бағалау бойынша", "по оценке", "estimate"),
    "d_walk": ("Жол", "Путь", "Walk"),
    "d_why": ("Неге", "Почему", "Why"),
    "d_price": ("Кіру ақысы", "Вход", "Admission"),
    "back_to_answer": ("Жауапқа оралу", "К ответу", "Back to the answer"),
    "opts_toggle": ("Шарттар", "Условия", "Options"),
    "when_hour": ("Бір сағаттан соң", "Через час", "In an hour"),
    "when_evening": ("Кешке", "Вечером", "This evening"),
    "facts_in_data": ("Деректерде", "В данных", "In the data"),
    "facts_places": ("{n} орын", "{n} мест", "{n} places"),
    "facts_hours": ("жұмыс уақыты белгілі: {p}", "часы известны у {p}", "hours known for {p}"),
    "facts_note": (
        "Жұмыс уақыты жоқ жерде көмекші «жұмыс уақыты белгісіз» деп жазады және ешқашан «ашық» демейді.",
        "Где часов нет, помощник пишет «часы неизвестны» и никогда не говорит «открыто».",
        "Where there are no hours, the assistant says “hours unknown” and never says “open”.",
    ),
    "turn_open": ("Жауапты ашу", "Открыть ответ", "Open the answer"),
    # ui-v3: first-screen suggestions, the language menu, the map's location button, «Мои места»
    "sug_eat": ("Тамақтану", "Поесть", "Eat"),
    "sug_eat_q": ("Тамақтанғым келеді", "Хочу поесть", "I want to eat"),
    "sug_coffee": ("Кофе", "Кофе", "Coffee"),
    "sug_coffee_q": ("Кофе ішкім келеді", "Хочу кофе", "I want a coffee"),
    "sug_walk": ("Серуендеу", "Погулять", "A walk"),
    "sug_walk_q": ("Серуендегім келеді", "Хочу погулять", "I want to go for a walk"),
    "sug_kids": ("Балалармен", "С детьми", "With kids"),
    "sug_kids_q": (
        "Балалармен қайда барсақ болады",
        "Куда сходить с детьми",
        "Where to go with kids",
    ),
    "sug_museum": ("Мұражай", "Музей", "A museum"),
    "sug_museum_q": ("Мұражайға барғым келеді", "Хочу в музей", "I want to visit a museum"),
    "sug_evening": ("Кешке қайда барамыз", "Вечером куда сходить", "Out this evening"),
    "sug_evening_q": (
        "Кешке қайда барсақ болады",
        "Куда сходить вечером",
        "Where to go this evening",
    ),
    "lang_menu": ("Тілді таңдау", "Выбрать язык", "Choose the language"),
    "loc_outside": (
        "Сіз Астанадан тыссыз. Іздеу басталатын нүкте өзгерген жоқ.",
        "Вы за пределами Астаны. Отправная точка осталась прежней.",
        "You are outside Astana. The starting point stays as it was.",
    ),
    "loc_denied": (
        "Орынды анықтауға рұқсат берілмеген. Браузер баптауынан рұқсат беріңіз немесе картадан таңдаңыз.",
        "Нет доступа к местоположению. Разрешите его в настройках браузера или выберите место на карте.",
        "No access to your location. Allow it in the browser settings or pick a place on the map.",
    ),
    "loc_found": ("Орныңыз табылды", "Нашли вас на карте", "Found you on the map"),
    "loc_places": ("Қаладағы орындар", "Места в городе", "Places in the city"),
    "map_start_here": ("Осы жерден бастау", "Начать отсюда", "Start from here"),
    "map_save_here": ("Орынды сақтау", "Сохранить это место", "Save this place"),
    "bm_title": ("Менің орындарым", "Мои места", "My places"),
    "bm_add": ("Орын қосу", "Добавить место", "Add a place"),
    "bm_edit_title": ("Орынды өзгерту", "Изменить место", "Edit the place"),
    "bm_empty": (
        "«Үй», «Жұмыс» немесе «Оқу» деп белгілеңіз: «үйге қарай бір жерде тамақтану» сияқты сұрауларда осыны ескеремін.",
        "Отметьте «Дом», «Работа» или «Учёба»: так я смогу искать «поесть по дороге домой».",
        "Mark Home, Work or Study, and I can look for “a bite on the way home”.",
    ),
    "bm_kind_home": ("Үй", "Дом", "Home"),
    "bm_kind_work": ("Жұмыс", "Работа", "Work"),
    "bm_kind_study": ("Оқу", "Учёба", "Study"),
    "bm_kind_other": ("Басқа", "Другое", "Other"),
    "bm_name": ("Атауы", "Название", "Name"),
    "bm_name_ph": ("Мысалы: әжемнің үйі", "Например: дача, спортзал", "E.g. gym, grandma's"),
    "bm_where": ("Орны", "Место", "Position"),
    "bm_where_now": ("Қазір: {name}", "Сейчас: {name}", "Now: {name}"),
    "bm_where_set": ("Таңдалған нүкте", "Выбранная точка", "The chosen point"),
    "bm_pick_hint": (
        "Картадан «{name}» орнын басыңыз.",
        "Нажмите на карте место для «{name}».",
        "Tap the map where “{name}” is.",
    ),
    "bm_save": ("Сақтау", "Сохранить", "Save"),
    "bm_delete": ("Жою", "Удалить", "Delete"),
    "bm_edit": ("Өзгерту: {name}", "Изменить: {name}", "Edit: {name}"),
    "bm_use": ("Осы жерден бастау: {name}", "Начать отсюда: {name}", "Start from: {name}"),
    "bm_full": (
        "Ең көбі {n} орын сақтауға болады.",
        "Можно сохранить не больше {n} мест.",
        "You can keep up to {n} places.",
    ),
    "bm_privacy": (
        "Орындар тек осы браузерде сақталады. Серверде сақталмайды, іздеген кезде сұранысқа ғана қосылады.",
        "Места хранятся только в этом браузере. На сервере они не сохраняются и уходят только вместе с вашим запросом.",
        "Places are kept only in this browser. The server does not store them; they go with your request only.",
    ),
    "bm_name_empty": ("Атауын жазыңыз", "Напишите название", "Give it a name"),
    # weather-fx: the map's weather effects (map-weather.js); the line says what each effect is drawn from
    "fx_btn": ("Эффекттер", "Эффекты", "Effects"),
    "fx_title": (
        "Картадағы ауа райы эффектілері: жел, жауын-шашын, аспан. Нақты өлшемдер бойынша.",
        "Погодные эффекты на карте: ветер, осадки, небо. Только по измеренным данным.",
        "Weather effects on the map: wind, precipitation, sky. Measured data only.",
    ),
    "fx_dir_0": ("С", "С", "N"),
    "fx_dir_1": ("СШ", "СВ", "NE"),
    "fx_dir_2": ("Ш", "В", "E"),
    "fx_dir_3": ("ОШ", "ЮВ", "SE"),
    "fx_dir_4": ("О", "Ю", "S"),
    "fx_dir_5": ("ОБ", "ЮЗ", "SW"),
    "fx_dir_6": ("Б", "З", "W"),
    "fx_dir_7": ("СБ", "СЗ", "NW"),
    "fx_wind": ("Жел {dir}, {speed} м/с", "Ветер {dir}, {speed} м/с", "Wind {dir}, {speed} m/s"),
    "fx_fact": ("{dir}, {speed} м/с", "{dir} {speed} м/с", "{dir} {speed} m/s"),
    "fx_snow_1": ("жеңіл қар", "слабый снег", "light snow"),
    "fx_snow_2": ("қар", "снег", "snow"),
    "fx_snow_3": ("қою қар", "сильный снег", "heavy snow"),
    "fx_rain_1": ("жеңіл жаңбыр", "слабый дождь", "light rain"),
    "fx_rain_2": ("жаңбыр", "дождь", "rain"),
    "fx_rain_3": ("нөсер", "сильный дождь", "heavy rain"),
    "fx_sky_0": ("ашық", "ясно", "clear"),
    "fx_sky_1": ("бұлт аз", "малооблачно", "partly cloudy"),
    "fx_sky_2": ("бұлтты", "облачно", "cloudy"),
    "fx_sky_3": ("бұлт басқан", "пасмурно", "overcast"),
    "fx_air_nmu": (
        "НМУ (Қазгидромет)",
        "НМУ (Казгидромет)",
        "adverse-weather notice (Kazhydromet)",
    ),
    "fx_air_smog": ("түтін немесе тұман", "дымка или дым", "haze or smoke"),
    "fx_src_metar": ("әуежай, {time}", "аэропорт, {time}", "airport, {time}"),
    "fx_src_metno": ("болжам MET Norway", "прогноз MET Norway", "MET Norway forecast"),
    "fx_sun_night": ("түн (есеп)", "ночь (расчёт)", "night (computed)"),
    "fx_sun_dawn": ("таң (есеп)", "рассвет (расчёт)", "dawn (computed)"),
    "fx_sun_golden": ("алтын сағат (есеп)", "золотой час (расчёт)", "golden hour (computed)"),
    "fx_sun_dusk": ("ымырт (есеп)", "закат (расчёт)", "dusk (computed)"),
    "fx_sun_day": ("күндіз (есеп)", "день (расчёт)", "day (computed)"),
} | PANEL

# The wording that names the public FOSSGIS router. With WALKS_VALHALLA_URL naming one's own (the public stand),
# the data page says so instead: `tr` and `ui_table` swap these entries in.
_PUBLIC_ROUTER = "Valhalla / FOSSGIS (valhalla1.openstreetmap.de)"
_OWN_ROUTER: Entry = (
    "Valhalla, OSM негізіндегі өз серверіміз",
    "Valhalla, свой сервер на OSM",
    "Valhalla, own server on OSM data",
)
OWN_ROUTER_WORDING: dict[str, Entry] = {
    "src_walk": _OWN_ROUTER,
    "footer": tuple(
        text.replace(_PUBLIC_ROUTER, own)
        for text, own in zip(UI["footer"], _OWN_ROUTER, strict=True)
    ),  # type: ignore[dict-item]
}


def ui_table() -> dict[str, Entry]:
    """Every UI string, with the router wording of this stand (own Valhalla or the public one)."""
    return UI | OWN_ROUTER_WORDING if own_router() else UI
