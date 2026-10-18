"""State-service requests in the dialogue (ЦОН): the lexicon concept, the retrieval that keeps `other` to the ЦОН, the hours
label «по данным ЦОН (gov4c.kz)», the one card line, the reply with the asked day's interval and source, the sports
register's administration hours that never drive open / closed. ru / kk / en."""

from __future__ import annotations

from datetime import datetime

import pytest

from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_named import find_named
from walks.hours import poi_hours
from walks.i18n_gov import GOV_STRINGS
from walks.intent import named_categories, parse_rules
from walks.models import POI, STATE_REGISTRY
from walks.reasons import hours_state_text

WED = datetime(2026, 10, 14, 12, 0)  # Wednesday noon
SAT_EVE = datetime(2026, 10, 17, 15, 0)  # Saturday, the branches closed at 13:00
LAT, LON = 51.0890, 71.4160
URL = "https://gov4c.kz/ru/contacts/speccony/287/"
SRC = {
    "source": STATE_REGISTRY,
    "license": "открытые данные госоргана РК",
    "snapshot_date": "2026-10-17",
    "url": URL,
    "snippet": "x",
}


def raw_poi(pid, name, category, lat, lon, **kw):
    base = {
        "id": pid,
        "name": name,
        "names": {"name": name},
        "lat": lat,
        "lon": lon,
        "category": category,
        "tags": [],
        "opening_hours": None,
        "address": None,
        "phone": None,
        "website": None,
        "description_auto": "",
        "description_source": "derived",
        "source": "osm",
        "collected_at": "2026-10-16",
        "sources": ["osm"],
        "field_sources": {},
        "hours_state": "unknown",
    }
    return {**base, **kw}


def cson(pid, name, hours, lat, lon):
    return POI.model_validate(
        raw_poi(
            pid,
            name,
            "other",
            lat,
            lon,
            tags=["gov_service=cson"],
            opening_hours=hours,
            address="ул. Мангилик ел, 30",
            website=URL,
            source=STATE_REGISTRY,
            sources=[STATE_REGISTRY],
            hours_state="known",
            field_sources={"opening_hours": SRC, "name": SRC},
            state_registry_match={"kind": "cson", "source": "gov4c.kz", "url": URL},
        )
    )


ESIL = cson(
    "gov/cson/a",
    "Отдел района «Есиль» по обслуживанию населения",
    "Mo-Fr 09:00-20:00; Sa 09:00-13:00",
    51.095,
    71.42,
)
ALMATY = cson(
    "gov/cson/b",
    "Отдел района «Алматы» по обслуживанию населения",
    "Mo-Fr 09:00-18:00",
    51.10,
    71.43,
)
CAFE = POI.model_validate(
    raw_poi("n/1", "Кофейня Бета", "cafe", 51.0895, 71.4165, opening_hours="Mo-Su 08:00-23:00")
)
PARK = POI.model_validate(raw_poi("n/2", "Парк Бета", "park_garden", 51.0900, 71.4170))
ALAU = POI.model_validate(
    raw_poi(
        "way/1",
        "Ледовый дворец Алау",
        "sport",
        51.1049,
        71.4051,
        sources=["osm", STATE_REGISTRY],
        admin_hours={
            "raw": "08:30-18:00",
            "scope": "administration",
            "registry": "ГККП «Ледовый дворец «Алау»",
        },
        state_registry_match={
            "kind": "sport_facility",
            "source": "data.egov.kz",
            "url": "https://data.egov.kz/x",
        },
        field_sources={"admin_hours": {**SRC, "url": "https://data.egov.kz/x"}},
    )
)
POIS = [ESIL, ALMATY, CAFE, PARK, ALAU]


def turn(lang, text, when=WED, pois=POIS):
    state = new_state(LAT, LON, lang=lang)
    return take_turn(state, text, TurnEnv(when=when, use_llm=False, language=lang, pois=pois)).turn


# ---- the concept --------------------------------------------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    [
        "где ближайший ЦОН",
        "ЦОН в субботу работает?",
        "нужно получить справку",
        "справку получить",
        "госуслуги рядом",
        "центр обслуживания населения",
        "ХҚКО қайда",
        "халыққа қызмет көрсету орталығы",
        "Public service centre nearby",
        "where is a government services office",
        "tson saturday",
    ],
)
def test_state_service_words_name_the_category_other(text):
    assert parse_rules(text).intent.categories == ["other"]
    assert named_categories(text) == ["other"]


@pytest.mark.parametrize(
    "text", ["кофе рядом с ЦОНом", "хочу кофе", "концерт сегодня", "парк возле центра"]
)
def test_other_words_do_not_name_other(text):
    assert "other" not in parse_rules(text).intent.categories


def test_the_model_does_not_drop_other_for_this_concept():
    from walks.intent import llm_dropped
    from walks.models import Intent

    rules = parse_rules("где ближайший ЦОН").intent
    assert llm_dropped(rules, Intent(categories=["other"]), "где ближайший ЦОН") == []
    assert llm_dropped(
        parse_rules("хочу кофе").intent, Intent(categories=["other"]), "хочу кофе"
    ) == ["other"]


# ---- retrieval: a ЦОН is never a walking destination --------------------------------------------------------


@pytest.mark.parametrize(
    "text",
    ["хочу кофе", "прогулка в парке", "cafe nearby", "кофе рядом с ЦОНом"],
)
def test_state_service_points_never_enter_other_answers(text):
    t = turn("ru", text)
    assert t.places
    assert all(p.category != "other" for p in t.places)


def test_state_request_is_not_padded_with_other_kinds():
    t = turn("ru", "ЦОН рядом")
    assert [p.category for p in t.places] == ["other"] * len(t.places)
    assert len(t.places) <= 2


def test_named_lookup_never_finds_a_ЦОН_by_its_name():
    assert find_named("какие часы у Есиль", POIS, (LAT, LON)) is None
    assert find_named("часы работы отдела района", POIS, (LAT, LON)) is None


# ---- the labels ---------------------------------------------------------------------------------------------


def test_hours_label_names_the_source():
    assert hours_state_text("open", STATE_REGISTRY, "ru") == "открыто по данным ЦОН (gov4c.kz)"
    assert "gov4c.kz" in hours_state_text("open", STATE_REGISTRY, "kk")
    en = hours_state_text("open", STATE_REGISTRY, "en")
    assert en == "open according to the Public Service Centre (gov4c.kz)"
    assert hours_state_text("open", "official_site", "ru") == "открыто по данным официального сайта"
    assert hours_state_text("open", None, "ru") == "открыто по данным OSM"
    assert hours_state_text("closed", STATE_REGISTRY, "ru") == "закрыто"


def test_data_label_and_hours_source():
    assert ESIL.hours_source() == STATE_REGISTRY
    assert ESIL.hours_source_url() == URL
    assert "gov4c.kz" in ESIL.data_label("ru")
    assert ALAU.data_label("ru").startswith("OSM + ")


def test_strings_have_three_languages():
    assert all(len(v) == 3 and all(v) for v in GOV_STRINGS.values())


# ---- the answer ---------------------------------------------------------------------------------------------


def test_saturday_question_gets_that_days_interval_and_source_ru():
    t = turn("ru", "ЦОН в субботу работает?")
    assert t.kind == "places"
    assert "в субботу — 09:00–13:00" in t.reply
    assert "ЦОН (gov4c.kz)" in t.reply
    first = t.places[0]
    assert first.id == "gov/cson/a"
    assert first.kind == "ЦОН"
    assert first.signal.kind == "state_registry"
    assert first.signal.text == "сб: 09:00-13:00; по данным gov4c.kz"
    assert first.signal.source.url == URL
    assert first.hours.source.label == "ЦОН (gov4c.kz)"
    assert first.hours.source.url == URL
    assert t.route is None


def test_saturday_question_kk_and_en():
    kk = turn("kk", "ХҚКО сенбіде жұмыс істей ме?")
    assert "сенбіде — 09:00–13:00" in kk.reply
    assert "ХҚКО (gov4c.kz)" in kk.reply
    assert kk.places[0].signal.text.startswith("сб: 09:00-13:00")
    en = turn("en", "is the public service centre open on Saturday?")
    assert "on Saturday — 09:00–13:00" in en.reply
    assert "Public Service Centre (gov4c.kz)" in en.reply
    assert en.places[0].signal.text == "Sat: 09:00-13:00; source: gov4c.kz"
    assert en.places[0].hours.text == "Open until 13:00"


def test_today_is_now_and_tomorrow_is_named():
    now = turn("ru", "где ближайший ЦОН")
    assert "сейчас — 09:00–20:00" in now.reply
    assert now.places[0].signal.text.startswith("ср: 09:00-20:00")
    tomorrow = turn("ru", "ЦОН завтра")
    assert "завтра — 09:00–20:00" in tomorrow.reply
    assert tomorrow.places[0].signal.text.startswith("чт: 09:00-20:00")


def test_a_day_without_branches_says_so_by_the_data():
    t = turn("ru", "ЦОН в воскресенье")
    assert t.kind == "none_found"
    assert t.reply == "По данным gov4c.kz в воскресенье ни один ЦОН не работает."
    assert [c.id for c in t.chips] == ["new"]
    assert "gov4c.kz" in turn("en", "tson on Sunday").reply
    assert "gov4c.kz" in turn("kk", "ХҚКО жексенбіде").reply


def test_saturday_afternoon_is_now_not_a_claim_about_the_day():
    t = turn("ru", "ЦОН в субботу", when=SAT_EVE)
    assert t.kind == "none_found"
    assert (
        "сейчас ни один ЦОН не работает" in t.reply
    )  # it is 15:00 on Saturday: «now», never «в субботу не работает»


def test_chips_of_a_state_request_are_only_more_and_closer():
    t = turn("ru", "ЦОН в субботу")
    assert {c.id for c in t.chips} <= {"more", "closer", "new"}


def test_follow_up_question_about_a_shown_branch_names_the_source():
    state = new_state(LAT, LON, lang="ru")
    env = TurnEnv(when=WED, use_llm=False, language="ru", pois=POIS)
    state = take_turn(state, "где ближайший ЦОН", env).state
    out = take_turn(state, "до скольки он работает?", env).turn
    assert out.kind == "place_answer"
    assert "по данным ЦОН (gov4c.kz)" in out.answers[0].text
    assert "сегодня 09:00–20:00" in out.answers[0].text


# ---- the sports register's administration hours --------------------------------------------------------------


def test_administration_hours_never_drive_open_or_closed():
    assert ALAU.opening_hours is None
    for when in (WED, datetime(2026, 10, 14, 3, 0), datetime(2026, 10, 14, 23, 0)):
        assert poi_hours(ALAU, when).state == "unknown"


def test_hours_answer_about_a_sports_object_says_the_office_week_is_not_its_hours():
    t = turn("ru", "до скольки работает Ледовый дворец Алау?")
    text = t.answers[0].text
    assert "График администрации (приёмной) 08:30-18:00" in text
    assert "не часы работы самого объекта" in text
    assert t.places[0].hours.state == "unknown"
    assert (
        t.places[0].signal is None
    )  # a sports object gets no card line: the answer carries the note


# ---- the shipped dataset -----------------------------------------------------------------------------------


def test_shipped_dataset_answers_a_saturday_question():
    t = take_turn(
        new_state(LAT, LON, lang="ru"),
        "ЦОН в субботу работает?",
        TurnEnv(when=WED, use_llm=False, language="ru"),
    ).turn
    assert t.kind == "places"
    assert "в субботу — 09:00–13:00" in t.reply
    assert t.places[0].signal.source.url.startswith("https://gov4c.kz/")
    cafe = take_turn(
        new_state(LAT, LON, lang="ru"), "хочу кофе", TurnEnv(when=WED, use_llm=False, language="ru")
    ).turn
    assert all(p.category != "other" for p in cafe.places)
