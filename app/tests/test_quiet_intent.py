"""A quiet request in ru / kk / en: the quiet words are read in every language, a negation switches them off, and a
generic word of the night («open late», «допоздна», «кешке дейін») never adds a bar or entertainment to a quiet request;
only a named bar keeps it. Rule parser and the offline pipeline on the real data/poi.json."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.intent import parse_rules
from walks.models import DEFAULT_POI_PATH, Intent, load_pois
from walks.pipeline import recommend

NAZARBAYEV_UNIVERSITY = (51.0906, 71.3985)
TUESDAY_20 = datetime(2026, 10, 13, 20, 0)
LOUD = {"bar_nightlife", "entertainment"}


def rules(text: str) -> Intent:
    return parse_rules(text).intent


@pytest.mark.parametrize(
    "text",
    [
        "quiet place to read",
        "a calm cafe",
        "somewhere peaceful",
        "silent place",
        "tranquility please",
        "need to study for exams",
        "a place to study",
        "somewhere to concentrate",
        "a place with no noise",
        "not noisy cafe",
        "тихое место",
        "спокойное место почитать",
        "место чтобы позаниматься",
        "подготовиться к экзамену",
        "тыныш жер",
        "сабырлы кафе",
        "оқуға жер",
        "кітап оқуға тыныш жер",
        "емтиханға дайындалатын жер",
    ],
)
def test_quiet_is_read_in_every_language(text):
    assert rules(text).quiet


@pytest.mark.parametrize(
    "text",
    [
        "not quiet, somewhere lively",
        "not a quiet place",
        "no quiet please",
        "I don't want a quiet place",
        "don't want quiet",
        "work on a laptop",
        "не тихое место",
        "не хочу тихо",
        "не нужна тишина",
        "тыныш емес",
        "open late",
        "допоздна",
        "кешке дейін ашық",
    ],
)
def test_no_quiet_without_a_quiet_word(text):
    assert not rules(text).quiet


@pytest.mark.parametrize(
    "text",
    [
        "quiet place to read, open late",
        "calm place to study, open till late",
        "peaceful, open late at night",
        "a quiet spot, open all night",
        "тихое место почитать, открыто допоздна",
        "спокойное место, работает поздно",
        "тихо, ночью",
        "тыныш жер, түнде ашық",
        "кітап оқуға тыныш жер, түнгі",
        "сабырлы жер, түнгі",
    ],
)
def test_a_generic_late_word_adds_no_bar_to_a_quiet_request(text):
    i = rules(text)
    assert i.quiet
    assert i.night  # the late hours still count
    assert not LOUD & set(i.categories)


@pytest.mark.parametrize(
    "text",
    [
        "quiet pub, open late",
        "a quiet bar open late",
        "want a drink somewhere quiet, open late",
        "тихий бар допоздна",
        "хочу выпить в тишине допоздна",
    ],
)
def test_a_named_bar_stays_in_a_quiet_request(text):
    i = rules(text)
    assert i.quiet
    assert "bar_nightlife" in i.categories


@pytest.mark.parametrize(
    "text", ["quiet bowling alley", "тихий боулинг", "quiet place with board games, open late"]
)
def test_named_entertainment_stays_in_a_quiet_request(text):
    assert "entertainment" in rules(text).categories


@pytest.mark.parametrize("text", ["open late", "допоздна", "late night spot", "что-нибудь ночью"])
def test_a_not_quiet_request_keeps_the_night_places(text):
    i = rules(text)
    assert not i.quiet
    assert "bar_nightlife" in i.categories
    assert "entertainment" in i.categories


@pytest.fixture(scope="module")
def pois():
    return load_pois(DEFAULT_POI_PATH)


@pytest.mark.parametrize(
    "text",
    [
        "quiet place to read, open late",
        "тихое место почитать, открыто допоздна",
        "оқуға тыныш жер, кешке дейін ашық",
    ],
)
def test_no_bar_is_recommended_for_a_quiet_reading_request(pois, text):
    lat, lon = NAZARBAYEV_UNIVERSITY
    res = recommend(text, lat, lon, TUESDAY_20, use_llm=False, pois=pois)
    assert res.intent.intent.quiet
    assert res.recs
    assert not LOUD & {r.poi.category for r in res.recs}
    assert not LOUD & {c.poi.category for c in res.retrieval.candidates}
