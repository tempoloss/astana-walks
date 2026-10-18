"""LLM chain: structured JSON output over an ordered fallback chain of providers/models and a response cache.

A chain is a comma-separated env list of `provider:model[@profile]` links (LLM_CHAIN for the recommendation
text, LLM_INTENT_CHAIN for intent refinement); the providers themselves are in walks.llm_providers. Each call
walks the chain in order. A link that answers 429 / 5xx / times out / returns a body that is not valid JSON for
the schema is abandoned at once (no backoff: the next link is the retry). A link that answered 503 or timed out
is skipped for BREAKER_S seconds by every later call in the process (circuit breaker). Only when the whole chain
fails does the caller get LLMUnavailable and switch to the no-AI path.

Successful answers are cached on disk (app/.local/llm_cache.json) under a sha256 of the caller's key material
and the chain, so replaying a demo scenario costs no API call.

The cache is a demo accelerator, not a guarantee: the offline guarantee is the template path (generate.py). With
WALKS_CACHE_PIN=1 (on in .env.demo) the key is the caller's material and the schema only (generate.cache_material
then drops the time bucket), and under WALKS_ENV=demo the recorded answers of data/demo_llm_cache.json
(`scripts/warm_cache.py`) are read as well, before the chain, also while Google is simulated down.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
import time
from collections.abc import Callable, Sequence
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import BaseModel

from .envcfg import cache_pin, demo_env, google_down, offline, replay_only
from .llm_providers import Link, ask, not_ready, parse_link
from .models import LLMAttempt, LLMStep

# Measured 18.10 on the real generation payload (5 calls each, p50): gemini-3.5-flash-lite 1.7 s, flash-lite-latest
# 1.6 s, 3.1-flash-lite 2.0 s, 2.5-flash 1.9 s (quota-limited on a free key), flash-latest / 3.7-flash 4.5-5.5 s,
# 3.5-flash 429 (quota) that day, gemma-4-26b 16 s and mostly invalid; all valid answers read alike. The fast links go
# first, the slow strong one is the fallback.
DEFAULT_GENERATION_CHAIN = (
    "gemini:gemini-3.5-flash-lite",
    "gemini:gemini-3.1-flash-lite",
    "gemini:gemini-2.5-flash",
    "gemini:gemini-flash-latest",
    "gemini:gemma-4-26b-a4b-it",  # last before the template; gemma-4-31b-it answered 504 for a whole day (16.10)
)
# The intent prompt: 3.5 / 3.1 flash-lite and flash-lite-latest answer in 1.4-1.8 s, 3.7-flash in 4.6 s.
DEFAULT_INTENT_CHAIN = (
    "gemini:gemini-3.5-flash-lite",
    "gemini:gemini-flash-lite-latest",
    "gemini:gemini-3.1-flash-lite",
    "gemini:gemma-4-26b-a4b-it",
)
GENERATION_TIMEOUT_S = (
    8.0  # per link attempt: the fast links answer in 2-3 s, a hung one gives way to the next
)
INTENT_TIMEOUT_S = 4.0
TOTAL_DEADLINE_S = (
    15.0  # hard cap per request over ALL links of intent + generation; then the template
)
INTENT_BUDGET_S = (
    5.0  # of which the intent step may use at most this much, the rest is for the generation
)
MIN_ATTEMPT_S = 1.0  # a link is not started with less time than this left
BREAKER_S = 120.0
CACHE_MAX_ENTRIES = 300
DEFAULT_CACHE_PATH = Path(__file__).resolve().parents[1] / ".local" / "llm_cache.json"
DEMO_CACHE_PATH = Path(__file__).resolve().parents[2] / "data" / "demo_llm_cache.json"
NOT_CONFIGURED = "ИИ не настроен (нет ключа Gemini и профилей LLM_PROFILE_*)"
OFFLINE_NOTE = "офлайн-режим (WALKS_OFFLINE): сетевые запросы отключены"
REPLAY_MISS_NOTE = "этот запрос не записан: в демо ИИ отвечает только записанными ответами"

_clock = time.monotonic  # tests replace it
_open_until: dict[str, float] = {}  # link label -> monotonic time until which it is skipped


class Deadline:
    """Time one request may still spend on LLM links, shared by the intent step and the generation step."""

    def __init__(self, total_s: float = TOTAL_DEADLINE_S):
        self._end = _clock() + total_s

    def remaining(self) -> float:
        return max(0.0, self._end - _clock())

    def capped(self, max_s: float) -> Deadline:
        """A deadline that ends with this one or `max_s` from now, whichever comes first."""
        sub = Deadline(0.0)
        sub._end = min(self._end, _clock() + max_s)
        return sub


class LLMUnavailable(RuntimeError):
    """No usable link or every link of the chain failed - callers switch to the no-AI fallback."""

    def __init__(self, message: str, step: LLMStep | None = None):
        super().__init__(message)
        self.step = step


class ReplayMiss(LLMUnavailable):
    """Replay-only mode (WALKS_REPLAY_ONLY): the request is not in the recording, no model is called."""


@dataclass
class LLMCall[T: BaseModel]:
    value: T
    step: LLMStep


def _chain(env: str, default: Sequence[str]) -> list[str]:
    names = [m.strip() for m in os.environ.get(env, "").split(",") if m.strip()]
    return list(dict.fromkeys(names)) or list(default)


def generation_models() -> list[str]:
    """Ordered chain for recommendation text (env LLM_CHAIN: provider:model[@profile], comma-separated)."""
    return _chain("LLM_CHAIN", DEFAULT_GENERATION_CHAIN)


def intent_models() -> list[str]:
    """Ordered chain for intent refinement (env LLM_INTENT_CHAIN, same syntax)."""
    return _chain("LLM_INTENT_CHAIN", DEFAULT_INTENT_CHAIN)


def _usable(spec: str) -> bool:
    try:
        return not_ready(parse_link(spec)) is None
    except ValueError:
        return False


def llm_available() -> bool:
    """True when at least one link of either chain has its key / profile configured; in replay-only mode always
    (the recording needs no key, and the cache lookup is only reached while the AI counts as available)."""
    return replay_only() or any(_usable(s) for s in [*generation_models(), *intent_models()])


def chain_text(models: Sequence[str]) -> str:
    """The chain as one line, links without a key / profile marked: 'gemini:a → openai:b@gw [не настроено]'."""
    return " → ".join(m if _usable(m) else f"{m} [не настроено]" for m in models)


def ai_off_reason(use_llm: bool) -> str:
    """Why the no-AI path is taken ('' when the LLM chain may be called)."""
    if offline():
        return OFFLINE_NOTE
    if not use_llm:
        return "ИИ отключён пользователем"
    return "" if llm_available() else NOT_CONFIGURED


# ---------------------------------------------------------------- circuit breaker


def reset_breakers() -> None:
    _open_until.clear()


def _breaker_left_s(label: str) -> int:
    return max(0, round(_open_until.get(label, 0.0) - _clock()))


def _classify(exc: Exception) -> tuple[str, bool]:
    """(short error text for the attempt log, whether the link should be skipped for a while).

    The text never carries a URL or a key: only an HTTP status, a keyword or the exception class."""
    from google.genai import errors

    if isinstance(exc, errors.APIError):
        code = getattr(exc, "code", None)
        return str(code), code == 503
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        return str(code), code == 503
    if isinstance(
        exc, TimeoutError | httpx.TimeoutException
    ):  # TimeoutError: raised by _with_deadline
        return "timeout", True
    if isinstance(exc, httpx.TransportError):
        return "network", False
    if isinstance(exc, ValueError):  # pydantic.ValidationError is a ValueError
        return "ответ не разобран", False
    return type(exc).__name__, False


# ---------------------------------------------------------------- cache


def _cache_path() -> Path | None:
    raw = os.environ.get("WALKS_LLM_CACHE", "").strip()
    if (
        raw.lower() == "off" or google_down()
    ):  # a simulated outage must not be answered from a Gemini cache hit
        return None
    return Path(raw) if raw else DEFAULT_CACHE_PATH


def _demo_cache_path() -> Path | None:
    """The recorded answers shipped with the repo (data/demo_llm_cache.json, read-only), only under WALKS_ENV=demo.
    Unlike the runtime cache it is read while Google is simulated down: it is the demo's recording, not a
    Gemini cache hit of this session. WALKS_LLM_CACHE=off disables both; WALKS_DEMO_CACHE=<path|off> overrides."""
    if not demo_env() or os.environ.get("WALKS_LLM_CACHE", "").strip().lower() == "off":
        return None
    raw = os.environ.get("WALKS_DEMO_CACHE", "").strip()
    if raw.lower() == "off":
        return None
    return Path(raw) if raw else DEMO_CACHE_PATH


def _full_key(
    material: str, models: Sequence[str], schema: type[BaseModel], *, pinned: bool = False
) -> str:
    """sha256 of the caller's material, the chain and the schema. Pinned (WALKS_CACHE_PIN): the chain is not part
    of it, so a recording made through one link is replayed whatever chain the demo machine has."""
    parts = [material, schema.__name__] if pinned else [material, ",".join(models), schema.__name__]
    return hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()


def _cache_load(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _cache_put(path: Path, key: str, model: str, body: str) -> None:
    data = _cache_load(path)
    data.pop(key, None)
    data[key] = {"model": model, "json": body}
    for old in list(data)[:-CACHE_MAX_ENTRIES]:
        del data[old]
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
        os.replace(tmp, path)
    except OSError:  # a read-only checkout must not break an answered request
        return


# ---------------------------------------------------------------- the call


def _with_deadline[R](fn: Callable[[], R], timeout_s: float) -> R:
    """Run fn in a daemon thread and give up after timeout_s (the thread is abandoned, never joined)."""
    box: dict = {}

    def target() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # handed back to the caller's thread
            box["error"] = exc

    worker = threading.Thread(target=target, daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        raise TimeoutError(f"нет ответа за {timeout_s:g} с")
    if "error" in box:
        raise box["error"]
    return box["value"]


def _cached_call[T: BaseModel](
    path: Path | None, key: str, chain: list[str], schema: type[T], t0: float
) -> LLMCall[T] | None:
    if path is None or not (hit := _cache_load(path).get(key)):
        return None
    try:
        value = schema.model_validate_json(hit["json"])
    except (ValueError, KeyError, TypeError):
        return None  # stale schema: ask again
    step = LLMStep(
        chain=chain, model=hit["model"], ms=round((time.perf_counter() - t0) * 1000), cached=True
    )
    return LLMCall(value, step)


def _skip_reason(spec: str) -> tuple[Link | None, LLMAttempt | None]:
    """The parsed link, or the attempt record explaining why this entry is not called."""
    try:
        link = parse_link(spec)
    except ValueError as exc:
        return None, LLMAttempt(model=spec, status="error", detail=str(exc))
    if why := not_ready(link):
        return None, LLMAttempt(model=link.label, status="skipped", detail=why)
    if left := _breaker_left_s(link.label):
        return None, LLMAttempt(
            model=link.label, status="skipped", detail=f"недавний сбой, ещё {left} с"
        )
    return link, None


def generate_json[T: BaseModel](
    prompt: str,
    schema: type[T],
    *,
    system: str,
    models: Sequence[str],
    timeout_s: float,
    cache_key: str | None = None,
    deadline: Deadline | None = None,
) -> LLMCall[T]:
    """Ask the first healthy link of `models` for a `schema` object; on failure move to the next one.

    `cache_key` is the caller's key material (hashed together with the chain and schema); None disables the
    cache for this call. `deadline` is the request-wide time budget: a link gets at most what is left of it and
    nothing is started once it is used up. Raises LLMUnavailable (with the attempt log in .step) when no link
    answered."""
    if offline():
        raise LLMUnavailable(OFFLINE_NOTE)
    chain = list(models)
    if not replay_only() and not any(_usable(s) for s in chain):
        raise LLMUnavailable(NOT_CONFIGURED)
    t0 = time.perf_counter()
    pinned = cache_pin()
    path = _cache_path() if cache_key is not None else None
    key = _full_key(cache_key or "", chain, schema, pinned=pinned)
    # the recording first: a runtime entry of the same pinned key (another chain's intent, an older answer) must not
    # take the demo off its recorded path
    for cache in (_demo_cache_path() if cache_key is not None and pinned else None, path):
        if (cached := _cached_call(cache, key, chain, schema, t0)) is not None:
            return cached
    # the public stand: a request that is not in the recording never reaches a model
    if replay_only():
        raise ReplayMiss(REPLAY_MISS_NOTE)
    attempts: list[LLMAttempt] = []
    for spec in chain:
        left = timeout_s if deadline is None else min(timeout_s, deadline.remaining())
        if deadline is not None and deadline.remaining() < MIN_ATTEMPT_S:
            attempts.append(
                LLMAttempt(model=spec, status="skipped", detail="бюджет времени запроса исчерпан")
            )
            break
        link, skipped = _skip_reason(spec)
        if link is None:
            attempts.append(skipped)  # type: ignore[arg-type]
            continue
        t = time.perf_counter()
        try:
            value = _with_deadline(
                lambda link=link, left=left: ask(link, prompt, system, schema, left), left
            )
        except Exception as exc:
            detail, trip = _classify(exc)
            if trip:
                _open_until[link.label] = _clock() + BREAKER_S
            attempts.append(
                LLMAttempt(
                    model=link.label,
                    status="error",
                    detail=detail,
                    ms=round((time.perf_counter() - t) * 1000),
                )
            )
            continue
        attempts.append(
            LLMAttempt(model=link.label, status="ok", ms=round((time.perf_counter() - t) * 1000))
        )
        if path is not None:
            _cache_put(path, key, link.label, value.model_dump_json())
        step = LLMStep(
            chain=chain,
            model=link.label,
            attempts=attempts,
            ms=round((time.perf_counter() - t0) * 1000),
        )
        return LLMCall(value, step)
    step = LLMStep(chain=chain, attempts=attempts, ms=round((time.perf_counter() - t0) * 1000))
    raise LLMUnavailable(f"все звенья цепочки недоступны: {step.attempts_text()}", step)
