"""Wording of the attribute checks and the honest «not in the data» notes (walks.claims, walks.retrieve): halal, quiet,
children, prices, booking, gaming machines, the nearest place of a kind that is absent nearby, and the user's own words
about the weather. An entry is a tuple (kk, ru, en), the same as in walks.i18n.STRINGS, which merges this table."""

from __future__ import annotations

ATTR_STRINGS: dict[str, tuple[str, str, str]] = {
    "fit_halal": (
        "деректерде халал деп белгіленген",
        "в данных отмечено как халяль",
        "marked halal in the data",
    ),
    "note_halal": (
        "Халал деректерде көрсетілмеген.",
        "Халяль в данных не указан.",
        "Halal is not stated in the data.",
    ),
    "note_halal_none": (
        "Табылған орындардың ешқайсысында халал белгісі жоқ: мейрамханадан өзіңіз нақтылаңыз.",
        "Ни у одного из найденных мест нет отметки халяль: уточните в самом заведении.",
        "None of the places found is marked halal in the data: ask the venue itself.",
    ),
    "note_quiet": (
        "Тыныштық деректерде расталмаған.",
        "Тишина в данных не подтверждена.",
        "Quietness is not confirmed in the data.",
    ),
    "note_kids": (
        "Балаларға лайықтылығы деректерде көрсетілмеген.",
        "Пригодность для детей в данных не указана.",
        "Suitability for children is not stated in the data.",
    ),
    "note_price": (
        "Бағасы мен кіру ақысы деректерде көрсетілмеген.",
        "Цены и платность входа в данных не указаны.",
        "Prices and entry fees are not stated in the data.",
    ),
    "note_booking": (
        "Банкеттер мен брондау деректерде көрсетілмеген.",
        "Банкеты и бронирование в данных не указаны.",
        "Banquets and booking are not stated in the data.",
    ),
    "note_gambling": (
        "Ойын автоматтары деректерде көрсетілмеген.",
        "Игровые автоматы в данных не указаны.",
        "Gaming machines are not stated in the data.",
    ),
    "note_nearest_far": (
        "Жақын жерде «{cat}» жоқ: ең жақыны — {km} км қашықтықта.",
        "Рядом нет места «{cat}»: ближайшее — в {km} км.",
        "There is no “{cat}” nearby: the nearest one is {km} km away.",
    ),
    "note_hint_outdoor": (
        "Ашық аспан астындағы орын, ал {reason}: далада болатын уақыт қысқартылды.",
        "Место на открытом воздухе, а {reason}: время на улице сокращено.",
        "An open-air place, but {reason}: the time outside is shortened.",
    ),
    "wx_hint_cold": (
        "өзіңіздің айтуыңызша, суық",
        "по вашим словам, холодно",
        "by your own words, it is cold",
    ),
    "wx_hint_rain": (
        "өзіңіздің айтуыңызша, жаңбыр немесе қар жауып тұр",
        "по вашим словам, идёт дождь или снег",
        "by your own words, it is raining or snowing",
    ),
    "wx_hint_heat": (
        "өзіңіздің айтуыңызша, ыстық",
        "по вашим словам, жара",
        "by your own words, it is hot",
    ),
    "wx_hint_smog": (
        "өзіңіздің айтуыңызша, ауа ластанған",
        "по вашим словам, смог",
        "by your own words, the air is smoggy",
    ),
}

# the diets of walks.attributes.DIETS: the card's note when the record does not mark it, the note of every card when no
# place found marks it, and the clause of the reason when the record does
_DIET_TEXT = {
    "vegetarian": (
        ("вегетариандық мәзір", "вегетарианское меню", "a vegetarian menu"),
        ("вегетариандық мәзір", "вегетарианское меню", "vegetarian dishes"),
    ),
    "vegan": (
        ("веган мәзірі", "веганское меню", "a vegan menu"),
        ("веган мәзірі", "веганское меню", "vegan dishes"),
    ),
    "gluten_free": (
        ("глютенсіз тағамдар", "блюда без глютена", "gluten-free dishes"),
        ("глютенсіз тағамдар", "блюда без глютена", "gluten-free dishes"),
    ),
    "kosher": (
        ("кошер тағамдары", "кошерная кухня", "kosher food"),
        ("кошер тағамдары", "кошерная кухня", "kosher food"),
    ),
}
for _d, (_n, _f) in _DIET_TEXT.items():
    ATTR_STRINGS[f"note_diet_{_d}"] = (
        f"{_n[0].capitalize()} деректерде көрсетілмеген.",
        f"{_n[1].capitalize()}: в данных не указано.",
        f"{_n[2].capitalize()}: not stated in the data.",
    )
    ATTR_STRINGS[f"note_diet_none_{_d}"] = (
        f"Табылған орындардың ешқайсысында «{_n[0]}» белгісі жоқ: мейрамханадан өзіңіз нақтылаңыз.",
        f"Ни у одного из найденных мест нет отметки «{_n[1]}»: уточните в самом заведении.",
        f"None of the places found is marked as having {_n[2]} in the data: ask the venue itself.",
    )
    ATTR_STRINGS[f"fit_diet_{_d}"] = (
        f"деректерде «{_f[0]}» деп белгіленген",
        f"в данных отмечено: {_f[1]}",
        f"marked in the data: {_f[2]}",
    )
ATTR_STRINGS["note_gluten_medical"] = (
    "Целиакия немесе аллергия кезінде құрамын қызметкерден сұраңыз: деректер глютенсіздікті растамайды.",
    "При целиакии или аллергии уточняйте состав у персонала: данные не подтверждают отсутствие глютена.",
    "With coeliac disease or an allergy, ask the staff about the ingredients: the data do not confirm gluten-free food.",
)
ATTR_STRINGS["note_night_unknown"] = (
    "Түнде жұмыс уақыты белгісіз орын жабық болуы мүмкін: бармас бұрын нақтылаңыз.",
    "Ночью место с неизвестными часами может быть закрыто: уточните перед выходом.",
    "At night a place with unknown hours may well be closed: check before you go.",
)
ATTR_STRINGS["note_unsupported"] = (
    "Бұл туралы деректер жоқ: «{what}».",
    "В записях нет данных об этом: «{what}».",
    "The records have no data on this: “{what}”.",
)
ATTR_STRINGS["note_pets"] = (
    "Үй жануарларымен келуге болатыны деректерде көрсетілмеген.",
    "Можно ли с животными, в данных не указано.",
    "Whether pets are allowed is not stated in the data.",
)
ATTR_STRINGS["note_group"] = (
    "Үлкен топқа арналған орын мен үстел деректерде көрсетілмеген: алдын ала хабарласыңыз.",
    "Вместимость и места для большой компании в данных не указаны: уточните заранее.",
    "Room for a large group is not stated in the data: ask ahead.",
)
ATTR_STRINGS["note_price_cap"] = (
    "Бағалар деректерде жоқ: {cap} теңгеге сыяр-сыймасын ескере алмаймыз, қызметкерден сұраңыз.",
    "Цен в данных нет: уложитесь ли вы в {cap} тг, мы проверить не можем, уточните в заведении.",
    "The data have no prices: we cannot tell whether {cap} tenge is enough, ask the venue.",
)
ATTR_STRINGS["note_cheaper"] = (
    "Бағалар деректерде көрсетілмеген: арзанырақтарды түрі бойынша (жылдам тамақ, кафе) ғана іріктедік.",
    "Цены в данных не указаны: подешевле мы подбирали только по типу заведения (фастфуд, кафе).",
    "Prices are not stated in the data: we chose the cheaper ones by kind of place only (fast food, cafe).",
)
ATTR_STRINGS["fit_info"] = (
    "сіз осы орын туралы сұрадыңыз",
    "вы спрашивали именно про это место",
    "you asked about this very place",
)
ATTR_STRINGS["fact_closed_now"] = (
    "OSM сағаттары бойынша осы уақытта жабық.",
    "По часам OSM в это время закрыто.",
    "Closed at this time according to the OSM hours.",
)
ATTR_STRINGS["note_view"] = (
    "Шолу алаңы мен көтерілу мүмкіндігі деректерде көрсетілмеген.",
    "Смотровая площадка и подъём в данных не указаны.",
    "A viewing platform or a way up is not stated in the data.",
)
ATTR_STRINGS["note_minor"] = (
    "Барлар алынып тасталды: сұраныста кәмелетке толмағандар аталған.",
    "Бары исключены: в запросе упоминаются несовершеннолетние.",
    "Bars are excluded: the request mentions minors.",
)
ATTR_STRINGS["fit_pets"] = (
    "деректерде үй жануарларына рұқсат белгіленген",
    "в данных отмечено, что можно с животными",
    "marked in the data as allowing pets",
)
