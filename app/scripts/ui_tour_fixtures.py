"""A stand with FORCED data for the UI tour (scripts/ui_tour.py): the layers behind the answer's extra lines have
nothing to show at any given moment of the real data, so the tour needs a stand where each of them speaks.

Rules-only, no network (WALKS_OFFLINE=1), no pin: the time is now. It forces, by patching this process only (nothing
in walks/ or web/ knows of it):

  * weather: an active Kazhydromet warning (marked as an example in its own text) and a station report with fog;
  * the afisha: three listings near the «EXPO» start point, one of them a cinema session, starting in the next hours
    (a file written into the scratch folder, `walks.events.DEFAULT_PATH` points at it);
  * an open OpenStreetMap closure note beside every place that heads the answer to the request `QUERY` at some half
    hour of the day (who heads it depends on the clock; `WALKS_CITY_DIR` points at a scratch folder with those notes).

    uv run python scripts/ui_tour_fixtures.py PORT SCRATCH_DIR
"""

from __future__ import annotations

import json
import os
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
QUERY = "хочу кофе"
EXAMPLE = "Пример для проверки интерфейса, не настоящие данные"


def _event(i: int, start: datetime, lat: float, kind: str = "event") -> dict:
    iso = start.isoformat(timespec="seconds")
    return {
        "id": f"fixture:{i}",
        "source": ("sxodim.com", "inastana.kz", "youticket.kz")[i % 3],
        "title": f"Пример {i}: {'сеанс' if kind == 'sessions' else 'концерт'}",
        "category": None,
        "kind": kind,
        "start": iso if kind == "event" else None,
        "end": None,
        "date_from": None,
        "date_to": None,
        "sessions": [iso] if kind == "sessions" else [],
        "hours_raw": None,
        "hours_osm": None,
        "price_text": None,
        "price_from": 2500,
        "url": f"https://example.kz/fixture/{i}",
        "fetched_at": datetime.now(UTC).isoformat(timespec="seconds"),
        "also_listed": [],
        "evidence": [],
        "venue": {
            "name": f"Зал примера {i}",
            "hall": None,
            "address": "пр. Мангилик Ел, 53",
            "lat": lat,
            "lon": 71.4165,
            "coords_source": "page",
            "poi_id": None,
            "poi_name": None,
            "match": None,
        },
    }


def _weather():
    from walks.models import WeatherWarning
    from walks.weather import make_weather

    warning = WeatherWarning(
        kind="storm",
        title="Штормовое предупреждение (пример)",
        text=f"г. Астана: ночью и утром ожидается туман. {EXAMPLE}.",
        source_url="https://www.kazhydromet.kz/ru/storm",
        issued=datetime.now().strftime("%d.%m.%Y"),
        active=True,
    )
    observed = (datetime.now().astimezone() - timedelta(minutes=10)).isoformat(timespec="minutes")
    return make_weather(
        3.0, 3.0, 20.0, 0.0, source="metar", conditions=["fog"], warnings=[warning],
        observed_at=observed, obs_raw="UACC (example)", precip_adverse=False,
    )  # fmt: skip


def main(port: int, scratch: Path) -> None:
    scratch.mkdir(parents=True, exist_ok=True)
    os.environ.update(
        WALKS_OFFLINE="1",
        WALKS_REQUEST_LOG="off",
        WALKS_LLM_CACHE="off",
        WALKS_WALK_CACHE="off",
        WALKS_FEEDBACK=str(scratch / "marks.json"),
        WALKS_CITY_DIR=str(scratch / "city"),
        PYTHONIOENCODING="utf-8",
    )
    for name in ("WALKS_ENV", "WALKS_DEMO_PIN", "WALKS_CACHE_PIN", "WALKS_REPLAY_ONLY"):
        os.environ.pop(name, None)
    sys.path.insert(0, str(APP))
    from walks import events
    from walks.pipeline import get_pois
    from walks.presets import PRESETS
    from web import turns
    from web.server import app

    lat, lon = PRESETS[turns.START_PRESET]
    now = datetime.now().astimezone()
    listings = [
        _event(1, now + timedelta(minutes=40), lat + 0.0006),
        _event(2, now + timedelta(minutes=90), lat + 0.0009, kind="sessions"),
        _event(3, now + timedelta(minutes=150), lat + 0.0012),
    ]
    stamp = datetime.now(UTC).isoformat(timespec="seconds")
    doc = {"schema": 1, "fetched_at": stamp, "events": listings}
    (scratch / "events.json").write_text(json.dumps(doc, ensure_ascii=False), encoding="utf-8")
    events.DEFAULT_PATH = scratch / "events.json"
    turns.fetch_weather = _weather

    (scratch / "city").mkdir(exist_ok=True)
    (scratch / "city" / "osm_notes.json").write_text("[]", encoding="utf-8")
    # which place heads the answer depends on the clock (hours decide who is open): sweep the day, and put the note
    # beside every place that heads it at some half hour, so the tour finds it whenever it runs
    heads: dict[str, None] = {}
    for minutes in range(0, 24 * 60, 30):
        at = f"{minutes // 60:02d}:{minutes % 60:02d}"
        got = turns.answer(turns.TurnRequest(text=QUERY, lat=lat, lon=lon, lang="ru", at=at))
        heads.setdefault(got["turn"]["places"][0]["id"])
    now_answer = turns.answer(turns.TurnRequest(text=QUERY, lat=lat, lon=lon, lang="ru"))
    heads.setdefault(now_answer["turn"]["places"][0]["id"])
    by_id = {p.id: p for p in get_pois()}
    rows = []
    for i, pid in enumerate(heads, start=1):
        poi = by_id[pid]
        rows.append(
            {
                "id": i,
                "lat": poi.lat + 0.0001,
                "lon": poi.lon,
                "status": "open",
                "date_created": now.strftime("%Y-%m-%d"),
                "classification": "closure",
                "snippet": f"{poi.name}: {EXAMPLE}",
                "url": f"https://www.openstreetmap.org/note/{i}",
            }
        )
    notes = json.dumps(rows, ensure_ascii=False)
    (scratch / "city" / "osm_notes.json").write_text(notes, encoding="utf-8")

    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=port, server_header=False)


if __name__ == "__main__":
    main(int(sys.argv[1]), Path(sys.argv[2]))
