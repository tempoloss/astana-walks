"""Process-wide switches read from the environment, and the optional `.env.<name>` loader.

- `WALKS_ENV=demo` -> `load_env_file()` reads app/.env.demo (untracked: it may name private endpoints) into
  os.environ without overriding variables that are already set.
- `WALKS_OFFLINE=1` -> `offline()`: no network call of any kind (LLM, weather/air, Valhalla); the template path,
  unknown weather (sun times from the local formula) and walking legs from the disk cache or the straight line.
- `WALKS_SIMULATE_GOOGLE_DOWN=1` -> `google_down()`: every gemini link fails as if Google were unreachable.
- `WALKS_CACHE_PIN=1` -> `cache_pin()`: demo replay mode of the LLM cache (on in .env.demo): the key is the scenario
  cell, the intent and the candidate ids only, so a recorded answer is replayed at any time of day.
- `WALKS_DEMO_PIN=1` -> `demo_pin()`: the demo preset (on in .env.demo): a recorded demo request (and the follow-ups of its
  dialogue) runs at a fixed time, with a fixed weather, walking legs from the shipped walk cache and the seeded copy of
  the people's marks (walks.demo_pin), so the warm-up script and the stage run exactly the same request; any other
  request is answered at the real time with the live weather.
- `WALKS_REPLAY_ONLY=1` -> `replay_only()`: recorded answers only (the jury's offline run): they are replayed (no key
  needed, no network LLM call is ever made), a request that is not in the recording gets the template text.
- `WALKS_AIR_DEMO=1` -> `air_demo()`: ask the Open-Meteo air-quality API for PM2.5 (the only PM2.5 leg without a key).
  Off by default: its free API is for non-commercial use only (open-meteo.com/en/terms), so it is a demo switch;
  the answer then says so (walks.weather.air_credit).
- `WALKS_DEMAND_SIM=1` -> `demand_sim()`: the «Город» demand view also offers the simulated demand file (labelled as
  simulated); off by default, so the page shows only the real request log and its honest empty state.
- `WALKS_FX_FAKE=1` -> `fx_fake()`: `/api/conditions?fake=…` serves a made-up scenario for the map's weather effects
  (screenshots and frame timings only).
"""

from __future__ import annotations

import os
from contextvars import ContextVar
from pathlib import Path

APP_DIR = Path(__file__).resolve().parents[1]
_TRUE = {"1", "true", "yes", "on"}


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in _TRUE


# Per-run override set by the UI toggle: a ContextVar keeps one session's toggle out of other sessions,
# unlike writing os.environ, which is process-wide and outlives the session that set it.
_OFFLINE_OVERRIDE: ContextVar[bool | None] = ContextVar("walks_offline_override", default=None)


def set_offline_override(value: bool | None) -> None:
    _OFFLINE_OVERRIDE.set(value)


def offline() -> bool:
    override = _OFFLINE_OVERRIDE.get()
    return _flag("WALKS_OFFLINE") if override is None else override


def google_down() -> bool:
    return _flag("WALKS_SIMULATE_GOOGLE_DOWN")


def demo_pin() -> bool:
    """WALKS_DEMO_PIN=1: the fixed demo configuration of walks.demo_pin."""
    return _flag("WALKS_DEMO_PIN")


def air_demo() -> bool:
    """WALKS_AIR_DEMO=1: the Open-Meteo PM2.5 leg is on (demo / non-commercial use only)."""
    return _flag("WALKS_AIR_DEMO")


def fx_fake() -> bool:
    """WALKS_FX_FAKE=1: `/api/conditions?fake=snow+night` serves a made-up scenario for the map weather effects (the
    screenshots and the frame timings; never on in a real run)."""
    return _flag("WALKS_FX_FAKE")


def demand_sim() -> bool:
    """WALKS_DEMAND_SIM=1: the «Город» demand view also serves the SIMULATED demand file (data/demand_sim.jsonl)."""
    return _flag("WALKS_DEMAND_SIM")


def demo_env() -> bool:
    return os.environ.get("WALKS_ENV", "").strip() == "demo"


def cache_pin() -> bool:
    """WALKS_CACHE_PIN=1: the LLM cache key drops the 30-minute time bucket and the chain (see walks.llm)."""
    return _flag("WALKS_CACHE_PIN")


def replay_only() -> bool:
    """WALKS_REPLAY_ONLY=1: the LLM is never called; the recorded answers (runtime cache, and under WALKS_ENV=demo +
    WALKS_CACHE_PIN the data/demo_llm_cache.json) are served, any other request takes the template path."""
    return _flag("WALKS_REPLAY_ONLY")


def load_env_file(directory: Path = APP_DIR) -> Path | None:
    """Load `.env.<WALKS_ENV>` from `directory` (KEY=VALUE lines, `#` comments); existing variables win.
    Returns the file that was read, None when WALKS_ENV is unset or the file does not exist."""
    name = os.environ.get("WALKS_ENV", "").strip()
    path = directory / f".env.{name}"
    if not name or not path.is_file():
        return None
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip().removeprefix("export ").strip(), value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
            value = value[1:-1]
        os.environ.setdefault(key, value)
    return path
