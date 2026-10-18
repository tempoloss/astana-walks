"""LLM back-ends behind one contract: `ask(link, prompt, system, schema, timeout_s)` returns a validated
`schema` instance or raises. Two providers:

- `gemini`: google-genai with an AI Studio key (env GEMINI_API_KEY, else the first line of GEMINI_KEY_FILE /
  <Hackathons>/.gemini-key). Per-model request settings live in `gemini_traits` (Gemma differs from Gemini).
- `openai`: any OpenAI-compatible `POST {base_url}/chat/completions` over httpx. The endpoint is a named profile
  (`openai:model@gw` reads LLM_PROFILE_GW_BASE_URL / _API_KEY / _API_KEY_FILE / _JSON_MODE); without a
  profile OPENAI_BASE_URL / OPENAI_API_KEY (default base https://api.openai.com/v1) are used.

An answer that is not valid JSON for the schema is an error for both providers, exactly like an HTTP failure:
the caller (walks.llm) moves to the next link of the chain. Nothing here puts a URL or a key into an exception.
"""

from __future__ import annotations

import functools
import json
import os
import re
import ssl
from dataclasses import dataclass
from pathlib import Path

import httpx
from pydantic import BaseModel

from .envcfg import google_down

PROVIDERS = ("gemini", "openai")
DEFAULT_OPENAI_BASE = "https://api.openai.com/v1"
# Public OpenAI-compatible endpoints that need only a key: LLM_PROFILE_ALEM_API_KEY[_FILE] (AlemLLM, models
# `alemllm`, `gemma4`). A LLM_PROFILE_<NAME>_BASE_URL overrides the default.
PROFILE_BASE_URLS = {"ALEM": "https://llm.alem.ai/v1"}
MIN_SERVER_DEADLINE_S = 10.0  # Gemini rejects a smaller X-Server-Timeout
CONNECT_TIMEOUT_S = (
    3.0  # an unreachable host must not eat the whole per-link / request budget: next link at once
)
MAX_MINIMAL_MINOR = 5  # explicit gemini-3.x names up to 3.5 take thinking level MINIMAL
# Fallback key file used on the hackathon workstation: <Hackathons>/.gemini-key (one line).
_KEY_FILE = Path(__file__).resolve().parents[3] / ".gemini-key"

_transport: httpx.BaseTransport | None = None  # tests inject httpx.MockTransport
_no_json_mode: set[str] = set()  # openai links whose endpoint refused `response_format`


@dataclass(frozen=True)
class Link:
    """One entry of a chain: `provider:model[@profile]`."""

    provider: str
    model: str
    profile: str | None = None

    @property
    def label(self) -> str:
        return f"{self.provider}:{self.model}" + (f"@{self.profile}" if self.profile else "")


def parse_link(spec: str) -> Link:
    provider, sep, rest = spec.strip().partition(":")
    model, _, profile = rest.rpartition("@") if "@" in rest else (rest, "", "")
    model, profile = model.strip(), profile.strip()
    if not sep or provider not in PROVIDERS or not model:
        raise ValueError(f"запись цепочки «{spec}» — ожидается provider:model[@profile]")
    if profile and provider != "openai":
        raise ValueError(f"профиль @{profile} возможен только у openai: {spec}")
    return Link(provider, model, profile or None)


# ---------------------------------------------------------------- credentials


def _first_line(path: Path) -> str | None:
    try:
        lines = path.read_text(encoding="utf-8").strip().splitlines()
    except OSError:
        return None
    return lines[0].strip() if lines and lines[0].strip() else None


def gemini_key() -> str | None:
    key = os.environ.get("GEMINI_API_KEY", "").strip()
    if key:
        return key
    return _first_line(Path(os.environ.get("GEMINI_KEY_FILE") or _KEY_FILE))


@dataclass(frozen=True)
class Endpoint:
    base_url: str
    api_key: str
    json_mode: str  # json_object | json_schema | none
    ca_file: str = ""  # extra CA bundle (PEM) for a gateway with a private CA


@functools.cache
def _tls_context(ca_file: str) -> ssl.SSLContext:
    """The operating system's trust store (httpx alone would use certifi, which lacks corporate / private CAs),
    plus the profile's own CA bundle when given."""
    context = ssl.create_default_context()
    if ca_file:
        context.load_verify_locations(cafile=ca_file)
    return context


def _env_name(profile: str) -> str:
    return re.sub(r"[^A-Z0-9]+", "_", profile.upper()).strip("_")


def openai_endpoint(profile: str | None) -> Endpoint | None:
    """Endpoint of an openai link, None when its base URL or key is not configured."""
    if profile:
        prefix = f"LLM_PROFILE_{_env_name(profile)}_"
        name = _env_name(profile)
        base = os.environ.get(prefix + "BASE_URL", "").strip() or PROFILE_BASE_URLS.get(name, "")
        key = os.environ.get(prefix + "API_KEY", "").strip()
        if not key and (key_file := os.environ.get(prefix + "API_KEY_FILE", "").strip()):
            key = _first_line(Path(key_file)) or ""
        mode = os.environ.get(prefix + "JSON_MODE", "json_object").strip().lower()
        ca_file = os.environ.get(prefix + "CA_FILE", "").strip()
    else:
        base = os.environ.get("OPENAI_BASE_URL", "").strip() or DEFAULT_OPENAI_BASE
        key = os.environ.get("OPENAI_API_KEY", "").strip()
        mode = "json_object"
        ca_file = os.environ.get("OPENAI_CA_FILE", "").strip()
    if not base or not key:
        return None
    return Endpoint(
        base.rstrip("/"),
        key,
        mode if mode in {"json_object", "json_schema"} else "none",
        ca_file,
    )


def is_public(spec: str) -> bool:
    """True for a link anybody can reach with their own key: any `gemini` link, or an `openai` link whose profile
    is a built-in public one (PROFILE_BASE_URLS) still pointing at its public base URL. Everything else (a private
    gateway, OPENAI_BASE_URL) is user infrastructure whose answers a shipped recording must not name."""
    try:
        link = parse_link(spec)
    except ValueError:
        return False
    if link.provider == "gemini":
        return True
    if not link.profile:
        return False
    name = _env_name(link.profile)
    public = PROFILE_BASE_URLS.get(name)
    override = os.environ.get(f"LLM_PROFILE_{name}_BASE_URL", "").strip().rstrip("/")
    return public is not None and override in ("", public)


def not_ready(link: Link) -> str | None:
    """Why the link cannot be called (missing key / profile), None when it can."""
    if link.provider == "gemini":
        return None if gemini_key() else "нет GEMINI_API_KEY"
    if openai_endpoint(link.profile) is None:
        return f"профиль {link.profile} не настроен" if link.profile else "нет OPENAI_API_KEY"
    return None


# ---------------------------------------------------------------- answer parsing


_FENCE = re.compile(r"^```(?:json)?\s*(.*?)\s*```$", re.S | re.I)


def parse_answer[T: BaseModel](text: str, schema: type[T]) -> T:
    """Validate a model's text as `schema`: a markdown fence around the JSON is tolerated, anything else that is
    not a valid object (prose, truncated JSON, wrong fields) raises ValueError."""
    body = text.strip()
    if m := _FENCE.match(body):
        body = m.group(1)
    return schema.model_validate_json(body)


def _schema_hint(schema: type[BaseModel]) -> str:
    return (
        "Reply with ONE JSON object only (no markdown, no commentary) that validates against this JSON "
        "Schema:\n" + json.dumps(schema.model_json_schema(), ensure_ascii=False)
    )


# ---------------------------------------------------------------- gemini


@dataclass(frozen=True)
class GeminiTraits:
    """Request settings that differ between model families (measured against the live API, 16.10)."""

    thinking: (
        str | None
    )  # "budget" | "level_minimal" | "level_low" | None: the model rejects any thinking config
    system_instruction: bool  # False: the system prompt is prepended to the user prompt
    json_mode: (
        bool  # False: no response_mime_type / response_schema; JSON is requested in the prompt
    )


def gemini_traits(model: str) -> GeminiTraits:
    """Thinking is kept minimal: the answers are short and structured, and an unrestricted 3.x model needed 30 s.
    2.5 takes a token budget (0 is allowed), explicit 3.x names take level MINIMAL, aliases such as
    gemini-flash-latest reject MINIMAL but accept LOW.

    Gemma (same API, live probes 16.10, gemma-4-26b-a4b-it): any thinking config -> 400 ("Thinking level/budget
    is not supported for this model"). The service itself is flaky (instant 500 INTERNAL, 504 after 30-45 s and
    429 after a burst, on every configuration), so only success rates can be compared: with a system_instruction
    1 valid answer in ~14 calls (27 s), the other attempts 500/504; with the system prompt folded into the user
    message plus response_mime_type + response_schema 4 valid answers in ~12 calls (3-13 s) and two degenerate
    bodies ("type-type-type...", rejected by validation -> next link). Hence: no thinking config, no
    system_instruction, JSON mode on (with the schema). On the real generation payload only that variant ever
    answered validly (1 of ~13 calls; mime-only / prompt-only variants 0 of ~26); its text has hyphen glitches.
    gemma-4-31b-it answered 504 on every call at probe time."""
    if model.startswith("gemma"):
        return GeminiTraits(thinking=None, system_instruction=False, json_mode=True)
    if "2.5" in model:
        return GeminiTraits("budget", True, True)
    return GeminiTraits("level_minimal" if _accepts_minimal(model) else "level_low", True, True)


def _accepts_minimal(model: str) -> bool:
    """Thinking level MINIMAL: explicit gemini-3.0 .. 3.5 names accept it; gemini-3.7-flash (live probe 17.10) answers 400
    «Thinking level MINIMAL is not supported», like the aliases (gemini-flash-latest), so newer versions use LOW."""
    match = re.match(r"gemini-3\.(\d+)", model)
    return match is not None and int(match.group(1)) <= MAX_MINIMAL_MINOR


def _gemini_config(model: str, system: str, schema: type[BaseModel]):
    from google.genai import types

    traits = gemini_traits(model)
    fields: dict = {"temperature": 0.3}
    if traits.system_instruction:
        fields["system_instruction"] = system
    if traits.json_mode:
        fields["response_mime_type"] = "application/json"
        fields["response_schema"] = schema
    if traits.thinking == "budget":
        fields["thinking_config"] = types.ThinkingConfig(thinking_budget=0)
    elif traits.thinking:
        level = (
            types.ThinkingLevel.MINIMAL
            if traits.thinking == "level_minimal"
            else types.ThinkingLevel.LOW
        )
        fields["thinking_config"] = types.ThinkingConfig(thinking_level=level)
    return types.GenerateContentConfig(**fields)


def _ask_gemini[T: BaseModel](
    model: str, prompt: str, system: str, schema: type[T], timeout_s: float
) -> T:
    if google_down():
        raise httpx.ConnectError("simulated Google outage")
    from google import genai
    from google.genai import types

    # The API refuses a server deadline under 10 s (HTTP 400), so HttpOptions.timeout only bounds the abandoned
    # request; the real per-attempt limit is enforced by walks.llm._with_deadline.
    client = genai.Client(
        api_key=gemini_key(),
        http_options=types.HttpOptions(timeout=int(max(timeout_s, MIN_SERVER_DEADLINE_S) * 1000)),
    )
    traits = gemini_traits(model)
    contents = prompt if traits.system_instruction else f"{system}\n\n{prompt}"
    if not traits.json_mode:
        contents = f"{contents}\n\n{_schema_hint(schema)}"
    resp = client.models.generate_content(
        model=model, contents=contents, config=_gemini_config(model, system, schema)
    )
    if resp.parsed is not None and isinstance(resp.parsed, schema):
        return resp.parsed
    return parse_answer(resp.text or "", schema)


# ---------------------------------------------------------------- openai-compatible


def _chat_body(link: Link, endpoint: Endpoint, prompt: str, system: str, schema: type[BaseModel]):
    body: dict = {
        "model": link.model,
        "temperature": 0.3,
        "messages": [
            {"role": "system", "content": f"{system}\n\n{_schema_hint(schema)}"},
            {"role": "user", "content": prompt},
        ],
    }
    if endpoint.json_mode == "json_object" and link.label not in _no_json_mode:
        body["response_format"] = {"type": "json_object"}
    elif endpoint.json_mode == "json_schema" and link.label not in _no_json_mode:
        body["response_format"] = {
            "type": "json_schema",
            "json_schema": {"name": schema.__name__, "schema": schema.model_json_schema()},
        }
    return body


def _ask_openai[T: BaseModel](
    link: Link, prompt: str, system: str, schema: type[T], timeout_s: float
) -> T:
    endpoint = openai_endpoint(link.profile)
    if endpoint is None:
        raise RuntimeError("endpoint не настроен")
    headers = {"Authorization": f"Bearer {endpoint.api_key}"}
    with httpx.Client(
        timeout=httpx.Timeout(timeout_s, connect=min(CONNECT_TIMEOUT_S, timeout_s)),
        transport=_transport,
        verify=_tls_context(endpoint.ca_file),
    ) as http:
        body = _chat_body(link, endpoint, prompt, system, schema)
        resp = http.post(f"{endpoint.base_url}/chat/completions", json=body, headers=headers)
        if resp.status_code in (400, 422) and "response_format" in body:
            _no_json_mode.add(
                link.label
            )  # the endpoint has no JSON mode: instruction + parsing only
            del body["response_format"]
            resp = http.post(f"{endpoint.base_url}/chat/completions", json=body, headers=headers)
        resp.raise_for_status()
        data = resp.json()
    try:
        content = data["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("в ответе нет choices[0].message.content") from exc
    return parse_answer(content or "", schema)


def ask[T: BaseModel](link: Link, prompt: str, system: str, schema: type[T], timeout_s: float) -> T:
    if link.provider == "gemini":
        return _ask_gemini(link.model, prompt, system, schema, timeout_s)
    return _ask_openai(link, prompt, system, schema, timeout_s)
