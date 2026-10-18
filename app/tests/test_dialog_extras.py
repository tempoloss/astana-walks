"""The extra lines of a dialogue answer (walks.dialog_extras, walks.dialog_asks), in ru / kk / en: the «Сегодня рядом»
block and the questions about the afisha, a Kazhydromet warning or the station's adverse weather, an open OpenStreetMap
note under a card, the airport bus, the nearest bus stop, the street lights along a night route. Each layer reads a
small hand-made file (no network); every line is checked for its source link and for silence when the layer is empty.
Behaviour, not wording: fields, counts, links, presence."""

from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path

import pytest

from walks import dialog_extras, events, mobility
from walks.dialog import TurnEnv, new_state, take_turn
from walks.dialog_asks import read_ask
from walks.dialog_types import DialogState, Turn
from walks.i18n_afisha import AFISHA_STRINGS
from walks.i18n_notices import NOTICE_STRINGS
from walks.i18n_signals import SIGNAL_STRINGS
from walks.i18n_weather import tw
from walks.models import WeatherWarning
from walks.pipeline import get_pois
from walks.walking import WalkingRouter, decode_polyline6, offline_router
from walks.weather import make_weather

EXPO = (51.0890, 71.4160)
NOW = datetime(2026, 10, 17, 19, 0)  # a Saturday evening, Astana local time
NIGHT = datetime(2026, 10, 17, 21, 0)  # after the sunset of that day
LANGS = ("ru", "kk", "en")
COFFEE = {"ru": "хочу кофе", "kk": "кофе ішкім келеді", "en": "i want coffee"}
FLIGHT = {
    "ru": "кофе, до вылета 2 часа",
    "kk": "ұшуға дейін 2 сағат, кофе ішкім келеді",
    "en": "coffee before my flight",
}
AFISHA = {
    "ru": ("что сегодня интересного", "концерт вечером", "кино сегодня", "афиша"),
    "kk": ("бүгін не қызық", "кешке концерт", "бүгін кино", "афиша"),
    "en": ("what's on today", "concert tonight", "movies today", "afisha"),
}
BUS = {
    "ru": ("как добраться до аэропорта", "последний автобус"),
    "kk": ("әуежайға қалай жетуге болады", "соңғы автобус"),
    "en": ("how do i get to the airport", "last bus"),
}
NO_EVENTS_CLAIM = re.compile(r"событий нет|нет событий|no events|іс-шара жоқ", re.I)
FETCHED = "2026-10-17T07:00:00+00:00"


def env(when: datetime = NOW, **kw) -> TurnEnv:
    kw.setdefault("router", offline_router())
    return TurnEnv(when=when, use_llm=False, **kw)


def say(text: str, lang: str, state: DialogState | None = None, **kw) -> tuple[Turn, DialogState]:
    out = take_turn(state or new_state(*EXPO, lang), text, env(**kw))
    return out.turn, out.state


# ------------------------------------------------------------------ the layers' files


def ev(i: int, start: str, lat: float = EXPO[0] + 0.0006, source: str = "sxodim.com") -> dict:
    return {
        "id": f"t:{i}",
        "source": source,
        "title": f"Событие {i}",
        "category": None,
        "kind": "event",
        "start": start,
        "end": None,
        "date_from": None,
        "date_to": None,
        "sessions": [],
        "hours_raw": None,
        "hours_osm": None,
        "price_text": None,
        "price_from": 2000,
        "url": f"https://example.kz/{i}",
        "fetched_at": FETCHED,
        "also_listed": [],
        "evidence": [],
        "venue": {
            "name": f"Зал {i}",
            "hall": None,
            "address": "ул. Туран, 1",
            "lat": lat,
            "lon": EXPO[1],
            "coords_source": "page",
            "poi_id": None,
            "poi_name": None,
            "match": None,
        },
    }


def afisha_file(tmp_path: Path, monkeypatch, *items: dict) -> None:
    path = tmp_path / "events.json"
    path.write_text(
        json.dumps({"schema": 1, "fetched_at": FETCHED, "events": list(items)}), encoding="utf-8"
    )
    monkeypatch.setattr(events, "DEFAULT_PATH", path)


def three_events(tmp_path: Path, monkeypatch) -> None:
    afisha_file(
        tmp_path,
        monkeypatch,
        ev(1, "2026-10-17T19:30:00+05:00"),
        ev(2, "2026-10-17T20:00:00+05:00", source="inastana.kz"),
        ev(3, "2026-10-17T20:30:00+05:00", source="youticket.kz"),
        ev(4, "2026-10-17T21:00:00+05:00", source="alem.ai"),
        sessions(5, "2026-10-17T20:15:00+05:00"),
    )


def city_dir(tmp_path: Path, monkeypatch, **files: list[dict]) -> Path:
    folder = tmp_path / "city"
    folder.mkdir(exist_ok=True)
    for name, rows in files.items():
        (folder / f"{name}.json").write_text(json.dumps(rows), encoding="utf-8")
    monkeypatch.setenv("WALKS_CITY_DIR", str(folder))
    return folder


def mobility_dir(tmp_path: Path, monkeypatch, **files: object) -> None:
    folder = tmp_path / "mobility"
    folder.mkdir(exist_ok=True)
    for name, doc in files.items():
        (folder / f"{name}.json").write_text(json.dumps(doc), encoding="utf-8")
    monkeypatch.setattr(mobility, "DATA_DIR", folder)


def warning(kind: str = "storm", active: bool = True) -> WeatherWarning:
    return WeatherWarning(
        kind=kind,  # type: ignore[arg-type]
        title="Штормовое предупреждение ОЯ № 17 с 20 ч. 17 октября до 08 ч. 18 октября",
        text="г. Астана: 18 октября ночью и утром ожидается туман.",
        source_url="https://www.kazhydromet.kz/ru/storm",
        issued="17.10.2026",
        active=active,
    )


# ------------------------------------------------------------------ the afisha


@pytest.mark.parametrize("lang", LANGS)
def test_a_search_carries_a_compact_events_block_with_links(lang, tmp_path, monkeypatch):
    three_events(tmp_path, monkeypatch)
    turn, _ = say(COFFEE[lang], lang)
    assert turn.kind == "places"
    assert turn.events is not None
    assert 1 <= len(turn.events.items) <= 2
    for item in turn.events.items:
        assert item.source.label
        assert item.source.url
        assert item.source.url.startswith("https://")
        assert item.title in item.text
    assert turn.events.heading


@pytest.mark.parametrize("lang", LANGS)
def test_the_block_is_silent_when_the_afisha_has_nothing_near(lang, tmp_path, monkeypatch):
    afisha_file(tmp_path, monkeypatch, ev(1, "2026-10-17T19:30:00+05:00", lat=EXPO[0] + 0.2))
    turn, _ = say(COFFEE[lang], lang)
    assert turn.events is None
    monkeypatch.setattr(events, "DEFAULT_PATH", tmp_path / "missing.json")
    turn, _ = say(COFFEE[lang], lang)
    assert turn.kind == "places"
    assert turn.events is None


def test_past_events_are_not_listed_under_a_search(tmp_path, monkeypatch):
    afisha_file(tmp_path, monkeypatch, ev(1, "2026-10-17T10:00:00+05:00"))
    turn, _ = say(COFFEE["ru"], "ru")
    assert turn.events is None


def test_a_stale_afisha_says_so(tmp_path, monkeypatch):
    three_events(tmp_path, monkeypatch)
    turn, _ = say(
        COFFEE["ru"], "ru", when=datetime(2026, 10, 19, 19, 0)
    )  # two days after the snapshot
    assert turn.events is None  # these events are over; nothing to show
    afisha_file(tmp_path, monkeypatch, ev(1, "2026-10-19T19:30:00+05:00"))
    turn, _ = say(COFFEE["ru"], "ru", when=datetime(2026, 10, 19, 19, 0))
    assert turn.events is not None
    assert "17 окт" in turn.events.note


@pytest.mark.parametrize("lang", LANGS)
def test_questions_about_the_afisha_are_answered_from_it(lang, tmp_path, monkeypatch):
    three_events(tmp_path, monkeypatch)
    for question in AFISHA[lang]:
        assert read_ask(question) is not None, question
        turn, state = say(question, lang)
        assert turn.kind == "place_answer", question
        assert turn.events is not None, question
        assert 1 <= len(turn.events.items) <= 3
        assert not turn.places
        assert state.shown == []  # no search happened
        sources = {i.source.label for i in turn.events.items}
        assert sources <= {"Sxodim", "InAstana", "YouTicket", "Alem.ai"}
        assert all(i.source.url for i in turn.events.items)
        # the afisha says how little it covers, by name
        assert all(name in turn.events.note for name in ("Sxodim", "InAstana", "YouTicket"))


@pytest.mark.parametrize("lang", LANGS)
def test_an_empty_afisha_answer_never_says_nothing_is_on(lang, tmp_path, monkeypatch):
    afisha_file(tmp_path, monkeypatch, ev(1, "2026-10-17T19:30:00+05:00", lat=EXPO[0] + 0.2))
    turn, _ = say(AFISHA[lang][0], lang)
    assert turn.kind == "place_answer"
    assert turn.events is None
    assert "Sxodim" in turn.reply  # the sources it covers, named
    assert not NO_EVENTS_CLAIM.search(turn.reply)
    monkeypatch.setattr(events, "DEFAULT_PATH", tmp_path / "missing.json")
    turn, _ = say(AFISHA[lang][0], lang)
    assert turn.events is None
    assert turn.reply
    assert not NO_EVENTS_CLAIM.search(turn.reply)


def test_the_afisha_never_invents_an_event(tmp_path, monkeypatch):
    three_events(tmp_path, monkeypatch)
    turn, _ = say("концерт вечером", "ru")
    assert turn.events is not None
    titles = {i.title for i in turn.events.items}
    assert titles <= {"Событие 1", "Событие 2", "Событие 3", "Событие 4", "Фильм 5"}


@pytest.mark.parametrize(
    "text",
    [
        "хочу кофе",
        "кафе рядом с кинотеатром",
        "до скольки работает кинотеатр",
        "что интересного рядом",
        "парк с детской площадкой",
        "музей на час",
        "аэропорт 2 часа до вылета",
    ],
)
def test_ordinary_requests_are_not_taken_for_afisha_or_bus_questions(text):
    assert read_ask(text) is None


# ------------------------------------------------------------------ weather


@pytest.mark.parametrize("lang", LANGS)
def test_an_active_warning_adds_one_notice_with_its_link(lang):
    turn, _ = say(COFFEE[lang], lang, weather=make_weather(10.0, 10.0, warnings=[warning()]))
    (notice,) = [n for n in turn.notices if n.kind == "weather"]
    assert notice.source is not None
    assert notice.source.url == "https://www.kazhydromet.kz/ru/storm"
    assert "ожидается туман" in notice.text  # the official words, as they are
    assert notice.detail.startswith("Штормовое предупреждение")


def test_a_warning_that_is_not_active_yet_says_nothing():
    turn, _ = say(
        COFFEE["ru"], "ru", weather=make_weather(10.0, 10.0, warnings=[warning(active=False)])
    )
    assert not [n for n in turn.notices if n.kind == "weather"]


@pytest.mark.parametrize("lang", LANGS)
def test_adverse_weather_at_the_station_is_said_in_the_lead_not_as_a_notice(lang):
    observed = make_weather(
        3.0,
        3.0,
        20.0,
        0.0,
        source="metar",
        conditions=["fog"],
        observed_at="2026-10-17T18:50+05:00",
        precip_adverse=False,
    )
    turn, _ = say(COFFEE[lang], lang, weather=observed)
    assert turn.notices == []
    assert tw("wx_c_fog", lang).lower() in turn.reply.lower()


@pytest.mark.parametrize("lang", LANGS)
def test_the_nmu_notice_names_astana_and_the_day_only(lang):
    nmu = WeatherWarning(
        kind="nmu",
        title="Ежедневный бюллетень состояния воздушного бассейна (НМУ)",
        text="18 октября в городах Костанай, Павлодар, Астана ожидаются НМУ. Ночью в Караганде.",
        source_url="https://www.kazhydromet.kz/ru/ecology/nmu",
        issued="17.10.2026",
        valid_from="2026-10-18T00:00+05:00",
        valid_to="2026-10-19T00:00+05:00",
        active=True,
    )
    turn, _ = say(COFFEE[lang], lang, weather=make_weather(10.0, 10.0, warnings=[nmu]))
    (notice,) = [n for n in turn.notices if n.kind == "weather"]
    assert notice.source is not None
    assert notice.source.url.endswith("/ru/ecology/nmu")
    assert not any(city in notice.text for city in ("Костанай", "Павлодар", "Караганд"))
    assert "18" in notice.text
    assert "НМУ" in notice.text or "NMU" in notice.text
    assert len(notice.text) < 80


def test_the_forecast_and_the_manual_weather_are_not_observations():
    for weather in (
        make_weather(-30.0, -30.0, 5.0, 0.0),
        make_weather(-30.0, -30.0, source="manual"),
    ):
        assert weather.adverse
        turn, _ = say(COFFEE["ru"], "ru", weather=weather)
        assert turn.notices == []
    turn, _ = say(COFFEE["ru"], "ru", weather=None)
    assert turn.notices == []


def test_calm_station_weather_says_nothing():
    calm = make_weather(
        12.0,
        12.0,
        8.0,
        0.0,
        source="metar",
        observed_at="2026-10-17T18:50+05:00",
        precip_adverse=False,
    )
    turn, _ = say(COFFEE["ru"], "ru", weather=calm)
    assert turn.notices == []


# ------------------------------------------------------------------ OpenStreetMap notes under a card


def note(nid: int, lat: float, lon: float, snippet: str, **kw) -> dict:
    row = {
        "id": nid,
        "lat": lat,
        "lon": lon,
        "status": "open",
        "date_created": "2026-06-27",
        "classification": "closure",
        "snippet": snippet,
        "url": f"https://www.openstreetmap.org/note/{nid}",
    }
    return row | kw


def primary_poi(lang: str):
    turn, _ = say(COFFEE[lang], lang)
    poi = next(p for p in get_pois() if p.id == turn.places[0].id)
    return turn, poi


@pytest.mark.parametrize("lang", LANGS)
def test_an_open_closure_note_adds_one_card_line_with_its_link(lang, tmp_path, monkeypatch):
    _, poi = primary_poi(lang)
    city_dir(
        tmp_path, monkeypatch, osm_notes=[note(5363571, poi.lat, poi.lon, f"{poi.name} закрылось")]
    )
    turn, _ = say(COFFEE[lang], lang)
    signal = turn.places[0].signal
    assert signal is not None
    assert signal.kind == "osm_note"
    assert signal.source.url == "https://www.openstreetmap.org/note/5363571"
    assert "27.06.2026" in signal.text
    assert "OpenStreetMap" in signal.text
    assert signal.date == "2026-06-27"
    others = [p for p in turn.places[1:] if p.signal]
    assert others == []  # one card, one line


def test_a_closure_note_lowers_the_confidence_to_at_most_medium(tmp_path, monkeypatch):
    first = take_turn(new_state(*EXPO, "ru"), COFFEE["ru"], env())
    poi = next(p for p in get_pois() if p.id == first.turn.places[0].id)
    assert first.result is not None
    city_dir(
        tmp_path, monkeypatch, osm_notes=[note(1, poi.lat, poi.lon, f"{poi.name}: place gone")]
    )
    noted = take_turn(new_state(*EXPO, "ru"), COFFEE["ru"], env())
    assert noted.result is not None
    flagged = next(r for r in noted.result.recs if r.poi.id == poi.id)
    assert flagged.confidence in ("medium", "low")
    before = next(r for r in first.result.recs if r.poi.id == poi.id)
    assert before.confidence != "high" or flagged.confidence == "medium"


def test_an_hours_note_is_a_different_line_and_other_notes_say_nothing(tmp_path, monkeypatch):
    _, poi = primary_poi("ru")
    here = (poi.lat, poi.lon, f"{poi.name}")
    city_dir(tmp_path, monkeypatch, osm_notes=[note(2, *here, classification="hours")])
    hours_line = say(COFFEE["ru"], "ru")[0].places[0].signal
    assert hours_line is not None
    city_dir(tmp_path, monkeypatch, osm_notes=[note(3, *here)])
    closure_line = say(COFFEE["ru"], "ru")[0].places[0].signal
    assert closure_line is not None
    assert closure_line.text != hours_line.text
    for ignored in (
        note(4, *here, status="closed"),  # resolved on the map
        note(5, *here, classification="other"),
        note(6, *here, classification="new_place"),
        note(7, poi.lat + 0.01, poi.lon, poi.name),  # a kilometre away
    ):
        city_dir(tmp_path, monkeypatch, osm_notes=[ignored])
        assert say(COFFEE["ru"], "ru")[0].places[0].signal is None


def test_a_missing_notes_file_is_no_line(tmp_path, monkeypatch):
    city_dir(tmp_path, monkeypatch)
    turn, _ = say(COFFEE["ru"], "ru")
    assert all(p.signal is None for p in turn.places)


def test_the_note_line_is_also_on_the_card_of_a_question_about_the_place(tmp_path, monkeypatch):
    _, poi = primary_poi("ru")
    city_dir(tmp_path, monkeypatch, osm_notes=[note(8, poi.lat, poi.lon, poi.name)])
    _, state = say(COFFEE["ru"], "ru")
    answer, _ = say("до скольки работает первое", "ru", state)
    assert answer.kind == "place_answer"
    assert answer.places[0].signal is not None


# ------------------------------------------------------------------ the airport bus


def last_bus() -> tuple[str, str]:
    info = mobility.airport_bus()
    assert info is not None
    assert info.last_to_airport is not None
    return info.last_to_airport


@pytest.mark.parametrize("lang", LANGS)
def test_a_flight_request_in_the_evening_adds_the_last_bus(lang):
    route, time = last_bus()
    turn, _ = say(FLIGHT[lang], lang)
    (notice,) = [n for n in turn.notices if n.kind == "airport"]
    assert route in notice.text
    assert time in notice.text
    assert notice.source is not None
    assert notice.source.label == "nn-airport.kz"
    assert notice.source.url
    assert "nn-airport.kz" in notice.source.url


def test_the_airport_bus_is_said_only_when_the_time_makes_it_relevant():
    _, last = last_bus()
    noon, _ = say(FLIGHT["ru"], "ru", when=datetime(2026, 10, 17, 12, 0))
    assert [n for n in noon.notices if n.kind == "airport"] == []
    gone, _ = say(FLIGHT["ru"], "ru", when=datetime(2026, 10, 17, 22, 40))
    assert [last in n.text for n in gone.notices if n.kind == "airport"] == [True]
    night, _ = say(FLIGHT["ru"], "ru", when=datetime(2026, 10, 17, 3, 0))
    assert len([n for n in night.notices if n.kind == "airport"]) == 1
    texts = {
        when: [n.text for n in say(FLIGHT["ru"], "ru", when=when)[0].notices]
        for when in (datetime(2026, 10, 17, 19, 0), datetime(2026, 10, 17, 22, 40))
    }
    assert texts[datetime(2026, 10, 17, 19, 0)] != texts[datetime(2026, 10, 17, 22, 40)]


@pytest.mark.parametrize(
    "word", ["аэропорт", "вылет", "рейс", "вокзал", "поезд", "әуежай", "airport", "train"]
)
def test_every_travel_word_makes_the_request_a_trip(word):
    turn, _ = say(f"кофе, {word} в 22:00", "ru")
    assert [n for n in turn.notices if n.kind == "airport"]


def test_a_request_without_a_trip_has_no_bus_line():
    turn, _ = say(COFFEE["ru"], "ru")
    assert [n for n in turn.notices if n.kind == "airport"] == []


@pytest.mark.parametrize("lang", LANGS)
def test_questions_about_the_airport_bus_are_answered_from_its_facts(lang):
    _, time = last_bus()
    for question in BUS[lang]:
        assert read_ask(question) is not None, question
        turn, state = say(question, lang, when=datetime(2026, 10, 17, 12, 0))  # any hour
        assert turn.kind == "place_answer"
        assert not turn.places
        assert time in turn.reply or any(time in n.text for n in turn.notices)
        (notice,) = turn.notices
        assert notice.kind == "airport"
        assert notice.source is not None
        assert notice.source.url
        assert state.shown == []


def test_without_the_timetable_the_answer_says_there_is_none_and_the_search_is_silent(
    tmp_path, monkeypatch
):
    mobility_dir(tmp_path, monkeypatch)
    turn, _ = say("как добраться до аэропорта", "ru")
    assert turn.kind == "place_answer"
    assert turn.notices == []
    assert "nn-airport.kz" in turn.reply  # where to look, no invented times
    assert not re.search(r"\d\d:\d\d", turn.reply)
    search, _ = say(FLIGHT["ru"], "ru")
    assert search.kind == "places"
    assert search.notices == []


# ------------------------------------------------------------------ the nearest bus stop


def stop(name: str, dlat: float) -> dict:
    return {
        "osm_id": None,
        "name": name,
        "lat": EXPO[0] + dlat,
        "lon": EXPO[1],
        "tags": {},
        "gtfs_ids": ["x"],
        "sources": [{"source": "zenodo_gtfs", "licence": "CC-BY-4.0"}],
    }


@pytest.mark.parametrize("lang", LANGS)
def test_the_two_directions_of_one_stop_are_one_stop(lang, tmp_path, monkeypatch):
    mobility_dir(
        tmp_path,
        monkeypatch,
        stops=[stop("Alpha", 0.0010), stop("Alpha", 0.0011), stop("Beta", 0.0020)],
    )
    found = dialog_extras.near_stop(*EXPO, lang)
    assert found is not None
    assert found.name == "Alpha"
    assert found.minutes >= 1
    assert found.distance_m == pytest.approx(111, abs=5)
    assert "Alpha" in found.text
    assert found.source is not None
    assert found.source.url
    assert "zenodo" in found.source.url


def test_a_far_stop_or_no_data_is_no_line(tmp_path, monkeypatch):
    mobility_dir(tmp_path, monkeypatch, stops=[stop("Far", 0.02)])
    assert dialog_extras.near_stop(*EXPO, "ru") is None
    mobility_dir(tmp_path, monkeypatch)
    assert dialog_extras.near_stop(*EXPO, "ru") is None


def test_a_card_carries_the_stop_in_its_details(tmp_path, monkeypatch):
    first, _ = say(COFFEE["ru"], "ru")
    spot = first.places[0]
    near = {**stop("Alpha", 0.0), "lat": spot.lat + 0.0005, "lon": spot.lon}
    mobility_dir(tmp_path, monkeypatch, stops=[near, near])
    turn, _ = say(COFFEE["ru"], "ru")
    assert turn.places[0].stop is not None
    assert turn.places[0].stop.name == "Alpha"


# ------------------------------------------------------------------ the street lights of a night route


def encode_polyline6(points: list[tuple[float, float]]) -> str:
    out, prev = [], (0, 0)
    for lat, lon in points:
        cur = (round(lat * 1e6), round(lon * 1e6))
        for delta in (cur[0] - prev[0], cur[1] - prev[1]):
            value = ~(delta << 1) if delta < 0 else delta << 1
            while value >= 0x20:
                out.append(chr((0x20 | (value & 0x1F)) + 63))
                value >>= 5
            out.append(chr(value + 63))
        prev = cur
    return "".join(out)


def sampled(
    a: tuple[float, float], b: tuple[float, float], n: int = 30
) -> list[tuple[float, float]]:
    return [(a[0] + (b[0] - a[0]) * i / n, a[1] + (b[1] - a[1]) * i / n) for i in range(n + 1)]


def routed(
    tmp_path: Path, lang: str = "ru"
) -> tuple[WalkingRouter, list[list[tuple[float, float]]]]:
    """A router whose cache holds the street line of every leg between the origin and the three places."""
    first, _ = say(COFFEE[lang], lang)
    points = [first.origin, *((p.lat, p.lon) for p in first.places)]
    cache, lines = {}, []
    for a, b in ((a, b) for a in points for b in points if a != b):
        shape = sampled(a, b)
        key = f"{round(a[0], 4):.4f},{round(a[1], 4):.4f}>{round(b[0], 4):.4f},{round(b[1], 4):.4f}"
        cache[key] = {"m": 300, "s": 240, "d": "2026-10-17", "g": encode_polyline6(shape)}
        lines.append(shape)
    path = tmp_path / "walks.json"
    path.write_text(json.dumps(cache), encoding="utf-8")
    return WalkingRouter(path, network=False), lines


def lit_ways(lines: list[list[tuple[float, float]]], value: str = "yes") -> list[dict]:
    return [
        {"id": i, "highway": "footway", "lit": value, "geometry": [list(p) for p in line]}
        for i, line in enumerate(lines)
    ]


def lighting(tmp_path, monkeypatch, when=NIGHT, lang="ru", ways=None, router=None) -> str:
    walk_router, lines = routed(tmp_path, lang)
    if ways is not False:
        city_dir(tmp_path, monkeypatch, lit=lit_ways(lines) if ways is None else ways)
    turn, _ = say(COFFEE[lang], lang, when=when, router=router or walk_router)
    assert turn.route is not None
    return turn.route.lighting


@pytest.mark.parametrize("lang", LANGS)
def test_a_night_route_along_lit_streets_says_so(lang, tmp_path, monkeypatch):
    line = lighting(tmp_path, monkeypatch, lang=lang)
    assert line
    assert "OpenStreetMap" in line


def test_a_daytime_route_has_no_lighting_line(tmp_path, monkeypatch):
    assert lighting(tmp_path, monkeypatch, when=datetime(2026, 10, 17, 13, 0)) == ""


def test_unlit_is_never_said_from_missing_or_negative_tags(tmp_path, monkeypatch):
    _, lines = routed(tmp_path)
    assert lighting(tmp_path, monkeypatch, ways=[]) == ""  # no data at all
    far = [[(p[0] + 0.05, p[1]) for p in line] for line in lines]
    assert lighting(tmp_path, monkeypatch, ways=lit_ways(far)) == ""  # lit streets, but elsewhere
    assert (
        lighting(tmp_path, monkeypatch, ways=lit_ways(lines, "no")) == ""
    )  # tagged lit=no: still no line
    turn, _ = say(COFFEE["ru"], "ru", when=NIGHT)
    assert not re.search(r"неосвещ|без освещения|unlit|жарықсыз", turn.model_dump_json(), re.I)


def test_a_route_without_known_street_lines_has_no_lighting_line(tmp_path, monkeypatch):
    assert lighting(tmp_path, monkeypatch, router=offline_router()) == ""


def test_a_missing_lit_file_is_no_line(tmp_path, monkeypatch):
    walk_router, _ = routed(tmp_path)
    city_dir(tmp_path, monkeypatch)
    turn, _ = say(COFFEE["ru"], "ru", when=NIGHT, router=walk_router)
    assert turn.route is not None
    assert turn.route.lighting == ""
    assert decode_polyline6(encode_polyline6([(51.1, 71.4), (51.2, 71.5)]))[1] == (51.2, 71.5)


# ------------------------------------------------------------------ the contract


def test_the_new_fields_are_optional_and_an_old_turn_still_reads():
    turn, _ = say(COFFEE["ru"], "ru")
    blob = turn.model_dump(mode="json")
    for field in ("notices", "events"):
        blob.pop(field)
    for place in blob["places"]:
        place.pop("signal")
        place.pop("stop")
    blob["route"].pop("lighting")
    old = Turn.model_validate(blob)
    assert old.notices == []
    assert old.events is None
    assert old.places[0].signal is None
    assert old.route is not None
    assert old.route.lighting == ""


@pytest.mark.parametrize("table", [NOTICE_STRINGS, SIGNAL_STRINGS, AFISHA_STRINGS])
def test_every_new_string_is_written_in_three_languages_with_the_same_fields(table):
    for key, entry in table.items():
        assert len(entry) == 3
        assert all(text.strip() for text in entry), key
        fields = [set(re.findall(r"\{(\w+)\}", text)) for text in entry]
        assert fields[0] == fields[1] == fields[2], key


def test_the_new_lines_use_plain_words():
    jargon = re.compile(r"\bOSM\b|\bPOI\b|\bGTFS\b(?!.*Zenodo)|confidence|уверенност", re.I)
    for table in (NOTICE_STRINGS, SIGNAL_STRINGS, AFISHA_STRINGS):
        for key, entry in table.items():
            assert not any(jargon.search(text) for text in entry), key


# ------------------------------------------------------------------ what the fuzzing of the dialogue found

NOT_IN_DATA = {
    "ru": ("школа рядом какая", "где стоматолог", "посольство рядом"),
    "kk": ("жақын жерде мектеп қайда", "тіс дәрігері қайда", "елшілік қайда"),
    "en": ("where is a school", "dentist nearby", "where is the embassy"),
}


@pytest.mark.parametrize("lang", LANGS)
def test_kinds_of_place_the_data_never_holds_get_an_honest_no_data_answer(lang):
    for text in NOT_IN_DATA[lang]:
        turn, _ = say(text, lang)
        assert turn.kind == "none_found", text
        assert not turn.places
        assert turn.chips  # the next step is offered, not a «не понял»


def test_a_kind_that_is_only_the_surroundings_of_a_search_is_still_searched():
    turn, _ = say("кафе рядом со школой", "ru")
    assert turn.kind == "places"


UNKNOWN_PLACE = {
    "ru": "какие часы у башни центральной площади",
    "kk": "орталық алаңдағы мұнараның жұмыс уақыты қандай",
    "en": "what are the opening hours of the central square tower",
}


@pytest.mark.parametrize("lang", LANGS)
def test_a_named_place_that_is_not_in_the_data_is_said_so_even_with_nothing_shown(lang):
    turn, state = say(UNKNOWN_PLACE[lang], lang)
    assert turn.kind == "place_answer"
    assert not turn.places
    assert turn.chips
    assert state.shown == []


def test_a_question_about_the_place_in_view_with_no_name_still_asks_which():
    turn, _ = say("до скольки работает", "ru")
    assert turn.kind == "clarify"


ROUTE = {"ru": "а туда как дойти", "kk": "ол жаққа қалай барамын", "en": "how go there"}
PRICE = {
    "ru": "сколько стоит капучино там",
    "kk": "ол жерде капучино қанша тұрады",
    "en": "how much is a cappuccino there",
}


@pytest.mark.parametrize("lang", LANGS)
def test_how_to_get_there_after_a_search_is_a_route_answer_for_the_main_place(lang):
    first, state = say(COFFEE[lang], lang)
    turn, after = say(ROUTE[lang], lang, state)
    assert turn.kind == "place_answer"
    assert [a.topic for a in turn.answers] == ["route"]
    assert turn.places[0].id == first.places[0].id
    assert after.shown == state.shown


@pytest.mark.parametrize("lang", LANGS)
def test_a_price_question_about_a_shown_place_says_the_data_has_none_not_a_new_search(lang):
    first, state = say(COFFEE[lang], lang)
    turn, after = say(PRICE[lang], lang, state)
    assert turn.kind == "place_answer"
    (answer,) = turn.answers
    assert answer.topic == "price"
    assert answer.known is False
    assert turn.places[0].id == first.places[0].id
    assert after.shown == state.shown


@pytest.mark.parametrize(
    "text",
    ["холодно, куда в тепло", "i am cold, where to warm up", "суық, жылы жер қайда"],
)
def test_the_time_notice_never_names_a_kind_the_weather_added(text):
    out = take_turn(new_state(*EXPO, "ru"), text, env())
    assert out.result is not None
    assert "culture_theatre_cinema" in out.result.retrieval.filters.excluded_stay_kinds
    assert out.turn.notice == ""


def test_a_kind_the_user_named_is_kept_when_the_time_is_short_and_the_card_says_so():
    turn, _ = say("хочу в ресторан на 20 минут", "ru")
    assert turn.places
    assert {p.category for p in turn.places} == {
        "restaurant"
    }  # the time-fit rule never replaces the named kind


STROLLER = {
    "ru": "куда сходить на коляске рядом",
    "kk": "арбамен қайда барсам болады",
    "en": "where can i go with a stroller nearby",
}


@pytest.mark.parametrize("lang", LANGS)
def test_a_stroller_in_the_words_sets_the_access_intent_instead_of_asking(lang):
    out = take_turn(new_state(*EXPO, lang), STROLLER[lang], env())
    assert out.turn.kind == "places"
    assert out.result is not None
    assert out.result.intent.intent.accessibility


def sessions(i: int, start: str) -> dict:
    return ev(i, start) | {
        "kind": "sessions",
        "sessions": [start],
        "title": f"Фильм {i}",
        "source": "inastana.kz",
    }


@pytest.mark.parametrize("lang", LANGS)
def test_a_cinema_question_shows_todays_sessions_near_the_point(lang, tmp_path, monkeypatch):
    afisha_file(
        tmp_path,
        monkeypatch,
        sessions(1, "2026-10-17T20:00:00+05:00"),
        ev(2, "2026-10-17T19:30:00+05:00"),  # a concert is not a film
    )
    text = {"ru": "кино вечером", "kk": "бүгін кино", "en": "movies tonight"}[lang]
    turn, _ = say(text, lang)
    assert turn.kind == "place_answer"
    assert turn.events is not None
    assert [i.title for i in turn.events.items] == ["Фильм 1"]


def test_a_cinema_question_without_sessions_searches_for_cinemas(tmp_path, monkeypatch):
    afisha_file(tmp_path, monkeypatch, ev(2, "2026-10-17T19:30:00+05:00"))
    turn, _ = say("кино вечером", "ru")
    assert turn.kind == "places"
    assert turn.places[0].category == "culture_theatre_cinema"
    assert turn.notice == ""
