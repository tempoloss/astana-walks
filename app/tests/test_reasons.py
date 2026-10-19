"""The reasons of a no-AI card: every sentence is backed by a field of the record (or of its peers), in three languages."""

from __future__ import annotations

import re
from datetime import datetime

import pytest

from walks.colocated import SHARED_COORD, collapse_shared_coordinates
from walks.generate import template_recs
from walks.i18n import t
from walks.models import POI, Candidate, Intent, WeatherInfo
from walks.pipeline import recommend
from walks.presets import PRESETS, SCENARIOS
from walks.reasons import MAX_FACTS, Trip, compose_why, facts, template_what
from walks.weather import manual_weather

LANGS = ("kk", "ru", "en")


def poi(pid="p", **kw) -> POI:
    base = {
        "id": pid,
        "name": pid,
        "lat": 51.09,
        "lon": 71.41,
        "category": "cafe",
        "sources": ["osm"],
    }
    return POI(**{**base, **kw})


def cand(pid="p", dist=300, state="unknown", reasons=(), **kw) -> Candidate:
    return Candidate(
        poi=poi(pid, **kw),
        distance_m=dist,
        walk_min=round(dist / 75),
        travel_min=round(dist / 75),
        hours_state=state,
        score=1.0,
        reasons=list(reasons),
    )


def intent(lang="ru", **kw) -> Intent:
    return Intent(language=lang, time_budget_min=60, time_stated=True, **kw)  # «на час»


TRIP = Trip(one_way_min=5, stay_min=30)


def said(c: Candidate, peers=None, lang="ru", weather=None, trip=TRIP) -> str:
    return " ".join(facts(c, intent(lang), weather, peers or [c], trip))


@pytest.mark.parametrize("lang", LANGS)
def test_the_time_window_fact_carries_the_numbers_of_the_trip_and_only_when_it_fits(lang):
    c = cand()
    text = said(c, lang=lang, trip=Trip(5, 30))
    assert "~10" in text
    assert "~30" in text
    assert "60" in text
    assert "~10" not in said(c, lang=lang, trip=Trip(40, 30))  # 80 + 30 > 60: nothing is promised


@pytest.mark.parametrize("lang", LANGS)
def test_a_reason_never_states_the_status_the_card_line_says_it(lang):
    for c in (
        cand(state="open", opening_hours="24/7"),
        cand(state="open", opening_hours="Mo-Su 09:00-21:00"),
        cand(state="unknown", opening_hours="Mo-Su 09:00-21:00"),
    ):
        text = said(c, lang=lang).lower()
        for word in ("открыт", "работает", "круглосуточ", "open", "24/7", "ашық", "тәулік"):
            assert word not in text, (word, text)


def test_no_selection_note_is_a_reason():
    near = cand("near", 100, state="open", opening_hours="Mo-Su 09:00-21:00")
    far = cand("far", 400, state="open", opening_hours="Mo-Su 09:00-21:00")
    park = cand("park", 250, category="park_garden", reasons=["category"])
    peers = [near, far, park]
    for c in peers:
        text = said(c, peers)
        for note in ("Ближайшее по прямой", "Единственное место", "как вы просили", "Совпадает с"):
            assert note not in text, text


def test_wikipedia_facts_follow_the_fields_and_the_ranking_among_peers():
    read = cand(
        "read", wikipedia={"ru": {"title": "x"}}, popularity_pageviews=900, category="viewpoint"
    )
    less = cand(
        "less",
        wikipedia={"ru": {"title": "y"}},
        popularity_pageviews=100,
        category="museum_gallery",
    )
    bare = cand("bare", wikipedia={"ru": {"title": "z"}}, category="park_garden")
    nothing = cand("nothing", category="park_garden")
    peers = [read, less, bare, nothing]
    assert "Самая читаемая" in said(read, peers)
    assert "~900" in said(read, peers)
    assert "Самая читаемая" not in said(less, peers)
    assert "~100" in said(less, peers)
    assert "О месте есть статья в Википедии." in said(bare, peers)
    assert "Википеди" not in said(nothing, peers)


def test_the_record_s_own_features_are_the_reason():
    tables = cand(outdoor_seating="yes", internet_access="wlan", wheelchair="yes")
    text = said(tables, lang="en").lower()
    assert "outdoor seating" in text
    assert "wi-fi" in text
    assert "step-free" in text
    bare = said(cand(outdoor_seating="no"), lang="en")
    assert "outdoor seating" not in bare
    assert "Wi-Fi" not in bare


def test_wishes_come_first_and_each_one_is_a_reason_code():
    c = cand(reasons=["kids", "quiet"], state="open", opening_hours="24/7")
    first = facts(c, intent("ru"), None, [c], TRIP)[0]
    assert "подходит для детей" in first.lower()
    assert "спокойное" in first
    plain = facts(cand(reasons=[]), intent("ru"), None, [cand()], TRIP)
    assert not any("детей" in f for f in plain)


@pytest.mark.parametrize("lang", LANGS)
def test_a_why_has_at_most_two_sentences_and_the_honest_line_when_nothing_is_known(lang):
    c = cand(reasons=["kids", "quiet", "category"], state="open", opening_hours="24/7")
    why = compose_why(c, intent(lang), None, [c], TRIP)
    assert len(re.split(r"(?<=[.!?])\s+", why)) <= MAX_FACTS
    bare = compose_why(
        cand(), intent(lang), None, [cand()], Trip(60, 60)
    )  # no time fact, nothing else: no filler, no «рядом с вами», the honest line
    assert bare == t("why_none", lang)


def test_an_off_category_card_says_so_first():
    c = cand(reasons=["off_category", "weather_indoor"], state="open", opening_hours="24/7")
    weather = WeatherInfo(apparent_c=-28, adverse=True, reason="x")
    why = compose_why(c, intent("ru"), weather, [c], TRIP)
    assert why.startswith(t("fit_head_off", "ru"))
    assert "Подходит под запрос" not in why


def test_what_to_do_uses_the_data_and_not_the_collectors_boilerplate():
    cafe = cand(
        tags=["cuisine=coffee_shop;burger"],
        description_auto="Кафе «X» в Астане. Работает круглосуточно.",
    )
    ru, en, kk = (template_what(cafe, intent(lang)) for lang in ("ru", "en", "kk"))
    assert ru.startswith("Кухня: кофе, бургеры.")
    assert en.startswith("Cuisine: coffee, burgers.")
    assert kk.startswith("Асханасы:")
    assert "в Астане" not in ru
    unknown_cuisine = cand(tags=["cuisine=ethiopian"], address="Астана, ул. Мира 1")
    assert template_what(unknown_cuisine, intent("ru")).startswith(
        "Адрес: ул. Мира 1."
    )  # no city word
    wiki = cand(
        description_source="wikipedia",
        description="Старое описание. Второе предложение.",
        wikipedia={"en": {"extract": "The Baiterek is a monument in Astana. It is 105 m tall."}},
    )
    assert template_what(wiki, intent("en")).startswith("The Baiterek is a monument in Astana.")
    assert "105" not in template_what(wiki, intent("en"))  # only the first sentence


def test_shared_overture_coordinates_keep_one_record_with_low_confidence():
    a = cand("a", 500, sources=["overture"], lat=51.01, lon=71.5)
    b = cand("b", 500, sources=["overture"], lat=51.01, lon=71.5)
    b = b.model_copy(update={"score": 2.0})
    osm = cand("osm", 500, sources=["osm"], lat=51.01, lon=71.5)
    other = cand("other", 100, sources=["overture"], lat=51.02, lon=71.5)
    kept, log = collapse_shared_coordinates([a, b, osm, other])
    ids = [c.poi.id for c in kept]
    assert ids == ["b", "osm", "other"]  # the best of the group, an OSM record and a lone one stay
    assert SHARED_COORD in kept[0].reasons
    assert SHARED_COORD not in kept[2].reasons
    assert log[0].kept_id == "b"
    assert "a" in log[0].merged[0]
    rec = template_recs([kept[0]], intent("ru"))[0]
    assert rec.confidence == "low"
    assert "координаты этой записи совпадают" in rec.notes.lower()


def test_the_reasons_name_the_final_walking_times_of_the_card():
    sc = SCENARIOS[3]
    res = recommend(
        sc.text_in("ru"),
        *PRESETS[sc.preset],
        datetime(2026, 10, 19, 14, 0),
        use_llm=False,
        weather=manual_weather(10.0, pm25=5.0),
        language="ru",
    )
    timed = [r for r in res.recs if "туда и обратно" in r.why]
    assert timed
    for r in timed:
        assert f"~{2 * r.walk_min} мин" in r.why
        assert f"~{r.time_on_site_min} мин" in r.why


def test_the_airport_preset_is_the_terminal_not_the_apron():
    lat, lon = PRESETS["Аэропорт"]
    t1 = (51.02797, 71.46348)  # OSM way 166500591, the international terminal
    assert abs(lat - t1[0]) < 0.0008
    assert abs(lon - t1[1]) < 0.0008
