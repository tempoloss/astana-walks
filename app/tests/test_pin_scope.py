"""The demo pin is per request: a recorded request (a scenario starter, a DEMO_REQUESTS one) and the follow-ups of its
dialogue run at the pinned moment and weather; every other request is answered at the real time, with the live weather.
Without this the stand answered «куда поесть» at 02:00 with the places that are open at the pinned 14:00."""

from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from walks import demo_pin
from walks.presets import DEMO_REQUESTS, PRESETS, SCENARIOS
from web import server, turns

DATA = Path(__file__).resolve().parents[2] / "data"
NIGHT = datetime(2026, 10, 14, 2, 0)  # a Wednesday, 02:00 Astana time
FREE = "куда можно поесть"
BAITEREK = PRESETS["Байтерек"]
STARTER = SCENARIOS[0]  # «Рядом с Mega Silk Way»: a day scenario, pinned at 14:00 on 19.10


@pytest.fixture
def stand(tmp_path, monkeypatch, pin_clock):
    """The stand's environment minus WALKS_REPLAY_ONLY (live models allowed; none is reachable offline), at 02:00."""
    marks = tmp_path / "city_feedback.json"
    shutil.copy(DATA / "city_feedback.json", marks)
    for name, value in {
        "WALKS_ENV": "demo",
        "WALKS_DEMO_PIN": "1",
        "WALKS_CACHE_PIN": "1",
        "WALKS_OFFLINE": "1",
        "WALKS_FEEDBACK": str(marks),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(server, "load_env_file", lambda: None)
    pin_clock(NIGHT)
    return TestClient(server.create_app())


def _turn(client, text, state=None, place=BAITEREK, at=None) -> dict:
    body = {"text": text, "lat": place[0], "lon": place[1], "state": state, "at": at}
    res = client.post("/api/turn", json=body)
    assert res.status_code == 200, res.text
    lines = [json.loads(line) for line in res.text.strip().splitlines()]
    assert "answer" in lines[-1], lines[-1]
    return lines[-1]["answer"]


def _chip(answer, chip_id) -> str:
    return next(c["send"] for c in answer["turn"]["chips"] if c["id"] == chip_id)


# ---- which request the pin applies to -------------------------------------------------------------


def test_the_pin_applies_to_recorded_requests_and_their_follow_ups_only(monkeypatch):
    monkeypatch.setenv("WALKS_DEMO_PIN", "1")
    for sc in SCENARIOS:
        assert all(demo_pin.pins(text) for text in sc.texts())  # the starter in kk, ru and en
    assert all(demo_pin.pins(text) for text, _ in DEMO_REQUESTS)
    assert demo_pin.pins("а поближе", SCENARIOS[0].text)  # a follow-up of a recorded dialogue
    assert not demo_pin.pins(FREE)
    assert not demo_pin.pins("а поближе")  # a follow-up of a free dialogue
    assert not demo_pin.pins("а поближе", FREE)
    monkeypatch.delenv("WALKS_DEMO_PIN")
    assert not demo_pin.pins(SCENARIOS[0].text)  # no pin on this stand at all
    assert not demo_pin.pinned()


# ---- the stand's clock and the answers ------------------------------------------------------------


def test_the_stand_clock_is_the_real_local_time(stand):
    cfg = stand.get("/api/config").json()
    assert cfg["now"] == "2026-10-14T02:00"
    assert cfg["mode"]["demo_pin"] is True


def test_a_recorded_starter_and_its_chip_are_answered_at_the_pinned_moment(stand):
    first = _turn(stand, STARTER.text)
    assert first["pinned"] is True
    assert first["at"] == {"time": "14:00", "date": "2026-10-19"}
    follow = _turn(stand, _chip(first, "closer"), state=first["state"])
    assert follow["pinned"] is True
    assert follow["at"] == {"time": "14:00", "date": "2026-10-19"}
    assert follow["state"]["demo_base"] == STARTER.text


def test_a_free_request_at_two_at_night_is_answered_at_two_at_night(stand):
    answer = _turn(stand, FREE)
    assert answer["pinned"] is False
    assert answer["at"] == {"time": "02:00", "date": "2026-10-14"}
    assert answer["state"]["demo_base"] is None
    places = answer["turn"]["places"]
    assert places
    for place in places:
        hours = place["hours"]
        if hours["state"] == "open":  # «открыто» only when the data's hours of the day cover 02:00
            assert any(a <= 2.0 < b for a, b in hours["today"] or []), place["name"]


def test_a_free_request_after_a_recorded_one_leaves_the_pin(stand):
    first = _turn(stand, STARTER.text)
    assert first["pinned"] is True
    free = _turn(stand, FREE, state=first["state"])
    assert free["pinned"] is False
    assert free["at"] == {"time": "02:00", "date": "2026-10-14"}
    assert free["state"]["demo_base"] is None
    follow = _turn(
        stand, _chip(free, "closer"), state=free["state"]
    )  # its follow-up is a free dialogue as well
    assert follow["pinned"] is False
    assert follow["at"] == {"time": "02:00", "date": "2026-10-14"}


def test_a_chosen_time_moves_a_free_request_but_never_a_pinned_one(stand):
    free = _turn(stand, FREE, at="19:00")
    assert free["at"] == {"time": "19:00", "date": "2026-10-14"}
    pinned = _turn(stand, STARTER.text, at="19:00")
    assert pinned["at"] == {"time": "14:00", "date": "2026-10-19"}


def test_the_live_weather_is_asked_only_by_a_request_that_is_not_pinned(stand, monkeypatch):
    calls: list[int] = []
    real = turns.fetch_weather

    def counted():
        calls.append(1)
        return real()

    monkeypatch.setattr(turns, "fetch_weather", counted)
    _turn(stand, STARTER.text)
    assert calls == []  # the pinned weather is manual
    _turn(stand, FREE)
    assert calls == [1]


# ---- the dialogue core on its own: a place that closes at 22:00 -----------------------------------


def test_a_cafe_that_closes_at_22_is_never_open_for_a_free_request_at_02_00(monkeypatch, pin_clock):
    from walks.dialog import TurnEnv, new_state, take_turn
    from walks.models import POI
    from walks.walking import offline_router

    monkeypatch.setenv("WALKS_DEMO_PIN", "1")
    pin_clock(NIGHT)
    cafe = POI(
        id="boom",
        name="Coffee BOOM",
        lat=BAITEREK[0] + 0.001,
        lon=BAITEREK[1],
        category="cafe",
        opening_hours="Mo-Su 08:00-22:00",
    )
    env = TurnEnv(use_llm=False, router=offline_router(), pois=[cafe])
    out = take_turn(new_state(*BAITEREK, "ru"), FREE, env)
    assert out.state.demo_base is None
    assert all(p.hours.state != "open" for p in out.turn.places)
    assert "открыто" not in out.turn.reply.lower()
