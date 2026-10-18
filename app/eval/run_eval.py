"""Run the pipeline over eval/cases.json (or --cases <file>) and write one JSONL record per case (with its verdict).

    python -m eval.run_eval --data ../data/poi.json --mode offline
    python -m eval.run_eval --data ../data/poi.enriched.json --mode llm --tz --label llm-gemini-only
    python -m eval.run_eval --data ../data/poi.json --mode offline --cases eval/holdout_cases.json

`offline`: WALKS_OFFLINE=1 (template text, no network). `llm`: the configured chain (LLM_CHAIN / defaults of
walks.llm), response cache off. Weather, air and time are injected from the case in both modes; walking legs are
the straight-line estimate unless --walking valhalla is given, so both datasets are compared on the same legs.
Results of a non-default case set carry its tag: results/runs_<dataset>_<tag>_<label>.jsonl (holdout_cases.json →
`holdout`, abstain_cases.json → `abstain`), so they never overwrite the main set's files.

The label names a run: it ends the file name and is written in the header, the first JSONL line, together with
the dataset path, the number of records, the git short sha, the mode and the time. Default: the label of the
--out file name when given, else the mode (so `--mode offline` still writes runs_<dataset>_offline.jsonl).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime
from pathlib import Path

from walks.envcfg import load_env_file
from walks.llm import generation_models
from walks.models import Result, load_pois
from walks.pipeline import recommend
from walks.walking import default_router, offline_router

from .attribution import data_at_rev
from .cases import (
    CASES_PATH,
    HEADER_KEY,
    LABEL_RE,
    REPO_ROOT,
    RESULTS_DIR,
    case_set_tag,
    case_weather,
    case_when,
    git_state,
    label_from_filename,
    load_cases,
    runs_name,
    sha_text,
)
from .metrics import dataset_index, judge_case
from .redact import public_run

LLM_PAUSE_S = 3.0  # between cases in llm mode (free-tier rate limits)


def dataset_name(path: Path) -> str:
    return path.stem  # poi / poi.enriched


def runs_path(dataset: str, label: str, tag: str = "") -> Path:
    return RESULTS_DIR / runs_name(dataset, label, tag)


def _rec_record(r) -> dict:
    p = r.poi
    return {
        "poi_id": p.id,
        "name": p.name,
        "category": p.category,
        "source": "+".join(p.sources or [p.source]),
        "hours_state": r.hours_state,
        "hours_raw": r.hours_raw,
        "hours_note": r.hours_note,
        "walk_min": r.walk_min,
        "distance_m": r.distance_m,
        "method": r.walk_method,
        "confidence": r.confidence,
        "text_source": r.text_source,
        "why": r.why,
        "what_to_do": r.what_to_do,
        "notes": r.notes,
        "padding": r.padding,
    }


def _route_record(res: Result) -> dict | None:
    rt = res.route
    if rt is None:
        return None
    return {
        "stops": rt.stops,
        "legs_min": rt.legs_min,
        "stay_min": rt.stay_min,
        "walk_min_total": rt.walk_min_total,
        "total_min": rt.total_min,
        "budget_min": rt.budget_min,
        "fits": rt.fits,
        "dropped": rt.dropped,
    }


def _intent_record(res: Result) -> dict:
    ir = res.intent
    i = ir.intent
    return {
        "parser": ir.parser,
        "model": ir.llm_step.model if ir.llm_step else None,
        "trace": ir.llm_step.attempts_text() if ir.llm_step else None,
        "time_budget_min": i.time_budget_min,
        "categories": list(i.categories),
        "with_kids": i.with_kids,
        "quiet": i.quiet,
        "needs_wifi_socket": i.needs_wifi_socket,
        "night": i.night,
        "accessibility": i.accessibility,
    }


def run_case(case: dict, pois, index, router, *, use_llm: bool, dataset: str, mode: str) -> dict:
    origin = case["origin"]
    res = recommend(
        case["query"],
        origin["lat"],
        origin["lon"],
        case_when(case),
        use_llm=use_llm,
        pois=pois,
        weather=case_weather(case),
        router=router,
    )
    recs = [_rec_record(r) for r in res.recs]
    route = _route_record(res)
    f = res.retrieval.filters
    return {
        "case_id": case["id"],
        "dataset": dataset,
        "mode": mode,
        "model_link": res.model if res.generation == "llm" else "template",
        "generation": res.generation,
        "generation_note": res.generation_note,
        "unbacked_claims_removed": res.unbacked_claims_removed,
        "generation_trace": res.generation_step.attempts_text() if res.generation_step else None,
        "intent": _intent_record(res),
        "timings": res.timings_ms,
        "filters": {
            "radius_declared_m": f.radius_declared_m,
            "radius_effective_m": f.radius_effective_m,
            "radius_factor": f.radius_factor,
            "in_radius": f.in_radius,
            "excluded_closed": f.excluded_closed,
            "excluded_min_stay": f.excluded_min_stay,
            "excluded_outdoor": f.excluded_outdoor,
            "candidates": f.candidates_returned,
            "categories_requested": f.categories_requested,
            "categories_relaxed": f.categories_relaxed,
            "weather_adapted": f.weather_adapted,
            "dark": f.dark,
            "holiday": f.holiday,
        },
        "recs": recs,
        "route": route,
        "route_total_min": route["total_min"] if route else None,
        "verdict": judge_case(case, recs, route, index),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Evaluate the walking pipeline on a cases file")
    ap.add_argument("--data", required=True, help="POI dataset, e.g. ../data/poi.json")
    ap.add_argument("--mode", choices=["offline", "llm"], required=True)
    ap.add_argument("--limit", type=int, help="only the first N cases")
    ap.add_argument(
        "--cases", type=Path, default=CASES_PATH, help="cases file (default eval/cases.json)"
    )
    ap.add_argument("--tz", action="store_true", help="only the five scenarios of the brief")
    ap.add_argument("--ids", nargs="+", help="only these case ids (a fixed, documented selection)")
    ap.add_argument("--walking", choices=["straight", "valhalla"], default="straight")
    ap.add_argument(
        "--pause", type=float, default=LLM_PAUSE_S, help="seconds between cases in llm mode"
    )
    ap.add_argument(
        "--label",
        help="name of the run: ends the file name and goes into the header (default: the label of --out, "
        "else the mode)",
    )
    ap.add_argument(
        "--out", type=Path, help="JSONL path (default results/runs_<dataset>[_<tag>]_<label>.jsonl)"
    )
    ap.add_argument(
        "--data-rev",
        help="read the file named by --data as of this git revision (`git show REV:data/<name>`): the same code "
        "on an older dataset, for attribution runs; the header records the revision",
    )
    args = ap.parse_args(argv)

    load_env_file()
    os.environ["WALKS_REQUEST_LOG"] = "off"
    os.environ["WALKS_LLM_CACHE"] = "off"
    if args.mode == "offline":
        os.environ["WALKS_OFFLINE"] = "1"
    else:
        os.environ.pop("WALKS_OFFLINE", None)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    data = Path(args.data).resolve()
    if args.data_rev:
        try:
            data_shown = f"git:{args.data_rev}:data/{data.name}"
            data = data_at_rev(args.data_rev, data.name)
        except FileNotFoundError as exc:
            ap.error(str(exc))
    else:
        data_shown = (
            data.relative_to(REPO_ROOT).as_posix() if data.is_relative_to(REPO_ROOT) else str(data)
        )
    dataset = dataset_name(data)
    pois = load_pois(data)
    index = dataset_index(pois)
    cases = load_cases(args.cases)
    if args.tz:
        cases = [c for c in cases if c.get("tz")]
    if args.ids:
        unknown = sorted(set(args.ids) - {c["id"] for c in cases})
        if unknown:
            ap.error(f"--ids: not in the case set: {', '.join(unknown)}")
        cases = [c for c in cases if c["id"] in args.ids]
    if args.limit:
        cases = cases[: args.limit]
    router = default_router() if args.walking == "valhalla" else offline_router()
    label = args.label or (label_from_filename(args.out) if args.out else args.mode)
    if not LABEL_RE.fullmatch(label):
        ap.error(f"--label {label!r}: only letters, digits and '-' (no '_')")
    tag = case_set_tag(args.cases)
    out = args.out or runs_path(dataset, label, tag)
    out.parent.mkdir(parents=True, exist_ok=True)
    chain = generation_models() if args.mode == "llm" else []
    header = {
        "label": label,
        "mode": args.mode,
        "dataset": dataset,
        "data_path": data_shown,
        "cases_file": args.cases.resolve().name,
        "case_set": tag or "main",
        "records": len(cases),
        "git": sha_text(git_state()),
        "walking": args.walking,
        "generated_at": datetime.now().astimezone().isoformat(timespec="seconds"),
    }

    with out.open("w", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps({HEADER_KEY: header}, ensure_ascii=False) + "\n")
        for n, case in enumerate(cases):
            if args.mode == "llm" and n:
                time.sleep(args.pause)
            rec = run_case(
                case,
                pois,
                index,
                router,
                use_llm=args.mode == "llm",
                dataset=dataset,
                mode=args.mode,
            )
            rec["chain"] = chain
            public_run(rec)
            fh.write(json.dumps(rec, ensure_ascii=False) + "\n")
            fh.flush()
            v = rec["verdict"]
            print(
                f"{case['id']:<34} {rec['model_link']:<28} recs={v['n_recs']} "
                f"{'ok' if v['all_ok'] else 'FAIL ' + ','.join(v['violations'])}"
            )
    print(f"{len(cases)} cases -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
