"""The web UI's side of the data layers: the data-quality tab's queue of OpenStreetMap notes, the afisha coverage, the
flag that tells the page whether residents' marks are saved, and the «Какие данные использованы» lines that carry the
weather's attribution and the Kazhydromet notices. Hand-made files, no network."""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path

from walks import events
from walks.dialog import TurnEnv, new_state, take_turn
from walks.models import WeatherWarning
from walks.walking import offline_router
from walks.weather import make_weather
from web import city, explain, turns

EXPO = (51.0890, 71.4160)
FETCHED = "2026-10-10T07:00:00+00:00"


def _city(tmp_path: Path, monkeypatch, notes: list[dict], construction: int = 2) -> None:
    folder = tmp_path / "city"
    folder.mkdir()
    (folder / "osm_notes.json").write_text(json.dumps(notes), encoding="utf-8")
    (folder / "construction.json").write_text(
        json.dumps([{"id": i, "geometry": [[51.0, 71.0]]} for i in range(construction)]),
        encoding="utf-8",
    )
    monkeypatch.setenv("WALKS_CITY_DIR", str(folder))


def _note(nid: int, classification: str, status: str = "open") -> dict:
    return {
        "id": nid,
        "lat": 51.1,
        "lon": 71.4,
        "status": status,
        "date_created": "2026-06-27",
        "classification": classification,
        "snippet": "Нету, тут кафе чтоли " * 12,
        "url": f"https://www.openstreetmap.org/note/{nid}",
    }


def test_the_queue_lists_open_closure_and_hours_notes_with_their_links(tmp_path, monkeypatch):
    _city(
        tmp_path,
        monkeypatch,
        [
            _note(1, "closure"),
            _note(2, "hours"),
            _note(3, "other"),  # not about a closure or the hours
            _note(4, "closure", status="closed"),  # already resolved on the map
        ],
        construction=3,
    )
    notes = city._layers()["notes"]
    assert notes is not None
    assert [n["id"] for n in notes["queue"]] == [1, 2]
    assert all(n["url"].startswith("https://www.openstreetmap.org/note/") for n in notes["queue"])
    assert all(len(n["snippet"]) <= city.SNIPPET_CHARS + 1 for n in notes["queue"])
    assert notes["attribution"]
    assert city._layers()["construction"] == 3


def test_a_missing_layer_is_none_not_zero(tmp_path, monkeypatch):
    monkeypatch.setenv("WALKS_CITY_DIR", str(tmp_path / "nothing"))
    monkeypatch.setattr(events, "DEFAULT_PATH", tmp_path / "missing.json")
    layers = city._layers()
    assert layers == {"notes": None, "construction": None, "events": None}


def test_the_afisha_coverage_counts_its_sources_and_says_when_it_is_stale(tmp_path, monkeypatch):
    def listing(i: int, source: str, lat: float | None) -> dict:
        return {"id": f"t:{i}", "source": source, "venue": {"lat": lat, "lon": 71.4}}

    path = tmp_path / "events.json"
    rows = [
        listing(1, "sxodim.com", 51.1),
        listing(2, "sxodim.com", None),
        listing(3, "alem.ai", 51.1),
    ]
    path.write_text(
        json.dumps({"schema": 1, "fetched_at": FETCHED, "events": rows}), encoding="utf-8"
    )
    monkeypatch.setattr(events, "DEFAULT_PATH", path)
    monkeypatch.setenv("WALKS_CITY_DIR", str(tmp_path / "nothing"))
    block = city._layers()["events"]
    assert block is not None
    assert (block["total"], block["located"]) == (3, 2)
    assert {s["label"]: s["count"] for s in block["sources"]} == {"Sxodim": 2, "Alem.ai": 1}
    assert block["stale"] is True  # the pinned clock of the tests is days after FETCHED


def test_the_page_is_told_whether_marks_are_saved(monkeypatch, tmp_path):
    monkeypatch.setenv("WALKS_FEEDBACK", "off")
    assert turns.config()["marks"] is False
    monkeypatch.setenv("WALKS_FEEDBACK", str(tmp_path / "marks.json"))
    assert turns.config()["marks"] is True


def test_the_data_panel_names_the_station_and_quotes_the_notices(tmp_path):
    warning = WeatherWarning(
        kind="storm",
        title="Штормовое предупреждение № 17",
        text="г. Астана: ночью ожидается туман.",
        source_url="https://www.kazhydromet.kz/ru/storm",
        active=True,
    )
    weather = make_weather(
        3.0, 3.0, 20.0, 0.0,
        source="metar", conditions=["fog"], warnings=[warning],
        observed_at="2026-10-17T18:50+05:00", precip_adverse=False,
    )  # fmt: skip
    env = TurnEnv(
        when=datetime(2026, 10, 17, 19, 0), use_llm=False, router=offline_router(), weather=weather
    )
    out = take_turn(new_state(*EXPO, "ru"), "хочу кофе", env)
    assert out.result is not None
    setting = explain.explain(out.result, "ru", manual_time=False)["sections"][0]["lines"]
    text = "\n".join(setting)
    assert "METAR UACC" in text  # the station, not Open-Meteo, as the source of the temperature
    assert "https://www.kazhydromet.kz/ru/storm" in text
