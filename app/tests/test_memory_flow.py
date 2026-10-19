"""The memory layers end to end: the CLI dialogue (the web UI side is in test_web.py) on the real dataset.

Every WALKS_* path points into tmp_path: the tests never write data/city_feedback.json or app/.local."""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime
from pathlib import Path

import pytest

from walks import cli

APP_DIR = Path(__file__).resolve().parents[1]
SEED = APP_DIR.parent / "data" / "city_feedback.json"
BAITEREK = ("51.1283", "71.4305")
CLI_BASE = ["--offline", "--weather", "off", "--no-walking", "--time", "2026-10-17 15:00"]
ASKED_AT = datetime(
    2026, 10, 17, 15, 0
)  # = CLI_BASE's --time and the UI tests' date_val / time_val


@pytest.fixture
def sandbox(tmp_path, monkeypatch, pin_clock):
    """Marks, profiles and dialogue state in tmp_path; the seed is copied so that it can be changed. The wall clock
    stands at the time the tests ask at: a mark stored by `--mark` or the UI is a fresh one at that time, on any day."""
    pin_clock(ASKED_AT)
    marks = tmp_path / "city_feedback.json"
    marks.write_text("[]", encoding="utf-8")
    monkeypatch.setenv("WALKS_FEEDBACK", str(marks))
    monkeypatch.setenv("WALKS_PROFILE_DIR", str(tmp_path / "profiles"))
    monkeypatch.setenv("WALKS_STATE_FILE", str(tmp_path / "conversation.json"))
    return tmp_path


def _run(capsys, *args: str) -> str:
    code = cli.main([*args, *CLI_BASE])
    out = capsys.readouterr().out
    assert code == 0, out
    return out


def _names(out: str) -> list[str]:
    return [m.group(1) for m in re.finditer(r"^\d\. (.+?) \[", out, re.M)]


# ---- CLI: layer 1 -----------------------------------------------------------------------------------


def test_cli_dialogue_request_closer_more(sandbox, capsys):
    first = _run(capsys, "--lat", BAITEREK[0], "--lon", BAITEREK[1], "--q", "Кафе", "--keep-state")
    shown1 = _names(first)
    assert shown1
    assert not (sandbox / "profiles").exists()
    closer = _run(capsys, "--follow-up", "--q", "а поближе?")
    assert "Диалог: Уточнение прошлого запроса: поближе (не дальше" in closer
    assert "Память: отсеяно диалогом 0" in closer
    more = _run(capsys, "--follow-up", "--q", "ещё")
    assert "Диалог: Уточнение прошлого запроса: без уже показанных мест" in more
    shown3 = _names(more)
    assert shown3
    assert not set(shown3) & (set(_names(first)) | set(_names(closer)))
    state = json.loads((sandbox / "conversation.json").read_text(encoding="utf-8"))
    assert state["turns"] == 3
    assert "Кафе" not in json.dumps(state, ensure_ascii=False)  # no request text in the state


def test_cli_follow_up_needs_a_saved_dialogue(sandbox):
    with pytest.raises(SystemExit, match="keep-state"):
        cli.main(["--follow-up", "--q", "ещё", *CLI_BASE])


def test_cli_without_keep_state_stores_no_dialogue(sandbox, capsys):
    _run(capsys, "--lat", BAITEREK[0], "--lon", BAITEREK[1], "--q", "Кафе")
    assert not (sandbox / "conversation.json").exists()


# ---- CLI: layer 3 -----------------------------------------------------------------------------------


def test_cli_marks_change_the_quiet_cafe_answer(sandbox, capsys):
    shutil.copy(SEED, sandbox / "city_feedback.json")  # the demo seed: Degirmen is already marked
    q = ["--lat", BAITEREK[0], "--lon", BAITEREK[1], "--q", "Тихое место с кофе и розеткой"]
    seeded = _run(capsys, *q)
    assert _names(seeded)[0] == "Degirmen"
    assert "по отметкам людей (примерные, не настоящие): есть розетка (3 отметки)" in seeded.lower()
    assert "Память: отсеяно диалогом 0, радиус ×1, кандидатов с отметками людей" in seeded
    (sandbox / "city_feedback.json").write_text("[]", encoding="utf-8")  # without any mark
    plain = _run(capsys, *q)
    assert _names(plain)[0] != "Degirmen"
    assert "по отметкам людей" not in plain
    # three people mark one more cafe, which the plain answer does not show: it enters the answer
    target = "node/6408271985"  # CrepeCafe near Baiterek, no Wi-Fi / socket in OSM
    assert "CrepeCafe" not in _names(plain)
    for _ in range(3):
        marked = _run_mark(capsys, f"{target}:has_socket")
        assert "Отметка сохранена" in marked
    after = _run(capsys, *q)
    assert "по отметкам людей: есть розетка (3 отметки)" in after.lower()
    assert "демо" not in after.lower().split("по отметкам людей:")[1].split("\n")[0]
    assert "CrepeCafe" in _names(after)
    rows = json.loads((sandbox / "city_feedback.json").read_text(encoding="utf-8"))
    assert len(rows) == 3
    assert all(set(r) == {"poi_id", "signal", "date", "weekday", "hour_bucket"} for r in rows)


def _run_mark(capsys, spec: str) -> str:
    assert cli.main(["--mark", spec]) == 0
    return capsys.readouterr().out


def test_cli_mark_rejects_an_unknown_signal(sandbox, capsys):
    assert cli.main(["--mark", "node/1:love_it"]) == 2
    assert "сигнал должен быть одним из" in capsys.readouterr().out


def test_cli_hours_from_people_are_a_separate_level(sandbox, capsys):
    q = ["--lat", BAITEREK[0], "--lon", BAITEREK[1], "--q", "Тихое место с кофе и розеткой"]
    # marrone rosso (0.39 км от Байтерек): без часов в OSM и с ПЕРСИСТИРОВАННЫМ промахом каталога
    # (catalog_match.jsonl: {poi_id: node/11910202470, match:false} — name+150 м, miss без часов навсегда),
    # часы картинки держатся только на людях; каталог-мёрж дал часы Drinkit (node/14100100182), поэтому
    # уровень людей проверяем на нём (was_open поднимает его на 1-е место)
    poi = "node/11910202470"
    assert "люди отмечали" not in _run(capsys, *q)
    # 2 × was_open дают уровень часов; розетка/Wi‑Fi/тихо поднимают карточку на 1-е место над Drinkit,
    # у которого после каталог-мёржа есть часы OSM (исходный node/14100100182 «no hours in OSM» больше не такой)
    for sig in ("was_open", "has_socket", "has_wifi", "quiet"):
        for _ in range(2):
            _run_mark(capsys, f"{poi}:{sig}")
    out = _run(capsys, *q)
    line = next(ln for ln in out.splitlines() if "люди отмечали открыто" in ln)
    assert re.search(
        r"часы: часы неизвестны; люди отмечали открыто \(2 раза, последний \d\d\.\d\d\) "
        r"\[по отметкам людей\]",
        line,
    )
    assert "по OSM" not in line.split("часы:")[1].split(";")[0]  # the OSM level still says unknown


# ---- CLI: layer 2 -----------------------------------------------------------------------------------


def test_cli_profile_is_remembered_reflected_and_forgotten(sandbox, capsys):
    uid = "2f9d1c2e-6a77-4d0e-9b0a-0d6a6f0c9a11"
    path = sandbox / "profiles" / f"{uid}.json"
    q = ["--lat", BAITEREK[0], "--lon", BAITEREK[1], "--q", "Кафе"]
    first = _run(capsys, *q, "--profile", uid, "--remember", "with_kids")
    assert "Профиль:" in first
    assert "Вы отмечали" not in first  # nothing was stored yet at that request
    assert path.exists()
    second = _run(capsys, *q, "--profile", uid)
    assert "Профиль: учтено with_kids" in second
    assert (
        "Вы отмечали" not in second
    )  # the dialogue lead says it once; the CLI prints the codes above
    assert '"with_kids":true' in second
    assert "Вы отмечали" not in _run(capsys, *q)  # the profile is opt-in: no --profile, no memory
    assert cli.main(["--profile", uid, "--forget"]) == 0
    assert "удалён" in capsys.readouterr().out
    assert not path.exists()
    assert "Вы отмечали" not in _run(capsys, *q, "--profile", uid)


def test_cli_remember_needs_a_profile(sandbox):
    with pytest.raises(SystemExit):
        cli.main(["--lat", "51", "--lon", "71", "--q", "Кафе", "--remember", "quiet", *CLI_BASE])
