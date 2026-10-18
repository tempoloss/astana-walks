"""Record the demo's LLM answers into data/demo_llm_cache.json (tracked), the file `WALKS_ENV=demo` replays.

Runs the 5 scenarios of the brief and the 6 refine chips of the dialogue on top of a base scenario through
`walks.demo_pin.recommend_pinned`, the very function the UI and the CLI call under WALKS_DEMO_PIN=1: the same fixed
time, manual weather, walking legs from data/walk_cache.json and seeded people's marks. So a recorded answer is
keyed (scenario cell + intent + candidate ids, WALKS_CACHE_PIN) exactly as the stage will ask for it.

Only PUBLIC links answer: every `gemini:*` link and the public AlemLLM profile (`openai:*@alem`, key from
LLM_PROFILE_ALEM_API_KEY[_FILE] or the file <Hackathons>/.alem-key). Private gateway links of app/.env.demo are
dropped from the chain for this run, and an entry whose stored `model` is not a public link is refused, so the
`model` field of the shipped file is reproducible by anybody with their own key.

A request is recorded only when both the intent step (rules+llm) and the generation step were answered by a model.
Afterwards EVERY scenario is run once more with the recording as the only source (no runtime cache) and the table
`scenario -> cached, model` is printed; the exit code is 0 only when all of them report cached=True.

    uv run python scripts/warm_cache.py [--dry-run] [--verify-only] [--fresh] [--pause 3]

Needs the demo chain (app/.env.demo is read; WALKS_ENV defaults to demo here) and spends real LLM quota: 11
requests to the pipeline, about 16 model calls. `--dry-run` prints the plan, `--verify-only` skips the recording and
only runs the replay check against the existing file (no model call when everything is in it). The recording is
valid for the parser and the data it was made with: run it again after a change of walks/lexicon_concepts.py,
walks/intent.py, the POI data or data/city_feedback.json (a stale entry is just not found, the live chain answers).
The run resets app/.local/city_feedback.demo.json to the tracked seed.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import tempfile
import time
from dataclasses import dataclass
from pathlib import Path

from walks.demo_pin import PIN_DATE, recommend_pinned, setup_for
from walks.envcfg import load_env_file
from walks.feedback import DEMO_PATH, reseed
from walks.followup import conversation_after
from walks.llm import DEMO_CACHE_PATH, generation_models, intent_models, llm_available
from walks.llm_providers import is_public
from walks.models import Conversation, Result
from walks.presets import DEMO_REQUESTS, PRESETS, SCENARIOS

ALEM_KEY_FILE = Path(__file__).resolve().parents[3] / ".alem-key"
# the demo's requests that are not scenario buttons (text, preset): the web UI offers them as starters too
EXTRA = DEMO_REQUESTS
# the refine chips of walks.dialog (their `send` in Russian), each on the scenario where it makes sense (index into
# SCENARIOS)
FOLLOW_UPS: tuple[tuple[str, int], ...] = (
    ("а поближе?", 0),
    ("что-то другое", 0),
    ("а без алкоголя", 4),
    ("а подешевле", 1),
    ("а если с ребёнком", 0),
    ("на час дольше", 3),
)


@dataclass(frozen=True)
class Step:
    label: str
    text: str
    preset: str
    base_text: str | None = None  # the scenario text this follow-up refines
    base: str | None = None  # label of the step whose answer this one refines


def plan() -> list[Step]:
    steps = [Step(sc.text, sc.text, sc.preset) for sc in SCENARIOS]
    steps += [Step(text, text, preset) for text, preset in EXTRA]
    for text, index in FOLLOW_UPS:
        sc = SCENARIOS[index]
        steps.append(Step(f"{sc.text} → {text}", text, sc.preset, sc.text, sc.text))
    return steps


def _read(path: Path) -> dict:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    return data if isinstance(data, dict) else {}


def _answered(res: Result) -> str:
    """'' when both LLM steps were answered by a model, else why not."""
    if res.generation != "llm":
        return f"генерация: {res.generation_note or res.generation}"
    if res.continued:
        return ""  # a follow-up read by rules calls no intent model
    if res.intent.parser != "rules+llm":
        return f"разбор запроса: {res.intent.note or res.intent.parser}"
    return ""


def _replayed(res: Result) -> bool:
    """True when every model step of this request came from the recording."""
    if res.generation != "llm" or res.generation_step is None or not res.generation_step.cached:
        return False
    step = res.intent.llm_step
    return res.continued or (step is not None and step.cached)


def _public_chains() -> None:
    """Restrict LLM_CHAIN / LLM_INTENT_CHAIN to public links (and make the public AlemLLM key file visible)."""
    if (
        not os.environ.get("LLM_PROFILE_ALEM_API_KEY")
        and not os.environ.get("LLM_PROFILE_ALEM_API_KEY_FILE")
        and ALEM_KEY_FILE.is_file()
    ):
        os.environ["LLM_PROFILE_ALEM_API_KEY_FILE"] = str(ALEM_KEY_FILE)
    for name, chain in (
        ("LLM_CHAIN", generation_models()),
        ("LLM_INTENT_CHAIN", intent_models()),
    ):
        public = [spec for spec in chain if is_public(spec)]
        for spec in chain:
            if spec not in public:
                print(
                    f"{name}: частное звено исключено из записи: {spec.partition('@')[2] or spec}"
                )
        os.environ[name] = ",".join(public)


def _run(steps: list[Step]) -> list[tuple[Step, Result]]:
    """Every step through the pinned code path, each follow-up on the answer of its base step."""
    results: dict[str, Conversation] = {}
    out: list[tuple[Step, Result]] = []
    for s in steps:
        lat, lon = PRESETS[s.preset]
        res = recommend_pinned(
            s.text,
            lat,
            lon,
            base_text=s.base_text,
            conversation=results.get(s.base) if s.base else None,
        )
        results[s.label] = conversation_after(None, res)
        out.append((s, res))
    return out


def _print_table(rows: list[tuple[Step, Result]]) -> bool:
    """scenario -> cached, model; True when every request came from the recording."""
    width = max(len(s.label) for s, _ in rows)
    print(f"{'scenario':<{width}}  cached  model")
    ok = True
    for s, res in rows:
        cached = _replayed(res)
        ok &= cached
        model = res.model or (res.generation_note or res.generation)
        print(f"{s.label:<{width}}  {cached!s:<6}  {model}")
    print(f"cached=True: {sum(_replayed(r) for _, r in rows)} of {len(rows)}")
    return ok


def _record(steps: list[Step], scratch: Path, recording: dict, pause: float) -> list[str]:
    """Run the live chain once per step and merge the new entries into `recording`; the failed steps."""
    failed: list[str] = []
    results: dict[str, Conversation] = {}
    for n, s in enumerate(steps):
        if n:
            time.sleep(pause)
        before = set(_read(scratch))
        lat, lon = PRESETS[s.preset]
        res = recommend_pinned(
            s.text,
            lat,
            lon,
            base_text=s.base_text,
            conversation=results.get(s.base) if s.base else None,
        )
        results[s.label] = conversation_after(None, res)
        fresh = {k: v for k, v in _read(scratch).items() if k not in before}
        private = [e["model"] for e in fresh.values() if not is_public(e["model"])]
        if why := _answered(res) or (f"звено не публичное: {private[0]}" if private else ""):
            failed.append(f"{s.label}: {why}")
            print(f"FAIL {s.label}: {why}")
            continue
        for key, entry in fresh.items():
            recording[key] = {**entry, "label": s.label}
        print(f"ok   {s.label}  ({res.model}, {len(fresh)} new)")
    return failed


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawTextHelpFormatter)
    ap.add_argument("--dry-run", action="store_true", help="print the plan, call nothing")
    ap.add_argument(
        "--verify-only", action="store_true", help="only replay every scenario from the recording"
    )
    ap.add_argument(
        "--fresh", action="store_true", help="start from an empty file (default: update it)"
    )
    ap.add_argument(
        "--missing",
        action="store_true",
        help="record only the requests the recording does not hold yet (the rest is replayed, no model call)",
    )
    ap.add_argument("--pause", type=float, default=3.0, help="seconds between requests")
    ap.add_argument("--out", type=Path, default=DEMO_CACHE_PATH, help="the recording to write")
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    steps = plan()
    if args.dry_run:
        for s in steps:
            setup = setup_for(s.text, s.base_text)
            print(f"{s.preset:<14} {s.label}\n{'':<14} {setup.describe()}")
        print(f"{len(steps)} requests (pinned to {PIN_DATE}) -> {args.out}")
        return 0

    os.environ.setdefault("WALKS_ENV", "demo")
    blockers = ["WALKS_OFFLINE", "WALKS_SIMULATE_GOOGLE_DOWN"]
    if not args.verify_only:
        blockers.append(
            "WALKS_REPLAY_ONLY"
        )  # replaying is what --verify-only does; recording needs the models
    for name in blockers:
        if os.environ.get(name):
            print(f"{name} is set: nothing can be recorded through it", file=sys.stderr)
            return 2
    if (env_file := load_env_file()) is not None:
        print(f"Окружение: {env_file.name}")
    # the stage configuration: the demo preset and the pinned cache key, the people's marks of the seed
    os.environ.update(WALKS_DEMO_PIN="1", WALKS_CACHE_PIN="1", WALKS_REQUEST_LOG="off")
    os.environ.pop("WALKS_FEEDBACK", None)
    reseed(DEMO_PATH)

    recording = {} if args.fresh else _read(args.out)
    failed: list[str] = []
    if not args.verify_only:
        _public_chains()
        if not llm_available():
            print(
                "no public LLM link is configured (GEMINI key, or the AlemLLM key file): nothing to record",
                file=sys.stderr,
            )
            return 2
        scratch = Path(tempfile.mkdtemp(prefix="warm_cache_")) / "llm_cache.json"
        # --missing: what the recording already holds is replayed (no model call), only the gaps go to the chain
        demo_cache = str(args.out) if args.missing else "off"
        os.environ.update(WALKS_LLM_CACHE=str(scratch), WALKS_DEMO_CACHE=demo_cache)
        failed = _record(steps, scratch, recording, args.pause)
        if bad := [k for k, e in recording.items() if not is_public(e.get("model", ""))]:
            print(f"{len(bad)} entries answered by a non-public link: not written", file=sys.stderr)
            return 1
        if recording:
            args.out.parent.mkdir(parents=True, exist_ok=True)
            args.out.write_text(
                json.dumps(recording, ensure_ascii=False, indent=1) + "\n",
                encoding="utf-8",
                newline="\n",
            )
        print(f"{len(recording)} entries -> {args.out}; failed: {len(failed)}")

    # replay: the stage reads only the recording (WALKS_ENV=demo, no runtime cache)
    reseed(DEMO_PATH)
    # WALKS_LLM_CACHE=off would switch the recording off too: an empty runtime cache stands in for the stage's own
    empty = Path(tempfile.mkdtemp(prefix="warm_cache_replay_")) / "llm_cache.json"
    os.environ.update(WALKS_LLM_CACHE=str(empty), WALKS_DEMO_CACHE=str(args.out))
    print(f"\nПроверка воспроизведения: каждый сценарий ещё раз, только из {args.out.name}")
    replayed = _print_table(_run(steps))
    return 0 if replayed and not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
