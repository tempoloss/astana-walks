"""Kazakh / Russian / English wording of the collapsed technical panel «Какие данные использованы» and of its
helper lines (see i18n.py: this table is merged into `UI`)."""

from __future__ import annotations

from walks.i18n import Entry

PANEL: dict[str, Entry] = {
    # memory-v2: the «Память» form «Изменить вручную»
    "mf_intro": (
        "Міндетті ештеңе жоқ: тек ескеру керек деген нәрсені толтырыңыз.",
        "Ничего не обязательно: заполните только то, что хотите, чтобы я учитывал.",
        "Nothing is required: fill in only what you want me to take into account.",
    ),
    "mf_s_who": ("Сіз туралы", "Кто вы", "About you"),
    "mf_kids": ("Балалармен жүремін", "Хожу с детьми", "I walk with children"),
    "mf_kids_age": ("Баланың жасы", "Возраст ребёнка", "Child's age"),
    "mf_age_none": ("Белгісіз", "Не указан", "Not given"),
    "mf_lang": ("Жауап тілі", "Язык ответов", "Language of the answers"),
    "mf_lang_as_query": ("Сұраудағыдай", "Как в запросе", "As in the request"),
    "mf_s_food": ("Тамақ пен сусын", "Еда и напитки", "Food and drink"),
    "mf_halal": ("Халал керек", "Нужен халяль", "I need halal"),
    "mf_alc": ("Алкогольсіз", "Без алкоголя", "No alcohol"),
    "mf_s_budget": ("Бюджет", "Бюджет", "Budget"),
    "mf_b_any": ("Маңызды емес", "Не важно", "Does not matter"),
    "mf_b_low": ("Арзан", "Недорого", "Cheap"),
    "mf_b_medium": ("Орташа", "Средний", "Medium"),
    "mf_b_high": ("Қымбатырағы да болады", "Можно дороже", "Pricier is fine"),
    "mf_s_access": ("Қолжетімділік", "Доступность", "Access"),
    "mf_m_none": ("Қажет емес", "Не нужна", "Not needed"),
    "mf_m_stroller": ("Арбамен", "С коляской", "With a stroller"),
    "mf_m_wheelchair": ("Мүгедектер арбасы", "Кресло-коляска", "Wheelchair"),
    "mf_access_hint": (
        "Сонда баспалдақсыз орындарды іздеймін.",
        "Тогда ищу места без ступенек.",
        "I then look for step-free places.",
    ),
    "mf_s_walk": ("Серуен", "Прогулка", "The walk"),
    "mf_quiet": ("Тыныш орындар ұнайды", "Люблю тихие места", "I like quiet places"),
    "mf_pace": ("Жүріс қарқыны", "Темп ходьбы", "Walking pace"),
    "mf_p_slow": ("Асықпай", "Неспешно", "Slow"),
    "mf_p_normal": ("Әдеттегідей", "Обычный", "Normal"),
    "mf_p_fast": ("Жылдам", "Быстрый", "Fast"),
    "mf_cold": ("Суық", "Холод", "Cold"),
    "mf_c_low": ("Тоңамын", "Мёрзну", "I feel the cold"),
    "mf_c_normal": ("Әдеттегідей", "Обычно", "Normal"),
    "mf_c_high": ("Суыққа төзімді", "Не боюсь холода", "Cold is fine"),
    "mf_s_kinds": ("Қандай орындар", "Какие места", "Which places"),
    "mf_liked": ("Ұнайды", "Нравятся", "I like"),
    "mf_avoid": ("Көрсетпеу", "Не показывать", "Leave out"),
    "mf_kinds_hint": (
        "Орын түрін басыңыз. «Көрсетпеу» өзіңіз сондай орын сұрамағанда ғана жұмыс істейді.",
        "Нажмите на вид места. «Не показывать» работает, пока вы сами не попросили такое место.",
        "Tap a kind of place. “Leave out” works until you ask for that kind yourself.",
    ),
    "mf_s_about": ("Өзіңіз туралы айтыңыз", "Расскажите о себе", "Tell us about yourself"),
    "mf_about_hint": (
        "Біз білуге тиіс бәрін еркін жазыңыз.",
        "Напишите всё, что нам стоит знать, своими словами.",
        "Write in your own words everything we should know.",
    ),
    "mf_about_ph": (
        "Мысалы: сол жағалауда тұрамын, кофе ішпеймін, көрінісі бар орындарды жақсы көремін, итіммен жүремін",
        "Например: живу на левом берегу, не пью кофе, люблю места с видом, хожу с собакой",
        "For example: I live on the left bank, I do not drink coffee, I like places with a view, I walk my dog",
    ),
    "mf_about_note": (
        "Бұл мәтін сұраныстарыңызбен бірге ЖИ моделіне барады; «Бәрін ұмыту» түймесімен өшіріледі.",
        "Этот текст уходит модели ИИ вместе с вашими запросами; удаляется кнопкой «Забыть всё».",
        "This text goes to the AI model together with your requests; the “Forget everything” button deletes it.",
    ),
    "mf_count": ("{n} / {max}", "{n} / {max}", "{n} / {max}"),
    "mf_save": ("Сақтау", "Сохранить", "Save"),
    "mf_saved": ("Сақталды", "Сохранено", "Saved"),
    "mf_save_fail": (
        "Сақтау мүмкін болмады. Өрістерді тексеріңіз.",
        "Не удалось сохранить. Проверьте поля.",
        "Could not save. Check the fields.",
    ),
    "profile_code_avoid": (
        "сіз алып тастаған орын түрлері",
        "виды мест, которые вы исключили",
        "kinds of place you left out",
    ),
    # ---- the data panel (collapsed)
    "dp_location": (
        "**Орын:** {lat}, {lon} — {n} таңбаға дейін дөңгелектелген (≈100 м). Нақты координаттар мен "
        "сұраныс мәтіні сақталмайды; ЖИ-ге тек дөңгелектелген нүкте барады.",
        "**Локация:** {lat}, {lon} — округлено до {n} знаков (≈100 м). Точные координаты и текст запроса "
        "не сохраняются; в ИИ уходит только округлённая точка.",
        "**Location:** {lat}, {lon} — rounded to {n} decimals (≈100 m). Exact coordinates and the request "
        "text are not stored; only the rounded point goes to the AI.",
    ),
    "dp_time": (
        "**Сұраныс уақыты:** {t}",
        "**Время запроса:** {t}",
        "**Time of the request:** {t}",
    ),
    "dp_time_manual": (" (қолмен қойылған)", " (задано вручную)", " (set by hand)"),
    "dp_wx_off": (
        "**Ауа райы, ауа, күн батуы:** ескерілмеді (баптауларда өшірілген).",
        "**Погода, воздух, закат:** не учитывались (отключено в настройках).",
        "**Weather, air, sunset:** not used (switched off in the settings).",
    ),
    "dp_src_met": (
        "болжам: MET Norway (CC BY 4.0), Астана орталығы",
        "прогноз: MET Norway (CC BY 4.0), центр Астаны",
        "forecast: MET Norway (CC BY 4.0), centre of Astana",
    ),
    "dp_src_om": (
        "Open-Meteo (open-meteo.com, CC BY 4.0, тек коммерциялық емес), Астана орталығы",
        "Open-Meteo (open-meteo.com, CC BY 4.0, только некоммерческое), центр Астаны",
        "Open-Meteo (open-meteo.com, CC BY 4.0, non-commercial use only), centre of Astana",
    ),
    "dp_wx_unknown": (
        "**Ауа райы:** белгісіз (сұраныс сәтсіз) — таңдау ауа райына қарай өзгермеді.",
        "**Погода:** неизвестна (запрос не удался) — подбор по погоде не менялся.",
        "**Weather:** unknown (the request failed) — the choice was not changed for the weather.",
    ),
    "dp_wx": (
        "**Ауа райы ({src}):** {t}°C, сезілуі {a}°C, жауын-шашын {p} мм",
        "**Погода ({src}):** {t}°C, ощущается {a}°C, осадки {p} мм",
        "**Weather ({src}):** {t}°C, feels like {a}°C, precipitation {p} mm",
    ),
    "dp_wx_bad": (
        " → қолайсыз ({reason}): ғимарат ішіндегі орындарға басымдық, жаяу {m} м-ден артық емес.",
        " → неблагоприятная ({reason}): приоритет помещениям, пешком не дальше {m} м.",
        " → adverse ({reason}): indoor places first, on foot not farther than {m} m.",
    ),
    "dp_wx_kept": (
        " → қолайсыз ({reason}): ашық аспан астындағы орынды сұрадыңыз, ол қалдырылды, серуенді қысқарту жөн; "
        "жаяу {m} м-ден артық емес.",
        " → неблагоприятная ({reason}): вы просили место на улице, оно оставлено, прогулку лучше сократить; "
        "пешком не дальше {m} м.",
        " → adverse ({reason}): you asked for an outdoor place, so it is kept, better keep the walk short; "
        "on foot not farther than {m} m.",
    ),
    "dp_wx_driver": ("**Ауа райы:**", "**Погода:**", "**Weather:**"),
    "dp_wx_ok": (" → таңдау өзгермеді.", " → подбор не менялся.", " → the choice was not changed."),
    "dp_air_unknown": (
        "**Ауа:** белгісіз (сұраныс сәтсіз) — таңдау ауаға қарай өзгермеді.",
        "**Воздух:** неизвестен (запрос не удался) — подбор по воздуху не менялся.",
        "**Air:** unknown (the request failed) — the choice was not changed for the air.",
    ),
    "dp_air": (
        "**Ауа ({src}):** PM2.5 {pm} мкг/м³",
        "**Воздух ({src}):** PM2.5 {pm} мкг/м³",
        "**Air ({src}):** PM2.5 {pm} µg/m³",
    ),
    "dp_air_aqi": (", AQI {aqi}", ", AQI {aqi}", ", AQI {aqi}"),
    "dp_air_bad": (
        " → {reason}: ғимарат ішіндегі орындарға басымдық.",
        " → {reason}: приоритет помещениям.",
        " → {reason}: indoor places first.",
    ),
    "dp_air_kept": (
        " → {reason}: ашық аспан астындағы орынды сұрадыңыз, ол қалдырылды, серуенді қысқарту жөн.",
        " → {reason}: вы просили место на улице, оно оставлено, прогулку лучше сократить.",
        " → {reason}: you asked for an outdoor place, so it is kept, better keep the walk short.",
    ),
    "dp_air_nopm": (
        "**Ауа:** PM2.5 белгісіз",
        "**Воздух:** PM2.5 неизвестен",
        "**Air:** PM2.5 unknown",
    ),
    "dp_air_ok": (
        " → {limit} шегінен аспайды, таңдау өзгермеді.",
        " → не выше порога {limit}, подбор не менялся.",
        " → not above the threshold {limit}, the choice was not changed.",
    ),
    "dp_sun": (
        "**Күн:** шығуы {rise}, батуы {sset} ({src})",
        "**Солнце:** восход {rise}, закат {sset} ({src})",
        "**Sun:** sunrise {rise}, sunset {sset} ({src})",
    ),
    "dp_sun_dark": (
        " → сұраныс сәтінде қараңғы: саябақ, алаң және шолу нүктелері рейтингте төмен.",
        " → на момент запроса темно: парки, площадки и смотровые ниже в рейтинге.",
        " → dark at the time of the request: parks, playgrounds and viewpoints rank lower.",
    ),
    "dp_sun_dark_kept": (
        " → сұраныс сәтінде қараңғы: ашық аспан астындағы орынды сұрадыңыз, ол қалдырылды; "
        "жарықтандыру деректерде жоқ.",
        " → на момент запроса темно: вы просили место на улице, оно оставлено; освещение в данных неизвестно.",
        " → dark at the time of the request: you asked for an outdoor place, so it is kept; lighting is not "
        "in the data.",
    ),
    "dp_sun_light": (
        " → жарық, таңдау өзгермеді.",
        " → светло, подбор не менялся.",
        " → daylight, the choice was not changed.",
    ),
    "dp_sun_calc": ("есеп", "расчёт", "calculation"),
    "dp_holiday": (
        "**Мереке күні:** {name} — OSM бойынша «ашық» «белгісіз» дәрежесіне дейін төмендетілді "
        "(тізім: gov.kz, «Қазақстан Республикасындағы мерекелер туралы» заң).",
        "**Праздничный день:** {name} — «открыто» по OSM понижено до «неизвестно» "
        "(список: gov.kz, закон «О праздниках в РК»).",
        "**Public holiday:** {name} — “open” by OSM is lowered to “unknown” "
        "(list: gov.kz, the law on holidays of Kazakhstan).",
    ),
    "dp_walk": (
        "**Жаяу бөліктер:** {stats} (valhalla — серверге сұраныс, cache — кэштен, straight — түзу сызық "
        "×1.3, estimate — жылдамдық моделі). Valhalla-ға дөңгелектелген нүкте мен ұсынылған орындардың "
        "координаттары кетті; іздеу радиусы түзу сызық бойынша есептеледі.",
        "**Пешие отрезки:** {stats} (valhalla — запрос к серверу, cache — из кэша, straight — по прямой "
        "×1.3, estimate — модель скорости). В Valhalla ушли: округлённая точка и координаты "
        "рекомендованных мест; радиус поиска считается по прямой.",
        "**Walking legs:** {stats} (valhalla — a request to the server, cache — from the cache, straight — "
        "straight line ×1.3, estimate — a speed model). Sent to Valhalla: the rounded point and the "
        "coordinates of the recommended places; the search radius is counted along the straight line.",
    ),
    "dp_lrt": ("**LRT:** {note}.", "**LRT:** {note}.", "**LRT:** {note}."),
    "dp_parse": (
        "**Сұранысты талдау:** {how}{note}",
        "**Разбор запроса:** {how}{note}",
        "**Parsing of the request:** {how}{note}",
    ),
    "dp_parse_llm": (
        "ережелер (ru/kk/en), содан кейін ЖИ нақтылайды: санаттар біріктіріледі, ережелер өшірілмейді",
        "правила (ru/kk/en), затем ИИ уточняет: категории объединяются, правила не стираются",
        "rules (ru/kk/en), then the AI refines: categories are united, rules are not erased",
    ),
    "dp_parse_rules": (
        "ережелер (ru/kk/en), **ЖИ-сіз**",
        "правила (ru/kk/en), **без ИИ**",
        "rules (ru/kk/en), **no AI**",
    ),
    "dp_chain_parse": (
        "**Модельдер тізбегі (талдау):** {chain} · {ms} мс",
        "**Цепочка моделей (разбор):** {chain} · {ms} мс",
        "**Model chain (parsing):** {chain} · {ms} ms",
    ),
    "dp_chain_gen": (
        "**Модельдер тізбегі (генерация):** {chain} · {ms} мс",
        "**Цепочка моделей (генерация):** {chain} · {ms} мс",
        "**Model chain (generation):** {chain} · {ms} ms",
    ),
    "dp_cached": (" · **кэштен**", " · **из кэша**", " · **from cache**"),
    "dp_retry_live": (
        "**Жазылған жауап жарамады:** бірде-бір карточкада модель мәтіні қалмады — модельдерден қайта сұралды, "
        "жаңа жауап қолданылды.",
        "**Записанный ответ не подошёл:** ни в одной карточке не осталось текста модели — модели спрошены "
        "заново, использован новый ответ.",
        "**The recorded answer was unusable:** no card was left with the model's text — the models were asked "
        "again and the new answer is used.",
    ),
    "dp_retry_failed": (
        "**Жазылған жауап жарамады:** бірде-бір карточкада модель мәтіні қалмады, ал қайта сұрау сәтсіз болды — "
        "карточка мәтіндері деректерден алынған үлгі бойынша.",
        "**Записанный ответ не подошёл:** ни в одной карточке не осталось текста модели, а повторный запрос "
        "к моделям не удался — тексты карточек по шаблону из данных.",
        "**The recorded answer was unusable:** no card was left with the model's text and asking the models "
        "again failed — the card texts are the template from the data.",
    ),
    "dp_filters": (
        "**Сүзгілер:** режим {mode} ({v} км/сағ), бюджет {b} мин, бюджеттің {s}% барып-қайтуға → радиус "
        "{r}; санаттар: {cats}{relaxed}; түнгі режим: {night}; кілт сөздер: {kw}.",
        "**Фильтры:** режим {mode} ({v} км/ч), бюджет {b} мин, {s}% бюджета на дорогу туда-обратно → "
        "радиус {r}; категории: {cats}{relaxed}; ночной режим: {night}; ключевые слова: {kw}.",
        "**Filters:** mode {mode} ({v} km/h), budget {b} min, {s}% of the budget for the round trip → "
        "radius {r}; categories: {cats}{relaxed}; night mode: {night}; keywords: {kw}.",
    ),
    "dp_relaxed": (
        " (табылғаны аз — басқалары қосылды, белгіленген)",
        " (нашлось мало — добавлены другие, помечены)",
        " (too few found — others were added and marked)",
    ),
    "dp_any": ("шектеусіз", "без ограничений", "no limits"),
    "yes": ("иә", "да", "yes"),
    "no": ("жоқ", "нет", "no"),
    "dp_candidates": (
        "**Үміткерлер:** барлығы POI {total}, радиуста {inr}, жабық болғандықтан шығарылды {closed}, "
        "көрсетілген үміткер {n} (жұмыс уақыты белгісіз: {unk}).",
        "**Кандидаты:** всего POI {total}, в радиусе {inr}, закрыто и исключено {closed}, показано "
        "кандидатов {n} (с неизвестными часами: {unk}).",
        "**Candidates:** {total} POI in all, {inr} in the radius, {closed} excluded as closed, {n} "
        "candidates shown ({unk} with unknown hours).",
    ),
    "dp_time_cut": (
        "**Уақыт бойынша іріктеу:** {n} (барып-қайтқаннан кейін орында болудың ең аз уақыты бюджетке "
        "сыймайды). **Біріктірілген желілер:** {chains}.",
        "**Отсев по времени:** {n} (минимальное время на месте не помещается в бюджет после дороги туда "
        "и обратно). **Слито сетей:** {chains}.",
        "**Cut by time:** {n} (the minimum stay does not fit the budget after the round trip). "
        "**Chains merged:** {chains}.",
    ),
    "dp_merged": (
        "**{name}** (`{id}`) карточкасына біріктірілді: {items}",
        "Объединено в карточку **{name}** (`{id}`): {items}",
        "Merged into the card **{name}** (`{id}`): {items}",
    ),
    "col_poi": ("POI", "POI", "POI"),
    "col_cat": ("санат", "категория", "category"),
    "col_m": ("м", "м", "m"),
    "col_min": ("мин", "мин", "min"),
    "col_hours": ("жұмыс уақыты", "часы", "hours"),
    "col_score": ("балл", "балл", "score"),
    "col_reasons": ("себептер", "причины", "reasons"),
    "dp_text_llm": (
        "**Ұсыныс мәтіні:** ЖИ (`{model}`) — тек үміткерлердің фактілері бойынша; қашықтық, уақыт және "
        "жұмыс уақытын код қояды; дерек көзін және орындағы уақытты да код анықтайды.",
        "**Текст рекомендаций:** ИИ (`{model}`) — только по фактам кандидатов; расстояния, время и часы "
        "подставлены кодом; источник данных и время на месте тоже определяет код.",
        "**Text of the recommendations:** AI (`{model}`) — only from the facts of the candidates; "
        "distances, times and hours are filled in by code; the data source and the time on site are also "
        "decided by code.",
    ),
    "dp_text_tpl": (
        "**Ұсыныс мәтіні:** **ЖИ-сіз** (деректерден алынған үлгі) — {note}.",
        "**Текст рекомендаций:** **без ИИ** (шаблон из данных) — {note}.",
        "**Text of the recommendations:** **no AI** (a template from the data) — {note}.",
    ),
    "dp_timing": (
        "**Уақыт:** талдау {i} мс · іздеу {r} мс · генерация {g} мс · маршрут {rt} мс · **барлығы {total} мс**",
        "**Время:** разбор {i} мс · поиск {r} мс · генерация {g} мс · маршрут {rt} мс · **всего {total} мс**",
        "**Time:** parsing {i} ms · search {r} ms · generation {g} ms · route {rt} ms · **total {total} ms**",
    ),
    "dp_payload_none": (
        "Генерация қадамында ЖИ-ге ештеңе жіберілмеді.",
        "На шаге генерации в ИИ ничего не отправлялось.",
        "Nothing was sent to the AI in the generation step.",
    ),
    "dp_parse_sent": (
        "Талдау қадамында ЖИ-ге сіздің сұраныс мәтініңіз бен ережелер жобасы (координаттарсыз) кетті.",
        "На шаге разбора в ИИ ушли текст вашего запроса и черновик правил (без координат).",
        "In the parsing step the text of your request and the draft of the rules went to the AI "
        "(without coordinates).",
    ),
    "dp_unbacked": (
        "**Деректерде дәлелі жоқ ЖИ сөйлемдері алынып тасталды:** {n}.",
        "**Удалено фраз ИИ без опоры на данные:** {n}.",
        "**AI sentences dropped for lack of backing in the data:** {n}.",
    ),
    # data-dash: the «Данные» page
    "data_title": ("Деректер", "Данные", "Data"),
    "data_lead": (
        "Анық фактілерді қайдан алады, олар қаншалықты толық және жауаптар қаншалықты адал.",
        "Откуда Анық берёт факты, насколько они полные и насколько честны ответы.",
        "Where Anyq gets its facts, how complete they are and how honest the answers are.",
    ),
    "dd_tile_places": ("базадағы орын", "мест в базе", "places in the base"),
    "dd_tile_hours": (
        "орынның жұмыс уақыты белгілі",
        "мест с известными часами",
        "places with known hours",
    ),
    "dd_tile_sources": ("дереккөз", "источников данных", "data sources"),
    "dd_tile_dates": ("деректер жиналған күн", "данные собраны", "data collected"),
    "data_sources": ("Дереккөздер", "Источники", "Sources"),
    "dd_sources_lead": (
        "Жауаптағы әр факт дереккөзімен белгіленеді. Мұнда — ол қайдан және қандай шартпен алынатыны.",
        "Каждый факт в ответе помечен источником. Здесь — откуда он берётся и на каких условиях.",
        "Every fact in an answer is marked with its source. Here is where it comes from and on what terms.",
    ),
    "dd_g_places": ("Орындар және олардың фактілері", "Места и их факты", "Places and their facts"),
    "dd_g_weather": ("Ауа райы және ауа", "Погода и воздух", "Weather and air"),
    "dd_g_moving": ("Жол, көлік, карта", "Дороги, транспорт, карта", "Roads, transit, the map"),
    "dd_g_city": ("Қала және тұрғындар", "Город и жители", "The city and its people"),
    "dd_unit_places": ("орын", "мест", "places"),
    "dd_unit_stops": ("аялдама", "остановок", "stops"),
    "dd_unit_events": ("оқиға", "событий", "events"),
    "dd_licence": ("Лицензия", "Лицензия", "Licence"),
    "dd_source": ("Дереккөз", "Источник", "Source"),
    "ds_osm": ("OpenStreetMap", "OpenStreetMap", "OpenStreetMap"),
    "ds_osm_what": (
        "Базаның негізі: атаулар, орын түрлері, жұмыс уақыты мен мекенжайлар. Сондай-ақ жабылу туралы "
        "ашық ескертпелер, жарықтандырылған көшелер мен жол жұмыстары.",
        "Основа базы: названия, виды мест, часы работы и адреса. Ещё — открытые заметки о закрытии, "
        "освещённые улицы и дорожные работы.",
        "The backbone of the base: names, kinds of places, opening hours and addresses. Also open notes "
        "about closures, lit streets and road works.",
    ),
    "ds_overture": ("Overture Maps", "Overture Maps", "Overture Maps"),
    "ds_overture_what": (
        "OpenStreetMap-та жоқ орындар мен телефондар. Әр жазбаның лицензиясы деректер авторына қарай: "
        "Meta, Microsoft, PinMeTo — CDLA-Permissive-2.0; Foursquare — Apache-2.0, © Foursquare Labs, "
        "Inc.; AllThePlaces — CC0. Файлдарды біз өзгерттік.",
        "Места, которых нет в OpenStreetMap, и телефоны. У каждой записи своя лицензия — по автору данных: "
        "Meta, Microsoft, PinMeTo — CDLA-Permissive-2.0; Foursquare — Apache-2.0, © Foursquare Labs, "
        "Inc.; AllThePlaces — CC0. Файлы изменены нами.",
        "Places OpenStreetMap lacks, and phone numbers. Each record has its own licence, by who "
        "contributed it: Meta, Microsoft, PinMeTo — CDLA-Permissive-2.0; Foursquare — Apache-2.0, © "
        "Foursquare Labs, Inc.; AllThePlaces — CC0. The files are changed by us.",
    ),
    "ds_wikidata": ("Wikidata", "Wikidata", "Wikidata"),
    "ds_wikidata_what": (
        "Тек Wikidata-да бар орындар.",
        "Места, которые есть только в Wikidata.",
        "Places that exist only in Wikidata.",
    ),
    "ds_wikipedia": ("Wikipedia", "Wikipedia", "Wikipedia"),
    "ds_wikipedia_what": (
        "Орындардың қысқа сипаттамасы: мақаладан үзінді, оған сілтемемен.",
        "Короткие описания мест: выдержка из статьи со ссылкой на неё.",
        "Short descriptions of places: an excerpt from the article with a link to it.",
    ),
    "ds_wikivoyage": ("Wikivoyage", "Wikivoyage", "Wikivoyage"),
    "ds_wikivoyage_what": (
        "Саяхат нұсқаулығынан сипаттама, жұмыс уақыты немесе баға: мақалаға сілтемемен дәйексөз.",
        "Описание, часы или цена из путеводителя: цитата со ссылкой на статью.",
        "A description, hours or a price from the travel guide: a quote with a link to the article.",
    ),
    "ds_sites": (
        "Мекемелердің өз сайттары",
        "Сайты самих заведений",
        "The venues' own websites",
    ),
    "ds_sites_what": (
        "{d} сайттан жұмыс уақыты, телефон және мекенжай — мекеменің өз сайтындағы фактілер. Әр фактінің "
        "беті мен дәйексөзі сақталған.",
        "Часы, телефон и адрес с {d} сайтов — факты с сайта самого заведения. У каждого факта сохранены "
        "страница и цитата.",
        "Hours, phone and address from {d} websites: facts from the venue's own site. Each fact keeps its "
        "page and quote.",
    ),
    "ds_museums": (
        "Мұражайлар реестрі e-museum.kz",
        "Реестр музеев e-museum.kz",
        "The e-museum.kz museum register",
    ),
    "ds_museums_what": (
        "Мәдениет министрлігі реестрінен мұражайлардың жұмыс уақыты мен билет бағасы. Әр фактінің "
        "карточкасы мен дәйексөзі сақталған; порталда пайдалану шарттары көрсетілмеген.",
        "Часы работы и цена билета музеев из реестра Министерства культуры. У каждого факта сохранены "
        "карточка и цитата; на портале условия использования не указаны.",
        "Museum hours and ticket prices from the Ministry of Culture's register. Each fact keeps its card "
        "and quote; the portal states no terms of use.",
    ),
    "ds_gov": (
        "ХҚКО және мемлекеттік спорт нысандары",
        "ЦОН и государственные спортобъекты",
        "Public Service Centres and state sports venues",
    ),
    "ds_gov_what": (
        "ХҚКО мекенжайлары мен кесте, мемлекеттік спорт нысандарының тізімі — мемлекеттік органдардың "
        "ашық деректері (ақпаратқа қол жеткізу туралы заң, № 401-V). Координаттарды OpenStreetMap-тан "
        "аламыз.",
        "Адреса и расписание ЦОН и перечень государственных спортивных объектов — открытые данные "
        "госорганов (закон о доступе к информации, № 401-V). Координаты берём из OpenStreetMap.",
        "Addresses and schedules of the Public Service Centres and the list of state sports venues: open "
        "data of state bodies (the access-to-information law, No. 401-V). Coordinates come from "
        "OpenStreetMap.",
    ),
    "ds_met": ("MET Norway", "MET Norway", "MET Norway"),
    "ds_met_what": (
        "Астана орталығы бойынша ауа райы болжамы: температура, жел, жауын-шашын. Күн шығуы мен батуы "
        "формула бойынша есептеледі. Data from MET Norway.",
        "Прогноз погоды по центру Астаны: температура, ветер, осадки. Восход и закат считаются по "
        "формуле. Data from MET Norway.",
        "The weather forecast for the centre of Astana: temperature, wind, precipitation. Sunrise and "
        "sunset are calculated. Data from MET Norway.",
    ),
    "ds_kazhydromet": ("Қазгидромет", "Казгидромет", "Kazhydromet"),
    "ds_kazhydromet_what": (
        "Әуежай метеостанциясының бақылауы (METAR), дауыл ескертулері мен НМУ — сөзбе-сөз, хабарлама "
        "бетінің сілтемесімен.",
        "Наблюдение метеостанции аэропорта (METAR), штормовые предупреждения и НМУ — дословно, со "
        "ссылкой на страницу уведомления.",
        "The airport weather station's observation (METAR), storm warnings and smog alerts: verbatim, "
        "with a link to the notice.",
    ),
    "ds_openmeteo": ("Open-Meteo", "Open-Meteo", "Open-Meteo"),
    "ds_openmeteo_what": (
        "Ауадағы PM2.5: оны оператор қосқанда ғана сұралады. Weather data by Open-Meteo.com.",
        "PM2.5 в воздухе: запрашивается, только если его включил оператор. Weather data by "
        "Open-Meteo.com.",
        "PM2.5 in the air: requested only when the operator switches it on. Weather data by "
        "Open-Meteo.com.",
    ),
    "ds_valhalla": ("Valhalla", "Valhalla", "Valhalla"),
    "ds_valhalla_what": (
        "OpenStreetMap бойынша жаяу жол уақыты; желі болмаса — түзу сызық бойынша бағалау.",
        "Время пути пешком по OpenStreetMap; без сети — оценка по прямой.",
        "Walking times over OpenStreetMap; without the network, an estimate along the straight line.",
    ),
    "src_walk": (
        "Valhalla (FOSSGIS, жария сервер — шағын жүктеме үшін)",
        "Valhalla (FOSSGIS, публичный сервер — для небольшой нагрузки)",
        "Valhalla (FOSSGIS public server — for a light load)",
    ),
    "ds_gtfs": (
        "Аялдамалар (GTFS, Zenodo)",
        "Остановки (GTFS, Zenodo)",
        "Bus stops (GTFS, Zenodo)",
    ),
    "ds_gtfs_what": (
        "AITU зерттеушілерінің ашық жиыны: тек аялдамалар. Кестелер жоқ: бұл жиында олар сенімсіз.",
        "Открытый набор исследователей AITU: только остановки. Расписаний нет: в этом наборе на них "
        "нельзя полагаться.",
        "An open dataset by AITU researchers: stops only. No timetables: in this set they cannot be "
        "relied on.",
    ),
    "ds_airport": ("nn-airport.kz", "nn-airport.kz", "nn-airport.kz"),
    "ds_airport_what": (
        "Әуежайға автобустар (№ 10, № 12): бірінші және соңғы рейс, аралық, ақы — әуежай бетінен күні "
        "көрсетілген фактілер. Сайтта лицензия көрсетілмеген.",
        "Автобусы в аэропорт (№ 10, № 12): первый и последний рейс, интервал, тариф — датированные факты "
        "со страницы аэропорта. Лицензия на сайте не указана.",
        "Buses to the airport (No. 10, No. 12): first and last departure, interval, fare — dated facts "
        "from the airport's page. The site states no licence.",
    ),
    "ds_basemap": ("OpenFreeMap", "OpenFreeMap", "OpenFreeMap"),
    "ds_basemap_what": (
        "Карта негізі. Интернетсіз карта негізсіз көрсетіледі.",
        "Подложка карты. Без интернета карта показывается без подложки.",
        "The base map. Without the internet the map shows without it.",
    ),
    "ds_afisha": ("Афиша", "Афиша событий", "Event listings"),
    "ds_afisha_what": (
        "Sxodim, InAstana, YouTicket, Qazaqconcert, Alem.ai және бір ашық Telegram-арна: тек фактілер "
        "(атауы, уақыты, орны, бағасы) оқиға бетіне сілтемемен. Афиша толық емес.",
        "Sxodim, InAstana, YouTicket, Qazaqconcert, Alem.ai и один публичный Telegram-канал: только "
        "факты (название, время, место, цена) со ссылкой на страницу события. Афиша неполная.",
        "Sxodim, InAstana, YouTicket, Qazaqconcert, Alem.ai and one public Telegram channel: facts only "
        "(title, time, place, price) with a link to the event's page. The listing is incomplete.",
    ),
    "ds_marks": ("Тұрғындар белгілері", "Отметки жителей", "Residents' marks"),
    "ds_marks_what": (
        "Анонимді белгілер: орын, белгі, күн, тәулік бөлігі. 30 күннен ескілері ескерілмейді.",
        "Анонимные отметки: место, отметка, день, часть суток. Старше 30 дней не учитываются.",
        "Anonymous marks: the place, the mark, the day, the part of the day. Marks older than 30 days "
        "are ignored.",
    ),
    "data_coverage": (
        "Деректер қаншалықты толық",
        "Насколько полные данные",
        "How complete the data is",
    ),
    "cov_lead": (
        "Көмекші іздейтін {n} орын бойынша (көлік аялдамаларынсыз):",
        "По {n} местам, среди которых ищет помощник (без остановок транспорта):",
        "Over the {n} places the assistant searches (transit stops excluded):",
    ),
    "dd_cov_fields": (
        "Орындар туралы не белгілі",
        "Что известно о местах",
        "What is known about places",
    ),
    "cov_hours": ("Жұмыс уақыты белгілі", "Известны часы работы", "Opening hours known"),
    "cov_hours_osm": ("…OpenStreetMap-тан", "…из OpenStreetMap", "…from OpenStreetMap"),
    "cov_hours_site": ("…ресми сайттан", "…с официального сайта", "…from the official website"),
    "cov_phone": ("Телефон", "Телефон", "Phone"),
    "cov_website": ("Сайт", "Сайт", "Website"),
    "cov_address": ("Мекенжай", "Адрес", "Address"),
    "cov_description": (
        "Адам жазған сипаттама",
        "Описание, написанное человеком",
        "Human-written description",
    ),
    "dd_cov_cats": (
        "Орын түрлері бойынша жұмыс уақыты",
        "Часы работы по видам мест",
        "Opening hours by kind of place",
    ),
    "dd_cov_dist": (
        "Аудандар бойынша жұмыс уақыты",
        "Часы работы по районам",
        "Opening hours by district",
    ),
    "dd_show_all": ("Барлығын көрсету ({n})", "Показать все ({n})", "Show all ({n})"),
    "cov_note": (
        "Жұмыс уақыты жоқ жерде көмекші «жұмыс уақыты белгісіз» деп жазады және ешқашан «ашық» "
        "демейді.",
        "Где часов нет, помощник пишет «часы неизвестны» и никогда не говорит «открыто».",
        "Where there are no hours, the assistant says “hours unknown” and never says “open”.",
    ),
    "data_honesty": (
        "Жауаптар қаншалықты адал",
        "Насколько честны ответы",
        "How honest the answers are",
    ),
    "dd_hon": (
        "Тексеру сұраныстарында {recs} ұсыныстың {n}-і ойдан шығарылған орын; жұмыс уақыты жоқ жерде "
        "«белгісіз» деп адал айтылғаны — {p}%; түзетулерден кейін жазылған {cases} жаңа сұраныстың "
        "қатесіз өткені — {all}%.",
        "На проверочных запросах выдуманных мест: {n} из {recs} рекомендаций; где часов нет, честно "
        "сказано «неизвестно» в {p}% случаев; {cases} новых запросов, написанных после правок, прошли "
        "без единой ошибки в {all}%.",
        "On the test requests there were {n} invented places in {recs} recommendations; where hours are "
        "missing, “unknown” was said honestly in {p}% of cases; of {cases} new requests written after "
        "the fixes, {all}% passed without a single error.",
    ),
    "dd_hon_date": ("Өлшеу: {date}.", "Замер: {date}.", "Measured on {date}."),
    "hon_missing": (
        "Өлшеу нәтижелері табылмады.",
        "Результаты замеров не найдены.",
        "No evaluation results found.",
    ),
    "data_attribution": ("Атрибуция", "Атрибуция", "Attribution"),
    # ---- the «Город» page
    "city_title": ("Қала", "Город", "City"),
    "city_lead": (
        "Көмекшіні қоректендіретін деректердің өзі — қала мен ғылыми орталыққа арналған. Тек 500 м "
        "ұяшықтар бойынша жиынтықтар.",
        "Те же данные, что питают помощника, — для города и научного центра. Только сводки по ячейкам "
        "500 м.",
        "The same data that feeds the assistant, for the city and the research centre. Only totals per "
        "500 m cell.",
    ),
    "city_tab_demand": ("Сұраныс", "Спрос", "Demand"),
    "city_tab_quality": ("Деректердегі олқылықтар", "Пробелы в данных", "Gaps in the data"),
    "city_tab_reports": ("Тұрғындар хабарлары", "Сообщения жителей", "Residents' reports"),
    "city_src_sim": ("Модельденген сұраныс", "Смоделированный спрос", "Simulated demand"),
    "city_src_real": ("Нақты сұраныстар журналы", "Реальный журнал запросов", "Real request log"),
    "city_sim_banner": (
        "Бұл — модельденген сұраныс, қала туралы бақылау емес. Нақты трафик әзірге жоқ: сұраныстар "
        "тұрғын үйлер санына пропорционал нүктелерде жасалған, оларға нағыз конвейер жауап береді. "
        "Карта мен кесте тұрғындардың қалауын емес, механизмді көрсетеді.",
        "Это смоделированный спрос, не наблюдение о городе. Реального трафика пока нет: запросы "
        "нарисованы в точках пропорционально числу жилых домов, и на них отвечает настоящий конвейер. "
        "Карта и таблица показывают механизм, а не то, чего хотят жители.",
        "This is simulated demand, not an observation of the city. There is no real traffic yet: "
        "requests were drawn at points in proportion to the number of residential buildings, and the "
        "real pipeline answered them. The map and the table show the mechanism, not what residents want.",
    ),
    "city_sim_meta": (
        "Қайталанады: seed {seed}, {n} сұраныс, {date}.",
        "Воспроизводимо: seed {seed}, {n} запросов, {date}.",
        "Reproducible: seed {seed}, {n} requests, {date}.",
    ),
    "city_no_log": (
        "Сұраныстар журналы өшірулі.",
        "Журнал запросов выключен.",
        "The request log is off.",
    ),
    "city_log_empty": (
        "Журналда әзірге сұраныс жоқ: ол адамдар көмекшіні қолданғанда толады (анонимді жазба: 500 м "
        "ұяшық, санаттар, есептегіштер).",
        "В журнале пока нет запросов: он наполняется, когда люди пользуются помощником (анонимная "
        "запись: ячейка 500 м, категории, счётчики).",
        "The log has no requests yet: it fills as people use the assistant (an anonymous record: a "
        "500 m cell, categories, counters).",
    ),
    "city_category": ("Санат", "Категория", "Category"),
    "city_bucket": ("Тәулік уақыты", "Время суток", "Time of day"),
    "city_all": ("Барлығы", "Все", "All"),
    "city_k": (
        "Топтағы ең аз сұраныс (k, кемінде {min})",
        "Минимум запросов в группе (k, от {min})",
        "Smallest group (k, at least {min})",
    ),
    "city_k_less": ("k азайту", "Уменьшить k", "Lower k"),
    "city_k_more": ("k көбейту", "Увеличить k", "Raise k"),
    "city_m_requests": ("Сұраныстар", "Запросов", "Requests"),
    "city_m_no_place": (
        "Радиуста ондай орын жоқ",
        "Нет такого места в радиусе",
        "No such place in reach",
    ),
    "city_m_hours_unknown": (
        "Орын бар, уақыты жоқ",
        "Место есть, часов нет",
        "Place exists, no hours",
    ),
    "city_m_cells_shown": ("Көрсетілген ұяшық", "Ячеек показано", "Cells shown"),
    "city_m_cells_hidden": ("Жасырылған ұяшық (<k)", "Ячеек скрыто (<k)", "Cells hidden (<k)"),
    "city_legend_few": ("аз", "мало", "few"),
    "city_legend_many": ("көп", "много", "many"),
    "city_demand_note": (
        "Түс — деректерде радиуста қажетті түрдегі орын таппаған сұраныстар саны. Жасыл — ондай "
        "сұраныс жоқ. {k}-тен аз сұранысы бар ұяшықтар көрсетілмейді.",
        "Цвет — сколько запросов не нашли в данных места нужного вида в радиусе. Зелёный — таких "
        "запросов нет. Ячейки, где запросов меньше {k}, не показаны.",
        "Colour: how many requests found no place of the wanted kind in reach in the data. Green: none. "
        "Cells with fewer than {k} requests are not shown.",
    ),
    "city_hidden_note": (
        "Жасырылған ұяшықтардағы сұраныстар: {n}.",
        "Запросов в скрытых ячейках: {n}.",
        "Requests in hidden cells: {n}.",
    ),
    "city_top_title": (
        "Ең көп жетіспейтін жерлер",
        "Где не хватает больше всего",
        "Where it is missing most",
    ),
    "city_col_district": ("Аудан", "Район", "District"),
    "city_col_category": ("Санат", "Категория", "Category"),
    "city_col_bucket": ("Уақыт", "Время суток", "Time of day"),
    "city_col_requests": ("Сұраныс", "Запросов", "Requests"),
    "city_col_no_place": ("Орын жоқ", "Нет места", "No place"),
    "city_col_share": ("Үлесі", "Доля", "Share"),
    "city_col_places": ("Орындар", "Мест", "Places"),
    "city_col_with_hours": ("Уақытымен", "С часами", "With hours"),
    "city_merged": (
        "k={k}-тен кіші топтар орынсыз «басқа» жолына біріктірілді: {g} топтағы {n} сұраныс.",
        "Группы меньше k={k} слиты в строку «прочее» без места: {n} запросов в {g} группах.",
        "Groups below k={k} were merged into «other» without a location: {n} requests in {g} groups.",
    ),
    "city_actions_title": (
        "Қалаға не істеу керек",
        "Что с этим делать городу",
        "What the city can do",
    ),
    "city_actions_sim": (
        "Модельденген сұраныс бойынша: бұл есептің үлгісі, тұрғындар туралы қорытынды емес.",
        "По смоделированному спросу: это пример отчёта, а не вывод о жителях.",
        "On simulated demand: this shows what the report looks like, not a finding about residents.",
    ),
    "city_act_supply": (
        "{district}: «{cat}» бойынша {of} сұраныстың {n}-і радиуста бірде-бір орын таппады. Алдымен "
        "картадан деректердегі олқылықты тексеру керек; орын шынымен жоқ болса — орналастыруға үміткер.",
        "{district}: {n} из {of} запросов на «{cat}» не нашли ни одного такого места в радиусе. "
        "Сначала проверить карту на пропуск в данных; если места правда нет — кандидат на размещение.",
        "{district}: {n} of {of} requests for “{cat}” found no such place in reach. First check the map "
        "for a gap in the data; if there really is none, it is a candidate site.",
    ),
    "city_actions_none": (
        "Көрсетілген топтарда (кемінде k сұраныс) мұндай жағдай жоқ.",
        "В показанных группах (не меньше k запросов) таких случаев нет.",
        "No such cases in the groups shown (at least k requests).",
    ),
    "city_padded": (
        "Жауап сапасы (қала туралы емес): {of} сұраныстың {n}-інде радиусты кеңейтуге немесе басқа "
        "санат алуға тура келді.",
        "Качество ответа (не про город): в {n} из {of} запросов пришлось расширить радиус или взять "
        "другую категорию.",
        "Answer quality (not about the city): {n} of {of} requests needed a wider radius or another "
        "category.",
    ),
    "city_how_title": (
        "Анонимдік және жүктеу",
        "Анонимность и выгрузка",
        "Anonymity and export",
    ),
    "city_how_1": (
        "Әр сұраныстан бір жол жазылады: сағат, 500 м ұяшық, санаттар, есептегіштер. Сұраныс мәтіні, "
        "есімдер, координаттар мен орын id жазылмайды; профильмен берілген жауаптар мүлдем жазылмайды.",
        "По каждому запросу пишется одна строка: час, ячейка 500 м, категории, счётчики. Без текста "
        "запроса, имён, координат и id мест; ответы с личным профилем не пишутся вовсе.",
        "Each request writes one line: the hour, a 500 m cell, categories, counters. No request text, "
        "names, coordinates or place ids; answers made with a personal profile are not written at all.",
    ),
    "city_how_2": (
        "Координаттар алдымен ~100 м-ге дейін дөңгелектенеді, содан кейін 500 × 500 м ұяшыққа "
        "келтіріледі.",
        "Координаты сначала округляются до ~100 м, затем сводятся к ячейке 500 × 500 м.",
        "Coordinates are first rounded to ~100 m, then reduced to a 500 × 500 m cell.",
    ),
    "city_how_3": (
        "«Ұяшық × санат × тәулік уақыты» тобы кемінде {k} сұраныс болса ғана көрсетіледі; қалғандары "
        "орынсыз «басқа» жолына қосылады. Нақты журнал үшін k 5-тен төмен түспейді.",
        "Группа «ячейка × категория × время суток» показывается, только если в ней не меньше {k} "
        "запросов; остальные сливаются в «прочее» без места. Для реального журнала k не опускается "
        "ниже 5.",
        "A “cell × category × time of day” group is shown only with at least {k} requests; the rest "
        "merge into “other” without a location. For the real log k never goes below 5.",
    ),
    "city_how_4": (
        "Үш көрсеткіш араластырылмайды: радиуста ондай орын жоқ (деректер туралы факт, картада тек "
        "сол), орын бар бірақ уақыты жоқ (деректер сапасы), жауапты толықтыруға тура келді (рейтинг "
        "сапасы).",
        "Три показателя не смешиваются: нет такого места в радиусе (факт о данных, на карте только он), "
        "место есть, но часов нет (качество данных), ответу пришлось добирать (качество ранжирования).",
        "Three indicators are never mixed: no such place in reach (a fact about the data, the only one "
        "on the map), a place exists but no hours (data quality), the answer had to be padded (ranking "
        "quality).",
    ),
    "city_how_5": (
        "CSV мен GeoJSON тек көрсетілген топтардан және координатсыз «басқа» жолынан жиналады.",
        "CSV и GeoJSON собираются только из показанных групп и строки «прочее» без координат.",
        "CSV and GeoJSON are built only from the groups shown and the “other” row without coordinates.",
    ),
    "city_export_title": (
        "Жүктеу (тек жиынтықтар)",
        "Выгрузка (только агрегаты)",
        "Export (totals only)",
    ),
    "city_dl_demand_csv": ("CSV: сұраныс", "CSV: спрос", "CSV: demand"),
    "city_dl_demand_geojson": ("GeoJSON: сұраныс", "GeoJSON: спрос", "GeoJSON: demand"),
    "city_dl_quality_csv": ("CSV: деректер сапасы", "CSV: качество данных", "CSV: data quality"),
    "city_dl_quality_geojson": (
        "GeoJSON: деректер сапасы",
        "GeoJSON: качество данных",
        "GeoJSON: data quality",
    ),
    "city_quality_lead": (
        "Ұяшықтағы орындардың қандай үлесінде жұмыс уақыты, адам жазған сипаттама және тұрғындар "
        "белгілері бар. Үлес төмен жерде көмекшінің айтары аз, ал қалаға жинайтыны көп.",
        "Какая доля мест в ячейке имеет часы работы, описание, написанное человеком, и отметки жителей. "
        "Где доля низкая, помощнику нечего сказать, а городу — что дособрать.",
        "What share of the places in a cell has opening hours, a human-written description and "
        "residents' marks. Where it is low, the assistant has little to say and the city has something "
        "to collect.",
    ),
    "city_q_places": ("Деректердегі орындар", "Мест в данных", "Places in the data"),
    "city_q_hours": ("жұмыс уақыты", "часы работы", "opening hours"),
    "city_q_description": ("адам жазған сипаттама", "описание от человека", "human description"),
    "city_q_people": ("тұрғындар белгілері", "отметки жителей", "residents' marks"),
    "city_q_demo_marks": (
        "Файлдағы тұрғындар белгілері — демо (көрсету үшін), нақты емес.",
        "Отметки жителей в файле — демонстрационные, не реальные.",
        "The residents' marks in the file are demo marks, not real ones.",
    ),
    "city_legend_low": ("ешкімде дерлік жоқ", "почти ни у кого", "almost none"),
    "city_legend_high": ("барлығында дерлік бар", "почти у всех", "almost all"),
    "city_worst_title": (
        "Жұмыс уақыты ең аз санаттар",
        "Категории с худшим покрытием часами",
        "Categories with the fewest opening hours",
    ),
    "city_hours_actions_title": (
        "Қай жерден жұмыс уақытын сұрау керек",
        "Где запросить часы работы",
        "Where to ask for opening hours",
    ),
    "city_act_hours": (
        "{district}: «{cat}» санатындағы {n} орыннан жұмыс уақытын сұрау; ауданда {of} орынның "
        "{have}-інде ғана бар.",
        "{district}: запросить часы работы у {n} мест «{cat}»; в районе они есть у {have} из {of}.",
        "{district}: ask {n} “{cat}” places for their opening hours; in the district {have} of {of} "
        "have them.",
    ),
    "city_hours_actions_note": (
        "Дерек: орындар деректеріндегі жұмыс уақыты; аудандар — OSM шекаралары.",
        "Данные: часы работы в наборе мест; районы — границы OSM.",
        "Data: the opening hours in the place data; districts are OSM borders.",
    ),
    "city_reports_lead": (
        "Тұрғындар орын карточкасынан хабарлайды: «жабық», «уақыты басқа», «бәрі дұрыс» және т.б. "
        "Белгілер анонимді, олар таңдауда бөлек деңгей ретінде ескеріледі және деректерді түзетуге "
        "көмектеседі.",
        "Жители сообщают прямо с карточки места: «закрыто», «другие часы», «всё верно» и т.д. Отметки "
        "анонимны, учитываются в подборе отдельным уровнем и помогают исправить данные.",
        "Residents report from a place's card: “closed”, “different hours”, “all correct” and so on. "
        "Marks are anonymous, count in the choice as a separate level and help fix the data.",
    ),
    "city_r_total": ("Барлық белгі", "Всего отметок", "Marks in all"),
    "city_r_demo": (
        "Олардың {n}-і демо (көрсету үшін), нақты емес.",
        "Из них {n} — демонстрационные, не реальные.",
        "{n} of them are demo marks, not real ones.",
    ),
    "city_r_closed": ("жабық", "закрыто", "closed"),
    "city_r_differ": ("уақыты басқа", "другие часы", "different hours"),
    "city_r_open": ("ашық / дұрыс", "открыто / верно", "open / correct"),
    "city_r_other": ("басқа белгілер", "другие отметки", "other marks"),
    "city_r_recent": ("Соңғы белгілер", "Последние отметки", "Latest marks"),
    "city_r_none": ("Әзірге белгі жоқ.", "Пока отметок нет.", "No marks yet."),
    "city_load_fail": (
        "Деректерді жүктеу мүмкін болмады. Бетті жаңартып көріңіз.",
        "Не удалось загрузить данные. Обновите страницу.",
        "Could not load the data. Reload the page.",
    ),
    "city_no_district": (
        "аудан шекарасынан тыс",
        "вне границ районов",
        "outside the district borders",
    ),
    "city_any_category": ("санатсыз", "без категории", "no category"),
    "bucket_morning": ("таң 05–11", "утро 05–11", "morning 05–11"),
    "bucket_day": ("күндіз 11–17", "день 11–17", "day 11–17"),
    "bucket_evening": ("кеш 17–22", "вечер 17–22", "evening 17–22"),
    "bucket_night": ("түн 22–05", "ночь 22–05", "night 22–05"),
    "part_morning": ("таңертең", "утром", "in the morning"),
    "part_day": ("күндіз", "днём", "in the daytime"),
    "part_evening": ("кешке", "вечером", "in the evening"),
    "part_night": ("түнде", "ночью", "at night"),
    "d_stop": ("Автобус", "Автобус", "Bus"),
    "marks_off": (
        "Бұл нұсқада белгілер сақталмайды.",
        "В этой версии отметки не сохраняются.",
        "Marks are not saved in this version.",
    ),
    "city_q_queue_title": (
        "Тексеру кезегі: OpenStreetMap ескертпелері",
        "Очередь на проверку: заметки OpenStreetMap",
        "To check: OpenStreetMap notes",
    ),
    "city_q_queue_lead": (
        "Орын жабылды немесе жұмыс уақыты өзгерді деп адамдар жазған ашық ескертпелер. Бұл болжам, дерек емес: "
        "орнында тексеріп, картаны түзетіңіз.",
        "Открытые заметки людей о том, что место закрылось или изменило часы. Это подозрение, а не факт: "
        "проверьте на месте и поправьте карту.",
        "Open notes where people say a place has closed or changed its hours. A suspicion, not a fact: check on "
        "the spot and fix the map.",
    ),
    "city_q_queue_none": (
        "Түсірілімде жабылу немесе жұмыс уақыты туралы ашық ескертпе жоқ.",
        "В снимке нет открытых заметок о закрытии или часах работы.",
        "The snapshot has no open notes about closures or opening hours.",
    ),
    "city_q_note_closure": ("жабылған болуы мүмкін", "могло закрыться", "may have closed"),
    "city_q_note_hours": (
        "жұмыс уақыты өзгерген болуы мүмкін",
        "часы могли измениться",
        "hours may have changed",
    ),
    "city_q_note_open": ("Ескертпені ашу", "Открыть заметку", "Open the note"),
    "city_q_note_date": ("{date} жазылған", "от {date}", "from {date}"),
    "city_q_constr": (
        "жол жұмысы учаскелері (OpenStreetMap)",
        "участков дорожных работ (OpenStreetMap)",
        "road-works sections (OpenStreetMap)",
    ),
    "city_q_notes_open": ("ашық ескертпе", "открытых заметок", "open notes"),
    "city_q_layers_none": (
        "Бұл құрастырмада қала туралы OpenStreetMap деректері жоқ.",
        "В этой сборке нет данных OpenStreetMap о городе (заметки, стройки).",
        "This build has no OpenStreetMap city data (notes, road works).",
    ),
    "city_q_events_title": ("Афиша қамтуы", "Охват афиши", "Afisha coverage"),
    "city_q_events": (
        "Афишада {n} оқиға, {located}-інің картада мекенжайы бар; көздер: {sources}. Жаңартылған: {date}.",
        "В афише {n} событий, у {located} есть адрес на карте; источники: {sources}. Обновлено: {date}.",
        "{n} events in the afisha, {located} with an address on the map; sources: {sources}. Updated: {date}.",
    ),
    "city_q_events_note": (
        "Афиша — бірнеше көз ғана, қаладағы барлық іс-шара емес; «іс-шара жоқ» деп айтпаймыз.",
        "Афиша — лишь несколько источников, не все события города; «событий нет» мы не говорим.",
        "The afisha is only a few sources, not every event in the city; we never say “there are no events”.",
    ),
    "city_q_events_none": ("Афиша деректері жоқ.", "Данных афиши нет.", "No afisha data."),
    "city_q_events_stale": (
        "Афиша ескірген (36 сағаттан артық).",
        "Афиша устарела (старше 36 ч).",
        "The afisha is out of date (over 36 h).",
    ),
}
