"""How fast the answers are, and what the page shows while one is made: the request log carries each answer's total
time (walks.reqlog), the «Данные» page reads the median and the 95th percentile from it (web.speed), the core reports
its real steps as it enters them (walks.dialog, walks.pipeline), and a repeated request is answered from the cache with
its rewrite (walks.generate). The rewrite of vague cards is asked only while the turn has time left for it, and never
of a link that has just timed out (walks.llm)."""

from __future__ import annotations

import json
import threading
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from starlette.testclient import TestClient

from tests.test_answer_quality import _cand, _city, _rec
from walks import generate as gen_mod
from walks import intent as intent_mod
from walks import llm, llm_providers
from walks.dialog import TurnEnv, new_state, take_turn
from walks.intent import parse_rules
from walks.llm_output import LLMOutput, LLMRec
from walks.models import Intent, LLMStep, load_pois
from walks.pipeline import recommend
from walks.presets import PRESETS
from walks.reqlog import held, write_held
from walks.specific import is_generic
from walks.walking import offline_router
from web import speed
from web.server import create_app

FIXTURE = Path(__file__).parent / "fixtures" / "poi_sample.json"
NOON = datetime(2026, 10, 14, 12, 0)
EXPO = PRESETS["EXPO"]
BAITEREK = PRESETS["Байтерек"]


@pytest.fixture
def client(monkeypatch, tmp_path):
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    monkeypatch.setenv("WALKS_PROFILE_DIR", str(tmp_path / "profiles"))
    (tmp_path / "marks.json").write_text("[]", encoding="utf-8")
    return TestClient(create_app())


def _lines(path: Path) -> list[dict]:
    return [json.loads(x) for x in path.read_text(encoding="utf-8").splitlines()]


def _log_times(path: Path, times: list[int | None]) -> None:
    rows = [
        {"cell": "1_1", "ts_hour": "2026-10-14T12:00"} | ({} if t is None else {"total_ms": t})
        for t in times
    ]
    path.write_text("".join(json.dumps(r) + "\n" for r in rows), encoding="utf-8")


# ---- the log ----------------------------------------------------------------------------------------


def test_a_logged_request_carries_the_total_time_of_its_answer(tmp_path, monkeypatch):
    log = tmp_path / "requests.jsonl"
    monkeypatch.setenv("WALKS_REQUEST_LOG", str(log))
    res = recommend("кофе", *EXPO, NOON, use_llm=False, pois=load_pois(FIXTURE))
    (row,) = _lines(log)
    assert row["total_ms"] == res.timings_ms["total"]


def test_held_records_are_written_with_the_time_of_the_whole_turn(tmp_path, monkeypatch):
    log = tmp_path / "requests.jsonl"
    monkeypatch.setenv("WALKS_REQUEST_LOG", str(log))
    with held() as records:
        recommend("кофе", *EXPO, NOON, use_llm=False, pois=load_pois(FIXTURE))
        assert not log.exists()  # nothing is written before the turn's own time is known
    write_held(records, 4321)
    (row,) = _lines(log)
    assert row["total_ms"] == 4321
    assert set(row) - {"total_ms"} == set(records[0]) - {"total_ms"}


def test_a_web_turn_logs_the_time_from_the_message_to_the_answer(client, tmp_path, monkeypatch):
    log = tmp_path / "requests.jsonl"
    monkeypatch.setenv("WALKS_REQUEST_LOG", str(log))
    res = client.post(
        "/api/turn", json={"text": "хочу кофе", "lat": BAITEREK[0], "lon": BAITEREK[1]}
    )
    assert res.status_code == 200
    (row,) = _lines(log)
    assert isinstance(row["total_ms"], int)
    assert row["total_ms"] > 0
    raw = log.read_text(encoding="utf-8")
    assert "хочу кофе" not in raw  # still anonymous: no text, no point
    assert "51.1283" not in raw


# ---- the «Данные» page -------------------------------------------------------------------------------


def test_the_median_and_the_95th_percentile_come_from_the_logged_times(tmp_path, monkeypatch):
    log = tmp_path / "requests.jsonl"
    _log_times(
        log, [1000 * s for s in range(1, 21)] + [None]
    )  # 1..20 s, and an older record without a time
    monkeypatch.setenv("WALKS_REQUEST_LOG", str(log))
    assert speed.answer_times() == {"requests": 20, "median_s": 10.5, "p95_s": 19.0}


def test_the_rotated_log_counts_too_and_a_damaged_line_is_skipped(tmp_path, monkeypatch):
    log = tmp_path / "requests.jsonl"
    _log_times(log, [2000, 4000])
    _log_times(tmp_path / "requests.jsonl.1", [3000])
    with log.open("a", encoding="utf-8") as fh:
        fh.write("{broken\n")
    monkeypatch.setenv("WALKS_REQUEST_LOG", str(log))
    assert speed.answer_times() == {"requests": 3, "median_s": 3.0, "p95_s": 4.0}


@pytest.mark.parametrize("state", ["missing", "empty", "off", "no_times"])
def test_an_empty_log_says_no_time_was_measured(tmp_path, monkeypatch, state):
    log = tmp_path / "requests.jsonl"
    if state == "empty":
        log.write_text("", encoding="utf-8")
    if state == "no_times":
        _log_times(log, [None, None])
    monkeypatch.setenv("WALKS_REQUEST_LOG", "off" if state == "off" else str(log))
    assert speed.answer_times() == {"requests": 0}


def test_the_data_page_carries_the_response_time(client, tmp_path, monkeypatch):
    log = tmp_path / "requests.jsonl"
    _log_times(log, [1200, 2400, 6000])
    monkeypatch.setenv("WALKS_REQUEST_LOG", str(log))
    body = client.get("/api/data?lang=ru").json()
    assert body["speed"] == {"requests": 3, "median_s": 2.4, "p95_s": 6.0}
    strings = client.get("/api/strings").json()
    assert strings["dd_speed"][1] == "Время ответа: медиана {med} с, 95 % быстрее {p95} с."
    assert all(strings[k] for k in ("dd_speed_none", "dd_req_one", "dd_req_many", "data_speed"))


# ---- the steps while an answer is made -----------------------------------------------------------------


class Chains:
    """The intent chain answers `reading`, the generation chain picks the first three candidates."""

    def __init__(self, monkeypatch, reading: Intent | None = None):
        self.reading = reading
        monkeypatch.setattr(llm, "llm_available", lambda: True)
        monkeypatch.setattr(intent_mod, "generate_json", self.intent)
        monkeypatch.setattr(gen_mod, "generate_json", self.generation)

    def intent(self, prompt, schema, **kw):
        draft = prompt.split("Draft Intent from the rule parser:\n", 1)[1].split("\n", 1)[0]
        value = self.reading or Intent.model_validate_json(draft)
        return llm.LLMCall(value, LLMStep(chain=["m"], model="m"))

    def generation(self, prompt, schema, **kw):
        ids = [c["poi_id"] for c in json.loads(prompt)["candidates"]][:3]
        recs = [
            LLMRec(
                poi_id=i,
                why="Здесь варят кофе.",
                time_on_site_min=30,
                what_to_do="Возьмите кофе.",
                confidence="medium",
                generated_idea=False,
            )
            for i in ids
        ]
        return llm.LLMCall(LLMOutput(recommendations=recs), LLMStep(chain=["m"], model="m"))


def _stages(text: str, **env) -> list[str]:
    stages: list[str] = []
    take_turn(
        new_state(*EXPO, "ru"),
        text,
        TurnEnv(
            when=NOON,
            router=offline_router(),
            pois=load_pois(FIXTURE),
            on_stage=stages.append,
            **env,
        ),
    )
    return stages


def test_the_steps_of_a_search_come_in_the_order_the_core_enters_them():
    assert _stages("хочу кофе", use_llm=False) == ["parse", "search", "hours", "write", "route"]


def test_a_message_that_is_not_a_search_reports_only_the_reading():
    assert _stages("спасибо", use_llm=False) == ["parse"]


def test_a_reading_the_model_changes_searches_again_and_says_so(monkeypatch):
    Chains(
        monkeypatch,
        Intent(categories=["attraction_landmark", "viewpoint", "museum_gallery", "park_garden"]),
    )
    stages = _stages("что посмотреть")
    assert stages[0] == "parse"
    assert stages[-1] == "route"
    assert (
        stages.count("search") == 2
    )  # the rules' places first, then the model's reading searched anew
    assert stages.index("write") < len(stages) - 1 - stages[::-1].index("search")


def test_a_confident_message_goes_straight_to_the_search(monkeypatch):
    Chains(monkeypatch)
    assert _stages("кофе рядом") == ["parse", "search", "hours", "write", "route"]


def test_the_stream_sends_every_step_before_the_answer(client):
    res = client.post(
        "/api/turn", json={"text": "хочу кофе", "lat": BAITEREK[0], "lon": BAITEREK[1]}
    )
    lines = [json.loads(line) for line in res.text.strip().splitlines()]
    assert [x["stage"] for x in lines[:-1]] == ["parse", "search", "hours", "write", "route"]
    assert "answer" in lines[-1]


# ---- the cache -----------------------------------------------------------------------------------------


def test_a_repeated_request_takes_the_answer_and_its_rewrite_from_the_cache(monkeypatch, tmp_path):
    """The first answer has a vague reason, so the model is asked once more for that card; the same request again (same
    candidates, same half hour) asks no model at all and shows the same cards."""
    monkeypatch.setenv("WALKS_LLM_CACHE", str(tmp_path / "llm_cache.json"))
    monkeypatch.setattr(llm, "_usable", lambda spec: True)
    monkeypatch.setattr(llm, "_skip_reason", lambda spec, role: (SimpleNamespace(label=spec), None))
    monkeypatch.setattr(gen_mod, "ai_off_reason", lambda use_llm: "")
    calls: list[bool] = []

    def ask(link, prompt, system, schema, timeout_s):
        rewrite = "rewrite" in json.loads(prompt)
        calls.append(rewrite)
        why = "Местная кухня и столики на улице." if rewrite else "Отлично подходит для ужина."
        return LLMOutput(recommendations=[_rec("rest1", why)])

    monkeypatch.setattr(llm, "ask", ask)
    cands = [_cand(p) for p in _city()[:2]]
    intent = parse_rules("хочу поесть").intent
    first = gen_mod.generate(intent, *EXPO, cands, NOON, use_llm=True)
    assert calls == [False, True]
    again = gen_mod.generate(intent, *EXPO, cands, NOON, use_llm=True)
    assert calls == [False, True]  # nothing asked the second time
    assert [(r.poi.id, r.why) for r in again.recs] == [(r.poi.id, r.why) for r in first.recs]
    assert "столики на улице" in again.recs[0].why


# ---- the time budget of the rewrite ----------------------------------------------------------------------------


def _timed_chain(monkeypatch, first_s: float) -> list[dict]:
    """The generation chain on a fake clock: a vague first answer that takes `first_s` of the request's time, then a
    specific rewrite. Returns the payloads the chain was asked with."""
    now = [100.0]
    monkeypatch.setattr(llm, "_clock", lambda: now[0])
    monkeypatch.setattr(gen_mod, "ai_off_reason", lambda use_llm: "")
    seen: list[dict] = []

    def ask(prompt, schema, **kw):
        payload = json.loads(prompt)
        seen.append(payload)
        now[0] += first_s if len(seen) == 1 else 4.0
        why = _SPECIFIC if "rewrite" in payload else _VAGUE
        return llm.LLMCall(
            LLMOutput(recommendations=[_rec("rest1", why)]), LLMStep(chain=["m"], model="m")
        )

    monkeypatch.setattr(gen_mod, "generate_json", ask)
    return seen


_VAGUE = "Отлично подходит для ужина."
_SPECIFIC = "Местная кухня и столики на улице."


def _answer(deadline: llm.Deadline):
    cands = [_cand(p) for p in _city()[:2]]
    intent = parse_rules("хочу поесть").intent
    return gen_mod.generate(intent, *EXPO, cands, NOON, use_llm=True, deadline=deadline)


def _card(gen, poi_id: str):
    return next(r for r in gen.recs if r.poi.id == poi_id)


def test_a_slow_first_answer_is_not_rewritten_and_its_vague_card_is_the_template_s(monkeypatch):
    seen = _timed_chain(monkeypatch, first_s=llm.REWRITE_CUTOFF_S + 0.5)
    gen = _answer(llm.Deadline())
    assert len(seen) == 1  # the turn has spent its share on the first answer: no second call
    assert gen.mode == "llm"
    card = _card(gen, "rest1")
    assert card.text_source == "template"  # the record's own facts (walks.reasons), not the filler
    assert not is_generic(card.why)


def test_a_first_answer_in_time_is_still_rewritten(monkeypatch):
    seen = _timed_chain(monkeypatch, first_s=llm.REWRITE_CUTOFF_S - 0.5)
    gen = _answer(llm.Deadline())
    assert [p.get("rewrite") for p in seen] == [None, ["rest1"]]
    card = _card(gen, "rest1")
    assert card.text_source == "llm"
    assert card.why.startswith(_SPECIFIC)


def test_the_rewrite_and_the_next_turn_skip_a_link_that_timed_out(monkeypatch):
    """A hung link is cut at its own limit and trips the breaker: the rewrite of the same turn and the next turn go
    straight to the next link instead of waiting for the hung one again."""
    monkeypatch.setenv("LLM_CHAIN", "gemini:hung,gemini:ok")
    monkeypatch.setattr(llm_providers, "gemini_key", lambda: "k")
    monkeypatch.setattr(gen_mod, "ai_off_reason", lambda use_llm: "")
    monkeypatch.setattr(gen_mod, "GENERATION_TIMEOUT_S", 0.05)
    release = threading.Event()
    asked: list[str] = []

    def ask(link, prompt, system, schema, timeout_s):
        asked.append(link.model)
        if link.model == "hung":
            release.wait(5)  # abandoned by walks.llm._with_deadline, never joined
        why = _SPECIFIC if "rewrite" in json.loads(prompt) else _VAGUE
        return LLMOutput(recommendations=[_rec("rest1", why)])

    monkeypatch.setattr(llm, "ask", ask)
    try:
        first = _answer(llm.Deadline())
        assert asked == ["hung", "ok", "ok"]  # the rewrite did not wait for the hung link again
        assert first.step is not None
        assert first.step.attempts[0].status == "skipped"
        _answer(llm.Deadline())
        assert asked[3:] == ["ok", "ok"]  # nor did the next turn
    finally:
        release.set()
