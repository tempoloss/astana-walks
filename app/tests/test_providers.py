"""LLM providers: OpenAI-compatible endpoints over httpx (MockTransport), profiles, Gemma settings, simulated Google
outage, offline mode, .env loader. Nothing here touches the network."""

from __future__ import annotations

import json
import os
import socket
import urllib.request
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest

from walks import envcfg, llm, llm_providers, walking
from walks.models import LLMOutput, load_pois
from walks.pipeline import recommend
from walks.presets import PRESETS
from walks.weather import fetch_weather

FIXTURE = Path(__file__).parent / "fixtures" / "poi_sample.json"
WED_NOON = datetime(2026, 10, 14, 12, 0)
OK_BODY = LLMOutput(recommendations=[]).model_dump_json()
SECRET = "tok-123-secret"
BASE = "https://gw.example.test/v1"


def _chat(content: str) -> dict:
    return {"choices": [{"message": {"role": "assistant", "content": content}}]}


class Gateway:
    """httpx.MockTransport handler: `script` maps a model to a status or a content string, in call order."""

    def __init__(self, monkeypatch, script: dict[str, list]):
        self.script, self.requests = script, []
        monkeypatch.setattr(llm_providers, "_transport", httpx.MockTransport(self))

    def __call__(self, request: httpx.Request) -> httpx.Response:
        body = json.loads(request.content)
        self.requests.append((str(request.url), dict(request.headers), body))
        behaviour = self.script[body["model"]].pop(0)
        if isinstance(behaviour, int):
            return httpx.Response(behaviour, json={"error": {"message": "nope"}})
        return httpx.Response(200, json=_chat(behaviour))


@pytest.fixture
def gw_profile(monkeypatch, tmp_path):
    key_file = tmp_path / "gateway.token"
    key_file.write_text(f"{SECRET}\n", encoding="utf-8")
    monkeypatch.setenv("LLM_PROFILE_GW_BASE_URL", BASE)
    monkeypatch.setenv("LLM_PROFILE_GW_API_KEY_FILE", str(key_file))


def test_openai_links_verify_tls_against_the_os_store_plus_profile_ca(monkeypatch):
    import ssl

    context = llm_providers._tls_context("")
    assert context.verify_mode == ssl.CERT_REQUIRED
    assert context.check_hostname
    monkeypatch.setenv("LLM_PROFILE_GW_BASE_URL", BASE)
    monkeypatch.setenv("LLM_PROFILE_GW_API_KEY", "k")
    monkeypatch.setenv("LLM_PROFILE_GW_CA_FILE", "/some/ca.pem")
    endpoint = llm_providers.openai_endpoint("gw")
    assert endpoint is not None
    assert endpoint.ca_file == "/some/ca.pem"


def _ask(models, **kw):
    return llm.generate_json("p", LLMOutput, system="s", models=models, timeout_s=2.0, **kw)


# ---- openai-compatible provider -----------------------------------------------------------------------


def test_openai_success_sends_auth_json_mode_and_schema(monkeypatch, gw_profile):
    gw = Gateway(monkeypatch, {"vendor/model-a": [OK_BODY]})
    call = _ask(["openai:vendor/model-a@gw"])
    assert call.value == LLMOutput(recommendations=[])
    assert call.step.model == "openai:vendor/model-a@gw"
    [(url, headers, body)] = gw.requests
    assert url == f"{BASE}/chat/completions"
    assert headers["authorization"] == f"Bearer {SECRET}"
    assert body["response_format"] == {"type": "json_object"}
    assert [m["role"] for m in body["messages"]] == ["system", "user"]
    assert (
        "JSON Schema" in body["messages"][0]["content"]
    )  # instruct+parse works without JSON mode too
    assert body["messages"][1]["content"] == "p"


def test_openai_markdown_fence_is_tolerated(monkeypatch, gw_profile):
    Gateway(monkeypatch, {"m": [f"```json\n{OK_BODY}\n```"]})
    assert _ask(["openai:m@gw"]).step.model == "openai:m@gw"


def test_openai_invalid_json_moves_to_next_link(monkeypatch, gw_profile):
    Gateway(monkeypatch, {"bad": ["Конечно! Вот ответ: не JSON"], "good": [OK_BODY]})
    call = _ask(["openai:bad@gw", "openai:good@gw"])
    assert call.step.model == "openai:good@gw"
    assert [(a.model, a.status, a.detail) for a in call.step.attempts] == [
        ("openai:bad@gw", "error", "ответ не разобран"),
        ("openai:good@gw", "ok", ""),
    ]


def test_openai_wrong_shape_is_invalid(monkeypatch, gw_profile):
    Gateway(monkeypatch, {"bad": [json.dumps({"recommendations": "nope"})], "good": [OK_BODY]})
    assert _ask(["openai:bad@gw", "openai:good@gw"]).step.model == "openai:good@gw"


def test_openai_503_moves_on_and_trips_the_breaker(monkeypatch, gw_profile):
    gw = Gateway(monkeypatch, {"down": [503], "up": [OK_BODY, OK_BODY]})
    call = _ask(["openai:down@gw", "openai:up@gw"])
    assert call.step.attempts[0].detail == "503"
    assert call.step.model == "openai:up@gw"
    _ask(["openai:down@gw", "openai:up@gw"])  # the breaker skips `down` now
    assert [b["model"] for _, _, b in gw.requests] == ["down", "up", "up"]


def test_openai_429_moves_on_without_breaker(monkeypatch, gw_profile):
    gw = Gateway(monkeypatch, {"busy": [429, 429], "up": [OK_BODY, OK_BODY]})
    _ask(["openai:busy@gw", "openai:up@gw"])
    _ask(["openai:busy@gw", "openai:up@gw"])
    assert [b["model"] for _, _, b in gw.requests] == ["busy", "up", "busy", "up"]


def test_openai_without_json_mode_support_retries_plain(monkeypatch, gw_profile):
    gw = Gateway(monkeypatch, {"m": [400, OK_BODY, OK_BODY]})
    assert _ask(["openai:m@gw"]).step.model == "openai:m@gw"
    assert "response_format" in gw.requests[0][2]
    assert "response_format" not in gw.requests[1][2]
    _ask(["openai:m@gw"])  # remembered: no response_format at all any more
    assert "response_format" not in gw.requests[2][2]


def test_profile_json_mode_can_be_switched_off_or_to_schema(monkeypatch, gw_profile):
    gw = Gateway(monkeypatch, {"m": [OK_BODY, OK_BODY]})
    monkeypatch.setenv("LLM_PROFILE_GW_JSON_MODE", "none")
    _ask(["openai:m@gw"])
    monkeypatch.setenv("LLM_PROFILE_GW_JSON_MODE", "json_schema")
    _ask(["openai:m@gw"], cache_key=None)
    assert "response_format" not in gw.requests[0][2]
    assert gw.requests[1][2]["response_format"]["type"] == "json_schema"


def test_attempt_log_never_contains_url_or_key(monkeypatch, gw_profile):
    Gateway(monkeypatch, {"a": [503], "b": ["garbage"]})
    with pytest.raises(llm.LLMUnavailable) as info:
        _ask(["openai:a@gw", "openai:b@gw"])
    shown = str(info.value) + info.value.step.model_dump_json()  # type: ignore[union-attr]
    assert "gw.example.test" not in shown
    assert SECRET not in shown
    assert "openai:a@gw" in shown


def test_unconfigured_profile_is_skipped_not_called(monkeypatch, gw_profile):
    Gateway(monkeypatch, {"m": [OK_BODY]})
    call = _ask(["openai:m@ghost", "openai:m@gw"])
    assert call.step.attempts[0].status == "skipped"
    assert "ghost" in call.step.attempts[0].detail
    assert call.step.model == "openai:m@gw"


def test_alem_profile_has_a_ready_base_url(monkeypatch, tmp_path):
    key_file = tmp_path / "alem.key"
    key_file.write_text("alem-key\n", encoding="utf-8")
    monkeypatch.setenv("LLM_PROFILE_ALEM_API_KEY_FILE", str(key_file))
    gw = Gateway(monkeypatch, {"alemllm": [OK_BODY], "gemma4": [OK_BODY]})
    call = _ask(["openai:alemllm@alem"])
    assert call.step.model == "openai:alemllm@alem"
    assert _ask(["openai:gemma4@alem"]).step.model == "openai:gemma4@alem"
    assert gw.requests[0][0] == "https://llm.alem.ai/v1/chat/completions"
    assert gw.requests[0][1]["authorization"] == "Bearer alem-key"


def test_inline_key_env_and_no_profile_defaults(monkeypatch):
    monkeypatch.setenv("LLM_PROFILE_MY_PROXY_API_KEY", "k1")
    monkeypatch.setenv("LLM_PROFILE_MY_PROXY_BASE_URL", "https://p.example.test/v1/")
    gw = Gateway(monkeypatch, {"m": [OK_BODY, OK_BODY]})
    _ask(["openai:m@my-proxy"])
    assert gw.requests[0][0] == "https://p.example.test/v1/chat/completions"
    monkeypatch.setenv("OPENAI_API_KEY", "k2")
    _ask(["openai:m"])
    assert gw.requests[1][0] == "https://api.openai.com/v1/chat/completions"


def test_mixed_chain_falls_over_from_gemini_to_openai(monkeypatch, gw_profile):
    monkeypatch.setattr(llm_providers, "gemini_key", lambda: "k")

    def boom(**kw):
        raise OSError("no route")

    monkeypatch.setattr("google.genai.Client", boom)
    Gateway(monkeypatch, {"m": [OK_BODY]})
    call = _ask(["gemini:gemini-3.5-flash", "openai:m@gw"])
    assert call.step.model == "openai:m@gw"
    assert call.step.attempts[0].status == "error"


# ---- Gemma settings -----------------------------------------------------------------------------------


@pytest.mark.parametrize("model", ["gemma-4-26b-a4b-it", "gemma-4-31b-it"])
def test_gemma_traits_and_request(monkeypatch, model):
    traits = llm_providers.gemini_traits(model)
    assert (
        traits.thinking is None
    )  # live API: 400 "Thinking level/budget is not supported for this model"
    assert not traits.system_instruction  # live API: 500/504 with system_instruction
    assert traits.json_mode
    cfg = llm_providers._gemini_config(model, "SYSTEM TEXT", LLMOutput)
    assert cfg.thinking_config is None
    assert cfg.system_instruction is None
    assert cfg.response_mime_type == "application/json"
    assert cfg.response_schema is LLMOutput

    seen = {}

    def generate_content(*, model, contents, config):
        seen.update(model=model, contents=contents, config=config)
        return SimpleNamespace(parsed=None, text=OK_BODY)

    monkeypatch.setattr(llm_providers, "gemini_key", lambda: "k")
    monkeypatch.setattr(
        "google.genai.Client",
        lambda **kw: SimpleNamespace(models=SimpleNamespace(generate_content=generate_content)),
    )
    assert _ask([f"gemini:{model}"]).step.model == f"gemini:{model}"
    assert seen["contents"] == "s\n\np"  # the system prompt is folded into the user message
    assert seen["config"].thinking_config is None


def test_gemini_still_gets_thinking_and_system_instruction():
    cfg = llm_providers._gemini_config("gemini-2.5-flash", "SYS", LLMOutput)
    assert cfg.system_instruction == "SYS"
    assert cfg.thinking_config.thinking_budget == 0


def test_gemma_fenced_text_answer_is_parsed(monkeypatch):
    monkeypatch.setattr(llm_providers, "gemini_key", lambda: "k")
    monkeypatch.setattr(
        "google.genai.Client",
        lambda **kw: SimpleNamespace(
            models=SimpleNamespace(
                generate_content=lambda **k: SimpleNamespace(
                    parsed=None, text=f"```json\n{OK_BODY}\n```"
                )
            )
        ),
    )
    assert _ask(["gemini:gemma-4-26b-a4b-it"]).value == LLMOutput(recommendations=[])


# ---- simulated Google outage ----------------------------------------------------------------------------


def test_google_down_fails_every_gemini_link_and_openai_answers(monkeypatch, gw_profile, tmp_path):
    monkeypatch.setattr(llm_providers, "gemini_key", lambda: "k")
    monkeypatch.setenv("WALKS_SIMULATE_GOOGLE_DOWN", "1")
    monkeypatch.setenv("WALKS_LLM_CACHE", str(tmp_path / "c.json"))

    def real_client(**kw):
        raise AssertionError("google.genai must not be reached while Google is 'down'")

    monkeypatch.setattr("google.genai.Client", real_client)
    Gateway(monkeypatch, {"m": [OK_BODY]})
    chain = ["gemini:a", "gemini:gemma-4-26b-a4b-it", "openai:m@gw"]
    call = _ask(chain, cache_key="k")
    assert call.step.model == "openai:m@gw"
    assert [a.status for a in call.step.attempts] == ["error", "error", "ok"]
    assert not (tmp_path / "c.json").exists()  # a simulated outage never reads or writes the cache


# ---- offline ------------------------------------------------------------------------------------------


def _forbid_network(monkeypatch):
    def boom(*a, **k):
        raise AssertionError("network access in offline mode")

    monkeypatch.setattr(socket.socket, "connect", boom)
    monkeypatch.setattr(urllib.request, "urlopen", boom)
    monkeypatch.setattr(httpx.Client, "send", boom)
    monkeypatch.setattr("google.genai.Client", boom)


def test_offline_pipeline_returns_recs_without_any_network(monkeypatch, tmp_path):
    pois = load_pois(FIXTURE)
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    monkeypatch.setattr(llm_providers, "gemini_key", lambda: "k")  # a key exists: still no call
    monkeypatch.delenv("WALKS_WALKING")  # routing enabled: offline must be what stops Valhalla
    monkeypatch.setenv("WALKS_WALK_CACHE", str(tmp_path / "walk.json"))
    _forbid_network(monkeypatch)

    weather = fetch_weather()
    assert weather.temperature_c is None
    assert weather.pm25 is None

    res = recommend("кофе рядом на час", *PRESETS["EXPO"], WED_NOON, pois=pois, weather=weather)
    assert res.recs
    assert res.generation == "template"
    assert res.intent.parser == "rules"
    assert "офлайн" in res.generation_note
    assert set(res.walk_stats) <= {"straight", "cache"}


def test_offline_uses_cached_walking_legs_only(monkeypatch, tmp_path):
    pois = load_pois(FIXTURE)
    monkeypatch.setenv("WALKS_OFFLINE", "1")
    monkeypatch.delenv("WALKS_WALKING")
    cache = tmp_path / "walk.json"
    monkeypatch.setenv("WALKS_WALK_CACHE", str(cache))
    _forbid_network(monkeypatch)

    first = recommend("кофе рядом на час", *PRESETS["EXPO"], WED_NOON, pois=pois)
    target = first.recs[0]
    user = (round(first.lat, 4), round(first.lon, 4))
    leg = walking.WalkingRouter(False, enabled=False).leg(user, (target.poi.lat, target.poi.lon))
    key = walking._key(user, (round(target.poi.lat, 4), round(target.poi.lon, 4)))
    cache.write_text(json.dumps({key: {"m": leg.distance_m, "s": 7 * 60, "d": "2026-10-01"}}))

    monkeypatch.setattr(walking, "_default", None)  # a fresh router reads the file
    again = recommend("кофе рядом на час", *PRESETS["EXPO"], WED_NOON, pois=pois)
    assert again.walk_stats.get("cache", 0) >= 1
    assert next(r for r in again.recs if r.poi.id == target.poi.id).walk_min == 7
    assert again.walk_stats.get("valhalla", 0) == 0


def test_offline_llm_call_raises_before_any_provider(monkeypatch):
    monkeypatch.setenv("WALKS_OFFLINE", "true")
    monkeypatch.setattr(llm_providers, "gemini_key", lambda: "k")
    _forbid_network(monkeypatch)
    with pytest.raises(llm.LLMUnavailable, match="офлайн"):
        _ask(["gemini:a"])
    assert llm.ai_off_reason(True) == llm.OFFLINE_NOTE


# ---- .env.<name> ------------------------------------------------------------------------------------------


def test_load_env_file_reads_demo_without_overriding(monkeypatch, tmp_path):
    (tmp_path / ".env.demo").write_text(
        "# comment\nLLM_CHAIN=gemini:a,openai:m@gw\nexport LLM_PROFILE_GW_BASE_URL='https://x.test/v1'\n"
        "ALREADY=file\n\nbroken line\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(
        os, "environ", os.environ.copy()
    )  # the loader writes straight into os.environ
    os.environ.update({"WALKS_ENV": "demo", "ALREADY": "shell"})
    os.environ.pop("LLM_CHAIN", None)
    os.environ.pop("LLM_PROFILE_GW_BASE_URL", None)
    assert envcfg.load_env_file(tmp_path) == tmp_path / ".env.demo"
    assert os.environ["LLM_CHAIN"] == "gemini:a,openai:m@gw"
    assert os.environ["LLM_PROFILE_GW_BASE_URL"] == "https://x.test/v1"
    assert os.environ["ALREADY"] == "shell"


def test_load_env_file_noop_without_walks_env(tmp_path):
    (tmp_path / ".env.demo").write_text("LLM_CHAIN=x\n", encoding="utf-8")
    assert envcfg.load_env_file(tmp_path) is None
