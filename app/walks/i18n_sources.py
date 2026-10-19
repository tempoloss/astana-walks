"""Wording of where a fact comes from when it is not OSM's: the business's own website (collect/sites). The label of the
source, of the hours state, the website's hours that disagree with OSM or name no days, its description. An entry is a
tuple (kk, ru, en), the same as in walks.i18n.STRINGS, which merges this table."""

from __future__ import annotations

SOURCE_STRINGS: dict[str, tuple[str, str, str]] = {
    "src_official_site": ("ресми сайт", "официальный сайт", "official website"),
    # e-museum.kz, the ministry's museum register (facts a museum did not publish on its own site)
    "src_museum_register": (
        "мұражайлар реестрі e-museum.kz",
        "реестр музеев e-museum.kz",
        "e-museum.kz museum register",
    ),
    "note_hours_unqualified_register": (
        "Жұмыс уақыты деректерде белгісіз — мұражайлар реестрінде: {raw}, күндері көрсетілмеген; шықпас бұрын нақтылаңыз.",
        "Часы работы в данных неизвестны — в реестре музеев: {raw}, дни не указаны; уточните перед выходом.",
        "Opening hours are unknown in the data - in the museum register: {raw}, days not stated; check before you go.",
    ),
    "src_wikivoyage": ("Wikivoyage", "Wikivoyage", "Wikivoyage"),
    # the label of the hours state names the source of the hours
    "hours_state_open_osm": (
        "OSM деректері бойынша ашық",
        "открыто по данным OSM",
        "open according to OSM",
    ),
    "hours_state_open_site": (
        "ресми сайт деректері бойынша ашық",
        "открыто по данным официального сайта",
        "open according to the official website",
    ),
    "hours_state_open_register": (
        "мұражайлар реестрі бойынша ашық",
        "открыто по данным реестра музеев",
        "open according to the museum register",
    ),
    "hours_state_open_voyage": (
        "Wikivoyage деректерінше ашық",
        "открыто по данным путеводителя Wikivoyage",
        "open according to the Wikivoyage travel guide",
    ),
    "people_vs_voyage": (
        "бұл Wikivoyage сағаттарымен сәйкес келмейді, сенімділік төмендетілді",
        "это расходится с часами путеводителя Wikivoyage, уверенность снижена",
        "this disagrees with the Wikivoyage travel guide's hours, confidence lowered",
    ),
    "hours_state_closed": ("жабық", "закрыто", "closed"),
    "hours_state_unknown": ("жұмыс уақыты белгісіз", "часы неизвестны", "hours unknown"),
    "people_vs_site": (
        "бұл ресми сайттың сағаттарымен сәйкес келмейді, сенімділік төмендетілді",
        "это расходится с часами официального сайта, уверенность снижена",
        "this disagrees with the official website's hours, confidence lowered",
    ),
    "people_vs_register": (
        "бұл мұражайлар реестрінің сағаттарымен сәйкес келмейді, сенімділік төмендетілді",
        "это расходится с часами реестра музеев, уверенность снижена",
        "this disagrees with the museum register's hours, confidence lowered",
    ),
    # notes under a card
    "note_hours_conflict": (
        "Сағаттар OSM-де және сайтта сәйкес келмейді: OSM {osm}, сайт {site}.",
        "Часы в OSM и на сайте расходятся: OSM {osm}, сайт {site}.",
        "Hours in OSM and on the website differ: OSM {osm}, website {site}.",
    ),
    "note_hours_split_tail": (
        "Қазір олар әртүрлі жауап береді, сондықтан күйі белгісіз — шықпас бұрын нақтылаңыз.",
        "Сейчас они дают разный ответ, поэтому статус неизвестен — уточните перед выходом.",
        "Right now they give different answers, so the status is unknown - check before you go.",
    ),
    "note_hours_unqualified": (
        "Жұмыс уақыты деректерде белгісіз — сайтта: {raw}, күндері көрсетілмеген; шықпас бұрын нақтылаңыз.",
        "Часы работы в данных неизвестны — на сайте: {raw}, дни не указаны; уточните перед выходом.",
        "Opening hours are unknown in the data - on the website: {raw}, days not stated; check before you go.",
    ),
    "info_site": (
        "Ресми сайттағы сипаттама бойынша: {text}",
        "По описанию на официальном сайте: {text}",
        "From the official website: {text}",
    ),
    "info_voyage": (
        "Уикивойаж деректерінше (CC BY-SA 4.0): {text}",
        "по данным путеводителя Wikivoyage (CC BY-SA 4.0): {text}",
        "according to the Wikivoyage travel guide (CC BY-SA 4.0): {text}",
    ),
    "note_opens_by_arrival": (
        "Қазір жабық, бірақ сіз келгенде (шамамен {t}) ашылады.",
        "Сейчас закрыто, но к вашему приходу (около {t}) откроется.",
        "Closed right now, but it opens by the time you arrive (about {t}).",
    ),
    "note_closes_soon": (
        "{t} жабылады: орнында шамамен {n} мин боласыз.",
        "Скоро закроется, в {t}: на месте можно пробыть около {n} мин.",
        "It closes soon, at {t}: you can stay about {n} min.",
    ),
    "note_toilet": (
        "Дәретхана деректерде расталмаған.",
        "Туалет в данных не подтверждён.",
        "A toilet is not confirmed in the data.",
    ),
}
