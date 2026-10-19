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
    }
)
