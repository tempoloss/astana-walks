"""Kazakh / Russian / English: the string tables, the template answers, the compromise labels (a08) and the UI."""

from __future__ import annotations

import re
import string
from datetime import datetime
from pathlib import Path

import pytest

from i18n import UI, places_count
from walks.i18n import CATEGORY, LANGS, STRINGS, TIP, holiday_name, t
from walks.intent import detect_language
from walks.models import DEFAULT_POI_PATH, load_pois
from walks.pipeline import recommend
from walks.presets import PRESETS, SCENARIOS
from walks.weather import manual_weather

APP_DIR = Path(__file__).resolve().parents[1]
CYRILLIC = re.compile(r"[А-Яа-яЁёӘәҒғҚқҢңӨөҰұҮүҺһІі]")
OFF_CATEGORY = {
    "ru": "Категория вне вашего запроса",
    "en": "Outside the requested categories",
    "kk": "Санат сұрауыңыздан тыс",
}


def _fields(text: str) -> set[str]:
    return {name for _, name, _, _ in string.Formatter().parse(text) if name}


@pytest.fixture(scope="module")
def pois():
    return load_pois(DEFAULT_POI_PATH)


@pytest.mark.parametrize("table", [STRINGS, UI], ids=["core", "ui"])
def test_every_text_exists_in_three_languages_with_the_same_fields(table):
    for key, entry in table.items():
        assert len(entry) == len(LANGS) == 3, key
        assert all(isinstance(x, str) and x.strip() for x in entry), key
        kk, ru, en = entry
        assert _fields(kk) == _fields(ru) == _fields(en), (
            f"{key}: {_fields(kk)} {_fields(ru)} {_fields(en)}"
        )


# words that are spelled the same in Kazakh: «радиус», «диалог», «файл», «Астана», units
SAME_IN_KAZAKH = {
    "mem_dialogue",
    "dp_lrt",
}


def test_kazakh_and_english_are_translations_not_copies():
    same = {"people_item"}
    for table in (STRINGS, UI):
        for key, (kk, ru, en) in table.items():
            if key in same or not CYRILLIC.search(ru):
                continue
            assert not CYRILLIC.search(en) or key in {"footer", "title"}, (
                f"{key} (en) still has Cyrillic: {en}"
            )
            if len(ru) > 12 and key not in SAME_IN_KAZAKH:
                assert kk != ru, f"{key} (kk) is the Russian text"
    for cat in CATEGORY:
        assert all(CATEGORY[cat])
        assert all(TIP[cat])


def test_the_selector_lists_kazakh_first():
    assert LANGS[0] == "kk"
    assert places_count(1, "ru") == "1 место"
    assert places_count(3, "ru") == "3 места"
    assert places_count(5, "ru") == "5 мест"
    assert places_count(3, "en") == "3 places"
    assert places_count(3, "kk") == "3 орын"


def test_holidays_are_named_in_every_language():
    assert holiday_name("День Победы (перенос)", "ru") == "День Победы (перенос)"
    assert holiday_name("День Победы", "kk") == "Жеңіс күні"
    assert holiday_name("День Победы (перенос)", "en").startswith("Victory Day")
    assert t("note_holiday", "kk", name="Жеңіс күні").startswith("Мемлекеттік мереке")


def test_scenarios_in_three_languages_mean_the_same_request(pois):
    base = {}
    for sc in SCENARIOS:
        seen = {}
        for lang in ("ru", "kk", "en"):
            res = recommend(
                sc.text_in(lang),
                *PRESETS[sc.preset],
                datetime(2026, 10, 19, 14, 0),
                use_llm=False,
                pois=pois,
                weather=manual_weather(10.0, pm25=5.0),
            )
            i = res.intent.intent
            assert i.language == lang, (sc.label, lang)
            seen[lang] = (
                tuple(sorted(i.categories)),
                i.time_budget_min,
                i.night,
                i.quiet,
                i.with_kids,
                i.needs_wifi_socket,
            )
        base[sc.label] = seen
        assert seen["kk"] == seen["ru"] == seen["en"], (sc.label, seen)
    assert len(base) == 5


@pytest.mark.parametrize("lang", ["kk", "ru", "en"])
def test_template_answer_is_fully_in_the_chosen_language(pois, lang):
    """ТЗ scenario 4 offline: the card text carries nothing of the other two languages (names and addresses are data)."""
    sc = SCENARIOS[3]
    res = recommend(
        sc.text_in("ru"),  # the request stays Russian: the chosen language is what counts
        *PRESETS[sc.preset],
        datetime(2026, 10, 19, 14, 0),
        use_llm=False,
        pois=pois,
        weather=manual_weather(10.0, pm25=5.0),
        language=lang,
    )
    assert res.intent.intent.language == lang
    assert res.recs
    for r in res.recs:
        assert r.text_source == "template"
        assert len(re.split(r"(?<=[.!?])\s+", r.why)) <= 2
        if lang == "en":
            assert not CYRILLIC.search(r.why + r.notes), (r.why, r.notes)
        if lang == "kk":
            for ru_text in (
                "Подходит под запрос",
                "Часы работы",
                "категория",
                "Fits your request",
                "Opening hours",
            ):
                assert ru_text not in r.why + r.what_to_do + r.notes
    assert res.retrieval.filters.radius_text(lang)


def test_the_language_replaces_the_one_read_from_the_text_in_a_dialogue(pois):
    kwargs = {"use_llm": False, "pois": pois, "weather": manual_weather(10.0, pm25=5.0)}
    first = recommend("Кафе", *PRESETS["EXPO"], datetime(2026, 10, 19, 14, 0), **kwargs)
    assert first.intent.intent.language == "ru"
    from walks.followup import conversation_after

    conv = conversation_after(None, first)
    again = recommend(
        "жақынырақ",
        *PRESETS["EXPO"],
        datetime(2026, 10, 19, 14, 0),
        conversation=conv,
        language="kk",
        **kwargs,
    )
    assert again.continued
    assert again.intent.intent.language == "kk"
    assert again.follow_up_note.startswith("Алдыңғы сұранысты нақтылау")


def _frost(pois, lang):
    """Abstain case a08: a playground wanted at −28 °C; indoor places come in because of the weather."""
    return recommend(
        "Прогулка с ребёнком, площадка",
        51.1197,
        71.4601,
        datetime(2026, 10, 21, 14, 0),
        use_llm=False,
        pois=pois,
        weather=manual_weather(-28.0),
        language=lang,
    )


@pytest.mark.parametrize("lang", ["kk", "ru", "en"])
def test_a08_every_off_category_card_says_so_in_its_language(pois, lang):
    res = _frost(pois, lang)
    requested = res.retrieval.filters.categories_requested
    assert requested == ["kids_playground"]
    off = [r for r in res.recs if r.poi.category not in requested]
    assert off, "the frost case must offer indoor places of another category"
    for r in off:
        assert OFF_CATEGORY[lang] in r.notes, (r.poi.name, r.notes)
        assert not r.why.startswith(t("fit_head", lang)), r.why  # not «подходит под запрос»


@pytest.mark.parametrize(
    ("text", "lang"),
    [
        (
            "Кофе и розетка, поработать",
            "ru",
        ),  # «розетка» is spelled alike in ru and kk: not a sign of Kazakh
        ("Тихое место с кофе и розеткой", "ru"),
        ("Кофесі мен розеткасы бар тыныш орын", "kk"),
        ("A quiet cafe with a power socket", "en"),
    ],
)
def test_a_russian_word_that_kazakh_shares_does_not_make_the_request_kazakh(text, lang):
    assert detect_language(text) == lang


# ------------------------------------------------------------------ private model names never reach the screen

PRIVATE_NAMES = ("vendor/secret-model", "SECRETGW", "openai:", ":31b")


def test_public_text_hides_every_non_google_link_in_three_languages():
    from walks.i18n import PRIVATE_LINK, public_text

    raw = (
        "gemini:gemini-3.5-flash: 503 (1.2 с) → openai:vendor/secret-model@SECRETGW: ok (3.1 с) → "
        "openai:other-model: timeout → openai:vendor-model:31b@SECRETGW: ok (0.9 с)"
    )
    for i, lang in enumerate(LANGS):
        out = public_text(raw, lang)
        assert "gemini:gemini-3.5-flash: 503" in out  # Google's links stay
        assert PRIVATE_LINK[i] in out
        assert out.count(PRIVATE_LINK[i]) == 3
        for name in PRIVATE_NAMES:
            assert name not in out
    assert public_text(None) == ""
    assert (
        public_text("ошибка ИИ: timeout, 10:30 на http://x")
        == "ошибка ИИ: timeout, 10:30 на http://x"
    )


def test_the_redacted_label_matches_the_one_of_the_eval():
    from eval.redact import PRIVATE_LINK as EVAL_LABEL
    from walks.i18n import PRIVATE_LINK

    assert PRIVATE_LINK[1] == EVAL_LABEL


def test_the_data_panel_never_shows_a_private_profile_or_model_name(pois):
    """The data panel (parse / generation chains, notes) of a request answered through a private profile: real
    names appear nowhere in what the web page is given."""
    import json

    from walks.models import LLMAttempt, LLMStep
    from web.explain import explain

    res = recommend(
        "кафе", *PRESETS["EXPO"], datetime(2026, 10, 19, 14, 0), use_llm=False, pois=pois
    )
    step = LLMStep(
        chain=["openai:vendor/secret-model@SECRETGW", "gemini:gemma-4-26b-a4b-it"],
        model="openai:vendor/secret-model@SECRETGW",
        attempts=[
            LLMAttempt(model="gemini:gemma-4-26b-a4b-it", status="error", detail="503", ms=900),
            LLMAttempt(model="openai:vendor/secret-model@SECRETGW", status="ok", ms=2100),
        ],
        ms=3000,
    )
    res = res.model_copy(
        update={
            "generation": "llm",
            "model": "openai:vendor/secret-model@SECRETGW",
            "generation_step": step,
            "generation_note": "ошибка ИИ: openai:vendor/secret-model@SECRETGW 429",
        }
    )
    for lang in LANGS:
        sections = explain(res, lang, manual_time=False)["sections"]
        shown = json.dumps(sections, ensure_ascii=False)
        assert "gemini:gemma-4-26b-a4b-it" in shown  # the public link is still there
        for name in PRIVATE_NAMES:
            assert name not in shown, (lang, name)


def test_the_walking_source_names_the_configured_router(monkeypatch):
    from starlette.testclient import TestClient

    from i18n import OWN_ROUTER_WORDING, tr, ui_table
    from walks import walking
    from web.server import app

    def served(key: str) -> list[str]:
        with TestClient(app) as client:
            return client.get("/api/strings").json()[key]

    assert "FOSSGIS" in tr("src_walk", "ru")  # the default: the public server
    assert all("FOSSGIS" in text for text in UI["footer"])
    assert ui_table() is UI

    monkeypatch.setenv("WALKS_VALHALLA_URL", "http://127.0.0.1:8002/route")
    assert tr("src_walk", "ru") == "Valhalla, свой сервер на OSM"
    assert tr("src_walk", "en") == "Valhalla, own server on OSM data"
    assert all(
        "FOSSGIS" not in text and "valhalla1" not in text for text in OWN_ROUTER_WORDING["footer"]
    )
    assert "свой сервер на OSM" in tr("footer", "ru")
    assert "© OpenStreetMap contributors (ODbL)" in tr("footer", "en")  # the attribution stays
    assert ui_table()["src_walk"] == OWN_ROUTER_WORDING["src_walk"]
    assert served("src_walk")[1] == "Valhalla, свой сервер на OSM"
    assert all(len(entry) == len(LANGS) for entry in OWN_ROUTER_WORDING.values())

    monkeypatch.setenv(
        "WALKS_VALHALLA_URL", walking.VALHALLA_URL
    )  # the public address is not «own»
    assert "FOSSGIS" in tr("src_walk", "ru")
    assert served("src_walk")[1] == "Valhalla (FOSSGIS, публичный сервер — для небольшой нагрузки)"


def test_the_footer_and_the_source_panel_carry_the_licence_duties():
    """data/NOTICE.md and docs/licensing.md §6: ODbL notice with its links, Overture's licence per contributor,
    the Foursquare notice, the MET Norway and Open-Meteo credits with the link, the fixthemap link."""
    from i18n import OWN_ROUTER_WORDING

    footers = list(UI["footer"]) + list(OWN_ROUTER_WORDING["footer"])
    for text in footers:
        for needle in (
            "© OpenStreetMap contributors (ODbL)",
            "https://www.openstreetmap.org/copyright",
            "https://opendatacommons.org/licenses/odbl/1-0/",
            "CDLA-Permissive-2.0",
            "Apache-2.0",
            "© Foursquare Labs, Inc.",
            "CC0",
            "MET Norway",
            "https://open-meteo.com",
            "https://www.openstreetmap.org/fixthemap",
            "OpenFreeMap © OpenMapTiles",
        ):
            assert needle in text, (needle, text[:60])
    for text in UI["ds_overture_what"]:
        for needle in ("CDLA-Permissive-2.0", "Apache-2.0", "CC0", "Foursquare"):
            assert needle in text, needle
    # the links of these duties are the data page's cards: tests/test_web.py::test_the_source_cards_carry_...
    assert all("Open-Meteo.com" in text for text in UI["ds_openmeteo_what"])
    assert all("open-meteo.com" in text for text in UI["dp_src_om"])
    assert all(
        "light" in text or "небольш" in text or "шағын" in text for text in UI["src_walk"]
    )  # the public server is for a small load
    assert all(
        "FOSSGIS" in text for text in UI["src_walk"]
    )  # the public server, until WALKS_VALHALLA_URL
