"""The replay-only fallback (WALKS_REPLAY_ONLY, no key, no network; deploy/vps/README.md) through the web server: every request the demo shows is
answered from data/demo_llm_cache.json, in the exact way the page sends it.

The 13 steps are the ones scripts/warm_cache.py records: the five scenario starters, the cold airport request, the
Kazakh request and the six follow-up chips. Each is sent like web/static/js/assistant.js sends it (the starter's own
text, place and time; a chip's phrase with the state of the previous answer). A model is never called: a miss would be
a template answer (generation "template"), and that is what these tests fail on."""

from __future__ import annotations

import json
import shutil
from pathlib import Path

import pytest
from starlette.testclient import TestClient

from walks import feedback, llm
from walks.dialog_types import Turn
from walks.presets import PRESETS
from web import server

DATA = Path(__file__).resolve().parents[2] / "data"
# (chip id, the starter whose answer it refines): the six chips of warm_cache.FOLLOW_UPS
CHIPS = (
    ("closer", "s0"),
    ("more", "s0"),
    ("no_alcohol", "s4"),
    ("cheaper", "s1"),
    ("kids", "s0"),
    ("longer", "s3"),
)


def _boom(*_a, **_kw):
    raise AssertionError("the replay-only stand must never call a model")


@pytest.fixture
def stand(tmp_path, monkeypatch):
    """The environment of the replay-only fallback, with the marks file a private copy of the tracked seed."""
    marks = tmp_path / "city_feedback.json"
    shutil.copy(DATA / "city_feedback.json", marks)
    for name, value in {
        "WALKS_ENV": "demo",
        "WALKS_DEMO_PIN": "1",
        "WALKS_CACHE_PIN": "1",
        "WALKS_REPLAY_ONLY": "1",
        "WALKS_FEEDBACK": str(marks),
        "WALKS_LLM_CACHE": str(
            tmp_path / "runtime_cache.json"
        ),  # `off` would switch the recording off too
        "WALKS_PROFILE_DIR": str(tmp_path / "profiles"),
    }.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setattr(
        server, "load_env_file", lambda: None
    )  # app/.env.demo is the developer's, not the stand's
    monkeypatch.setattr(llm, "ask", _boom)
    return TestClient(server.create_app())


class Page:
    """What the page does: the config of the stand, a turn per message."""

    def __init__(self, client: TestClient) -> None:
        self.client = client
        cfg = client.get("/api/config").json()
        self.cfg = cfg
        self.places = {p["id"]: p for p in cfg["presets"]}

    def starter(self, lang: str, sid: str) -> dict:
        return next(s for s in self.cfg["starters"][lang] if s["id"] == sid)

    def turn(
        self,
        text: str,
        preset: str,
        at: str | None,
        lang: str = "ru",
        state: dict | None = None,
        **extra,
    ):
        place = self.places[preset]
        body = {
            "text": text,
            "lat": place["lat"],
            "lon": place["lon"],
            "lang": lang,
            "lang_fixed": False,
            "at": at,
            "weather": "now",
            "budget_min": None,
            "company": None,
            "state": state,
            "profile_on": False,
            "profile_id": None,
        } | extra
        resp = self.client.post("/api/turn", json=body)
        assert resp.status_code == 200
        lines = [json.loads(x) for x in resp.text.splitlines() if x.strip()]
        assert "answer" in lines[-1], lines[-1]
        return lines[-1]["answer"]

    def start(self, lang: str, sid: str, **extra):
        s = self.starter(lang, sid)
        return self.turn(s["text"], s["preset"], s["at"], lang, **extra), s


def _from_the_recording(answer: dict) -> bool:
    turn = Turn.model_validate(answer["turn"])
    meta = turn.meta
    return (
        meta is not None
        and meta.generation == "llm"
        and meta.cached
        and (meta.model or "").startswith("gemini:")
    )


def _all_thirteen(page: Page) -> dict[str, bool]:
    """step -> served from the recording, for the 13 steps of the demo."""
    out: dict[str, bool] = {}
    answers: dict[str, dict] = {}
    for sid in ("s0", "s1", "s2", "s3", "s4", "r0"):
        answers[sid], _ = page.start("ru", sid)
        out[sid] = _from_the_recording(answers[sid])
    answer, _ = page.start("kk", "r1")
    out["r1"] = _from_the_recording(answer)
    for chip_id, sid in CHIPS:
        s = page.starter("ru", sid)
        before = answers[sid]
        chip = next(c for c in before["turn"]["chips"] if c["id"] == chip_id)
        follow = page.turn(chip["send"], s["preset"], s["at"], state=before["state"])
        out[f"{sid} → {chip_id}"] = _from_the_recording(follow)
    return out


def test_the_stand_serves_all_13_demo_steps_from_the_recording(stand):
    page = Page(stand)
    assert page.cfg["mode"] == {"offline": False, "replay_only": True, "ai": True, "demo_pin": True}
    served = _all_thirteen(page)
    assert len(served) == 13
    assert served == dict.fromkeys(served, True), [k for k, v in served.items() if not v]


@pytest.mark.parametrize("signal", sorted(feedback.SIGNALS))
def test_a_visitors_mark_does_not_move_the_recorded_answers(stand, signal):
    """The report button writes a mark; the next starter must still be the recorded request. (One «был: закрыто» on
    Degirmen, the first card of «Тихо, кофе, розетка», used to push the night starter to the template.)"""
    page = Page(stand)
    first, _ = page.start("ru", "s1")
    for place in first["turn"]["places"]:
        resp = stand.post("/api/report", json={"poi_id": place["id"], "signal": signal})
        assert resp.status_code == 200
    served = _all_thirteen(page)
    assert served == dict.fromkeys(served, True), [k for k, v in served.items() if not v]


def test_pinned_requests_use_the_seed_marks_with_or_without_live_models(tmp_path, monkeypatch):
    """A recorded scenario is answered with the marks it was recorded with, whatever visitors have marked since: on the
    stand with live models a changed candidate list would take the starter off its recording."""
    from walks import demo_pin

    marks = tmp_path / "city_feedback.json"
    shutil.copy(DATA / "city_feedback.json", marks)
    rows = json.loads(marks.read_text(encoding="utf-8"))
    marks.write_text(json.dumps([*rows, rows[0]]), encoding="utf-8")  # one more mark than the seed
    monkeypatch.setenv("WALKS_FEEDBACK", str(marks))
    for replay in ("", "1"):
        monkeypatch.setenv("WALKS_REPLAY_ONLY", replay)
        assert len(demo_pin.setup_for("Кафе").feedback) == len(rows)


def test_the_starters_send_the_places_of_the_recording(stand):
    page = Page(stand)
    for sid, preset in (
        ("s0", "Mega Silk Way"),
        ("s1", "Байтерек"),
        ("s2", "Хан Шатыр"),
        ("s3", "Аэропорт"),
        ("s4", "Байтерек"),
    ):
        assert page.starter("ru", sid)["preset"] == preset
        assert preset in PRESETS
    assert page.starter("ru", "s4")["at"] == "23:00"
