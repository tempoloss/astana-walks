"""Model fallback chain, circuit breaker, rules-first intent, code-derived labels, stay clamp, response cache.

The Gemini client is replaced by a scripted fake; nothing here touches the network."""

from __future__ import annotations

import time
from datetime import datetime
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from google.genai import errors

from walks import generate as gen_mod
from walks import intent as intent_mod
from walks import llm, llm_providers
from walks.intent import parse_intent, parse_rules
from walks.llm_output import LLMOutput, LLMRec
from walks.models import POI, Intent, LLMStep, load_pois
from walks.presets import PRESETS
from walks.retrieve import retrieve

FIXTURE = Path(__file__).parent / "fixtures" / "poi_sample.json"


@pytest.fixture(autouse=True)
def _reasons_not_checked_for_facts(monkeypatch):
    """These tests are about the chain, the cache and the claims: their fake reasons are not checked for a concrete
    fact of the place (tests/test_answer_quality.py checks that)."""
    import walks.generate as generation

    monkeypatch.setattr(generation, "vague_ids", lambda *a, **k: [])


WED_NOON = datetime(2026, 10, 14, 12, 0)
EXPO_QUERY = "Я у EXPO, хочу что-то необычное на 1-2 часа, пешком"


@pytest.fixture(scope="module")
def pois():
    return load_pois(FIXTURE)


class FakeGenai:
    """Stands in for google.genai.Client: `script` maps a model to an LLMOutput, a raw text or an exception."""

    def __init__(self, monkeypatch, script: dict):
        self.script, self.calls, self.client_kwargs = script, [], []
        monkeypatch.setattr(llm_providers, "gemini_key", lambda: "k")
        monkeypatch.setattr("google.genai.Client", self._client)

    def _client(self, **kw):
        self.client_kwargs.append(kw)
        return SimpleNamespace(models=SimpleNamespace(generate_content=self._generate))

    def _generate(self, *, model, contents, config):
        self.calls.append(model)
        behaviour = self.script[model]
        if isinstance(behaviour, Exception):
            raise behaviour
        if callable(behaviour):
            behaviour = behaviour()
        if isinstance(behaviour, str):
            return SimpleNamespace(parsed=None, text=behaviour)
        return SimpleNamespace(parsed=behaviour, text=behaviour.model_dump_json())


def _api_error(code: int) -> errors.APIError:
    return errors.APIError(code, {"error": {"message": "x"}})


def _ask(models, **kw):
    chain = [f"gemini:{m}" for m in models]  # the fake script is keyed by the bare model name
    return llm.generate_json("p", LLMOutput, system="s", models=chain, timeout_s=1.0, **kw)


OK = LLMOutput(recommendations=[])


# ---- chain ----------------------------------------------------------------------------------------


def test_chain_advances_on_503_and_records_attempts(monkeypatch):
    fake = FakeGenai(monkeypatch, {"a": _api_error(503), "b": OK})
    call = _ask(["a", "b"])
    assert fake.calls == ["a", "b"]
    assert call.value is OK
    assert call.step.model == "gemini:b"
    assert [(x.model, x.status, x.detail) for x in call.step.attempts] == [
        ("gemini:a", "error", "503"),
        ("gemini:b", "ok", ""),
    ]
    assert "gemini:a: 503" in call.step.attempts_text()
    assert "gemini:b: ok" in call.step.attempts_text()
    assert not call.step.cached


@pytest.mark.parametrize(
    "exc",
    [_api_error(429), _api_error(500), httpx.ReadTimeout("slow")],
    ids=["429", "5xx", "timeout"],
)
def test_chain_advances_on_other_transient_errors(monkeypatch, exc):
    fake = FakeGenai(monkeypatch, {"a": exc, "b": OK})
    assert _ask(["a", "b"]).step.model == "gemini:b"
    assert fake.calls == ["a", "b"]


def test_unparsable_answer_advances(monkeypatch):
    FakeGenai(monkeypatch, {"a": "not json", "b": OK})
    call = _ask(["a", "b"])
    assert call.step.attempts[0].status == "error"
    assert call.step.model == "gemini:b"


def test_whole_chain_failure_raises_with_log(monkeypatch):
    FakeGenai(monkeypatch, {"a": _api_error(503), "b": _api_error(429), "c": _api_error(500)})
    with pytest.raises(llm.LLMUnavailable) as info:
        _ask(["a", "b", "c"])
    step = info.value.step
    assert step is not None
    assert step.model is None
    assert [x.detail for x in step.attempts] == ["503", "429", "500"]


def test_chain_env_and_defaults(monkeypatch):
    assert llm.generation_models() == list(llm.DEFAULT_GENERATION_CHAIN)
    assert llm.intent_models() == list(llm.DEFAULT_INTENT_CHAIN)
    assert llm.generation_models()[0] == "gemini:gemini-3.5-flash-lite"
    assert llm.intent_models()[0] == "gemini:gemini-3.5-flash-lite"
    monkeypatch.setenv("LLM_CHAIN", " gemini:x, openai:m@prof ,gemini:x,,")
    monkeypatch.setenv("LLM_INTENT_CHAIN", "gemini:z")
    assert llm.generation_models() == ["gemini:x", "openai:m@prof"]
    assert llm.intent_models() == ["gemini:z"]


@pytest.mark.parametrize(
    ("spec", "expected"),
    [
        ("gemini:gemma-4-26b-a4b-it", ("gemini", "gemma-4-26b-a4b-it", None)),
        ("openai:vendor/model-a@gw", ("openai", "vendor/model-a", "gw")),
        ("openai:gpt-4o-mini", ("openai", "gpt-4o-mini", None)),
        (" openai:alemllm@alem ", ("openai", "alemllm", "alem")),
    ],
)
def test_parse_link(spec, expected):
    link = llm_providers.parse_link(spec)
    assert (link.provider, link.model, link.profile) == expected
    assert link.label == spec.strip()


@pytest.mark.parametrize("spec", ["gemini", "gemma:x", "gemini:", "gemini:m@p", ":m"])
def test_parse_link_rejects_bad_entries(spec):
    with pytest.raises(ValueError, match=r"provider:model|openai"):
        llm_providers.parse_link(spec)


def test_bad_chain_entry_is_a_failed_link_not_a_crash(monkeypatch):
    FakeGenai(monkeypatch, {"b": OK})
    call = llm.generate_json(
        "p", LLMOutput, system="s", models=["nonsense", "gemini:b"], timeout_s=1.0
    )
    assert call.step.model == "gemini:b"
    assert call.step.attempts[0].status == "error"


def test_llm_available_follows_configured_links(monkeypatch, tmp_path):
    assert not llm.llm_available()  # no key, no profile
    monkeypatch.setenv("LLM_CHAIN", "openai:m@gw")
    monkeypatch.setenv("LLM_INTENT_CHAIN", "openai:m@gw")
    assert not llm.llm_available()
    key_file = tmp_path / "tok"
    key_file.write_text("sekret\n", encoding="utf-8")
    monkeypatch.setenv("LLM_PROFILE_GW_BASE_URL", "https://gw.example/v1")
    monkeypatch.setenv("LLM_PROFILE_GW_API_KEY_FILE", str(key_file))
    assert llm.llm_available()


def test_no_key_raises(monkeypatch):
    monkeypatch.setattr(llm_providers, "gemini_key", lambda: None)
    with pytest.raises(llm.LLMUnavailable):
        _ask(["a"])


# ---- circuit breaker ------------------------------------------------------------------------------


def test_breaker_skips_model_after_503_then_recovers(monkeypatch):
    now = [1000.0]
    monkeypatch.setattr(llm, "_clock", lambda: now[0])
    fake = FakeGenai(monkeypatch, {"a": _api_error(503), "b": OK})
    _ask(["a", "b"])
    assert fake.calls == ["a", "b"]

    fake.calls.clear()
    now[0] += 60
    call = _ask(["a", "b"])
    assert call.step.model == "gemini:b"
    assert call.step.attempts[0].status == "skipped"
    assert "ещё 60 с" in call.step.attempts[0].detail

    fake.calls.clear()
    now[0] += llm.BREAKER_S  # window over: a is tried again
    _ask(["a", "b"])
    assert fake.calls == ["a", "b"]


def test_breaker_not_tripped_by_429(monkeypatch):
    fake = FakeGenai(monkeypatch, {"a": _api_error(429), "b": OK})
    _ask(["a", "b"])
    _ask(["a", "b"])
    assert fake.calls == ["a", "b", "a", "b"]


def test_breaker_opens_on_timeout(monkeypatch):
    fake = FakeGenai(monkeypatch, {"a": httpx.ReadTimeout("slow"), "b": OK})
    _ask(["a", "b"])
    fake.calls.clear()
    _ask(["a", "b"])
    assert fake.calls == ["b"]


def test_all_models_skipped_by_breaker_raises(monkeypatch):
    FakeGenai(monkeypatch, {"a": _api_error(503)})
    with pytest.raises(llm.LLMUnavailable):
        _ask(["a"])
    with pytest.raises(llm.LLMUnavailable) as info:
        _ask(["a"])
    assert info.value.step is not None
    assert info.value.step.attempts[0].status == "skipped"


# ---- timeouts -------------------------------------------------------------------------------------


def test_default_timeouts_and_server_deadline_floor(monkeypatch):
    fake = FakeGenai(monkeypatch, {"a": OK})
    assert llm.INTENT_TIMEOUT_S == 4.0
    assert llm.GENERATION_TIMEOUT_S == 8.0
    for seconds in (llm.INTENT_TIMEOUT_S, llm.GENERATION_TIMEOUT_S):
        llm.generate_json("p", LLMOutput, system="s", models=["gemini:a"], timeout_s=seconds)
    # the API rejects a server deadline below 10 s, so the short intent limit is enforced client-side
    assert [kw["http_options"].timeout for kw in fake.client_kwargs] == [10000, 10000]


def test_slow_model_times_out_and_chain_advances(monkeypatch):
    def slow() -> LLMOutput:
        time.sleep(0.3)
        return OK

    fake = FakeGenai(monkeypatch, {"a": slow, "b": OK})
    start = time.perf_counter()
    call = llm.generate_json(
        "p", LLMOutput, system="s", models=["gemini:a", "gemini:b"], timeout_s=0.05
    )
    assert time.perf_counter() - start < 0.25  # did not wait for the slow model
    assert [(x.model, x.status, x.detail) for x in call.step.attempts] == [
        ("gemini:a", "error", "timeout"),
        ("gemini:b", "ok", ""),
    ]
    fake.calls.clear()
    llm.generate_json("p", LLMOutput, system="s", models=["gemini:a", "gemini:b"], timeout_s=0.05)
    assert fake.calls == ["b"]  # a timed out: the breaker skips it now


# ---- intent: rules first, Gemini only adds ---------------------------------------------------------


def _fake_intent_llm(monkeypatch, returned: Intent | Exception):
    monkeypatch.setattr(llm, "llm_available", lambda: True)

    def fake(prompt, schema, **kw):
        fake.prompt, fake.kw = prompt, kw
        if isinstance(returned, Exception):
            raise returned
        return llm.LLMCall(returned, LLMStep(chain=["m"], model="m", ms=5))

    monkeypatch.setattr(intent_mod, "generate_json", fake)
    return fake


def test_rules_categories_survive_llm_returning_empty(monkeypatch):
    rules = parse_rules(EXPO_QUERY).intent
    assert rules.categories  # 'необычное' alone implies categories
    fake = _fake_intent_llm(monkeypatch, Intent(categories=[], time_budget_min=45))
    res = parse_intent(EXPO_QUERY)
    assert res.parser == "rules+llm"
    assert res.intent.categories == rules.categories
    assert res.llm is not None
    assert res.llm.categories == []
    assert res.rules == rules
    assert res.intent.time_budget_min == rules.time_budget_min == 90  # explicit '1-2 часа' wins
    assert "Allowed category values" in fake.prompt
    assert "culture_theatre_cinema" in fake.prompt  # the enum from models.CATEGORIES is spelled out
    assert fake.kw["models"] == llm.intent_models()
    assert fake.kw["timeout_s"] == llm.INTENT_TIMEOUT_S


def test_llm_adds_categories_and_flags_but_never_removes(monkeypatch):
    rules = parse_rules("кофе").intent
    assert rules.categories == ["cafe"]
    _fake_intent_llm(
        monkeypatch, Intent(categories=["park_garden", "cafe"], quiet=True, time_budget_min=30)
    )
    res = parse_intent("кофе")
    assert res.intent.categories == ["cafe", "park_garden"]  # union, rules first
    assert res.intent.quiet
    assert res.intent.time_budget_min == 30  # no time in the text: Gemini's reading is used
    assert "park_garden" in res.note


def test_rules_stand_when_llm_chain_fails(monkeypatch):
    step = LLMStep(chain=["a"], attempts=[])
    _fake_intent_llm(monkeypatch, llm.LLMUnavailable("все модели недоступны", step))
    res = parse_intent(EXPO_QUERY)
    assert res.parser == "rules"
    assert res.intent == parse_rules(EXPO_QUERY).intent
    assert res.llm is None
    assert res.llm_step is step
    assert "все модели недоступны" in res.note


def test_use_llm_false_never_calls_llm(monkeypatch):
    fake = _fake_intent_llm(monkeypatch, Intent())
    res = parse_intent(EXPO_QUERY, use_llm=False)
    assert res.parser == "rules"
    assert not hasattr(fake, "prompt")


# ---- generation: labels, stay, one call ------------------------------------------------------------


def _cafe_candidates(pois, budget=120):
    lat, lon = PRESETS["Mega Silk Way"]
    intent = Intent(time_budget_min=budget, categories=["cafe", "park_garden"])
    return intent, lat, lon, retrieve(pois, lat, lon, intent, WED_NOON).candidates


def _rec(poi_id: str, *, minutes=30, idea=False) -> LLMRec:
    return LLMRec(
        poi_id=poi_id,
        why="Подходит.",
        time_on_site_min=minutes,
        what_to_do="Зайдите.",
        confidence="high",
        generated_idea=idea,
    )


def _generate(pois, monkeypatch, recs, *, budget=120):
    monkeypatch.setattr(llm, "llm_available", lambda: True)
    calls = []

    def fake(prompt, schema, **kw):
        calls.append(kw)
        return llm.LLMCall(LLMOutput(recommendations=recs), LLMStep(chain=["m"], model="m"))

    monkeypatch.setattr(gen_mod, "generate_json", fake)
    intent, lat, lon, cands = _cafe_candidates(pois, budget)
    return gen_mod.generate(intent, lat, lon, cands, WED_NOON), calls


def test_one_generation_call_for_all_recs(pois, monkeypatch):
    _, _, _, cands = _cafe_candidates(pois)
    ids = [c.poi.id for c in cands[:3]]
    g, calls = _generate(pois, monkeypatch, [_rec(i) for i in ids])
    assert len(g.recs) == len(ids) >= 2
    assert len(calls) == 1
    assert calls[0]["models"] == llm.generation_models()
    assert calls[0]["timeout_s"] == llm.GENERATION_TIMEOUT_S


def test_source_label_comes_from_code_not_the_model(pois, monkeypatch):
    _, _, _, cands = _cafe_candidates(pois)
    first = cands[0].poi
    # description derived from tags (the bulk of the data) is NOT an AI idea; the model said no idea
    assert first.description_source == "derived"
    g, _ = _generate(pois, monkeypatch, [_rec(first.id, idea=False)])
    assert not g.recs[0].generated_idea
    assert g.recs[0].poi.data_label() == "OSM"
    # the idea flag marks the advice only; the data label does not change
    g, _ = _generate(pois, monkeypatch, [_rec(first.id, idea=True)])
    assert g.recs[0].generated_idea
    assert g.recs[0].poi.data_label() == "OSM"


def test_data_label_and_wikipedia_attribution():
    base = {"id": "node/1", "name": "X", "lat": 51.0, "lon": 71.0, "category": "park_garden"}
    assert POI(**base).data_label() == "OSM"
    assert POI(**base, sources=["osm", "overture"]).data_label() == "OSM + Overture"
    assert POI(**base, source="overture", sources=["overture"]).data_label() == "Overture"
    wiki = POI(
        **base,
        sources=["osm"],
        description_source="wikipedia",
        wikipedia={"ru": {"title": "T", "url": "https://ru.wikipedia.org/wiki/T", "extract": "e"}},
    )
    assert wiki.data_label() == "OSM + Wikipedia"
    assert wiki.has_real_description()
    assert wiki.wikipedia_credit("ru") == (
        "Wikipedia, CC BY-SA 4.0",
        "https://ru.wikipedia.org/wiki/T",
    )
    assert POI(**base, description_source="derived").wikipedia_credit() is None
    assert not POI(**base, description_source="derived").has_real_description()
    assert POI(**base, description_source="osm").has_real_description()


def test_wikipedia_description_counts_in_retrieval_score(pois):
    lat, lon = PRESETS["Mega Silk Way"]
    intent = Intent(time_budget_min=120, categories=["cafe"])
    plain = retrieve(pois, lat, lon, intent, WED_NOON).candidates
    target = plain[0].poi
    boosted = [
        p.model_copy(update={"description_source": "wikipedia"}) if p.id == target.id else p
        for p in pois
    ]
    after = retrieve(boosted, lat, lon, intent, WED_NOON).candidates
    before_score = next(c.score for c in plain if c.poi.id == target.id)
    after_score = next(c.score for c in after if c.poi.id == target.id)
    assert after_score == pytest.approx(before_score + 0.3)


@pytest.mark.parametrize(
    ("category", "asked", "expected"),
    [
        ("culture_theatre_cinema", 25, 120),
        ("culture_theatre_cinema", 500, 150),
        ("museum_gallery", 20, 60),
        ("museum_gallery", 300, 90),
        ("cafe", 5, 30),
        ("park_garden", 45, 45),
        ("attraction_landmark", 90, 30),
        ("bar_nightlife", 10, 30),
        ("unknown_category", 500, 45),
    ],
)
def test_category_stay_clamp(category, asked, expected):
    assert gen_mod.category_stay(asked, category) == expected


def test_stay_clamped_by_category_then_budget(pois, monkeypatch):
    _, _, _, cands = _cafe_candidates(pois)
    cafe = next(c for c in cands if c.poi.category == "cafe")
    g, _ = _generate(pois, monkeypatch, [_rec(cafe.poi.id, minutes=5)], budget=300)
    assert g.recs[0].time_on_site_min == 30  # category floor
    g, _ = _generate(pois, monkeypatch, [_rec(cafe.poi.id, minutes=500)], budget=300)
    assert g.recs[0].time_on_site_min == 60  # category ceiling
    g, _ = _generate(pois, monkeypatch, [_rec(cafe.poi.id, minutes=60)], budget=40)
    assert g.recs[0].time_on_site_min <= 40  # the route budget has the last word


# ---- cache ----------------------------------------------------------------------------------------


def test_cache_hit_skips_the_api(monkeypatch, tmp_path):
    path = tmp_path / "cache.json"
    monkeypatch.setenv("WALKS_LLM_CACHE", str(path))
    out = LLMOutput(recommendations=[_rec("node/12")], route_order=["node/12"])
    fake = FakeGenai(monkeypatch, {"a": out})

    first = _ask(["a"], cache_key="secret-key-material")
    assert not first.step.cached
    assert fake.calls == ["a"]
    assert path.is_file()
    assert "secret-key-material" not in path.read_text(encoding="utf-8")  # a hash, no clear text

    second = _ask(["a"], cache_key="secret-key-material")
    assert fake.calls == ["a"]  # no second request
    assert second.step.cached
    assert second.step.model == "gemini:a"
    assert second.value == out

    _ask(["a"], cache_key="other")  # other key: miss
    assert fake.calls == ["a", "a"]
    FakeGenai(monkeypatch, {"b": out})
    third = _ask(["b"], cache_key="secret-key-material")  # other chain: miss
    assert not third.step.cached


def test_cache_disabled_without_key_material(monkeypatch, tmp_path):
    monkeypatch.setenv("WALKS_LLM_CACHE", str(tmp_path / "c.json"))
    fake = FakeGenai(monkeypatch, {"a": OK})
    _ask(["a"])
    _ask(["a"])
    assert fake.calls == ["a", "a"]
    assert not (tmp_path / "c.json").exists()


def test_corrupt_cache_is_ignored(monkeypatch, tmp_path):
    path = tmp_path / "c.json"
    path.write_text("{broken", encoding="utf-8")
    monkeypatch.setenv("WALKS_LLM_CACHE", str(path))
    fake = FakeGenai(monkeypatch, {"a": OK})
    assert not _ask(["a"], cache_key="k").step.cached
    assert fake.calls == ["a"]


def test_generate_replay_is_served_from_cache(pois, monkeypatch, tmp_path):
    monkeypatch.setenv("WALKS_LLM_CACHE", str(tmp_path / "c.json"))
    monkeypatch.setattr(llm, "llm_available", lambda: True)
    intent, lat, lon, cands = _cafe_candidates(pois)
    out = LLMOutput(recommendations=[_rec(cands[0].poi.id)])
    scripted = {spec.partition(":")[2]: out for spec in llm.generation_models()}
    fake = FakeGenai(monkeypatch, scripted)

    first = gen_mod.generate(intent, lat, lon, cands, WED_NOON)
    assert first.mode == "llm"
    assert first.step is not None
    assert not first.step.cached

    later = datetime(2026, 10, 14, 12, 20)  # same 30-minute bucket
    again = gen_mod.generate(intent, lat, lon, cands, later)
    assert again.step is not None
    assert again.step.cached
    assert [r.poi.id for r in again.recs] == [r.poi.id for r in first.recs]
    assert len(fake.calls) == 1

    gen_mod.generate(intent, lat, lon, cands, datetime(2026, 10, 14, 12, 40))  # next bucket
    assert len(fake.calls) == 2


def test_cache_material_keys():
    intent = Intent(categories=["cafe"])
    other_intent = Intent(categories=["park_garden"])
    base = gen_mod.cache_material(intent, 51.089, 71.416, [], WED_NOON)
    assert base != gen_mod.cache_material(intent, 51.090, 71.416, [], WED_NOON)
    assert base != gen_mod.cache_material(other_intent, 51.089, 71.416, [], WED_NOON)
    assert base != gen_mod.cache_material(
        intent, 51.089, 71.416, [], datetime(2026, 10, 14, 12, 30)
    )
    assert base == gen_mod.cache_material(
        intent, 51.089, 71.416, [], datetime(2026, 10, 14, 12, 29)
    )


# ---- template fallback only when the whole chain fails ----------------------------------------------


def test_template_only_after_whole_chain_failed(pois, monkeypatch):
    monkeypatch.setenv("LLM_CHAIN", "gemini:a,gemini:b")
    FakeGenai(monkeypatch, {"a": _api_error(503), "b": _api_error(503)})
    intent, lat, lon, cands = _cafe_candidates(pois)
    g = gen_mod.generate(intent, lat, lon, cands, WED_NOON)
    assert g.mode == "template"
    assert g.recs
    assert g.step is not None
    assert [a.model for a in g.step.attempts] == ["gemini:a", "gemini:b"]
    assert "ошибка ИИ" in g.note


def test_second_model_answers_so_no_template(pois, monkeypatch):
    monkeypatch.setenv("LLM_CHAIN", "gemini:a,gemini:b")
    intent, lat, lon, cands = _cafe_candidates(pois)
    out = LLMOutput(recommendations=[_rec(cands[0].poi.id)])
    FakeGenai(monkeypatch, {"a": _api_error(503), "b": out})
    g = gen_mod.generate(intent, lat, lon, cands, WED_NOON)
    assert g.mode == "llm"
    assert g.model == "gemini:b"
    assert g.step is not None
    assert [a.status for a in g.step.attempts] == ["error", "ok"]


def test_thinking_switch_per_model_family():
    traits = llm_providers.gemini_traits
    assert traits("gemini-2.5-flash-lite").thinking == "budget"
    assert traits("gemini-3.5-flash").thinking == "level_minimal"
    assert traits("gemini-flash-latest").thinking == "level_low"
    assert traits("gemini-3.1-flash-lite").thinking == "level_minimal"
    assert (
        traits("gemini-3.7-flash").thinking == "level_low"
    )  # 3.7 answers 400 to MINIMAL (live probe 17.10)
    assert traits("gemini-3.8-flash").thinking == "level_low"
    cfg = llm_providers._gemini_config("gemini-3.5-flash", "sys", LLMOutput)
    assert cfg.thinking_config.thinking_level.value == "MINIMAL"
    assert cfg.system_instruction == "sys"
