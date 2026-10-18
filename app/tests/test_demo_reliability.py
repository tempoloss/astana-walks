"""Demo reliability: the demo preset (walks.demo_pin), the warm-up script on the same code path, public-only
recording, the ignored feedback copy and the live timeout budget. Fake providers only; nothing touches the network."""

from __future__ import annotations

import hashlib
import json
import sys
import threading
import time
from datetime import datetime
from pathlib import Path

import httpx
import pytest

from walks import demo_pin, feedback, llm, llm_providers, walking
from walks.cli import main as cli_main
from walks.models import Intent, LLMOutput, LLMRec
from walks.presets import PRESETS, SCENARIOS

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP / "scripts"))
import warm_cache  # noqa: E402

SEED = feedback.SEED_PATH
QUIET = "Тихое место с кофе и розеткой"
NIGHT = "Необычная ночная активность"


# ---------------------------------------------------------------- feedback copy


def _digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_marks_go_to_an_ignored_copy_seeded_from_the_tracked_file(tmp_path, monkeypatch):
    monkeypatch.delenv("WALKS_FEEDBACK")
    local = tmp_path / ".local" / "city_feedback.json"
    monkeypatch.setattr(feedback, "LOCAL_PATH", local)
    before = _digest(SEED)
    assert not local.exists()
    assert len(feedback.load_feedback()) == len(json.loads(SEED.read_text(encoding="utf-8")))
    assert local.exists()  # seeded on first use
    feedback.add_feedback("node/1", "quiet", datetime(2026, 10, 19, 14, 0))
    rows = json.loads(local.read_text(encoding="utf-8"))
    assert rows[-1]["poi_id"] == "node/1"
    assert len(rows) == len(json.loads(SEED.read_text(encoding="utf-8"))) + 1
    assert _digest(SEED) == before  # the tracked file is never written


def test_a_mark_on_a_fresh_clone_seeds_then_appends(tmp_path, monkeypatch):
    monkeypatch.delenv("WALKS_FEEDBACK")
    local = tmp_path / "city_feedback.json"
    monkeypatch.setattr(feedback, "LOCAL_PATH", local)
    feedback.add_feedback(
        "node/2", "noisy", datetime(2026, 10, 19, 9, 0)
    )  # the very first call is a write
    rows = json.loads(local.read_text(encoding="utf-8"))
    assert [r["poi_id"] for r in rows][-1] == "node/2"
    assert any(r.get("demo") for r in rows)  # the demo seed came along


def test_walks_feedback_overrides_the_path_and_is_not_seeded(tmp_path, monkeypatch):
    path = tmp_path / "mine.json"
    monkeypatch.setenv("WALKS_FEEDBACK", str(path))
    assert feedback.feedback_path() == path
    assert len(feedback.load_feedback()) == 0
    assert not path.exists()


def test_the_demo_pin_has_its_own_copy_of_the_seed(tmp_path, monkeypatch):
    monkeypatch.delenv("WALKS_FEEDBACK")
    monkeypatch.setenv("WALKS_DEMO_PIN", "1")
    monkeypatch.setattr(feedback, "LOCAL_PATH", tmp_path / "city_feedback.json")
    monkeypatch.setattr(feedback, "DEMO_PATH", tmp_path / "city_feedback.demo.json")
    assert feedback.feedback_path() == tmp_path / "city_feedback.demo.json"
    feedback.add_feedback("node/3", "quiet", datetime(2026, 10, 19, 9, 0))
    assert not (tmp_path / "city_feedback.json").exists()
    feedback.reseed(tmp_path / "city_feedback.demo.json")
    assert len(feedback.read_entries()) == len(json.loads(SEED.read_text(encoding="utf-8")))


# ---------------------------------------------------------------- the demo preset


def test_every_scenario_has_one_fixed_moment():
    for sc in SCENARIOS:
        when = demo_pin.when_for(sc.text)
        assert when.date() == demo_pin.PIN_DATE
        assert when.time() == (sc.at or demo_pin.DEFAULT_TIME)
    assert demo_pin.when_for(NIGHT).hour == 23
    assert (
        demo_pin.when_for("а без алкоголя", NIGHT).hour == 23
    )  # a follow-up keeps its scenario's moment


def test_pinned_weather_is_normal_except_for_cold_and_smog_scenarios():
    normal = demo_pin.weather_for(QUIET)
    assert (normal.apparent_c, normal.pm25, normal.adverse, normal.air_bad) == (
        10.0,
        5.0,
        False,
        False,
    )
    assert normal.source == "manual"
    assert demo_pin.weather_for("Турист, на улице холод, 2 часа до вылета").adverse
    assert demo_pin.weather_for("Куда пойти, если в городе смог").air_bad
    assert demo_pin.weather_for("а подешевле", "Куда пойти, если в городе смог").air_bad


def test_the_pinned_router_reads_the_shipped_cache_and_never_the_network(monkeypatch):
    router = walking.shipped_router()
    cached = json.loads(walking.SHIPPED_CACHE_PATH.read_text(encoding="utf-8"))
    a, _, b = next(iter(cached)).partition(">")
    pa, pb = (tuple(map(float, x.split(","))) for x in (a, b))
    hit = router.leg(pa, pb)
    assert (hit.method, hit.from_cache) == ("valhalla", True)
    miss = router.leg((51.0, 71.0), (51.5, 71.5))
    assert miss.method == "straight"
    assert router.network_calls == 0


def test_public_links_are_gemini_and_the_alem_profile_only(monkeypatch):
    assert llm_providers.is_public("gemini:gemini-2.5-flash")
    assert llm_providers.is_public("openai:alemllm@alem")
    assert not llm_providers.is_public("openai:some/model@gw")
    assert not llm_providers.is_public("openai:gpt-x")  # OPENAI_BASE_URL is the user's own
    monkeypatch.setenv("LLM_PROFILE_ALEM_BASE_URL", "https://my-proxy.example.test/v1")
    assert not llm_providers.is_public("openai:alemllm@alem")
    monkeypatch.setenv("LLM_PROFILE_ALEM_BASE_URL", "https://llm.alem.ai/v1/")
    assert llm_providers.is_public("openai:alemllm@alem")
    assert not llm_providers.is_public("nonsense")


# ---------------------------------------------------------------- the warm-up is the stage


class FakeModel:
    """Replaces the provider call: a valid intent and a one-card answer built from the first candidate."""

    def __init__(self, monkeypatch, *, fail: bool = False):
        self.calls: list[str] = []
        self.fail = fail
        monkeypatch.setattr(llm, "ask", self)
        monkeypatch.setattr(llm_providers, "gemini_key", lambda: "k")

    def __call__(self, link, prompt, system, schema, timeout_s):
        self.calls.append(link.label)
        if self.fail:
            raise AssertionError("no model call expected")
        if schema is LLMOutput:
            first = json.loads(prompt)["candidates"][0]["poi_id"]
            card = LLMRec(
                poi_id=first,
                why="Подходит под запрос.",
                time_on_site_min=20,
                what_to_do="Зайти и осмотреться.",
                confidence="medium",
                generated_idea=False,
            )
            return LLMOutput(recommendations=[card])
        return Intent()


def _stage_env(monkeypatch, tmp_path):
    """The environment a warm-up run starts in, with everything it changes registered for restoration."""
    for name in (
        "WALKS_ENV",
        "WALKS_DEMO_PIN",
        "WALKS_CACHE_PIN",
        "WALKS_REQUEST_LOG",
        "WALKS_LLM_CACHE",
        "WALKS_DEMO_CACHE",
        "LLM_CHAIN",
        "LLM_INTENT_CHAIN",
        "WALKS_FEEDBACK",
    ):
        monkeypatch.setenv(name, "x")
    # unset, so that warm_cache applies its own defaults (WALKS_ENV=demo)
    for name in ("LLM_CHAIN", "LLM_INTENT_CHAIN", "WALKS_ENV"):
        monkeypatch.delenv(name)
    monkeypatch.setattr(warm_cache, "load_env_file", lambda: None)
    demo_copy = tmp_path / "city_feedback.demo.json"
    monkeypatch.setattr(feedback, "DEMO_PATH", demo_copy)
    monkeypatch.setattr(warm_cache, "DEMO_PATH", demo_copy)
    monkeypatch.setattr(warm_cache, "ALEM_KEY_FILE", tmp_path / "no-alem-key")
    return tmp_path / "demo_llm_cache.json"


def test_warm_up_records_then_replays_every_scenario_from_the_recording(
    tmp_path, monkeypatch, capsys
):
    out = _stage_env(monkeypatch, tmp_path)
    model = FakeModel(monkeypatch)
    assert warm_cache.main(["--out", str(out), "--pause", "0"]) == 0
    table = capsys.readouterr().out
    steps = warm_cache.plan()
    assert table.count("True ") == len(steps)
    assert "False" not in table
    assert "cached=True: 13 of 13" in table
    live_calls = len(model.calls)
    assert live_calls >= len(steps)  # every scenario asked the model at least once
    recording = json.loads(out.read_text(encoding="utf-8"))
    assert recording
    assert all(llm_providers.is_public(e["model"]) for e in recording.values())

    # the stage: an empty runtime cache, the recording only, a model that must not be called
    FakeModel(monkeypatch, fail=True)
    assert warm_cache.main(["--verify-only", "--out", str(out)]) == 0
    assert "cached=True: 13 of 13" in capsys.readouterr().out


def test_warm_up_fails_when_a_scenario_is_not_in_the_recording(tmp_path, monkeypatch, capsys):
    out = _stage_env(monkeypatch, tmp_path)
    FakeModel(monkeypatch)
    assert warm_cache.main(["--out", str(out), "--pause", "0"]) == 0
    recording = json.loads(out.read_text(encoding="utf-8"))
    victim = next(k for k, e in recording.items() if e["label"] == QUIET)
    del recording[victim]
    out.write_text(json.dumps(recording), encoding="utf-8")
    capsys.readouterr()
    FakeModel(monkeypatch, fail=True)
    assert warm_cache.main(["--verify-only", "--out", str(out)]) == 1
    table = capsys.readouterr().out
    assert "False" in table
    assert "cached=True: 12 of 13" in table


def test_warm_up_never_asks_or_records_a_private_link(tmp_path, monkeypatch):
    out = _stage_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROFILE_GW_BASE_URL", "https://gw.example.test/v1")
    monkeypatch.setenv("LLM_PROFILE_GW_API_KEY", "k")
    monkeypatch.setenv("LLM_CHAIN", "openai:vendor/m@gw,gemini:gemini-2.5-flash")
    monkeypatch.setenv("LLM_INTENT_CHAIN", "openai:vendor/m@gw,gemini:gemini-2.5-flash-lite")
    model = FakeModel(monkeypatch)
    assert warm_cache.main(["--out", str(out), "--pause", "0"]) == 0
    assert "openai:vendor/m@gw" not in model.calls
    assert not any(
        "@gw" in e["model"] for e in json.loads(out.read_text(encoding="utf-8")).values()
    )


def test_a_private_answer_is_refused_even_if_the_chain_filter_is_bypassed(tmp_path, monkeypatch):
    out = _stage_env(monkeypatch, tmp_path)
    monkeypatch.setenv("LLM_PROFILE_GW_BASE_URL", "https://gw.example.test/v1")
    monkeypatch.setenv("LLM_PROFILE_GW_API_KEY", "k")
    monkeypatch.setenv("LLM_CHAIN", "openai:vendor/m@gw")
    monkeypatch.setenv("LLM_INTENT_CHAIN", "openai:vendor/m@gw")
    monkeypatch.setattr(warm_cache, "_public_chains", lambda: None)
    FakeModel(monkeypatch)
    assert warm_cache.main(["--out", str(out), "--pause", "0"]) == 1
    assert not out.exists()  # nothing private reached a file, and an empty recording is not written


def test_the_cli_under_the_pin_answers_the_second_run_from_the_cache(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("WALKS_DEMO_PIN", "1")
    monkeypatch.setenv("WALKS_CACHE_PIN", "1")
    monkeypatch.setenv("WALKS_LLM_CACHE", str(tmp_path / "llm_cache.json"))
    demo_copy = tmp_path / "city_feedback.demo.json"
    monkeypatch.setattr(feedback, "DEMO_PATH", demo_copy)
    monkeypatch.delenv("WALKS_FEEDBACK")
    model = FakeModel(monkeypatch)
    lat, lon = PRESETS["Байтерек"]
    argv = ["--lat", str(lat), "--lon", str(lon), "--q", QUIET]
    assert cli_main(argv) == 0
    first = capsys.readouterr().out
    assert "Демо-пресет (WALKS_DEMO_PIN=1)" in first
    assert "19.10 14:00" in first
    assert "cached=False" in first
    calls = len(model.calls)
    assert cli_main(argv) == 0
    second = capsys.readouterr().out
    assert "cached=True" in second
    assert "cached=False" not in second
    assert len(model.calls) == calls  # the second run called no model
    assert "Цепочка ИИ, текст:" in second


# ---------------------------------------------------------------- live timeout budget


class Hang:
    """A provider call that never answers (an unroutable host), or answers instantly for `ok:` links."""

    def __init__(self, monkeypatch):
        self.release = threading.Event()
        monkeypatch.setattr(llm, "ask", self)
        monkeypatch.setattr(llm_providers, "gemini_key", lambda: "k")
        monkeypatch.setattr(llm, "MIN_ATTEMPT_S", 0.05)

    def __call__(self, link, prompt, system, schema, timeout_s):
        if link.model.startswith("ok"):
            return LLMOutput(recommendations=[])
        self.release.wait(5)  # abandoned by walks.llm._with_deadline, never joined
        raise httpx.ConnectTimeout("unroutable")


def _chain(*names: str) -> list[str]:
    return [f"gemini:{n}" for n in names]


def test_a_hung_link_is_cut_at_its_own_deadline_and_the_next_link_answers(monkeypatch):
    hang = Hang(monkeypatch)
    t0 = time.perf_counter()
    call = llm.generate_json(
        "p",
        LLMOutput,
        system="s",
        models=_chain("hang-1", "ok-2"),
        timeout_s=0.3,
        deadline=llm.Deadline(2.0),
    )
    elapsed = time.perf_counter() - t0
    hang.release.set()
    assert call.step.model == "gemini:ok-2"
    first = call.step.attempts[0]
    assert (first.model, first.status, first.detail) == ("gemini:hang-1", "error", "timeout")
    assert 250 <= first.ms < 600  # the per-link deadline, not the 2 s request budget
    assert elapsed < 1.0


def test_the_request_wide_cap_stops_the_chain_and_the_caller_gets_the_template_path(monkeypatch):
    hang = Hang(monkeypatch)
    t0 = time.perf_counter()
    with pytest.raises(llm.LLMUnavailable) as exc:
        llm.generate_json(
            "p",
            LLMOutput,
            system="s",
            models=_chain("hang-1", "hang-2", "ok-3"),
            timeout_s=0.3,
            deadline=llm.Deadline(0.45),
        )
    elapsed = time.perf_counter() - t0
    hang.release.set()
    attempts = exc.value.step.attempts
    assert [a.status for a in attempts] == ["error", "error", "skipped"]
    assert attempts[1].ms < 300  # the second link got only what was left of the cap
    assert attempts[2].detail == "бюджет времени запроса исчерпан"
    assert 0.4 <= elapsed < 0.9


def test_an_unreachable_host_is_cut_by_the_connect_timeout_not_the_whole_budget(
    monkeypatch, tmp_path
):
    seen: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request.extensions["timeout"])
        return httpx.Response(
            200,
            json={
                "choices": [
                    {"message": {"content": LLMOutput(recommendations=[]).model_dump_json()}}
                ]
            },
        )

    monkeypatch.setattr(llm_providers, "_transport", httpx.MockTransport(handler))
    monkeypatch.setenv("LLM_PROFILE_DEAD_BASE_URL", "http://10.255.255.1/v1")
    monkeypatch.setenv("LLM_PROFILE_DEAD_API_KEY", "k")
    llm.generate_json("p", LLMOutput, system="s", models=["openai:m@dead"], timeout_s=15.0)
    assert seen[0]["connect"] == llm_providers.CONNECT_TIMEOUT_S < seen[0]["read"] == 15.0


# ---------------------------------------------------------------- replay-only (public stand without a key)


def _recorded(tmp_path, monkeypatch) -> Path:
    """A one-entry recording of an intent answer, read the way data/demo_llm_cache.json is (pinned key, demo env)."""
    path = tmp_path / "recording.json"
    material = "m-1"
    key = llm._full_key(material, ["gemini:a"], Intent, pinned=True)
    path.write_text(
        json.dumps({key: {"model": "gemini:a", "json": Intent().model_dump_json()}}),
        encoding="utf-8",
    )
    monkeypatch.setenv("WALKS_ENV", "demo")
    monkeypatch.setenv("WALKS_CACHE_PIN", "1")
    monkeypatch.setenv("WALKS_DEMO_CACHE", str(path))
    monkeypatch.setenv(
        "WALKS_LLM_CACHE", str(tmp_path / "runtime.json")
    )  # `off` would switch the recording off too
    monkeypatch.setenv("WALKS_REPLAY_ONLY", "1")
    return path


def _boom(*_a, **_kw):
    raise AssertionError("replay-only must never call a model")


def test_replay_only_serves_the_recording_without_any_key_or_network(tmp_path, monkeypatch):
    _recorded(tmp_path, monkeypatch)
    monkeypatch.setattr(llm, "ask", _boom)
    assert llm.llm_available()  # no key, no profile: the recording still counts as the AI
    assert llm.ai_off_reason(True) == ""
    call = llm.generate_json(
        "p", Intent, system="s", models=["gemini:a"], timeout_s=1.0, cache_key="m-1"
    )
    assert call.step.cached
    assert call.step.model == "gemini:a"


def test_replay_only_miss_goes_to_the_template_without_a_model_call(tmp_path, monkeypatch):
    _recorded(tmp_path, monkeypatch)
    monkeypatch.setattr(llm, "ask", _boom)
    with pytest.raises(llm.ReplayMiss, match="не записан"):
        llm.generate_json(
            "p", Intent, system="s", models=["gemini:a"], timeout_s=1.0, cache_key="other"
        )
    # a key-less call without the recording being asked (no cache_key) is a miss too
    with pytest.raises(llm.ReplayMiss):
        llm.generate_json("p", Intent, system="s", models=["gemini:a"], timeout_s=1.0)


def test_replay_only_off_keeps_the_old_behaviour(tmp_path, monkeypatch):
    _recorded(tmp_path, monkeypatch)
    monkeypatch.delenv("WALKS_REPLAY_ONLY")
    assert not llm.llm_available()
    with pytest.raises(llm.LLMUnavailable, match="не настроен"):
        llm.generate_json(
            "p", Intent, system="s", models=["gemini:a"], timeout_s=1.0, cache_key="m-1"
        )


def test_replay_only_is_still_offline_when_offline(tmp_path, monkeypatch):
    _recorded(tmp_path, monkeypatch)
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    assert llm.ai_off_reason(True) == llm.OFFLINE_NOTE


def test_replay_only_free_query_in_the_cli_is_a_labelled_template(monkeypatch, capsys):
    monkeypatch.setenv("WALKS_REPLAY_ONLY", "1")
    monkeypatch.setenv("WALKS_DEMO_PIN", "1")
    monkeypatch.setattr(llm, "ask", _boom)
    lat, lon = PRESETS["Байтерек"]
    assert cli_main(["--lat", str(lat), "--lon", str(lon), "--q", "Что-нибудь свободное"]) == 0
    out = capsys.readouterr().out
    assert "ИИ: только записанные ответы демо" in out
    assert "без ИИ (шаблон из данных)" in out
    assert "этот запрос не записан" in out
    assert "ошибка ИИ" not in out
    assert (
        "Демо-пресет" not in out
    )  # a request that was not recorded runs at the real time and weather


def test_the_warm_up_refuses_to_record_in_replay_only_mode(tmp_path, monkeypatch, capsys):
    out = _stage_env(monkeypatch, tmp_path)
    monkeypatch.setenv("WALKS_REPLAY_ONLY", "1")
    FakeModel(monkeypatch)
    assert warm_cache.main(["--out", str(out), "--pause", "0"]) == 2
    assert not out.exists()
