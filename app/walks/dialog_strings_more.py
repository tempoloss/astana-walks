"""Dialogue strings of the questions about a shown place (sockets, a kids' room), the «if it is not cold» condition and
the weather compared with now, in Kazakh, Russian, English; merged into walks.dialog_strings.STRINGS."""

from __future__ import annotations

Entry = tuple[str, str, str]

MORE_STRINGS: dict[str, Entry] = {}

# ---- sockets, a kids' room, and the «if it is not cold» condition
MORE_STRINGS.update(
    {
        "w_socket": ("розеткалар", "розетки", "power sockets"),
        "w_kids_room": ("балалар бөлмесі", "детская комната", "a kids' room"),
        "a_socket_yes": (
            "{name}: иә, розеткалар бар ({by}).",
            "«{name}»: да, розетки есть ({by}).",
            "{name}: yes, there are sockets ({by}).",
        ),
        "a_wifi_yes": (
            "Wi-Fi бар ({by}).",
            "Wi-Fi есть ({by}).",
            "There is Wi-Fi ({by}).",
        ),
        "a_kids_yes": (
            "{name}: иә, балаларға арналған орын бар ({by}).",
            "«{name}»: да, есть место для детей ({by}).",
            "{name}: yes, there is a place for kids ({by}).",
        ),
        "cond_at": (
            "болжам бойынша {t} — ",
            "по прогнозу {t} — ",
            "forecast {t} — ",
        ),
        "cond_now": ("қазір {t} — ", "сейчас {t} — ", "it is {t} right now — "),
        "cond_cold": (
            "суық, сондықтан далада емес, үйдегі орындарды ұсынамын.",
            "холодно, поэтому вместо улицы предлагаю места в помещении.",
            "cold, so I suggest indoor places instead of the street.",
        ),
        "cond_warm": (
            "суық емес, далада да болады.",
            "не холодно, можно и на улице.",
            "not cold, so outdoors is fine.",
        ),
        "cond_unknown": (
            "Қазір температура туралы деректер жоқ, сондықтан суық па, жоқ па — айта алмаймын; сұраған орыныңызды ұсынамын.",
            "Температуры сейчас в данных нет, так что холодно или нет — сказать не могу; предлагаю то, что вы просили.",
            "The data has no temperature right now, so I cannot say whether it is cold; here is what you asked for.",
        ),
        "indoors": ("жылы жер", "в помещении", "indoors"),
    }
)


# ---- the weather against the present, a day's conditions
MORE_STRINGS.update(
    {
        "wx_cmp_warmer": (
            "Қазіргіден {d} °C жылырақ (қазір {a}).",
            "Теплее, чем сейчас, на {d} °C (сейчас {a}).",
            "Warmer than now by {d} °C (now {a}).",
        ),
        "wx_cmp_colder": (
            "Қазіргіден {d} °C суығырақ (қазір {a}).",
            "Холоднее, чем сейчас, на {d} °C (сейчас {a}).",
            "Colder than now by {d} °C (now {a}).",
        ),
        "wx_cmp_same": (
            "Қазіргідей шамасында (қазір {a}).",
            "Примерно так же, как сейчас ({a}).",
            "About the same as now ({a}).",
        ),
        "wx_cmp_unknown": (
            "Қазіргі температура деректерде жоқ, салыстыра алмаймын.",
            "Температуры сейчас в данных нет, сравнить не с чем.",
            "The data has no temperature for now, so there is nothing to compare with.",
        ),
    }
)

# ---- what an answer lacks, said before it (walks.dialog_lead.honest_gaps)
MORE_STRINGS.update(
    {
        "kids_none_entertainment": (
            "Жақын жерде балалар ойын орталығы деректерде жоқ.",
            "Детских игровых центров рядом в данных нет.",
            "The data has no kids' play centre nearby.",
        ),
        "kids_none_museum_gallery": (
            "Жақын жерде балалар мұражайы деректерде жоқ.",
            "Детских музеев рядом в данных нет.",
            "The data has no children's museum nearby.",
        ),
        "kids_none_indoor": (
            "Жақын жерде жабық ойын орындары деректерде жоқ — балаларға қолайлы ең жақын нұсқаларды көрсетемін.",
            "Крытых игровых мест рядом в данных нет — показываю, что подходит для детей из имеющегося.",
            "The data has no indoor play place nearby — here is what else suits children.",
        ),
        "sub_far_kids_doctor": (
            "Жақын жерде балалар емханасы деректерде жоқ, ең жақыны — «{name}», {walk}.",
            "Детских поликлиник рядом в данных нет — ближайшая: «{name}», {walk}.",
            "The data has no children's clinic nearby — the nearest is {name}, {walk}.",
        ),
        "sub_none_kids_doctor": (
            "Біздің деректерде балалар емханалары жоқ.",
            "Детских поликлиник в наших данных нет.",
            "Our data has no children's clinics.",
        ),
        "ld_errand_kids_doctor": (
            "Ең жақын балалар емханасы",
            "Ближайшая детская поликлиника",
            "The nearest children's clinic",
        ),
        "ld_errand_open_kids_doctor": (
            "Ең жақын ашық балалар емханасы",
            "Ближайшая открытая детская поликлиника",
            "The nearest open children's clinic",
        ),
        "local_food_none": (
            "Жақын жердегі орындардың деректерінде қазақ асханасы аталмаған.",
            "У мест рядом казахская кухня в данных не указана.",
            "None of the places nearby is marked as Kazakh food in the data.",
        ),
        "known_hours_closed": (  # one clause after the answer, never its opening
            "(жақын жердегі тағы {n} орын қазір жабық)",
            "(ещё {n} {places} рядом сейчас {closed})",
            "({n} more {places} nearby {closed} closed now)",
        ),
        "note_far_view": (
            "Жаяу {n} мин — алыс, көлікпен барған дұрыс.",
            "Пешком {n} мин — далеко, лучше на транспорте.",
            "{n} min on foot — far, better take a vehicle.",
        ),
        "note_near_sight": (
            "Жақынырақ — жақын жердегі көрікті орын.",
            "Ближе — что посмотреть рядом.",
            "Nearer: something to see close by.",
        ),
        "ld_dark_later": (
            "ол кезде қараңғы болады",
            "к этому времени стемнеет",
            "it will be dark by then",
        ),
    }
)

# ---- an errand none of which is in the data nearby: said as the data's absence, and nothing is offered instead
MORE_STRINGS.update(
    {
        "none_pharmacy": (
            "Біздің деректерде жақын жерде дәріхана жоқ (OpenStreetMap-та белгіленгендері ғана) — оның орнына "
            "басқа орын ұсынбаймын.",
            "В наших данных аптек рядом нет (только отмеченные в OpenStreetMap) — другое место вместо аптеки не "
            "предлагаю.",
            "Our data has no pharmacies nearby (only those mapped in OpenStreetMap), so I am not offering another "
            "place instead.",
        ),
        "none_grocery": (
            "Біздің деректерде жақын жерде азық-түлік дүкені жоқ (OpenStreetMap-та белгіленгендері ғана) — сауда "
            "орталығы мен кафені оның орнына ұсынбаймын.",
            "В наших данных продуктовых магазинов рядом нет (только отмеченные в OpenStreetMap) — торговый центр или "
            "кафе вместо них не предлагаю.",
            "Our data has no grocery shops nearby (only those mapped in OpenStreetMap), so I am not offering a mall or "
            "a café instead.",
        ),
        "none_money": (
            "Біздің деректерде жақын жерде банкомат пен банк жоқ (OpenStreetMap-та белгіленгендері ғана) — олардың "
            "орнына басқа орын ұсынбаймын.",
            "В наших данных банкоматов и банков рядом нет (только отмеченные в OpenStreetMap) — другое место вместо "
            "них не предлагаю.",
            "Our data has no ATMs or banks nearby (only those mapped in OpenStreetMap), so I am not offering another "
            "place instead.",
        ),
        "none_lodging": (
            "Біздің деректерде жақын жерде қонақүй мен хостел жоқ.",
            "В наших данных гостиниц и хостелов рядом нет.",
            "Our data has no hotels or hostels nearby.",
        ),
        "none_clinic": (
            "Біздің деректерде жақын жерде клиника мен тіс емханасы жоқ (OpenStreetMap-та белгіленгендері ғана) — "
            "олардың орнына басқа орын ұсынбаймын.",
            "В наших данных клиник и стоматологий рядом нет (только отмеченные в OpenStreetMap) — другое место "
            "вместо них не предлагаю.",
            "Our data has no clinics or dentists nearby (only those mapped in OpenStreetMap), so I am not offering "
            "another place instead.",
        ),
        "none_post": (
            "Біздің деректерде жақын жерде пошта бөлімшесі жоқ (OpenStreetMap-та белгіленгендері ғана) — оның "
            "орнына басқа орын ұсынбаймын.",
            "В наших данных почтовых отделений рядом нет (только отмеченные в OpenStreetMap) — другое место вместо "
            "них не предлагаю.",
            "Our data has no post offices nearby (only those mapped in OpenStreetMap), so I am not offering another "
            "place instead.",
        ),
    }
)

# An overnight close said as a person says it (walks.status): «до полуночи», «до 05:00 утра».
MORE_STRINGS.update(
    {
        "h_midnight": ("түн ортасына", "полуночи", "midnight"),
        "h_next_morning": ("таңғы {t}-ге", "{t} утра", "{t} am"),
        "ld_errand_pick": (
            "{what} — «{name}», {walk}{tail}",
            "{what} — «{name}», {walk}{tail}",
            "{what} is {name}, {walk}{tail}",
        ),
        "ld_errand_pharmacy": ("Ең жақын дәріхана", "Ближайшая аптека", "The nearest pharmacy"),
        "ld_errand_open_pharmacy": (
            "Ең жақын ашық дәріхана",
            "Ближайшая открытая аптека",
            "The nearest open pharmacy",
        ),
        "ld_errand_grocery": (
            "Ең жақын азық-түлік дүкені",
            "Ближайший продуктовый магазин",
            "The nearest grocery shop",
        ),
        "ld_errand_open_grocery": (
            "Ең жақын ашық азық-түлік дүкені",
            "Ближайший открытый продуктовый магазин",
            "The nearest open grocery shop",
        ),
        "ld_errand_money": ("Ең жақын банк", "Ближайший банк", "The nearest bank"),
        "ld_errand_open_money": (
            "Ең жақын ашық банк",
            "Ближайший открытый банк",
            "The nearest open bank",
        ),
        "ld_errand_atm": ("Ең жақын банкомат", "Ближайший банкомат", "The nearest ATM"),
        "ld_errand_open_atm": (
            "Ең жақын жұмыс істеп тұрған банкомат",
            "Ближайший работающий банкомат",
            "The nearest working ATM",
        ),
        "ld_errand_lodging": (
            "Ең жақын қонақ үй",
            "Ближайшая гостиница",
            "The nearest place to stay",
        ),
        "ld_errand_open_lodging": (
            "Ең жақын ашық қонақ үй",
            "Ближайшая открытая гостиница",
            "The nearest open place to stay",
        ),
        "ld_errand_public_toilet": ("Ең жақын дәретхана", "Ближайший туалет", "The nearest toilet"),
        "ld_errand_open_public_toilet": (
            "Ең жақын ашық дәретхана",
            "Ближайший открытый туалет",
            "The nearest open toilet",
        ),
        "ld_errand_clinic": ("Ең жақын клиника", "Ближайшая клиника", "The nearest clinic"),
        "ld_errand_open_clinic": (
            "Ең жақын ашық клиника",
            "Ближайшая открытая клиника",
            "The nearest open clinic",
        ),
        "ld_errand_post": (
            "Ең жақын пошта бөлімшесі",
            "Ближайшее почтовое отделение",
            "The nearest post office",
        ),
        "ld_errand_open_post": (
            "Ең жақын ашық пошта бөлімшесі",
            "Ближайшее открытое почтовое отделение",
            "The nearest open post office",
        ),
        "ld_errand_dentist": (
            "Ең жақын тіс емханасы",
            "Ближайшая стоматология",
            "The nearest dentist",
        ),
        "ld_errand_open_dentist": (
            "Ең жақын ашық тіс емханасы",
            "Ближайшая открытая стоматология",
            "The nearest open dentist",
        ),
    }
)

# ---- a kind inside a category that the first card is not (walks.dialog_facts.subkind_gap): the nearest one, in one
# sentence; the first card follows as the nearest of the rest (`ld_errand_rest_*`, walks.dialog_lead.errand_pick)
MORE_STRINGS.update(
    {
        "sub_far_dentist": (
            "Жақын жерде тіс емханасы деректерде жоқ, ең жақыны — «{name}», {walk}.",
            "Стоматологий рядом в данных нет — ближайшая: «{name}», {walk}.",
            "The data has no dentist nearby — the nearest is {name}, {walk}.",
        ),
        "sub_none_dentist": (
            "Біздің деректерде тіс емханалары жоқ.",
            "Стоматологий в наших данных нет.",
            "Our data has no dentists.",
        ),
        "sub_far_atm": (
            "Жақын жерде банкомат деректерде жоқ, ең жақыны — «{name}», {walk}.",
            "Банкоматов рядом в данных нет — ближайший: «{name}», {walk}.",
            "The data has no cash machine nearby — the nearest is {name}, {walk}.",
        ),
        "sub_none_atm": (
            "Біздің деректерде банкоматтар жоқ.",
            "Банкоматов в наших данных нет.",
            "Our data has no cash machines.",
        ),
        "ld_errand_rest_dentist": (
            "Басқа клиникалардан ең жақыны",
            "Из других клиник ближе всего",
            "Of the other clinics, the nearest",
        ),
        "ld_errand_rest_kids_doctor": (
            "Басқа клиникалардан ең жақыны",
            "Из других клиник ближе всего",
            "Of the other clinics, the nearest",
        ),
        "ld_errand_rest_atm": (
            "Банк бөлімшелерінен ең жақыны",
            "Из отделений банков ближе всего",
            "Of the bank branches, the nearest",
        ),
        # from walks.wishes.FAR_WALK_MIN on foot: the distance and the transport, never the minutes
        "walk_far": (
            "жаяу алыс: {d} — көлікпен барған дұрыс",
            "пешком далеко: {d} — лучше на транспорте",
            "too far to walk: {d} — better take transport",
        ),
    }
)


# ---- a cash machine, changing currency, «круглосуточно» asked of a shown place
MORE_STRINGS.update(
    {
        "w_atm": ("банкомат", "банкомат", "a cash machine"),
        "w_exchange": ("валюта айырбастау", "обмен валюты", "currency exchange"),
        "a_atm_yes": (
            "{name}: иә, бұл банкомат ({by}).",
            "«{name}»: да, это банкомат ({by}).",
            "{name}: yes, this is a cash machine ({by}).",
        ),
        "a_atm_unknown": (
            "{name}: банкомат бар-жоғы деректерде жоқ — бөлімшеде нақтылаңыз.",
            "«{name}»: есть ли банкомат, в данных этого нет — уточните в отделении.",
            "{name}: the data does not say whether there is a cash machine — ask at the branch.",
        ),
        "a_exchange_yes": (
            "{name}: иә, валюта айырбастау бар ({by}).",
            "«{name}»: да, обмен валюты есть ({by}).",
            "{name}: yes, currency exchange is offered ({by}).",
        ),
        "a_exchange_currency": (
            "{name}: деректер бойынша {cur} айырбасталады ({by}).",
            "«{name}»: по данным меняют {cur} ({by}).",
            "{name}: per the data it changes {cur} ({by}).",
        ),
        "a_exchange_unknown": (
            "{name}: валюта айырбастау туралы деректерде ештеңе жоқ — бөлімшеде нақтылаңыз.",
            "«{name}»: обмен валюты — в данных этого нет, уточните в отделении.",
            "{name}: the data has nothing on currency exchange — ask at the branch.",
        ),
        "a_round_yes": (
            "{name}: иә, тәулік бойы ашық ({src}).",
            "«{name}»: да, открыто круглосуточно ({src}).",
            "{name}: yes, open around the clock ({src}).",
        ),
        "a_round_no": (
            "{name}: жоқ, тәулік бойы емес; {iv} ({src}).",
            "«{name}»: нет, не круглосуточно; {iv} ({src}).",
            "{name}: no, not around the clock; {iv} ({src}).",
        ),
    }
)


# ---- a kind of place the data cannot represent: said, then the closest kind; the scope of the assistant
MORE_STRINGS.update(
    {
        "unmapped_gaming": (
            "Ойын клубтары (PS, компьютер клубтары) деректерімізде жоқ. Мағынасы ең жақынын көрсетемін.",
            "Игровых клубов (PS, компьютерных) в наших данных рядом нет. Показываю ближайшее по смыслу.",
            "The data has no PS or computer gaming clubs near. Here is the closest in spirit.",
        ),
        "unmapped_hookah": (
            "Қалянханалар деректерімізде бөлек белгіленбеген. Мағынасы ең жақынын көрсетемін.",
            "Кальянные в наших данных отдельно не отмечены. Показываю ближайшее по смыслу.",
            "Hookah lounges are not marked apart in our data. Here is the closest in spirit.",
        ),
        "unmapped_sauna": (
            "Сауналар мен моншалар деректерімізде жоқ. Мағынасы ең жақынын көрсетемін.",
            "Саун и бань в наших данных рядом нет. Показываю ближайшее по смыслу.",
            "The data has no saunas or bathhouses near. Here is the closest in spirit.",
        ),
        "unmapped_karaoke": (
            "Караоке деректерімізде бөлек белгіленбеген. Мағынасы ең жақынын көрсетемін.",
            "Караоке в наших данных отдельно не отмечено. Показываю ближайшее по смыслу.",
            "Karaoke is not marked apart in our data. Here is the closest in spirit.",
        ),
        "unmapped_billiards": (
            "Бильярд залдары деректерімізде жоқ. Мағынасы ең жақынын көрсетемін.",
            "Бильярдных в наших данных рядом нет. Показываю ближайшее по смыслу.",
            "The data has no billiard halls near. Here is the closest in spirit.",
        ),
        "unmapped_bowling": (
            "Боулинг деректерімізде жоқ. Мағынасы ең жақынын көрсетемін.",
            "Боулинга в наших данных рядом нет. Показываю ближайшее по смыслу.",
            "The data has no bowling near. Here is the closest in spirit.",
        ),
        "unmapped_quest": (
            "Квесттер деректерімізде жоқ. Мағынасы ең жақынын көрсетемін.",
            "Квестов в наших данных рядом нет. Показываю ближайшее по смыслу.",
            "The data has no quest rooms near. Here is the closest in spirit.",
        ),
        "unmapped_massage": (
            "Массаж бен спа деректерімізде жоқ. Мағынасы ең жақынын көрсетемін.",
            "Массажа и спа в наших данных рядом нет. Показываю ближайшее по смыслу.",
            "The data has no massage or spa near. Here is the closest in spirit.",
        ),
        "unmapped_sports_screen": (
            "Матч көрсететін орындар деректерімізде белгіленбеген. Мағынасы ең жақынын көрсетемін.",
            "Мест с трансляциями матчей в наших данных не отмечено. Показываю ближайшее по смыслу — бары.",
            "Places that show matches are not marked in our data. Here is the closest in spirit: bars.",
        ),
        "emergency_103": (
            "Өмірге қауіп төнсе, 103 нөміріне қоңырау шалыңыз. Емханалар мен стоматологиялар бойынша көмектесе аламын.",
            "При угрозе жизни звоните 103. Клиники и поликлиники рядом подскажу.",
            "In a life-threatening emergency call 103. I can show clinics and polyclinics nearby.",
        ),
        "scope_line": (
            "Мен Астанадағы орындарды ұсынамын: қайда тамақтануға, серуендеуге, нені көруге болады, жақын жердегі дәріхана мен банкомат. Не іздейміз?",
            "Я подсказываю места в Астане: где поесть, погулять, что посмотреть, аптеки и банкоматы рядом. Что поищем?",
            "I suggest places in Astana: where to eat, walk, what to see, pharmacies and cash machines nearby. What shall we look for?",
        ),
        "refused_part": (
            "Жыныстық қызмет сұрауына көмектеспеймін.",
            "С запросом на секс-услуги не помогу.",
            "I will not help with a request for sexual services.",
        ),
        "toward_on": (
            "«{name}» бағытына қарай жолда іздеймін.",
            "Ищу по пути в сторону «{name}».",
            "Looking along the way toward “{name}”.",
        ),
        "toward_missing": (
            "«{name}» дегенді таппадым — сізге жақын жерден іздеймін.",
            "«{name}» не нашёл — ищу рядом с вами.",
            "I could not find “{name}” — searching near you.",
        ),
    }
)
