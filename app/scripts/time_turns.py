"""How long POST /api/turn takes, stage by stage, on a local server with the live model chain.

    uv run python scripts/time_turns.py --port 8911 --label before [--out .local/timing] [--keep-breakers]

The app runs in this process (uvicorn on 127.0.0.1:<port>) in the stand's configuration: no demo pin, no pinned cache
key, no replay, the model chain of app/.env.<WALKS_ENV> (default `demo`), the LLM response cache off (every message
reaches a model, as a new message does), walking legs in memory only. Timers are wrapped around the core's own
functions (nothing else changes); every message goes over HTTP as the page sends it; after some of them the first
chip of the answer is tapped (a follow-up with the returned state). Every turn starts with the chain's circuit
breakers closed, so each one measures the model path; --keep-breakers keeps them across the turns, as a running
stand does (a link one turn found hung or slow is skipped by the next ones, walks.llm).

Stages, wall-clock milliseconds per turn. Parallel steps overlap, so the stages do not add up to the total:
  rules           the dialogue's rule reading before the search, and every walks.intent.parse_rules
  intent_model    the model calls that read the message (the Intent and FollowUp schemas)
  retrieval       walks.retrieve.retrieve
  routing         the pipeline's route step (walking legs, the route, visit hours) and the map's street lines
  weather_events  the weather lookup, the notices and the afisha block
  generation      the model calls that write the answer (the LLMOutput schema; a second call counts too)
  verification    code's checks of the model's answer (walks.generate: ids, claims, the opening, vague reasons)
  total           the client's wait: from sending the request to the answer line
  first_line      the client's wait for the first progress line
Writes <out>/<label>.jsonl (one row per turn) and <label>.md (p50 / p95 per stage). The request log of the run goes to
<out>/<label>_requests.jsonl."""

from __future__ import annotations

import argparse
import json
import math
import os
import sys
import threading
import time
from collections.abc import Callable
from pathlib import Path

APP = Path(__file__).resolve().parents[1]
DEFAULT_OUT = APP / ".local" / "timing"
sys.path.insert(0, str(APP))

# (text, tap the first chip of the answer afterwards)
MESSAGES = (
    ("хочу поесть", True),
    ("кофе рядом", True),
    ("погулять хочу просто", False),
    ("аптека рядом", False),
    ("что посмотреть", True),
    ("куда сходить с ребёнком", False),
    ("баламен қайда баруға болады", False),
    ("what should i see", True),
    ("где поужинать недорого", False),
    ("хочу в парк", True),
    ("музей", False),
    ("банкомат рядом", False),
    ("продуктовый магазин рядом", False),
    ("куда пойти вечером с друзьями", False),
    ("кофе с wifi поработать", False),
    ("кофе ішкім келеді", False),
    ("a quiet place to read", False),
    ("coffee nearby", False),
    ("где погулять с собакой", False),
    ("куда сходить на 2 часа", False),
)
STAGES = (
    "rules",
    "intent_model",
    "retrieval",
    "routing",
    "weather_events",
    "generation",
    "verification",
    "other",
    "total",
    "first_line",
)
MODEL_STAGE = {"Intent": "intent_model", "FollowUp": "intent_model", "LLMOutput": "generation"}

_lock = threading.Lock()
SPANS: list[tuple[str, float, float]] = []
RESULTS: list = []  # the pipeline's Result of each search of the turn


def _configure(label: str, out: Path, *, repeat: bool) -> None:
    os.environ.setdefault("WALKS_ENV", "demo")
    cache = out / f"{label}_llm_cache.json"
    cache.unlink(missing_ok=True)  # this run's own response cache, empty at the start
    # set before the env file is read: existing variables win over it, so the run is the stand's configuration
    os.environ.update(
        WALKS_DEMO_PIN="0",
        WALKS_CACHE_PIN="0",
        WALKS_REPLAY_ONLY="0",
        WALKS_DEMAND_SIM="0",
        WALKS_LLM_CACHE=str(cache) if repeat else "off",
        WALKS_WALK_CACHE="off",
        WALKS_REQUEST_LOG=str(out / f"{label}_requests.jsonl"),
    )


def _span(stage: str, t0: float) -> None:
    with _lock:
        SPANS.append((stage, t0, time.perf_counter()))


def _timed(stage: str | Callable[..., str], fn: Callable) -> Callable:
    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        try:
            return fn(*args, **kwargs)
        finally:
            _span(stage(*args, **kwargs) if callable(stage) else stage, t0)

    return wrapper


def _kept(fn: Callable) -> Callable:
    """The pipeline's own call: its span (the search) and its Result."""

    def wrapper(*args, **kwargs):
        t0 = time.perf_counter()
        res = fn(*args, **kwargs)
        with _lock:
            SPANS.append(("search", t0, time.perf_counter()))
            RESULTS.append(res)
        return res

    return wrapper


def _model_stage(_prompt, schema=None, *_, **kwargs) -> str:
    schema = schema or kwargs.get("schema")
    return MODEL_STAGE.get(getattr(schema, "__name__", ""), "model_other")


def _everywhere(orig: Callable, wrapper: Callable) -> int:
    """Replace `orig` by `wrapper` in every loaded module of the app that holds it by name."""
    hits = 0
    for name, mod in list(sys.modules.items()):
        if mod is None or name.split(".")[0] not in ("walks", "web"):
            continue
        for attr, value in list(vars(mod).items()):
            if value is orig:
                setattr(mod, attr, wrapper)
                hits += 1
    return hits


def _instrument() -> None:
    import walks.dialog as dialog
    import walks.generate as gen
    import walks.intent as intent
    import walks.llm as llm
    import walks.pipeline as pipeline
    import walks.retrieve as retrieve
    import web.server  # noqa: F401  (loads every module the app serves with)
    import web.turns as turns
    from walks.walking import WalkingRouter

    plan = [
        (intent.parse_rules, "rules"),
        (llm.generate_json, _model_stage),
        (retrieve.retrieve, "retrieval"),
        (pipeline.apply_leg, "routing"),
        (pipeline.replace_unreachable, "routing"),
        (pipeline.build_route, "routing"),
        (pipeline.sync_stays, "routing"),
        (pipeline.attach_lrt_hints, "routing"),
        (turns.route_shape, "routing"),
        (turns.place_legs, "routing"),
        (dialog._lighting, "routing"),
        (turns.fetch_weather, "weather_events"),
        (dialog.weather_at, "weather_events"),
        (dialog.events_block, "weather_events"),
        (dialog._notices, "weather_events"),
        (gen._from_llm, "verification"),
        (gen._finish, "verification"),
        (gen.checked_opening, "verification"),
        (gen.vague_ids, "verification"),
        (gen._clean_want, "verification"),
        (pipeline.visit_note, "verification"),
        (pipeline.refresh_why, "verification"),
        (dialog.take_turn, "turn"),
        (turns.answer, "answer"),
    ]
    for fn, stage in plan:
        if not _everywhere(fn, _timed(stage, fn)):
            raise SystemExit(f"nothing to time: {fn.__module__}.{fn.__name__}")
    _everywhere(pipeline.recommend, _kept(pipeline.recommend))
    WalkingRouter.leg = _timed("routing", WalkingRouter.leg)
    WalkingRouter._fetch = _timed("routing_network", WalkingRouter._fetch)


def _union(intervals: list[tuple[float, float]]) -> float:
    total, end = 0.0, -math.inf
    for a, b in sorted(intervals):
        if b <= end:
            continue
        total += b - max(a, end)
        end = b
    return total


def _stages(spans: list[tuple[str, float, float]], total_ms: float) -> dict:
    """Milliseconds per stage of one turn from its spans (the union of a stage's intervals). `rules` is the dialogue's
    reading before the pipeline (minus any model call there) plus every rule parse inside the pipeline."""
    by: dict[str, list[tuple[float, float]]] = {}
    for stage, a, b in spans:
        by.setdefault(stage, []).append((a, b))
    answer = by.get("answer", [(0.0, 0.0)])[0]
    turn = by.get("turn", [answer])[0]
    search = min((a for a, _ in by.get("search", [])), default=turn[1])
    pre = (turn[0], search)
    models = [
        iv
        for s in ("intent_model", "generation", "model_other", "retrieval", "routing")
        for iv in by.get(s, [])
    ]
    inside = [(max(a, pre[0]), min(b, pre[1])) for a, b in models if b > pre[0] and a < pre[1]]
    pre_rules = max((pre[1] - pre[0]) - _union(inside), 0.0)
    later_rules = [b - a for a, b in by.get("rules", []) if a >= pre[1]]
    out = {"rules": (pre_rules + sum(later_rules)) * 1000}
    for stage in (
        "intent_model",
        "retrieval",
        "routing",
        "weather_events",
        "generation",
        "verification",
        "routing_network",
    ):
        out[stage] = _union(by.get(stage, [])) * 1000
    out["network_legs"] = len(by.get("routing_network", []))
    out["intent_calls"] = len(by.get("intent_model", []))
    out["generation_calls"] = len(by.get("generation", []))
    covered = _union(
        [pre]
        + [
            iv
            for s in (
                "rules",
                "intent_model",
                "retrieval",
                "routing",
                "weather_events",
                "generation",
                "verification",
                "model_other",
            )
            for iv in by.get(s, [])
        ]
    )
    out["other"] = max((answer[1] - answer[0]) - covered, 0.0) * 1000
    out["server"] = (answer[1] - answer[0]) * 1000
    out["total"] = total_ms
    return out


def _send(client, url: str, body: dict) -> tuple[dict, list[tuple[str, float]], float]:
    lines: list[tuple[str, float]] = []
    t0 = time.perf_counter()
    with client.stream("POST", url, json=body, timeout=120) as resp:
        resp.raise_for_status()
        for raw in resp.iter_lines():
            if not raw.strip():
                continue
            ms = (time.perf_counter() - t0) * 1000
            msg = json.loads(raw)
            if "stage" in msg:
                lines.append((msg["stage"], round(ms)))
            elif "answer" in msg:
                return msg["answer"], lines, ms
            else:
                raise RuntimeError(f"the turn failed: {msg}")
    raise RuntimeError("no answer line")


def _turn_row(text: str, follow: bool, answer: dict, lines, total_ms: float) -> dict:
    from walks.generate import pick_diverse

    with _lock:
        spans, results = list(SPANS), list(RESULTS)
        SPANS.clear()
        RESULTS.clear()
    stages = _stages(spans, total_ms)
    stages["first_line"] = lines[0][1] if lines else total_ms
    row = {
        "text": text,
        "follow_up": follow,
        "kind": answer["turn"]["kind"],
        "places": [p["id"] for p in answer["turn"]["places"]],
        "lines": lines,
        "ms": {k: round(v) for k, v in stages.items()},
    }
    if results:
        res = results[-1]
        picks = [c.poi.id for c in pick_diverse(res.retrieval.candidates)]
        row |= {
            "parser": res.intent.parser,
            "intent_step": res.intent.llm_step.attempts_text() if res.intent.llm_step else "",
            "generation": res.generation,
            "generation_step": res.generation_step.attempts_text() if res.generation_step else "",
            "pipeline_ms": res.timings_ms,
            "first_picks": picks,
            "places_known_after_retrieval": picks == row["places"],
        }
    return row


def _pct(values: list[float], q: float) -> float:
    s = sorted(values)
    k = (len(s) - 1) * q
    lo, hi = math.floor(k), math.ceil(k)
    return s[lo] + (s[hi] - s[lo]) * (k - lo)


def table(rows: list[dict], title: str) -> str:
    head = [
        f"## {title}",
        "",
        f"Ходов: {len(rows)}.",
        "",
        "| Этап | p50, мс | p95, мс |",
        "|---|---:|---:|",
    ]
    for stage in STAGES:
        values = [r["ms"][stage] for r in rows if stage in r["ms"]]
        if values:
            head.append(f"| {stage} | {_pct(values, 0.5):.0f} | {_pct(values, 0.95):.0f} |")
    same = [r for r in rows if "places_known_after_retrieval" in r]
    if same:
        n = sum(r["places_known_after_retrieval"] for r in same)
        head += ["", f"Места ответа = первые места поиска (до модели): {n} из {len(same)}."]
    return "\n".join(head) + "\n"


def run(
    port: int, label: str, out: Path, *, repeat: bool, keep_breakers: bool = False
) -> list[dict]:
    import httpx
    import uvicorn

    from walks.llm import reset_breakers
    from walks.presets import PRESETS
    from walks.walking import default_router

    _instrument()
    from web.server import app

    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    while not server.started:
        time.sleep(0.05)
    url = f"http://127.0.0.1:{port}/api/turn"
    lat, lon = PRESETS["EXPO"]
    rows: list[dict] = []
    rows_path = out / f"{label}.jsonl"
    with httpx.Client() as client, rows_path.open("w", encoding="utf-8") as fh:

        def turn(body: dict, follow: bool) -> dict:
            # every turn starts with the chain's breakers closed (unless --keep-breakers): a tripped one would answer
            # from the template in ~0.1 s and hide the time of the model path being measured
            if not keep_breakers:
                reset_breakers()
            default_router().reset_cooldown()
            SPANS.clear()
            RESULTS.clear()
            answer, lines, ms = _send(client, url, body)
            rows.append(_turn_row(body["text"], follow, answer, lines, ms))
            fh.write(json.dumps(rows[-1], ensure_ascii=False) + "\n")
            print(f"{ms:7.0f} мс  {'↳ ' if follow else ''}{body['text']}", flush=True)
            return answer

        # the first request after a start pays for loading the base and the lexicon: measured once, kept out of the table
        t0 = time.perf_counter()
        client.get(f"http://127.0.0.1:{port}/api/data?lang=ru", timeout=120).raise_for_status()
        _send(client, url, {"text": "привет", "lat": lat, "lon": lon, "lang": "ru", "state": None})
        cold = round((time.perf_counter() - t0) * 1000)
        fh.write(json.dumps({"warm_up_ms": cold}) + "\n")
        print(f"{cold:7.0f} мс  (прогрев: /api/data и «привет»)", flush=True)
        for n in range(2 if repeat else 1):
            for text, tap in MESSAGES:
                body = {"text": text, "lat": lat, "lon": lon, "lang": "ru", "state": None}
                answer = turn(body, False)
                chips = [c for c in answer["turn"]["chips"] if c["kind"] != "reset"]
                if tap and chips:
                    turn({**body, "text": chips[0]["send"], "state": answer["state"]}, True)
            # the first pass only fills the cache: the table is the second one
            if repeat and n == 0:
                print("--- the same messages again", flush=True)
                rows.clear()
    server.should_exit = True
    thread.join(timeout=10)
    return rows


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Время /api/turn по этапам")
    ap.add_argument("--port", type=int, default=8911)
    ap.add_argument("--label", default="before")
    ap.add_argument(
        "--out", type=Path, default=DEFAULT_OUT, help="directory of the rows and the table"
    )
    ap.add_argument(
        "--repeat",
        action="store_true",
        help="the response cache on: every message twice, the table is the second pass (a repeated request)",
    )
    ap.add_argument(
        "--keep-breakers",
        action="store_true",
        help="keep the chain's circuit breakers across the turns, as a running stand does",
    )
    args = ap.parse_args(argv)
    out = args.out if args.out.is_absolute() else APP / args.out
    out.mkdir(parents=True, exist_ok=True)
    _configure(args.label, out, repeat=args.repeat)
    rows = run(args.port, args.label, out, repeat=args.repeat, keep_breakers=args.keep_breakers)
    report = (
        table(rows, f"{args.label}: все ходы")
        + "\n"
        + table([r for r in rows if not r["follow_up"]], f"{args.label}: первые сообщения")
    )
    follow = [r for r in rows if r["follow_up"]]
    if follow:
        report += "\n" + table(follow, f"{args.label}: кнопки-уточнения")
    (out / f"{args.label}.md").write_text(report, encoding="utf-8")
    print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
