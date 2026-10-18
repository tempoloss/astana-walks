"""Demo locations and the five scenarios from the case (shared by the UI and the tests)."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import time

from .i18n import norm

PRESETS: dict[str, tuple[float, float]] = {
    "EXPO": (51.0890, 71.4160),
    "Mega Silk Way": (51.0886, 71.4030),
    "Байтерек": (51.1283, 71.4305),
    "Хан Шатыр": (51.1325, 71.4033),
    "Аэропорт": (
        51.0280,
        71.4635,
    ),  # terminal T1 (OSM way 166500591); the old point was on the apron
}
# the same places in Kazakh and English (the Russian name is the key of PRESETS)
PRESET_NAMES: dict[str, dict[str, str]] = {
    "Байтерек": {"kk": "Бәйтерек", "en": "Baiterek"},
    "Хан Шатыр": {"kk": "Хан Шатыр", "en": "Khan Shatyr"},
    "Аэропорт": {"kk": "Әуежай", "en": "Airport"},
}


def preset_name(preset: str, lang: str | None) -> str:
    return PRESET_NAMES.get(preset, {}).get(norm(lang), preset)


@dataclass(frozen=True)
class Scenario:
    label: str  # Russian; the button text and the request are the same
    text: str
    preset: str  # key of PRESETS where the scenario starts
    at: time | None = None  # forced local time (to demo night); None = use the chosen/real time
    kk: str = ""  # the same request in Kazakh / English
    en: str = ""

    def text_in(self, lang: str | None) -> str:
        lang = norm(lang)
        return (self.kk if lang == "kk" else self.en if lang == "en" else self.text) or self.text

    def label_in(self, lang: str | None) -> str:
        return self.text_in(lang)

    def texts(self) -> tuple[str, ...]:
        return tuple(x for x in (self.kk, self.text, self.en) if x)

    def matches(self, text: str) -> bool:
        """Is `text` this scenario's request in any of the three languages?"""
        return text in self.texts()


SCENARIOS: list[Scenario] = [
    Scenario(
        "Рядом с Mega Silk Way, прогулка 30–60 мин",
        "Рядом с Mega Silk Way, прогулка 30–60 мин",
        "Mega Silk Way",
        kk="Mega Silk Way жанында 30–60 минут серуендеу",
        en="Near Mega Silk Way, a 30–60 min walk",
    ),
    Scenario(
        "Тихое место с кофе и розеткой",
        "Тихое место с кофе и розеткой",
        "Байтерек",
        kk="Кофесі мен розеткасы бар тыныш орын",
        en="A quiet place with coffee and a power socket",
    ),
    Scenario(
        "С ребёнком: площадка или интерактивный музей",
        "С ребёнком: площадка или интерактивный музей",
        "Хан Шатыр",
        kk="Баламмен: ойын алаңы немесе интерактивті музей",
        en="With a child: playground or an interactive museum",
    ),
    Scenario(
        "Турист, 2 часа до вылета",
        "Турист, 2 часа до вылета",
        "Аэропорт",
        kk="Турист, ұшуға дейін 2 сағат қалды",
        en="Tourist, 2 hours before the flight",
    ),
    Scenario(
        "Необычная ночная активность",
        "Необычная ночная активность",
        "Байтерек",
        time(23, 0),
        kk="Түнгі ерекше демалыс",
        en="Something unusual to do at night",
    ),
]

# The demo's requests beyond the five scenario buttons: (text, key of PRESETS). The recorded answers of
# scripts/warm_cache.py hold them too; the cold one is pinned at -25 °C by its own words (walks.demo_pin).
DEMO_REQUESTS: tuple[tuple[str, str], ...] = (
    ("Турист, 2 часа до вылета, на улице мороз", "Аэропорт"),
    ("Баламен қайда баруға болады?", "EXPO"),
)
