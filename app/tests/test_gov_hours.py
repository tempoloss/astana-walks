"""Hours of state objects (walks.gov_hours): scope rules, the weekday question, the card line, the CLI lines."""

from __future__ import annotations

import json
from datetime import date, datetime

import pytest

from walks import cli, gov_hours
from walks.i18n_gov import GOV_STRINGS, WEEKDAY_STEMS

SAT = datetime(2026, 10, 17, 10, 0)  # a Saturday, not a public holiday
SUN = datetime(2026, 10, 18, 10, 0)
MON_NIGHT = datetime(2026, 10, 19, 22, 0)
SRC = {
    "source": "state_registry",
    "license": "открытые данные госоргана РК",
    "snapshot_date": "2026-10-17",
    "url": "https://gov4c.kz/ru/contacts/speccony/287/",
    "snippet": "x",
}


def cson(pid, name, hours, lat=51.09, lon=71.42, **extra):
    p = {
        "id": pid,
        "name": name,
        "lat": lat,
        "lon": lon,
        "address": "ул. Мангилик ел, 30",
        "sources": ["state_registry"],
        "source": "state_registry",
        "opening_hours": hours,
        "hours_unqualified": None,
        "state_registry_match": {
            "kind": "cson",
            "source": "gov4c.kz",
            "url": SRC["url"],
            "hours_scope": "venue",
        },
        "field_sources": {"opening_hours": SRC, "name": SRC} if hours else {"name": SRC},
    }
    p.update(extra)
    return p


ESIL = cson("gov/cson/a", "Отдел района «Есиль»", "Mo-Fr 09:00-20:00; Sa 09:00-13:00")
ALMATY = cson("gov/cson/b", "Отдел №1 района «Алматы»", "Mo-Fr 09:00-18:00", lat=51.13, lon=71.43)
NOHOURS = cson("gov/cson/c", "Сектор без часов", None, lat=51.10, lon=71.40)
UNQ = cson(
    "gov/cson/d",
    "Сектор «с 10 до 22»",
    None,
    hours_unqualified="с 10:00 до 22:00",
    field_sources={"name": SRC, "hours_unqualified": SRC},
)
ALAU = {
    "id": "way/1",
    "name": "Ледовый дворец Алау",
    "lat": 51.10,
    "lon": 71.40,
    "address": "x",
    "opening_hours": None,
    "sources": ["osm", "state_registry"],
    "source": "osm",
    "hours_unqualified": None,
    "admin_hours": {
        "raw": "08:30-18:00",
        "scope": "administration",
        "registry": "ГККП «Ледовый дворец «Алау»",
    },
    "state_registry_match": {
        "kind": "sport_facility",
        "source": "data.egov.kz",
        "url": "https://data.egov.kz/x",
    },
    "field_sources": {"admin_hours": {**SRC, "url": "https://data.egov.kz/x"}},
}
CAFE = {
    "id": "n/1",
    "name": "Кофейня",
    "lat": 51.09,
    "lon": 71.42,
    "sources": ["osm"],
    "opening_hours": "Mo-Su 08:00-22:00",
    "field_sources": {},
}
DATA = [ESIL, ALMATY, NOHOURS, UNQ, ALAU, CAFE]


def test_day_intervals_follow_the_weekday():
    raw = "Mo-Fr 09:00-20:00; Sa 09:00-13:00"
    assert gov_hours.day_intervals(raw, date(2026, 10, 17)) == [("09:00", "13:00")]
    assert gov_hours.day_intervals(raw, date(2026, 10, 19)) == [("09:00", "20:00")]
    assert gov_hours.day_intervals(raw, date(2026, 10, 18)) == []  # Sunday: closed
    assert gov_hours.day_intervals(None, date(2026, 10, 18)) == []
    assert gov_hours.day_intervals("not hours", date(2026, 10, 18)) == []


def test_saturday_hours_of_a_branch():
    r = gov_hours.gov_hours(ESIL, SAT)
    assert (r.scope, r.state, r.day_open, r.day_text, r.day) == (
        "venue",
        "open",
        True,
        "09:00-13:00",
        "сб",
    )
    assert r.line.startswith("сб: 09:00-13:00")
    assert "gov4c.kz" in r.line
    assert gov_hours.gov_hours(ESIL, SUN).line.startswith("вс: закрыто")
    assert gov_hours.gov_hours(ESIL, MON_NIGHT).state == "closed"
    assert gov_hours.gov_hours(ESIL, SAT, "en").line.startswith("Sat: 09:00-13:00")


def test_missing_hours_are_unknown_never_closed():
    r = gov_hours.gov_hours(NOHOURS, SAT)
    assert (r.state, r.scope, r.day_open) == ("unknown", None, None)
    assert "данных нет" in r.line
    q = gov_hours.gov_hours(UNQ, SAT)
    assert q.state == "unknown"
    assert "без дней" in q.line
    assert q.hours == "с 10:00 до 22:00"


def test_administration_hours_never_answer_open_or_closed():
    r = gov_hours.gov_hours(ALAU, SAT)
    assert (r.scope, r.state, r.day_open) == ("administration", "unknown", None)
    assert "не часы работы объекта" in r.line
    assert r.hours == "08:30-18:00"
    assert gov_hours.gov_hours(ALAU, MON_NIGHT).state == "unknown"  # 22:00: still not «closed»


def test_hours_not_from_the_registry_are_ignored():
    osm_hours = {**ESIL, "field_sources": {"opening_hours": {**SRC, "source": "osm"}, "name": SRC}}
    assert gov_hours.gov_hours(osm_hours, SAT).scope is None


def test_card_line_only_for_state_objects():
    assert gov_hours.card_line(CAFE, SAT) is None
    assert gov_hours.card_line(ESIL, SAT, "kk").startswith("сб: 09:00-13:00")
    assert gov_hours.card_line(ALAU, SAT, "ru")


def test_lookup_open_that_day_first_then_nearest():
    rows = gov_hours.lookup(DATA, SAT, kind="cson", near=(51.09, 71.42))
    assert rows[0].poi_id == "gov/cson/a"
    assert rows[0].day_open
    sun = gov_hours.lookup(DATA, SUN, kind="cson", near=(51.09, 71.42), open_that_day=True)
    assert sun == []
    sat = gov_hours.lookup(DATA, SAT, kind="cson", near=(51.09, 71.42), open_that_day=True)
    assert [r.poi_id for r in sat] == ["gov/cson/a"]
    assert sat[0].distance_m == 0
    assert [r.poi_id for r in gov_hours.lookup(DATA, SAT, kind="sport_facility")] == ["way/1"]
    assert {r.kind for r in gov_hours.lookup(DATA, SAT, kind=None)} == {"cson", "sport_facility"}


def test_rows_are_json_serialisable():
    payload = json.dumps(
        gov_hours.to_json(gov_hours.lookup(DATA, SAT, kind=None)), ensure_ascii=False
    )
    assert json.loads(payload)[0]["poi_id"]


@pytest.mark.parametrize(
    ("q", "kind", "weekday"),
    [
        ("ЦОН в субботу", "cson", 5),
        ("центр обслуживания населения в воскресенье", "cson", 6),
        ("ХҚКО сенбіде", "cson", 5),
        ("Public Service Centre on Monday", "cson", 0),
        ("ЦОН завтра", "cson", -2),
        ("ЦОН сегодня", "cson", -1),
        ("ЦОН", "cson", None),
        ("спортивный комплекс в пятницу", "sport_facility", 4),
        ("кофе в субботу", None, 5),
    ],
)
def test_parse_query(q, kind, weekday):
    assert gov_hours.parse_query(q) == (kind, weekday)


def test_target_date_is_the_next_such_weekday():
    assert gov_hours.target_date(5, datetime(2026, 10, 14, 15, 30)) == datetime(2026, 10, 17, 10, 0)
    assert gov_hours.target_date(2, datetime(2026, 10, 14, 15, 30)) == datetime(
        2026, 10, 14, 10, 0
    )  # today
    assert gov_hours.target_date(-2, datetime(2026, 10, 14, 15, 30)) == datetime(
        2026, 10, 15, 10, 0
    )
    assert gov_hours.target_date(None, datetime(2026, 10, 14, 15, 30)) == datetime(
        2026, 10, 14, 15, 30
    )


def test_cli_lookup_offline(tmp_path, capsys):
    path = tmp_path / "poi.json"
    path.write_text(json.dumps(DATA, ensure_ascii=False), encoding="utf-8")
    lines = gov_hours.run_cli(
        "cson", "ЦОН в субботу", 51.09, 71.42, datetime(2026, 10, 14, 12, 0), path
    )
    text = "\n".join(lines)
    assert "2026-10-17 10:00" in text
    assert "сб: 09:00-13:00" in text
    assert "[gov/cson/a]" in text
    assert "Ледовый дворец" not in text  # sport objects are another kind


def test_cli_flag_wiring(capsys):
    rc = cli.main(["--gov-hours", "--q", "ЦОН в субботу", "--time", "2026-10-14 12:00"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "ЦОН" in out
    assert "2026-10-17 10:00" in out


def test_cli_says_how_many_registry_objects_have_no_coordinates(tmp_path):
    (tmp_path / "poi.json").write_text(json.dumps(DATA, ensure_ascii=False), encoding="utf-8")
    when = datetime(2026, 10, 14, 12, 0)
    # no build stats next to the dataset: the line is absent, not «0»
    assert "без координат" not in "\n".join(
        gov_hours.run_cli("cson", "ЦОН", None, None, when, tmp_path / "poi.json")
    )
    stats = {
        "state_registry": {
            "unmapped_records": [{"kind": "cson"}, {"kind": "cson"}, {"kind": "sport_facility"}]
        }
    }
    (tmp_path / "poi_enriched_stats.json").write_text(json.dumps(stats), encoding="utf-8")
    cson_lines = gov_hours.run_cli("cson", "ЦОН", None, None, when, tmp_path / "poi.json")
    assert "ещё 2 объектов реестра без координат" in "\n".join(cson_lines)
    assert (
        gov_hours.unmapped_count("sport_facility", tmp_path / "poi.json") is None
    )  # sport only attaches


def test_shipped_dataset_has_saturday_hours_of_branches():
    rows = gov_hours.lookup(gov_hours.load_dataset(), SAT, kind="cson", open_that_day=True)
    assert rows, "the shipped dataset carries ЦОН branches open on Saturday"
    assert all(r.scope == "venue" and r.day_open and r.url and "gov4c.kz" in r.url for r in rows)
    admin = gov_hours.lookup(gov_hours.load_dataset(), SAT, kind="sport_facility")
    assert admin
    assert all(r.scope == "administration" and r.state == "unknown" for r in admin)


def test_strings_cover_three_languages_and_weekdays():
    assert all(len(v) == 3 and all(v) for v in GOV_STRINGS.values())
    assert len(WEEKDAY_STEMS) == 7
