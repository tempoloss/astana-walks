"""Every sentence of the dialogue layer (walks.dialog*), in Kazakh, Russian, English: plain words, no jargon.
`s(key, lang, **fields)`; the order of an entry is (kk, ru, en), as in walks.i18n."""

from __future__ import annotations

Entry = tuple[str, str, str]
LANGS = ("kk", "ru", "en")

STRINGS: dict[str, Entry] = {
    # ---- replies of a turn
    "more_1": ("тағы бір орын", "ещё одно место", "one more place"),
    "more_2": ("тағы екі орын", "ещё два места", "two more places"),
    "change_head": ("{change}: {rest}", "{change}: {rest}", "{change}: {rest}"),
    "none_found": (
        "Жақын жерден лайықты орын табылмады — әрі қарай іздейік пе?",
        "Рядом ничего подходящего не нашлось — поищем подальше?",
        "Nothing suitable nearby — shall we look farther?",
    ),
    "none_new": (
        "Жаңа орындар жақын жерде қалмады — әрі қарай іздейік пе?",
        "Новых мест рядом больше нет — поищем подальше?",
        "No new places left nearby — shall we look farther?",
    ),
    "not_in_data": (
        "Менің деректерімде {what} жоқ: мен тамақтануға, серуендеуге және демалуға орын табуға көмектесемін.",
        "В моих данных нет {what}: я подсказываю, где поесть, погулять и отдохнуть.",
        "My data has no {what}: I help with places to eat, walk and relax.",
    ),
    "ood_pharmacy": ("дәріханалар", "аптек", "pharmacies"),
    "ood_exchange": ("валюта айырбастау орындары", "обменников валюты", "currency exchanges"),
    "ood_bank": ("банктер мен банкоматтар", "банков и банкоматов", "banks or cash machines"),
    "ood_gas": ("жанармай бекеттері", "заправок", "petrol stations"),
    "ood_clinic": ("емханалар мен ауруханалар", "больниц и поликлиник", "clinics or hospitals"),
    "ood_school": ("мектептер", "школ", "schools"),
    "ood_dentist": ("тіс дәрігерлері", "стоматологов", "dentists"),
    "ood_embassy": ("елшіліктер", "посольств", "embassies"),
    "ood_police": ("полиция бөлімшелері", "отделений полиции", "police stations"),
    "a_unknown_place_bare": (
        "Мұндай орынды деректерден таппадым — атын басқаша жазыңыз немесе не іздейтініңізді айтыңыз.",
        "Такого места в данных не нашёл — назовите иначе или напишите, что ищете рядом.",
        "I could not find that place in the data — name it differently or tell me what you are looking for nearby.",
    ),
    "notice_time": (
        "«{kind}» үшін бұл уақыт аз: әдетте кемі {lo} мин керек. Міне, үлгеретіндер.",
        "На «{kind}» этого времени мало: обычно нужно от {lo} мин. Вот что успеете.",
        "This is too little time for “{kind}”: it usually takes at least {lo} min. Here is what you can do.",
    ),
    "clarify_start": (
        "Жақын жерден не іздейміз?",
        "Что хотите найти рядом?",
        "What would you like to find nearby?",
    ),
    "clarify_hello": (
        "Сәлеметсіз бе! Жақын жерден не іздейміз?",
        "Здравствуйте! Что хотите найти рядом?",
        "Hello! What would you like to find nearby?",
    ),
    "clarify_unclear": (
        "Түсінбедім. Жақын жерден не іздейміз?",
        "Не совсем понял. Что хотите найти рядом?",
        "I did not quite get that. What would you like to find nearby?",
    ),
    "clarify_new": (
        "Жаңадан бастайық. Не іздейміз?",
        "Начнём заново. Что ищем?",
        "Let's start over. What are we looking for?",
    ),
    "clarify_no_place": (
        "Әзірге ешқандай орын көрсетілген жоқ. Не іздейміз?",
        "Пока я ничего не показывал. Что ищем?",
        "I have not shown anything yet. What are we looking for?",
    ),
    "clarify_change": (
        "Не өзгертейік?",
        "Что поменять в подборке?",
        "What should I change?",
    ),
    "thanks": (
        "Оқасы жоқ! Бір нәрсе керек болса, жазыңыз.",
        "Пожалуйста! Если что-то понадобится — пишите.",
        "You're welcome! Write if you need anything else.",
    ),
    "bye": (
        "Сау болыңыз! Серуен сәтті болсын.",
        "До встречи! Приятной прогулки.",
        "Goodbye! Enjoy your walk.",
    ),
    "decline": (
        "Жақсы. Ойыңыз өзгерсе, жазыңыз.",
        "Хорошо. Если передумаете — напишите.",
        "All right. Write if you change your mind.",
    ),
    # ---- a walking time
    "walk_walk": ("жаяу {n} мин", "{n} мин пешком", "{n} min on foot"),
    "walk_car": ("көлікпен {n} мин", "{n} мин на машине", "{n} min by car"),
    "walk_transit": (
        "қоғамдық көлікпен {n} мин",
        "{n} мин на транспорте",
        "{n} min by public transport",
    ),
    # ---- the card
    "why_fallback": ("Жақын жердегі {kind}.", "Это {kind} рядом с вами.", "A {kind} close to you."),
    "caveat_expanded": ("сәл алысырақ", "чуть дальше", "a bit farther"),
    "caveat_other": ("басқа санат", "другая категория", "another kind of place"),
    "src_osm": ("OpenStreetMap", "OpenStreetMap", "OpenStreetMap"),
    "src_overture": ("Overture Maps", "Overture Maps", "Overture Maps"),
    "src_site": ("ресми сайт", "официальный сайт", "official website"),
    "src_wikipedia": ("Уикипедия", "Википедия", "Wikipedia"),
    "src_wikivoyage": ("Wikivoyage", "Wikivoyage", "Wikivoyage"),
    # ---- hours
    "h_open": ("Ашық", "Открыто", "Open"),
    "h_open_until": ("{t} дейін ашық", "Открыто до {t}", "Open until {t}"),
    "h_open_247": ("Тәулік бойы ашық", "Открыто круглосуточно", "Open 24/7"),
    "h_closed": ("Жабық", "Закрыто", "Closed"),
    "h_closed_opens": ("Жабық, {t} ашылады", "Закрыто, откроется {t}", "Closed, opens {t}"),
    "h_unknown": ("Жұмыс уақыты белгісіз", "Часы неизвестны", "Hours unknown"),
    "h_at": ("{t}", "в {t}", "at {t}"),
    "h_tomorrow": ("ертең {t}", "завтра в {t}", "tomorrow at {t}"),
    "h_note_conflict": (
        "Сайт пен картадағы сағаттар сәйкес келмейді — шықпас бұрын нақтылаңыз.",
        "Часы на сайте и на карте расходятся — уточните перед выходом.",
        "Hours on the website and on the map differ — check before you go.",
    ),
    "h_note_split": (
        "Сайт пен карта қазір әртүрлі жауап береді — шықпас бұрын нақтылаңыз.",
        "Сайт и карта сейчас дают разный ответ — уточните перед выходом.",
        "The website and the map disagree right now — check before you go.",
    ),
    "h_note_unqualified": (
        "Сайтта сағаттар бар, бірақ күндері көрсетілмеген — нақтылаңыз.",
        "На сайте есть часы, но без дней недели — уточните.",
        "The website lists hours but no days — please check.",
    ),
    "h_note_unknown": (
        "Деректерде жұмыс уақыты жоқ — шықпас бұрын нақтылаңыз.",
        "В данных нет часов работы — уточните перед выходом.",
        "The data has no opening hours — check before you go.",
    ),
    "h_note_holiday": (
        "Мереке күні сағаттар басқаша болуы мүмкін.",
        "В праздник часы могут отличаться.",
        "Hours may differ on a public holiday.",
    ),
    # ---- answers about a shown place
    "a_hours_open": (
        "{name}: қазір ашық ({src}).",
        "«{name}»: сейчас открыто ({src}).",
        "{name}: open now ({src}).",
    ),
    "a_hours_open_until": (
        "{name}: қазір ашық, {t} дейін ({src}).",
        "«{name}»: сейчас открыто, до {t} ({src}).",
        "{name}: open now, until {t} ({src}).",
    ),
    "a_hours_open_247": (
        "{name}: тәулік бойы ашық ({src}).",
        "«{name}»: открыто круглосуточно ({src}).",
        "{name}: open 24/7 ({src}).",
    ),
    "a_hours_closed": (
        "{name}: қазір жабық ({src}).",
        "«{name}»: сейчас закрыто ({src}).",
        "{name}: closed now ({src}).",
    ),
    "a_hours_closed_opens": (
        "{name}: қазір жабық, {t} ашылады ({src}).",
        "«{name}»: сейчас закрыто, откроется {t} ({src}).",
        "{name}: closed now, opens {t} ({src}).",
    ),
    "a_hours_unknown": (
        "{name}: деректерде нақты жұмыс уақыты жоқ — шықпас бұрын нақтылаңыз{contact}.",
        "«{name}»: точных часов в данных нет — лучше уточнить перед выходом{contact}.",
        "{name}: the data has no exact hours — better check before you go{contact}.",
    ),
    "a_contact_phone": (", телефон {phone}", ", телефон {phone}", ", phone {phone}"),
    "a_contact_site": (", сайт {site}", ", сайт {site}", ", website {site}"),
    "a_address": (
        "{name}: мекенжайы — {address}; {walk}.",
        "«{name}»: адрес — {address}; {walk}.",
        "{name}: address — {address}; {walk}.",
    ),
    "a_address_none": (
        "{name}: мекенжайы деректерде жоқ, бірақ картада көрсетілген нүкте бар; {walk}.",
        "«{name}»: адреса в данных нет, но точка на карте есть; {walk}.",
        "{name}: the data has no street address, but the point is on the map; {walk}.",
    ),
    "a_route": (
        "{name}: түзу сызықпен шамамен {d}, {walk}. Нақты бағытты картадан қараңыз.",
        "«{name}»: по прямой около {d}, {walk}. Точный маршрут смотрите на карте.",
        "{name}: about {d} in a straight line, {walk}. See the map for the exact route.",
    ),
    "a_route_far": (
        "{name}: түзу сызықпен шамамен {d}, {walk} — алыстау, көлікпен немесе қоғамдық көлікпен тиімдірек.",
        "«{name}»: по прямой около {d}, {walk} — это далековато, лучше на транспорте.",
        "{name}: about {d} in a straight line, {walk} — quite far, better take a vehicle.",
    ),
    "a_phone": (
        "{name}: телефон — {phone}.",
        "«{name}»: телефон — {phone}.",
        "{name}: phone — {phone}.",
    ),
    "a_phone_none": (
        "{name}: деректерде телефон жоқ.",
        "«{name}»: телефона в данных нет.",
        "{name}: the data has no phone number.",
    ),
    "a_site": (
        "{name}: сайт — {site}.",
        "«{name}»: сайт — {site}.",
        "{name}: website — {site}.",
    ),
    "a_site_none": (
        "{name}: деректерде сайт жоқ.",
        "«{name}»: сайта в данных нет.",
        "{name}: the data has no website.",
    ),
    "a_attr_yes": (
        "{name}: иә, деректер бойынша {what} бар ({src}).",
        "«{name}»: да, по данным — {what} ({src}).",
        "{name}: yes, per the data — {what} ({src}).",
    ),
    "a_attr_no": (
        "{name}: деректер бойынша жоқ: {what} ({src}).",
        "«{name}»: по данным — нет: {what} ({src}).",
        "{name}: per the data — no: {what} ({src}).",
    ),
    "a_attr_limited": (
        "{name}: ішінара: {what} ({src}).",
        "«{name}»: частично — {what} ({src}).",
        "{name}: partly — {what} ({src}).",
    ),
    "a_unknown": (
        "{name}: бұл туралы деректерде ештеңе жоқ ({what}) — шықпас бұрын нақтылаңыз.",
        "«{name}»: в данных этого нет ({what}) — лучше уточнить на месте или по телефону.",
        "{name}: the data has nothing on this ({what}) — better check on the spot or by phone.",
    ),
    "a_price": (
        "{name}: {price} ({by}).",
        "«{name}»: {price} ({by}).",
        "{name}: {price} ({by}).",
    ),
    "src_host": ("{host} дереккөзі", "источник {host}", "source {host}"),
    "by_host": ("{host} деректері бойынша", "по данным {host}", "according to {host}"),
    "src_record": ("деректер жазбасы", "запись данных", "the data record"),
    "by_record": ("жазба бойынша", "по данным записи", "per the record"),
    "a_about": (
        "{name}: {kind}, {walk}; {hours}.",
        "«{name}»: {kind}, {walk}; {hours}.",
        "{name}: a {kind}, {walk}; {hours}.",
    ),
    "src_museum_register": (
        "мұражайлар реестрі e-museum.kz",
        "реестр музеев e-museum.kz",
        "e-museum.kz museum register",
    ),
    "by_register": (
        "мұражайлар реестрі бойынша",
        "по данным реестра музеев",
        "according to the museum register",
    ),
    "by_osm": ("OpenStreetMap деректері бойынша", "по данным OpenStreetMap", "per OpenStreetMap"),
    "by_site": (
        "ресми сайт деректері бойынша",
        "по данным официального сайта",
        "per the official website",
    ),
    "a_unknown_place": (
        "Мұндай орынды деректерден таппадым — атын басқаша жазыңыз немесе көрсетілгендердің бірін таңдаңыз.",
        "Такого места в данных не нашёл — назовите иначе или выберите одно из показанных.",
        "I could not find that place in the data — name it differently or pick one of those shown.",
    ),
    "today_hours": ("бүгін {iv}", "сегодня {iv}", "today {iv}"),
    "a_which": (
        "Қай орын туралы? Көрсетілгендердің бірін атаңыз.",
        "Про какое место? Назовите одно из показанных.",
        "Which place? Name one of those shown.",
    ),
    # what a question is about (the «what» of a missing fact)
    "w_toilet": ("дәретхана", "туалет", "toilet"),
    "w_wifi": ("Wi-Fi", "Wi-Fi", "Wi-Fi"),
    "w_wheelchair": ("арбамен кіру", "доступ с коляской", "wheelchair access"),
    "w_terrace": ("далада орын", "столики на улице", "outdoor seating"),
    "w_takeaway": ("өзіммен алып кету", "еда с собой", "takeaway"),
    "w_price": ("бағасы", "цены", "prices"),
    "w_parking": ("тұрақ", "парковка", "parking"),
    "w_reserve": ("үстел брондау", "бронирование столика", "table booking"),
    # ---- chips
    "c_more": ("Басқа орындар", "Другие места", "Other places"),
    "c_closer": ("Жақынырақ", "Поближе", "Closer"),
    "c_cheaper": ("Арзанырақ", "Подешевле", "Cheaper"),
    "c_no_alcohol": ("Алкогольсіз", "Без алкоголя", "No alcohol"),
    "c_kids": ("Баламен", "С ребёнком", "With a child"),
    "c_longer": ("Бір сағат көбірек", "На час дольше", "One more hour"),
    "c_quiet": ("Тыныштау", "Потише", "Quieter"),
    "c_wifi": ("Wi-Fi бар", "С Wi-Fi", "With Wi-Fi"),
    "c_food": ("Тамақтану", "Поесть", "Eat"),
    "c_coffee": ("Кофе", "Кофе", "Coffee"),
    "c_walk": ("Серуендеу", "Погулять", "A walk"),
    "c_kids_start": ("Баламен", "С детьми", "With kids"),
    "c_museum": ("Мұражай", "Музей", "Museum"),
    "c_unusual": ("Ерекше нәрсе", "Необычное", "Something unusual"),
    "c_new": ("Жаңа іздеу", "Новый поиск", "New search"),
    # what the chip sends: a phrase the rule parser reads (ru ones are the demo recording's phrases)
    "q_more": ("басқа бір нәрсе", "что-то другое", "something else"),
    "q_closer": ("жақынырақ", "а поближе?", "closer"),
    "q_cheaper": ("арзанырақ", "а подешевле", "cheaper"),
    "q_no_alcohol": ("алкогольсіз", "а без алкоголя", "no alcohol"),
    "q_kids": ("баламен барсам ше", "а если с ребёнком", "what if I am with a child"),
    "q_longer": ("бір сағат ұзағырақ", "на час дольше", "one more hour"),
    "q_quiet": ("тыныштау", "а потише", "quieter"),
    "q_wifi": ("wifi бар жер", "а с wifi", "with wifi"),
    "q_food": ("тамақтанғым келеді", "хочу поесть", "I want to eat"),
    "q_coffee": ("кофе ішкім келеді", "хочу кофе", "I want coffee"),
    "q_walk": ("серуендегім келеді", "хочу погулять", "I want a walk"),
    "q_kids_start": (
        "баламен қайда барамыз",
        "куда сходить с ребёнком",
        "where to go with a child",
    ),
    "q_museum": ("мұражайға барғым келеді", "хочу в музей", "I want a museum"),
    "q_unusual": ("ерекше нәрсе керек", "хочу что-нибудь необычное", "something unusual"),
    "q_new": ("жаңа іздеу", "новый поиск", "new search"),
    # the short name of a change, for the reply of a refined search
    "ch_closer": ("жақынырақ", "поближе", "closer"),
    "ch_more": ("басқа орындар", "другие места", "other places"),
    "ch_no_alcohol": ("алкогольсіз", "без алкоголя", "no alcohol"),
    "ch_cheaper": ("арзанырақ", "подешевле", "cheaper"),
    "ch_pricier": ("қымбатырақ", "подороже", "pricier"),
    "ch_kids_yes": ("баламен", "с ребёнком", "with a child"),
    "ch_kids_no": ("баласыз", "без ребёнка", "without a child"),
    "ch_quiet": ("тыныштау", "потише", "quieter"),
    "ch_wifi": ("Wi-Fi-мен", "с Wi-Fi", "with Wi-Fi"),
    "ch_longer": ("ұзағырақ", "дольше", "longer"),
    "ch_shorter": ("қысқарақ", "покороче", "shorter"),
    "ch_mode": ("басқа көлікпен", "другим транспортом", "another way of getting there"),
    "ch_changed": ("өзгертілді", "поправил", "adjusted"),
    # ---- the lead of an answer (walks.dialog_lead): conditions in Astana, what you want, the recommendation
    "ld_now": ("Қазір {t} °C", "Сейчас {t} °C", "It is {t} °C now"),
    "ld_feels": ("сезілуі {f} °C", "ощущается как {f} °C", "feels like {f} °C"),
    "ld_precip": ("жауын-шашын жауып тұр", "идут осадки", "it is raining or snowing"),
    "ld_dark": ("қазір қараңғы", "уже темно", "it is already dark"),
    "ld_nmu": (
        "Астанада НМУ — ауа әдеттегіден нашар",
        "в Астане действует НМУ — воздух хуже обычного",
        "Astana has an air-quality alert (NMU) — the air is worse than usual",
    ),
    "ld_pm": (
        "ауа лас (PM2.5 {pm})",
        "воздух грязный (PM2.5 {pm})",
        "the air is dirty (PM2.5 {pm})",
    ),
    "ld_haze": (
        "ауада түтін немесе тұман бар",
        "в воздухе дым или дымка",
        "there is smoke or haze in the air",
    ),
    "ld_holiday": (
        "бүгін мереке — {name}",
        "сегодня праздник — {name}",
        "today is a holiday — {name}",
    ),
    "ld_indoor": (
        "сондықтан алдымен үйдегі орындар",
        "поэтому сначала места в помещении",
        "so indoor places come first",
    ),
    "ld_outdoor_kept": (
        "көшедегі орын сұрауыңыз бойынша қалдырылды, серуенді қысқарту жөн",
        "место на улице оставлено по вашему запросу, прогулку лучше сократить",
        "the outdoor place you asked for is kept, better keep the walk short",
    ),
    "ld_want": ("Сіз іздеп жатырсыз: {what}", "Вы ищете: {what}", "You are looking for: {what}"),
    "ld_pick": (
        "«{name}» жеріне барыңыз, {walk}{tail}",
        "советую «{name}», {walk}{tail}",
        "I suggest {name}, {walk}{tail}",
    ),
    "ld_from": ("«{bm}» нүктесінен", "от «{bm}»", "from “{bm}”"),
    "ld_more": ("; төменде {more}", "; ниже {more}", "; {more} below"),
    "ld_way_home": (
        "әрі үйге бара жатқан жолда",
        "и как раз по пути домой",
        "and right on your way home",
    ),
    "ld_way_work": (
        "әрі жұмысқа бара жатқан жолда",
        "и как раз по пути на работу",
        "and right on your way to work",
    ),
    "ld_way_study": (
        "әрі оқуға бара жатқан жолда",
        "и как раз по пути на учёбу",
        "and right on your way to class",
    ),
    "ld_way_other": (
        "әрі «{name}» жолында",
        "и как раз по пути к «{name}»",
        "and right on your way to “{name}”",
    ),
}


def s(key: str, lang: str | None, **fields: object) -> str:
    entry = STRINGS[key]
    text = entry[LANGS.index(lang) if lang in LANGS else 1]
    return text.format(**fields) if fields else text
