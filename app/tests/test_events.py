"""walks/events.py: the «сегодня рядом» block of the afisha: time window, past events, order, silence, staleness,
labels in three languages and the `--events` CLI flag. The data are small hand-made snapshots (no network)."""

from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

import pytest

from walks import cli, events, i18n_events

TZ5 = timezone(timedelta(hours=5))
KHAN = (51.1325, 71.4039)  # Khan Shatyr
NOW = datetime(2026, 10, 17, 19, 0)  # Astana local time (a Saturday)
FETCHED = "2026-10-17T07:00:00+00:00"  # 12:00 Astana: 7 h before NOW


def ev(i, kind="event", lat=KHAN[0], lon=KHAN[1] + 0.003, **kw):
    base = {
        "id": f"t:{i}",
        "source": "sxodim.com",
        "title": f"Событие {i}",
        "category": None,
        "kind": kind,
        "start": None,
        "end": None,
        "date_from": None,
        "date_to": None,
        "sessions": [],
        "hours_raw": None,
        "hours_osm": None,
        "price_text": None,
        "price_from": None,
        "url": f"https://example.kz/{i}",
        "fetched_at": FETCHED,
        "also_listed": [],
        "evidence": [],
        "venue": {
            "name": f"Зал {i}",
            "hall": None,
            "address": "ул. Туран, 1",
            "lat": lat,
            "lon": lon,
            "coords_source": "page",
            "poi_id": None,
            "poi_name": None,
            "match": None,
        },
    }
    base.update(kw)
    return base


def snap(*items, fetched_at=FETCHED):
    return events.Snapshot(tuple(items), fetched_at)


def ids(hits):
    return [h.id for h in hits]


def near(snapshot, when=NOW, **kw):
    return events.events_near(*KHAN, when, snapshot=snapshot, **kw)


# ---- the time window -------------------------------------------------------------------------------------------


def test_today_evening_is_in_past_is_out():
    s = snap(
        ev(1, start="2026-10-17T20:00:00+05:00"),  # in an hour
        ev(2, start="2026-10-17T10:00:00+05:00", end="2026-10-17T12:00:00+05:00"),  # this morning
        ev(3, start="2026-10-16T19:00:00+05:00"),  # yesterday evening
        ev(
            4, start="2026-10-17T18:00:00+05:00", end="2026-10-17T19:00:00+05:00"
        ),  # ended this very minute
        ev(5, start="2026-10-17T18:30:00+05:00", end="2026-10-17T19:30:00+05:00"),  # on now
        ev(6, start="2026-10-17T23:30:00+05:00"),  # after the 3-hour window
        ev(7, start="2026-10-18T19:00:00+05:00"),  # tomorrow
    )
    assert ids(near(s)) == ["t:5", "t:1"]
    assert [h.ongoing for h in near(s)] == [True, False]
    assert ids(near(s, window_min=300)) == ["t:5", "t:1", "t:6"]


def test_event_without_end_lasts_two_hours():
    s = snap(ev(1, start="2026-10-17T17:30:00+05:00"), ev(2, start="2026-10-17T16:59:00+05:00"))
    assert ids(near(s)) == ["t:1"]  # 17:30 + 2 h = 19:30 > 19:00; 16:59 + 2 h = 18:59 < 19:00
    assert near(s)[0].ongoing


def test_timezone_is_utc_plus_5_whatever_the_input_zone():
    s = snap(ev(1, start="2026-10-17T19:30:00+05:00"))
    assert ids(near(s, datetime(2026, 10, 17, 19, 0))) == ["t:1"]  # naive = Astana local
    assert ids(near(s, datetime(2026, 10, 17, 14, 0, tzinfo=UTC))) == [
        "t:1"
    ]  # 14:00 UTC = 19:00 Astana
    assert (
        ids(near(s, datetime(2026, 10, 17, 19, 0, tzinfo=UTC))) == []
    )  # 00:00 next day Astana: past
    assert near(s)[0].start == "2026-10-17T19:30:00+05:00"
    # a start written in another offset is the same instant
    s2 = snap(ev(1, start="2026-10-17T14:30:00+00:00"))
    assert near(s2)[0].start == "2026-10-17T19:30:00+05:00"


def test_cinema_sessions_are_listed_until_a_short_late_entry():
    sessions = [
        "2026-10-17T18:30:00+05:00",
        "2026-10-17T18:45:00+05:00",
        "2026-10-17T19:10:00+05:00",
        "2026-10-17T21:40:00+05:00",
        "2026-10-17T22:30:00+05:00",
    ]
    s = snap(
        ev(1, kind="sessions", sessions=sessions, date_from="2026-10-15", date_to="2026-10-18")
    )
    (hit,) = near(s)
    assert hit.sessions == (
        "2026-10-17T18:45:00+05:00",
        "2026-10-17T19:10:00+05:00",
        "2026-10-17T21:40:00+05:00",
    )
    assert hit.ongoing
    assert hit.start == "2026-10-17T18:45:00+05:00"
    done = snap(ev(1, kind="sessions", sessions=sessions[:1]))
    assert near(done) == []


def test_run_of_dates_counts_in_daytime_hours_of_its_days():
    run = ev(1, kind="run", date_from="2026-10-10", date_to="2026-10-17")
    assert ids(near(snap(run))) == ["t:1"]  # Saturday evening, its last day
    assert near(snap(run))[0].until == "2026-10-17"
    assert near(snap(run))[0].start is None
    assert near(snap(run), datetime(2026, 10, 17, 23, 0), window_min=60) == []  # after 22:00
    assert (
        near(snap(run), datetime(2026, 10, 17, 22, 30), window_min=600) == []
    )  # the run ends today
    next_day = ev(1, kind="run", date_from="2026-10-10", date_to="2026-10-18")
    assert (
        near(snap(next_day), datetime(2026, 10, 17, 22, 30), window_min=600) == []
    )  # 9:00 is after the window
    assert ids(near(snap(next_day), datetime(2026, 10, 17, 22, 30), window_min=700)) == ["t:1"]
    ended = ev(1, kind="run", date_from="2026-10-01", date_to="2026-10-16")
    assert near(snap(ended)) == []
    starts_later = ev(1, kind="run", date_from="2026-10-20", date_to="2026-10-25")
    assert near(snap(starts_later)) == []


def test_venue_with_hours_counts_while_open():
    museum = ev(1, kind="standing", hours_osm="Tu-Su 10:00-18:30", hours_raw="10:00-18:30 Tue-Sun")
    assert near(snap(museum), datetime(2026, 10, 17, 16, 0)) != []  # open Saturday afternoon
    assert near(snap(museum), datetime(2026, 10, 17, 18, 0))[0].ongoing
    assert near(snap(museum), datetime(2026, 10, 17, 19, 0)) == []  # closed
    soon = near(
        snap(museum), datetime(2026, 10, 17, 8, 0)
    )  # opens at 10:00, inside the 3-hour window
    assert soon[0].start == "2026-10-17T10:00:00+05:00"
    assert not soon[0].ongoing
    assert near(snap(museum), datetime(2026, 10, 19, 12, 0)) == []  # Monday: closed
    assert near(snap(ev(2, kind="standing", hours_osm=None)), datetime(2026, 10, 17, 12, 0)) == []


# ---- placing, order, silence ------------------------------------------------------------------------------------


def test_radius_coordinates_and_limit():
    s = snap(
        ev(1, start="2026-10-17T20:00:00+05:00", lon=KHAN[1] + 0.001),
        ev(2, start="2026-10-17T20:00:00+05:00", lon=KHAN[1] + 0.05),  # ~3.5 km
        ev(
            3, start="2026-10-17T20:00:00+05:00", lat=None, lon=None
        ),  # no place: nobody can be near it
    )
    assert ids(near(s)) == ["t:1"]
    assert ids(near(s, radius_m=5000)) == ["t:1", "t:2"]
    assert len(near(s, radius_m=5000, limit=1)) == 1
    assert near(s)[0].distance_m == pytest.approx(70, abs=10)


def test_order_is_start_then_distance_with_untimed_last():
    s = snap(
        ev(1, start="2026-10-17T20:30:00+05:00", lon=KHAN[1] + 0.001),
        ev(2, start="2026-10-17T20:00:00+05:00", lon=KHAN[1] + 0.008),
        ev(3, start="2026-10-17T20:00:00+05:00", lon=KHAN[1] + 0.002),
        ev(4, kind="run", date_from="2026-10-10", date_to="2026-10-20", lon=KHAN[1] + 0.0005),
        ev(
            5,
            start="2026-10-17T18:00:00+05:00",
            end="2026-10-17T19:30:00+05:00",
            lon=KHAN[1] + 0.009,
        ),
    )
    assert ids(near(s, radius_m=2000)) == ["t:5", "t:3", "t:2", "t:1", "t:4"]


def test_silent_without_events_never_says_there_are_none():
    past = snap(ev(1, start="2026-10-17T09:00:00+05:00"))
    assert events.nearby_events(*KHAN, NOW, snapshot=past) is None
    assert events.nearby_events(*KHAN, NOW, snapshot=snap()) is None
    assert events.load_snapshot("does/not/exist.json").events == ()
    for lang in i18n_events.LANGS:
        text = " ".join(
            v[i18n_events.LANGS.index(lang)] for v in i18n_events.STRINGS.values()
        ).casefold()
        assert "нет событий" not in text
        assert "событий нет" not in text
        assert "no events" not in text


def test_snapshot_age_and_stale_flag():
    fresh = events.nearby_events(
        *KHAN, NOW, snapshot=snap(ev(1, start="2026-10-17T20:00:00+05:00"))
    )
    assert fresh.stale is False
    assert fresh.fetched_at == FETCHED
    old = snap(
        ev(1, start="2026-10-17T20:00:00+05:00"), fetched_at="2026-10-15T20:00:00+00:00"
    )  # 42 h
    assert events.nearby_events(*KHAN, NOW, snapshot=old).stale is True
    assert snap(fetched_at=None).is_stale(NOW)  # an unknown age is not fresh
    assert old.age_hours(NOW) == pytest.approx(42)
    edge = snap(fetched_at=(NOW.replace(tzinfo=TZ5) - timedelta(hours=36)).isoformat())
    assert not edge.is_stale(NOW)
    assert edge.age_hours(NOW) == pytest.approx(36)


def test_hits_are_json_serializable_and_carry_source_and_link():
    s = snap(
        ev(1, start="2026-10-17T20:00:00+05:00", price_from=1500, price_text="от 1 500 тенге"),
        ev(2, kind="sessions", sessions=["2026-10-17T20:00:00+05:00"]),
    )
    result = events.nearby_events(*KHAN, NOW, snapshot=s)
    blob = json.loads(json.dumps(result.to_dict(), ensure_ascii=False))
    hit = blob["hits"][0]
    assert hit["source"] == "sxodim.com"
    assert hit["url"] == "https://example.kz/1"
    assert hit["price_from"] == 1500
    assert hit["fetched_at"] == FETCHED
    assert blob["fetched_at"] == FETCHED
    assert blob["stale"] is False
    assert isinstance(blob["hits"][1]["sessions"], list)


# ---- wording ----------------------------------------------------------------------------------------------------


def test_labels_in_three_languages():
    s = snap(
        ev(
            1,
            start="2026-10-17T20:00:00+05:00",
            price_from=3000,
            title="Концерт",
            source="qazaqconcert.kz",
        ),
        ev(
            2, kind="run", date_from="2026-10-10", date_to="2026-10-31", source="t.me/sxodim_astana"
        ),
        ev(3, kind="sessions", sessions=["2026-10-17T19:10:00+05:00", "2026-10-17T21:00:00+05:00"]),
        ev(4, start="2026-10-18T01:30:00+05:00"),
    )
    result = events.nearby_events(*KHAN, NOW, snapshot=s, window_min=600)
    out = {lang: events.format_block(result, lang, NOW) for lang in ("ru", "kk", "en")}
    assert out["ru"][0] == "Сегодня рядом:"
    assert out["kk"][0] == "Бүгін жақын жерде:"
    assert out["en"][0] == "Nearby today:"
    ru = "\n".join(out["ru"])
    assert "20:00 · Концерт — Зал 1, ул. Туран, 1 · от 3 000 ₸ · " in ru
    assert "источник: Қазақконцерт" in ru
    assert "до 31 окт" in ru
    assert "источник: @sxodim_astana" in ru
    assert "сеансы: 19:10, 21:00" in ru
    assert "18 окт 01:30" in ru
    assert "from 3 000 ₸" in "\n".join(out["en"])
    assert "sessions: 19:10, 21:00" in "\n".join(out["en"])
    assert "3 000 ₸-дан" in "\n".join(out["kk"])
    assert "31 мам" not in "\n".join(out["kk"])


def test_stale_note_is_shown_only_for_an_old_snapshot():
    old = snap(ev(1, start="2026-10-17T20:00:00+05:00"), fetched_at="2026-10-15T07:00:00+00:00")
    block = events.format_block(events.nearby_events(*KHAN, NOW, snapshot=old), "ru", NOW)
    assert "Афиша обновлялась 15 окт 12:00" in block[-1]
    block_en = events.format_block(events.nearby_events(*KHAN, NOW, snapshot=old), "en", NOW)
    assert "last updated 15 Oct 12:00" in block_en[-1]
    fresh = events.format_block(
        events.nearby_events(*KHAN, NOW, snapshot=snap(ev(1, start="2026-10-17T20:00:00+05:00"))),
        "ru",
        NOW,
    )
    assert len(fresh) == 2


# ---- the file and the CLI flag ----------------------------------------------------------------------------------


def test_load_snapshot_rereads_a_changed_file(tmp_path):
    """Rewrites within one file-clock tick keep the same mtime on Windows; a new size still forces a re-read."""
    import os

    path = tmp_path / "events.json"
    stamp = 1_700_000_000
    path.write_text(
        json.dumps({"schema": 1, "fetched_at": FETCHED, "events": [ev(1)]}), encoding="utf-8"
    )
    os.utime(path, (stamp, stamp))
    assert len(events.load_snapshot(path).events) == 1
    path.write_text(
        json.dumps({"schema": 1, "fetched_at": FETCHED, "events": [ev(1), ev(2)]}), encoding="utf-8"
    )
    os.utime(path, (stamp, stamp))
    assert len(events.load_snapshot(path).events) == 2
    path.write_text("{broken", encoding="utf-8")
    os.utime(path, (stamp + 5, stamp + 5))
    assert events.load_snapshot(path).events == ()


def test_shipped_events_file_has_the_schema_the_module_reads():
    path = Path(__file__).resolve().parents[2] / "data" / "events.json"
    if not path.exists():
        pytest.skip("data/events.json not built yet")
    doc = json.loads(path.read_text(encoding="utf-8"))
    assert doc["schema"] == 1
    assert doc["events"]
    for e in doc["events"]:
        assert e["kind"] in ("event", "run", "sessions", "standing")
        assert e["url"].startswith("http")
        assert e["source"]
        assert e["fetched_at"]
        assert e["evidence"]
        assert e["venue"]["name"]
    assert events.load_snapshot(path).events


def test_cli_events_flag(tmp_path, monkeypatch, capsys):
    path = tmp_path / "events.json"
    path.write_text(
        json.dumps(
            {
                "schema": 1,
                "fetched_at": FETCHED,
                "events": [
                    ev(
                        1,
                        start="2026-10-17T20:00:00+05:00",
                        title="Вечерний концерт",
                        price_from=2000,
                    ),
                    ev(2, start="2026-10-17T09:00:00+05:00", title="Утренняя ярмарка"),
                ],
            }
        ),
        encoding="utf-8",
    )
    monkeypatch.setattr(events, "DEFAULT_PATH", path)
    assert (
        cli.main(
            ["--events", "--lat", str(KHAN[0]), "--lon", str(KHAN[1]), "--time", "2026-10-17 19:00"]
        )
        == 0
    )
    out = capsys.readouterr().out
    assert "Сегодня рядом:" in out
    assert "Вечерний концерт" in out
    assert "Утренняя ярмарка" not in out
    assert "fetched_at=2026-10-17T07:00:00+00:00" in out
    assert "https://example.kz/1" in out
    assert (
        cli.main(["--events", "--lat", "51.2", "--lon", "71.6", "--time", "19:00", "--lang", "en"])
        == 0
    )
    quiet = capsys.readouterr().out
    assert "Nearby today" not in quiet
    assert "молчит" in quiet
    with pytest.raises(SystemExit):
        cli.main(["--events", "--time", "19:00"])  # no coordinates


def test_line_shows_a_clean_venue_name_once():
    cinema = ev(
        1,
        kind="sessions",
        sessions=["2026-10-17T19:10:00+05:00"],
        title="Чужая мама",
    )
    cinema["venue"]["name"] = "Chaplin Khan Shatyr (Чаплин Хан Шатыр), кинотеатр в городе Астана"
    museum = ev(2, kind="standing", hours_osm="Mo-Su 10:00-23:00", title="Museum")
    museum["venue"]["name"] = "Museum"
    result = events.nearby_events(*KHAN, NOW, snapshot=snap(cinema, museum))
    lines = events.format_block(result, "ru", NOW)
    assert "в городе" not in " ".join(lines)
    assert "Чужая мама — Chaplin Khan Shatyr (Чаплин Хан Шатыр), ул. Туран, 1" in " ".join(lines)
    assert "Museum — Museum" not in " ".join(lines)
