"""The address search of «Где вы?» (web.geocode, GET /api/geocode) on the shipped gazetteer and dataset: the spellings
of one name meet, a house number may stand on either side, a typo is forgiven, a house beats a street beats a place,
every point is in Astana, and what was typed is never logged."""

from __future__ import annotations

import logging

import pytest
from starlette.testclient import TestClient

from web import geocode
from web.server import create_app

ASTANA = {"south": 50.8, "north": 51.4, "west": 71.1, "east": 71.9}


def labels(found: list[dict], kind: str) -> list[str]:
    return [h["label"] for h in found if h["kind"] == kind]


@pytest.mark.parametrize(
    ("a", "b"),
    [
        ("Мәңгілік Ел", "Мангилик Ел"),
        ("Мәңгілік Ел даңғылы", "Mangilik Yel avenue"),
        ("Қабанбай батыр", "Kabanbay batyr"),
        ("проспект Кабанбай Батыр", "Қабанбай Батыр даңғылы"),
        ("улица Сарайшык", "Сарайшық көшесі"),
        ("Kenesary str.", "ул. Кенесары"),
        ("Тәуелсіздік", "Tauelsizdik"),
    ],
)
def test_fold_meets_the_spellings(a, b):
    assert geocode.fold(a) == geocode.fold(b)


def test_fold_drops_street_type_words_only():
    assert geocode.fold("пр. Республики") == geocode.fold("Республики") == "республики"
    assert geocode.fold("улица 150 лет Абая") == "150 лет абая"


@pytest.mark.parametrize(
    ("typed", "street", "number"),
    [
        ("Кенесары 40", "кенесари", "40"),
        ("Кенесары, 40", "кенесари", "40"),
        ("40 Кенесары", "кенесари", "40"),
        ("ул. Кенесары, д. 40", "ул кенесары", "40"),
        ("Мәңгілік Ел 55/22", "мәңгілік ел", "55/22"),
        ("Абая 12а", "абая", "12а"),
    ],
)
def test_parse_finds_the_house_number_on_either_side(typed, street, number):
    first = geocode.parse(typed)[0]
    assert first[1] == number
    assert geocode.fold(first[0]) == geocode.fold(street)


def test_parse_keeps_a_number_that_is_part_of_the_name():
    texts = [text for text, number in geocode.parse("150 лет Абая") if number is None]
    assert texts == ["150 лет абая"]
    assert labels(geocode.search("150 лет Абая", "ru"), "street")


@pytest.mark.parametrize(
    "typed", ["Кенесары 40", "кенесары, 40", "40 Кенесары", "Kenesary str 40", "кенисары 40"]
)
def test_a_house_comes_first_then_its_street(typed):
    found = geocode.search(typed, "ru")
    assert [h["kind"] for h in found[:2]] == ["house", "street"]
    assert found[0]["label"].endswith(", 40")
    assert "Кенесары" in found[0]["label"]
    assert abs(found[0]["lat"] - 51.1655) < 0.01


def test_a_street_without_that_house_is_a_street_not_an_invented_house():
    found = geocode.search("Кенесары 99999", "ru")
    assert found[0]["kind"] == "street"
    assert not labels(found, "house")


def test_the_nearest_house_numbers_are_shown_with_their_own_number():
    found = geocode.search("Мангилик Ел 55", "ru")
    houses = labels(found, "house")
    assert houses
    assert all(h.split(", ")[1].startswith("55") for h in houses)
    assert found[0]["kind"] == "house"


def test_latin_kk_and_ru_find_the_same_street():
    ru = geocode.search("Кабанбай батыра 53", "ru")
    en = geocode.search("Kabanbay batyr 53", "en")
    kk = geocode.search("Қабанбай батыр 53", "kk")
    assert ru[0]["kind"] == en[0]["kind"] == kk[0]["kind"] == "house"
    assert (
        (ru[0]["lat"], ru[0]["lon"]) == (en[0]["lat"], en[0]["lon"]) == (kk[0]["lat"], kk[0]["lon"])
    )


def test_the_label_is_in_the_language_of_the_page():
    kk = geocode.search("Сарайшық", "kk")[0]["label"]
    ru = geocode.search("Сарайшық", "ru")[0]["label"]
    en = geocode.search("Сарайшық", "en")[0]["label"]
    assert "көшесі" in kk
    assert "улица" in ru
    assert en.isascii()


def test_a_place_by_its_name_in_any_script():
    for typed in ("хан шатыр", "Khan Shatyr", "Хан Шатыр"):
        found = geocode.search(typed, "ru")
        assert found[0]["kind"] == "place"
        assert "Хан Шатыр" in found[0]["label"] or "Khan Shatyr" in found[0]["label"]
        assert abs(found[0]["lat"] - 51.1325) < 0.01


def test_a_landmark_beats_a_lane_of_the_same_name():
    found = geocode.search("Байтерек", "ru")
    assert found[0]["kind"] == "place"


def test_a_street_beats_a_place_of_the_same_match():
    found = geocode.search("Достык", "ru")
    assert found[0]["kind"] == "street"


def test_a_typo_is_forgiven_but_a_short_query_is_not_guessed():
    assert labels(geocode.search("Кенисары", "ru"), "street")
    assert all("ке" in geocode.fold(h["label"]) for h in geocode.search("Ке", "ru"))


@pytest.mark.parametrize("typed", ["", "   ", "ул", "40", "ъъъъъъ", "qqqqqqqqqq zzzz"])
def test_nothing_is_found_for_nothing(typed):
    assert geocode.search(typed, "ru") == []


def test_results_are_at_most_five_and_inside_astana():
    for typed in ("мангилик", "республики", "coffee", "парк", "достык", "а"):
        found = geocode.search(typed, "ru")
        assert len(found) <= 5
        for h in found:
            assert set(h) == {"label", "kind", "lat", "lon", "district"}
            assert h["kind"] in {"house", "street", "place"}
            assert ASTANA["south"] < h["lat"] < ASTANA["north"]
            assert ASTANA["west"] < h["lon"] < ASTANA["east"]


def test_the_district_is_named_in_the_language_of_the_page():
    ru = geocode.search("Кенесары 40", "ru")[0]["district"]
    kk = geocode.search("Кенесары 40", "kk")[0]["district"]
    assert ru == "Байконур"
    assert kk


def test_a_very_long_query_is_cut_not_refused():
    assert geocode.search("Кенесары 40 " + "ы" * 5000, "ru") is not None


def test_the_same_name_a_few_hundred_metres_apart_is_one_answer():
    found = [h for h in geocode.search("Байтерек", "ru") if h["kind"] == "place"]
    for i, one in enumerate(found):
        for other in found[i + 1 :]:
            assert (
                one["label"].casefold() != other["label"].casefold()
                or geocode._km(one, other) >= 1.0
            )


# ---------------------------------------------------------------- the endpoint


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    return TestClient(create_app())


def test_the_endpoint_answers_results_and_is_never_cached(client):
    res = client.get("/api/geocode", params={"q": "Кенесары 40", "lang": "ru"})
    assert res.status_code == 200
    assert res.headers["cache-control"] == "no-store"
    body = res.json()
    assert body["results"][0]["kind"] == "house"
    assert len(body["results"]) <= 5


def test_the_endpoint_without_a_query_is_an_empty_list(client):
    assert client.get("/api/geocode").json() == {"results": []}
    assert client.get("/api/geocode", params={"q": "zzzzzzzzzz", "lang": "en"}).json() == {
        "results": []
    }


def test_the_endpoint_follows_the_language(client):
    kk = client.get("/api/geocode", params={"q": "Сарайшық", "lang": "kk"}).json()["results"][0][
        "label"
    ]
    en = client.get("/api/geocode", params={"q": "Сарайшық", "lang": "en"}).json()["results"][0][
        "label"
    ]
    assert kk != en


def test_what_was_typed_is_never_logged(client, caplog):
    secret = "Кенесары 40 секретный-запрос"
    with caplog.at_level(logging.DEBUG):
        client.get("/api/geocode", params={"q": secret, "lang": "ru"})
    assert "секретный" not in caplog.text


def test_the_access_line_of_uvicorn_loses_the_query():
    record = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", "/api/geocode?q=%D0%9A%D0%B5&lang=ru", "1.1", 200), None,
    )  # fmt: skip
    assert all(f.filter(record) for f in logging.getLogger("uvicorn.access").filters)
    assert "q=" not in record.getMessage()
    assert "/api/geocode" in record.getMessage()
    other = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s HTTP/%s" %d',
        ("127.0.0.1:1", "GET", "/api/city/demand?k=5", "1.1", 200), None,
    )  # fmt: skip
    assert all(f.filter(other) for f in logging.getLogger("uvicorn.access").filters)
    assert "k=5" in other.getMessage()


# ---------------------------------------------------------------- the house under a point


def test_reverse_names_the_house_at_a_point():
    house = geocode.search("Кенесары 40", "ru")[0]
    found = geocode.reverse(house["lat"] + 0.0003, house["lon"], "ru")
    assert found
    assert found[0]["kind"] == "house"
    assert found[0]["label"].startswith("улица Кенесары")


def test_reverse_is_silent_far_from_every_house():
    assert geocode.reverse(51.0, 71.3, "ru") == []
    assert geocode.reverse(0.0, 0.0, "ru") == []


def test_the_endpoint_reverses_a_point_and_refuses_a_bad_one(client):
    house = geocode.search("Кенесары 40", "ru")[0]
    res = client.get(
        "/api/geocode", params={"lat": house["lat"], "lon": house["lon"], "lang": "en"}
    )
    assert res.json()["results"][0]["kind"] == "house"
    assert client.get("/api/geocode", params={"lat": "x", "lon": "y"}).status_code == 422
