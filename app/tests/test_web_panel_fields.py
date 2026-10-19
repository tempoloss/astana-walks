"""The optional fields the compact panel draws from: the day strip of a card (`Hours.today`, `Hours.soon`), the price
line (`Place.price`), the way to every place (`place_legs`, `WalkingRouter.line`), the moment of the answer (`at`) and
the kind of route (`Route.kind`). Every one of them is absent, never invented, when the data has nothing behind it."""

from __future__ import annotations

import io
import json
from datetime import datetime

import pytest
from starlette.testclient import TestClient

from walks.dialog_place import closes_soon, price_of, today_spans
from walks.models import POI
from walks.presets import PRESETS
from walks.walking import VALHALLA_URL, WalkingRouter
from web.server import create_app

BAITEREK = PRESETS["Байтерек"]
MONDAY_NOON = datetime(2026, 10, 19, 12, 0)
MONDAY_LATE = datetime(2026, 10, 19, 22, 30)
SUNDAY = datetime(2026, 10, 18, 12, 0)


def _poi(**kw) -> POI:
    return POI(id="node/1", name="Кафе", lat=51.1, lon=71.4, category="cafe", **kw)


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    monkeypatch.setenv("WALKS_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("WALKS_STATE_FILE", str(tmp_path / "conversation.json"))
    (tmp_path / "marks.json").write_text("[]", encoding="utf-8")
    return TestClient(create_app())


def _turn(client, text, place=BAITEREK) -> dict:
    body = {"text": text, "lat": place[0], "lon": place[1]}
    res = client.post("/api/turn", json=body)
    assert res.status_code == 200, res.text
    return json.loads(res.text.strip().splitlines()[-1])["answer"]


# ---- the day strip ---------------------------------------------------------------------------------


def test_the_open_spans_of_the_day_are_hours_and_a_closed_day_is_an_empty_list():
    weekdays = _poi(opening_hours="Mo-Fr 08:00-24:00")
    assert today_spans(weekdays, MONDAY_NOON) == [(8.0, 24.0)]
    assert today_spans(weekdays, SUNDAY) == []  # known and closed all day: not «unknown»
    assert today_spans(_poi(opening_hours="24/7"), MONDAY_NOON) == [(0.0, 24.0)]
    split = _poi(opening_hours="Mo-Su 08:00-13:00,14:00-22:30")
    assert today_spans(split, MONDAY_NOON) == [(8.0, 13.0), (14.0, 22.5)]
    assert today_spans(_poi(), MONDAY_NOON) is None  # no schedule at all


def test_closing_soon_is_an_open_place_whose_schedule_closes_within_the_hour():
    cafe = _poi(opening_hours="Mo-Su 08:00-23:00")
    assert closes_soon(cafe, "open", MONDAY_LATE) is True
    assert closes_soon(cafe, "open", MONDAY_NOON) is False
    assert closes_soon(cafe, "closed", MONDAY_LATE) is False
    assert closes_soon(_poi(opening_hours="24/7"), "open", MONDAY_LATE) is False
    assert closes_soon(_poi(), "unknown", MONDAY_LATE) is False


def test_a_card_with_unknown_hours_has_no_strip(client):
    places = _turn(client, "хочу кофе")["turn"]["places"]
    for p in places:
        hrs = p["hours"]
        if hrs["state"] == "unknown":
            assert hrs["today"] is None
            assert hrs["soon"] is False
        else:
            assert hrs["today"] is not None


# ---- the price ---------------------------------------------------------------------------------------


def test_the_price_is_the_places_own_wording_with_its_source_and_day():
    register = {
        "source": "museum_register",
        "url": "https://e-museum.kz/x",
        "snapshot_date": "2026-10-17",
    }
    museum = _poi(price_text="1000 тг.", field_sources={"price_text": register})
    price = price_of(museum, "ru")
    assert price is not None
    assert price.text == "1000 тг."  # never parsed into a number
    assert price.source is not None
    assert "e-museum.kz" in price.source.label
    assert price.source.url == "https://e-museum.kz/x"
    assert price.date == "2026-10-17"
    voyage = _poi(price_text="free", field_sources={"price_text": {"source": "wikivoyage"}})
    assert price_of(voyage, "en").source.label == "Wikivoyage"
    assert price_of(_poi(), "ru") is None


# ---- the way to every place, the moment, the kind of route -------------------------------------------------


def test_every_place_has_its_way_and_the_answer_says_its_moment(client):
    answer = _turn(client, "хочу кофе")
    places, legs = answer["turn"]["places"], answer["place_legs"]
    assert len(legs) == len(places)
    for place, leg in zip(places, legs, strict=True):
        assert leg["minutes"] == place["walk"]["minutes"]
        assert leg["meters"] == place["walk"]["distance_m"]
        assert leg["method"] == place["walk"]["method"]
        assert leg["shape"] is None or len(leg["shape"]) > 1
    assert set(answer["at"]) == {"time", "date", "day"}
    assert len(answer["at"]["time"]) == 5


def test_a_plain_request_is_a_nearest_route_and_a_listed_order_is_a_plan(client):
    assert _turn(client, "хочу кофе")["turn"]["route"]["kind"] == "nearest"
    plan = _turn(client, "сначала кофе, потом музей")["turn"]["route"]
    assert len(plan["stops"]) > 1
    assert plan["kind"] == "plan"


def test_the_config_gives_the_stands_clock(client):
    now = client.get("/api/config").json()["now"]
    assert len(now) == len("2026-10-19T14:00")
    assert now[10] == "T"


# ---- the street line: the cache, an own router, never the shared public server ---------------------------------


def _polyline6(points) -> str:
    out, last = [], (0, 0)
    for lat, lon in points:
        cur = (round(lat * 1e6), round(lon * 1e6))
        for a, b in zip(cur, last, strict=True):
            v = a - b
            v = ~(v << 1) if v < 0 else v << 1
            while v >= 0x20:
                out.append(chr((0x20 | (v & 0x1F)) + 63))
                v >>= 5
            out.append(chr(v + 63))
        last = cur
    return "".join(out)


def _opener(calls, shape):
    def opener(req, timeout):
        calls.append(req.full_url)
        trip = {"summary": {"length": 0.5, "time": 400}, "legs": [{"shape": shape}]}
        return io.BytesIO(json.dumps({"trip": trip}).encode())

    return opener


A, B = (51.0890, 71.4160), (51.0894, 71.4180)


def test_the_street_line_comes_from_a_router_of_ones_own_and_is_kept():
    shape = _polyline6([A, (51.0892, 71.4170), B])
    calls: list[str] = []
    own = "http://127.0.0.1:8002/route"
    router = WalkingRouter(False, opener=_opener(calls, shape), url=own, sleep=lambda s: None)
    line = router.line(A, B)
    assert line is not None
    assert len(line) == 3
    assert line[1] == pytest.approx((51.0892, 71.4170))
    assert router.line(A, B) == line  # the second ask is the memory, not the network
    assert calls == [own]


def test_the_public_server_is_never_asked_for_a_line():
    calls: list[str] = []
    shape = _polyline6([A, B])
    router = WalkingRouter(
        False, opener=_opener(calls, shape), url=VALHALLA_URL, sleep=lambda s: None
    )
    assert router.line(A, B) is None
    assert calls == []
    router.leg(
        A, B
    )  # the leg itself asks (it is the answer's minutes) and keeps the line it came with
    line = router.line(A, B)
    assert line is not None
    assert len(line) == 2
    assert calls == [VALHALLA_URL]
