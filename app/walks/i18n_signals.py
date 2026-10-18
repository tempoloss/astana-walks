"""Wording of the one extra line of a card or a route (walks.dialog_extras): an open OpenStreetMap note about a place,
the nearest bus stop, the street lights along the way. An entry is a tuple (kk, ru, en); `ts` is this table's own
lookup. A note is a suspicion, never a fact: the lines say «may», not «is»."""

from __future__ import annotations

from .i18n import Entry, pick

SIGNAL_STRINGS: dict[str, Entry] = {
    "note_closure": (
        "OpenStreetMap-та ескертпе бар: орын жабылып қалуы мүмкін ({date})",
        "на OpenStreetMap есть заметка: место могло закрыться ({date})",
        "there is an OpenStreetMap note that the place may have closed ({date})",
    ),
    "note_hours": (
        "OpenStreetMap-та ескертпе бар: жұмыс уақыты өзгеруі мүмкін ({date})",
        "на OpenStreetMap есть заметка: часы работы могли измениться ({date})",
        "there is an OpenStreetMap note that the opening hours may have changed ({date})",
    ),
    "note_source": ("OpenStreetMap ескертпесі", "заметка OpenStreetMap", "OpenStreetMap note"),
    "stop_line": (
        "«{name}» аялдамасы — жаяу {n} мин",
        "Остановка «{name}» — {n} мин пешком",
        "Bus stop “{name}” — {n} min on foot",
    ),
    "stop_source": (
        "GTFS (Zenodo, CC BY 4.0)",
        "GTFS (Zenodo, CC BY 4.0)",
        "GTFS (Zenodo, CC BY 4.0)",
    ),
    "lit_most": (
        "жолдың көп бөлігі жарықтандырылған көшелермен өтеді — OpenStreetMap деректері бойынша",
        "большая часть пути по освещённым улицам — по данным OpenStreetMap",
        "most of the way is along lit streets — per OpenStreetMap",
    ),
}


def ts(key: str, lang: str | None, **fields: object) -> str:
    text = pick(SIGNAL_STRINGS[key], lang)
    return text.format(**fields) if fields else text
