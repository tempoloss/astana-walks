"""Aggregate eval/results/runs_*.jsonl into summaries, a poi.json vs poi.enriched.json comparison,
results/canonical.md and docs/scenarios.md.

    python -m eval.report            # all runs found in eval/results/

Outputs (eval/results/): summary_<dataset>_<label>.json|md, comparison_<label>.md (when both datasets have a run
with that label). The held-out set (eval/holdout_cases.json, runs_<dataset>_holdout_<label>.jsonl) and the
abstention set (eval/abstain_cases.json, runs_<dataset>_abstain_<label>.jsonl) get the same files with
`holdout` / `abstain` in the name, plus main_vs_holdout_<label>.md: main and held-out metrics side by side.
canonical.md is the single table (main / holdout / abstain x poi / poi.enriched, offline runs, every metric,
the git sha) that the deck cites. docs/scenarios.md is rendered by eval.scenarios from the main set's files only.
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import subprocess
import sys
from collections import Counter
from functools import lru_cache
from pathlib import Path

from walks.models import POI, load_pois

from . import attribution
from .attribution import PRESWAP_LABEL, preswap_index
from .cases import (
    CASE_SETS,
    DATA_DIR,
    HEADER_KEY,
    HOLDOUT2_PATH,
    REPO_ROOT,
    RESULTS_DIR,
    git_state,
    load_cases,
    read_header,
    runs_name,
    sha_text,
)
from .metrics import (
    CATEGORY_FORBIDDEN,
    CATEGORY_NOT_ALLOWED,
    OPEN_CLAIM_IN_TEXT,
    dataset_index,
    judge_abstain,
    judge_case,
    padding_missing_fields,
    rec_padding,
)
from .redact import public_run

BASE, CANDIDATE = "poi", "poi.enriched"
MODES = (
    "offline",
    "llm",
    "llm-public",
    "llm-gemini-only",
)  # llm-public: the reproducible run on public Gemini links; the last: llm run of 16.10 (every flash link 429)

# metric key -> (label, kind). kind: "pct" share in %, "int" count, "ms" milliseconds, "num" plain float.
METRIC_ROWS: list[tuple[str, str, str]] = [
    ("cases", "кейсов", "int"),
    ("hallucinated_poi", "hallucinated_poi (должно быть 0)", "int"),
    ("constraint_ok_rate", "constraint_ok_rate (рекомендации без нарушений)", "pct"),
    ("case_all_ok_rate", "кейсов без единого нарушения", "pct"),
    ("honest_unknown_rate", "honest_unknown_rate (кейсы)", "pct"),
    ("honest_unknown_rate_flagged", "honest_unknown_rate, кейсы «ночь/праздник»", "pct"),
    ("coverage", "coverage (≥1 рекомендация проходит все ограничения)", "pct"),
    ("diversity", "diversity (нет дублей сети среди рекомендаций)", "pct"),
    ("top1_ok_rate", "top-1 без нарушений ограничений", "pct"),
    ("top1_open_rate", "top-1 с подтверждённым «открыто»", "pct"),
    ("unknown_hours_rec_share", "доля рекомендаций с неизвестными часами", "pct"),
    ("non_osm_rec_share", "доля рекомендаций не из OSM-записей", "pct"),
    ("avg_walk_min", "средняя дорога до рекомендации, мин", "num"),
    (
        "padded_rec_share",
        "padding: рекомендации, добранные расширением радиуса, другой категорией или заменой из-за погоды",
        "pct",
    ),
    ("expanded_rec_share", "… за счёт расширения радиуса (radius_factor > 1)", "pct"),
    ("backfill_rec_share", "… за счёт другой категории (back-fill)", "pct"),
    (
        "substituted_rec_share",
        "… за счёт замены из-за мороза или смога (место в помещении вместо уличного, substituted)",
        "pct",
    ),
    ("padded_case_share", "padding: кейсы хотя бы с одной такой рекомендацией", "pct"),
    (
        "honest_abstain_rate",
        "honest_abstain_rate (нет рекомендаций или каждое несовпадение помечено)",
        "pct",
    ),
    ("llm_chain_failed", "кейсов, где вся цепочка ИИ недоступна (→ шаблон)", "int"),
    ("llm_invalid_answers", "кейсов, где ответ ИИ не прошёл проверку poi_id (→ шаблон)", "int"),
    ("latency_ms_median", "latency пайплайна, медиана", "ms"),
    ("latency_ms_p90", "latency пайплайна, p90", "ms"),
    ("generation_ms_median", "latency ответа ИИ, медиана", "ms"),
    ("generation_ms_p90", "latency ответа ИИ, p90", "ms"),
]
# Defined only when a model answered: an offline run has no chain, no validation fallback and no LLM latency, so
# its cells read «н/п» instead of a 0 or a template timing. The pipeline latency of an offline run is the
# template path's and is labelled so.
LLM_ONLY = {
    "llm_chain_failed",
    "llm_invalid_answers",
    "generation_ms_median",
    "generation_ms_p90",
}
LATENCY_KEYS = {"latency_ms_median", "latency_ms_p90"}
NOT_AVAILABLE = "н/п"
TEMPLATE_TAG = "шаблон"

# Runs kept for the record that are not current numbers: label -> (date, what happened). Their summaries carry the
# note, canonical.md lists them apart from the current table and docs/scenarios.md leaves them out.
HISTORICAL_RUNS = {
    "llm-gemini-only": (
        "16.10.2026",
        "пять сценариев ТЗ через цепочку только из звеньев Google, когда у ключа был исчерпан лимит (429 на "
        "flash-звеньях, 5xx / таймаут на gemma): стресс-прогон в шторм квоты, а не измерение качества ИИ",
    ),
}


def historical_note(label: str) -> str | None:
    """The line that marks the files of a historical run (None for an ordinary label)."""
    if label not in HISTORICAL_RUNS:
        return None
    date, what = HISTORICAL_RUNS[label]
    return (
        f"> **Исторический прогон {date}**, не текущие цифры: {what}. Файл записан до введения заголовков "
        "(кода и данных того дня в нём не отражено)."
    )


def _cell(s: dict, key: str, kind: str, *, tag_template: bool) -> str:
    """One metric cell of a summary: «н/п» for an LLM-only metric of an offline run; a latency of an offline run
    gets the «шаблон» tag when the row label cannot carry it (`tag_template`)."""
    offline = s.get("mode") == "offline"
    if offline and key in LLM_ONLY:
        return NOT_AVAILABLE
    text = fmt(s.get(key), kind)
    return f"{text} ({TEMPLATE_TAG})" if offline and key in LATENCY_KEYS and tag_template else text


def _row_label(key: str, label: str, *, all_offline: bool) -> str:
    return f"{label} ({TEMPLATE_TAG}, без ИИ)" if key in LATENCY_KEYS and all_offline else label


def metric_rows(
    summaries: list[dict], skip: frozenset[str] | set[str] = frozenset()
) -> list[tuple[str, list[str]]]:
    """[(row label, one cell per summary)] for every metric of METRIC_ROWS not in `skip`. When all the summaries
    are offline runs the latency rows say «шаблон» in the label, otherwise in each offline cell."""
    all_offline = all(s.get("mode") == "offline" for s in summaries)
    return [
        (
            _row_label(key, label, all_offline=all_offline),
            [_cell(s, key, kind, tag_template=not all_offline) for s in summaries],
        )
        for key, label, kind in METRIC_ROWS
        if key not in skip
    ]


def _pct(num: int | float, den: int | float) -> float | None:
    return round(100 * num / den, 1) if den else None


def percentile(values: list[float], q: float) -> float | None:
    """Nearest-rank percentile (q in 0..100); None for an empty list."""
    if not values:
        return None
    s = sorted(values)
    return s[max(0, math.ceil(q / 100 * len(s)) - 1)]


@lru_cache(maxsize=4)
def _index(dataset: str) -> dict[str, POI]:
    return dataset_index(load_pois(DATA_DIR / f"{dataset}.json"))


def load_runs(dataset: str, label: str, directory: Path = RESULTS_DIR, tag: str = "") -> list[dict]:
    """The runs of a file (without its header line) with their verdicts recomputed by the current eval.metrics
    (so a change of a check needs no new — possibly rate-limited — LLM run); the verdict stored in the JSONL is
    only the run-time one. A historical run (HISTORICAL_RUNS) keeps its stored verdict: the dataset it ran on
    has been replaced, so its place ids would count as hallucinated. `label` names the run (the mode unless the
    run had --label), `tag` selects the case set ("" main, "holdout", "abstain"); runs of the abstain set also
    get an `abstain` verdict."""
    path = directory / runs_name(dataset, label, tag)
    if not path.is_file():
        return []
    lines = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    runs = [r for r in lines if HEADER_KEY not in r]
    cases = {c["id"]: c for c in load_cases(CASE_SETS[tag])}
    # the pre-swap run (attribution) is judged against the dataset it ran on, not the current one
    index = preswap_index(dataset) if label == PRESWAP_LABEL else _index(dataset)
    for run in runs:
        public_run(run)
        if label in HISTORICAL_RUNS or index is None:
            continue  # judged by the checks and the dataset of its day (no longer in the tree / not readable)
        case = cases[run["case_id"]]
        run["verdict"] = judge_case(case, run["recs"], run["route"], index)
        if tag == "abstain":
            run["abstain"] = judge_abstain(case, run, index)
    return runs


def _ai_detail(run: dict) -> dict:
    """What one answer of a model run needs for the AI-mode section: who wrote the text (a model or the template),
    who read the intent, what the checks said about the card, how long it took."""
    intent, v = run.get("intent") or {}, run["verdict"]
    codes = set(v["violations"])
    return {
        "case_id": run["case_id"],
        "model_link": run["model_link"],
        "by_ai": run["generation"] == "llm",
        "intent_by_ai": intent.get("parser") == "rules+llm",
        "intent_model": intent.get("model"),
        "n_recs": v["n_recs"],
        "top1": (
            f"{run['recs'][0]['name']} ({run['recs'][0]['category']})" if run["recs"] else "—"
        ),
        "open_claim_in_text": OPEN_CLAIM_IN_TEXT in codes,
        "category_violation": bool(codes & {CATEGORY_NOT_ALLOWED, CATEGORY_FORBIDDEN}),
        "honest_ok": v["honest_ok"],
        "violations": v["violations"],
        "total_ms": run["timings"]["total"],
        "generation_ms": run["timings"]["generation"],
    }


def summarize(runs: list[dict], cases: list[dict]) -> dict:
    flagged = {c["id"] for c in cases if c["expected"].get("must_flag_unknown_hours")}
    wifi_cases = {c["id"] for c in cases if c["expected"].get("needs_wifi_socket")}
    with_recs = [r for r in runs if r["recs"]]
    recs_total = sum(len(r["recs"]) for r in runs)
    ok_recs = sum(r["verdict"]["ok_recs"] for r in runs)
    honest_recs_bad = sum(len(r["verdict"]["honesty_violations"]) for r in runs)
    flagged_runs = [r for r in with_recs if r["case_id"] in flagged]
    multi = [r for r in runs if len(r["recs"]) >= 2]
    top1_ok = top1_open = 0
    for r in with_recs:
        first = r["recs"][0]
        top1_ok += first["poi_id"] not in r["verdict"]["constraint_violations"]
        top1_open += first["hours_state"] == "open"
    unknown = sum(rec["hours_state"] == "unknown" for r in runs for rec in r["recs"])
    non_osm = sum(rec["source"] != "osm" for r in runs for rec in r["recs"])
    walks = [rec["walk_min"] for r in runs for rec in r["recs"]]
    wifi_recs = [rec for r in runs if r["case_id"] in wifi_cases for rec in r["recs"]]
    wifi_in_data = sum(
        r["verdict"]["wifi_socket_in_data"] for r in runs if r["case_id"] in wifi_cases
    )
    totals = [float(r["timings"]["total"]) for r in runs]
    gens = [float(r["timings"]["generation"]) for r in runs]
    violation_cases: Counter[str] = Counter()
    for r in runs:
        violation_cases.update(r["verdict"]["violations"])
    paddings = [rec_padding(r, rec)[0] for r in runs for rec in r["recs"]]
    padded = [p for p in paddings if p != "none"]
    derived_recs = sum(rec_padding(r, rec)[1] for r in runs for rec in r["recs"])
    missing_fields = {m for r in runs for rec in r["recs"] for m in padding_missing_fields(r, rec)}
    abstain = [r["abstain"] for r in runs if "abstain" in r]
    return {
        "dataset": runs[0]["dataset"] if runs else None,
        "mode": runs[0]["mode"] if runs else None,
        "chain": runs[0].get("chain", []) if runs else [],
        "cases": len(runs),
        "cases_with_recs": len(with_recs),
        "recs_total": recs_total,
        "hallucinated_poi": sum(len(r["verdict"]["hallucinated"]) for r in runs),
        "constraint_ok_rate": _pct(ok_recs, recs_total),
        "case_all_ok_rate": _pct(sum(r["verdict"]["all_ok"] for r in runs), len(runs)),
        "honest_unknown_rate": _pct(
            sum(r["verdict"]["honest_ok"] for r in with_recs), len(with_recs)
        ),
        "honest_unknown_rate_flagged": _pct(
            sum(r["verdict"]["honest_ok"] for r in flagged_runs), len(flagged_runs)
        ),
        "honest_rec_rate": _pct(recs_total - honest_recs_bad, recs_total),
        "coverage": _pct(sum(r["verdict"]["coverage_ok"] for r in runs), len(runs)),
        "diversity": _pct(sum(not r["verdict"]["duplicate_chains"] for r in multi), len(multi)),
        "top1_ok_rate": _pct(top1_ok, len(with_recs)),
        "top1_open_rate": _pct(top1_open, len(with_recs)),
        "unknown_hours_rec_share": _pct(unknown, recs_total),
        "non_osm_rec_share": _pct(non_osm, recs_total),
        "avg_walk_min": round(statistics.fmean(walks), 1) if walks else None,
        "wifi_socket_in_data_share": _pct(wifi_in_data, len(wifi_recs)),
        "route_stop_closed_cases": sum(bool(r["verdict"]["route_closed_stops"]) for r in runs),
        "latency_ms_median": statistics.median(totals) if totals else None,
        "latency_ms_p90": percentile(totals, 90),
        "generation_ms_median": statistics.median(gens) if gens else None,
        "generation_ms_p90": percentile(gens, 90),
        "model_link": dict(Counter(r["model_link"] for r in runs).most_common()),
        "llm_chain_failed": sum(r["generation_note"].startswith("ошибка ИИ") for r in runs),
        "llm_invalid_answers": sum("не прошёл проверку" in r["generation_note"] for r in runs),
        "violation_cases": dict(violation_cases.most_common()),
        "padded_rec_share": _pct(len(padded), recs_total),
        "expanded_rec_share": _pct(sum(p == "expanded" for p in paddings), recs_total),
        "backfill_rec_share": _pct(sum(p == "backfill" for p in paddings), recs_total),
        "substituted_rec_share": _pct(sum(p == "substituted" for p in paddings), recs_total),
        "padded_case_share": _pct(
            sum(any(rec_padding(r, x)[0] != "none" for x in r["recs"]) for r in with_recs),
            len(with_recs),
        ),
        "padding_derived_recs": derived_recs,
        "padding_missing_fields": sorted(missing_fields),
        "honest_abstain_rate": _pct(sum(a["honest_abstain"] for a in abstain), len(abstain)),
        "abstained_cases": sum(a["abstained"] for a in abstain) if abstain else None,
        "silent_mismatch_cases": sum(not a["honest_abstain"] for a in abstain) if abstain else None,
        "abstain_detail": [
            {
                "case_id": r["case_id"],
                "n_recs": len(r["recs"]),
                "labelled_recs": r["abstain"]["labelled_recs"],
                "silent": r["abstain"]["silent_mismatches"],
            }
            for r in runs
            if "abstain" in r
        ],
        "ai_detail": [_ai_detail(r) for r in runs] if runs and runs[0]["mode"] != "offline" else [],
        "failing_cases": [
            {"case_id": r["case_id"], "violations": r["verdict"]["violations"]}
            for r in runs
            if not r["verdict"]["all_ok"]
        ],
    }


def fmt(value: float | int | None, kind: str) -> str:
    if value is None:
        return "—"
    if kind == "pct":
        return f"{value:.1f}%"
    if kind == "ms":
        return f"{value:.0f} мс"
    if kind == "num":
        return f"{value:.1f}"
    return str(int(value))


def _delta(a, b, kind: str) -> str:
    if a is None or b is None:
        return "—"
    d = b - a
    if kind == "pct":
        return f"{d:+.1f} п.п."
    if kind == "ms":
        return f"{d:+.0f} мс"
    if kind == "num":
        return f"{d:+.1f}"
    return f"{int(d):+d}"


def summary_md(s: dict) -> str:
    lines = [
        f"# Оценка: `{s['dataset']}`, режим `{s['mode']}`",
        "",
        *([note, ""] if (note := historical_note(s.get("label", ""))) else []),
        f"Набор кейсов: {s['case_set']}. Кейсов: {s['cases']}, рекомендаций: {s['recs_total']}.",
        f"Прогон: {_header_text(s.get('header'))}.",
    ]
    if s["chain"]:
        lines.append(f"Цепочка генерации: `{' → '.join(s['chain'])}`.")
    if s["padding_missing_fields"]:
        lines.append(
            f"Padding посчитан по доступному: нет полей {', '.join(s['padding_missing_fields'])} "
            f"(выведено из текста карточки и distance_m у {s['padding_derived_recs']} рекомендаций)."
        )
    lines += ["", "| метрика | значение |", "|---|---|"]
    lines += [f"| {label} | {cells[0]} |" for label, cells in metric_rows([s])]
    lines += [
        f"| honest_unknown_rate по рекомендациям | {fmt(s['honest_rec_rate'], 'pct')} |",
        f"| Wi-Fi/розетка есть в данных у рекомендаций кейсов «розетка» | "
        f"{fmt(s['wifi_socket_in_data_share'], 'pct')} |",
        f"| кейсов, где остановка маршрута закрыта к моменту прихода по порядку маршрута | "
        f"{s['route_stop_closed_cases']} |",
    ]
    lines += ["", "## Распределение моделей (`model_link`)", "", "| звено | кейсов |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in s["model_link"].items()]
    lines += ["", "## Нарушения (кейсов с кодом)", "", "| код | кейсов |", "|---|---|"]
    lines += [f"| {k} | {v} |" for k, v in s["violation_cases"].items()] or ["| — | 0 |"]
    lines += ["", "## Кейсы с нарушениями", ""]
    lines += [f"- `{f['case_id']}`: {', '.join(f['violations'])}" for f in s["failing_cases"]] or [
        "—"
    ]
    return "\n".join(lines) + "\n"


def _top1_text(run: dict) -> str:
    if not run["recs"]:
        return "— (нет рекомендаций)"
    r = run["recs"][0]
    bad = run["verdict"]["constraint_violations"].get(r["poi_id"])
    flag = f" ⚠ {', '.join(bad)}" if bad else ""
    return f"{r['name']} · {r['category']} · {r['source']} · {r['hours_state']} · {r['walk_min']} мин{flag}"


def _top1_id(run: dict) -> str | None:
    return run["recs"][0]["poi_id"] if run["recs"] else None


def top1_diffs(base: list[dict], cand: list[dict]) -> list[tuple[str, dict, dict]]:
    by_id = {r["case_id"]: r for r in cand}
    return [
        (r["case_id"], r, by_id[r["case_id"]])
        for r in base
        if r["case_id"] in by_id and _top1_id(r) != _top1_id(by_id[r["case_id"]])
    ]


def comparison_md(mode: str, base_s: dict, cand_s: dict, base: list[dict], cand: list[dict]) -> str:
    lines = [
        f"# `{BASE}.json` vs `{CANDIDATE}.json`, режим `{mode}`",
        "",
        *([note, ""] if (note := historical_note(mode)) else []),
        f"Кейсов: {base_s['cases']} / {cand_s['cases']}.",
        "",
        f"| метрика | {BASE} | {CANDIDATE} | Δ |",
        "|---|---|---|---|",
    ]
    offline = base_s.get("mode") == cand_s.get("mode") == "offline"
    for key, label, kind in METRIC_ROWS:
        a, b = base_s.get(key), cand_s.get(key)
        delta = NOT_AVAILABLE if offline and key in LLM_ONLY else _delta(a, b, kind)
        lines.append(
            f"| {_row_label(key, label, all_offline=offline)} | "
            f"{_cell(base_s, key, kind, tag_template=False)} | "
            f"{_cell(cand_s, key, kind, tag_template=False)} | {delta} |"
        )
    for key, label in (
        ("honest_rec_rate", "honest_unknown_rate по рекомендациям"),
        ("wifi_socket_in_data_share", "Wi-Fi/розетка в данных у рекомендаций кейсов «розетка»"),
    ):
        a, b = base_s.get(key), cand_s.get(key)
        lines.append(f"| {label} | {fmt(a, 'pct')} | {fmt(b, 'pct')} | {_delta(a, b, 'pct')} |")
    lines += ["", "## model_link", ""]
    lines += [f"- {BASE}: {base_s['model_link']}", f"- {CANDIDATE}: {cand_s['model_link']}"]
    diffs = top1_diffs(base, cand)
    lines += ["", f"## Кейсы, где изменился top-1 ({len(diffs)} из {base_s['cases']})", ""]
    lines += [f"| кейс | {BASE} | {CANDIDATE} |", "|---|---|---|"]
    lines += [f"| `{cid}` | {_top1_text(a)} | {_top1_text(b)} |" for cid, a, b in diffs]
    return "\n".join(lines) + "\n"


def _split_run_name(stem: str, tag: str) -> tuple[str, str] | None:
    """(dataset, mode) of runs_<dataset>[_<tag>]_<mode> when it belongs to the case set `tag`, else None."""
    rest, _, mode = stem.removeprefix("runs_").rpartition("_")
    other = [t for t in CASE_SETS if t and t != tag]
    if tag:
        return (rest.removesuffix(f"_{tag}"), mode) if rest.endswith(f"_{tag}") else None
    return None if any(rest.endswith(f"_{t}") for t in other) else (rest, mode)


def write_summaries(directory: Path = RESULTS_DIR, tag: str = "") -> dict[tuple[str, str], dict]:
    cases = load_cases(CASE_SETS[tag])
    sfx = f"_{tag}" if tag else ""
    out: dict[tuple[str, str], dict] = {}
    for path in sorted(directory.glob("runs_*_*.jsonl")):
        parsed = _split_run_name(path.stem, tag)
        if parsed is None:
            continue
        dataset, mode = parsed
        runs = load_runs(dataset, mode, directory, tag)
        if not runs:
            continue
        s = {
            **summarize(runs, cases),
            "case_set": tag or "main",
            "label": mode,
            "header": read_header(directory / runs_name(dataset, mode, tag)),
        }
        out[(dataset, mode)] = s
        name = f"summary_{dataset}{sfx}_{mode}"
        (directory / f"{name}.json").write_text(
            json.dumps(s, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
        )
        (directory / f"{name}.md").write_text(summary_md(s), encoding="utf-8", newline="\n")
    for mode in MODES:
        if (BASE, mode) in out and (CANDIDATE, mode) in out:
            text = comparison_md(
                mode,
                out[(BASE, mode)],
                out[(CANDIDATE, mode)],
                load_runs(BASE, mode, directory, tag),
                load_runs(CANDIDATE, mode, directory, tag),
            )
            name = f"comparison{sfx}_{mode}.md" if tag else f"comparison_{mode}.md"
            (directory / name).write_text(text, encoding="utf-8", newline="\n")
    return out


def main_vs_holdout_md(
    mode: str,
    main: dict[tuple[str, str], dict],
    holdout: dict[tuple[str, str], dict],
    holdout2: dict[tuple[str, str], dict] | None = None,
    holdout3: dict[tuple[str, str], dict] | None = None,
) -> str:
    """Metrics of the tuned main set next to the held-out sets, for each dataset that has both."""
    cols = [
        (ds, label, src[(ds, mode)])
        for ds in (BASE, CANDIDATE)
        for label, src in (
            ("main", main),
            ("holdout", holdout),
            ("holdout2", holdout2 or {}),
            ("holdout3", holdout3 or {}),
        )
        if (ds, mode) in src
    ]
    lines = [
        f"# Основной набор vs held-out, режим `{mode}`",
        "",
        "Основной набор подгонялся под правила ранжирования; held-out писался отдельно, по здравому смыслу.",
        "",
        "| метрика | "
        + " | ".join(f"{ds} / {label} ({s['cases']})" for ds, label, s in cols)
        + " |",
        "|---|" + "---|" * len(cols),
    ]
    cs = [s for _, _, s in cols]
    lines += [f"| {label} | " + " | ".join(cells) + " |" for label, cells in metric_rows(cs)]
    a = [fmt(s.get("honest_rec_rate"), "pct") for s in cs]
    lines.append("| honest_unknown_rate по рекомендациям | " + " | ".join(a) + " |")
    return "\n".join(lines) + "\n"


def write_main_vs_holdout(
    main: dict[tuple[str, str], dict],
    holdout: dict[tuple[str, str], dict],
    holdout2: dict[tuple[str, str], dict] | None = None,
    holdout3: dict[tuple[str, str], dict] | None = None,
    directory: Path = RESULTS_DIR,
) -> None:
    for mode in MODES:
        if any(m == mode for _, m in holdout):
            (directory / f"main_vs_holdout_{mode}.md").write_text(
                main_vs_holdout_md(mode, main, holdout, holdout2 or {}, holdout3 or {}),
                encoding="utf-8",
                newline="\n",
            )


CANONICAL_LABEL = "offline"
CANONICAL_SETS = ("main", "holdout", "holdout2", "holdout3", "abstain")
# metrics that are not defined for a set: the abstention set wants no recommendation to pass the constraints,
# and the abstention rate exists only there
NOT_APPLICABLE = {"abstain": {"case_all_ok_rate", "coverage"}}
ABSTAIN_ONLY = {"honest_abstain_rate"}


def _header_text(h: dict | None) -> str:
    if not h:
        return "—"
    if h.get("legacy"):
        return f"метка `{h['label']}`, заголовка в файле нет (прогон до введения заголовков)"
    return (
        f"метка `{h['label']}`, режим `{h['mode']}`, {h['records']} записей, данные "
        f"`{h['data_path']}`, git `{h['git']}`, {h['generated_at']}"
    )


AI_LABEL = "llm-public"
AI_BEFORE_LABEL = "llm-public-before"


def _median_ms(values: list[float]) -> str:
    return f"{statistics.median(values):.0f} мс" if values else "—"


def _ai_runs(groups: dict[str, dict[tuple[str, str], dict]]) -> list[tuple[str, dict]]:
    """[(case set, summary)] of the public-Gemini run, main first."""
    return [
        (name, groups[name][(CANDIDATE, AI_LABEL)])
        for name in ("main", "holdout")
        if (CANDIDATE, AI_LABEL) in groups.get(name, {})
    ]


def _ai_section(groups: dict[str, dict[tuple[str, str], dict]]) -> list[str]:
    """canonical.md block for the run on public Gemini links: per-link distribution, the share of answers a model
    wrote against the template's, the text checks of the model's answers, one row per case. A template answer is
    never counted as AI."""
    parts = _ai_runs(groups)
    rows = [(name, d) for name, s in parts for d in s["ai_detail"]]
    if not rows:
        return []
    n = len(rows)
    head = parts[0][1].get("header") or {}
    date = (head.get("generated_at") or "")[:10]
    date_ru = ".".join(reversed(date.split("-"))) if date else "дата не записана"
    ai = [d for _, d in rows if d["by_ai"]]
    intent_ai = [d for _, d in rows if d["intent_by_ai"]]
    links = Counter(d["model_link"] for _, d in rows if d["by_ai"])
    chain_specs = parts[0][1]["chain"]
    if not chain_specs or not all(c.startswith("gemini:") for c in chain_specs):
        return []  # not a public run: no section that says «публичные модели Gemini»
    chain = " → ".join(chain_specs)
    sets = ", ".join(f"{name} {s['cases']}" for name, s in parts)
    lat_ai = [d["total_ms"] for d in ai]
    lat_tpl = [d["total_ms"] for _, d in rows if not d["by_ai"]]
    lines = [
        "",
        f"## ИИ-режим (публичные модели Gemini, {n} кейсов, {date_ru})",
        "",
        f"Датасет `{CANDIDATE}.json`, git `{head.get('git', '—')}`, кэш ответов выключен, в цепочках только "
        f"звенья `gemini:*` (без частного профиля), пауза между кейсами 6 с. Цепочка текста: `{chain}`. "
        f"Наборы: {sets}: пять сценариев ТЗ "
        "(`tz1`–`tz5`) и пять кейсов holdout, выбранных вручную до прогона и зафиксированных списком: "
        "`h04` (коляска, без алкоголя), `h08` (казахский), `h13` (ночь, голод), `h18` (английский), `h20` "
        "(Новый год). Выбор не случайный: в `h04`, `h18` и `h20` у правил был пробел при разборе намерения "
        "(см. «Дополнительная польза ИИ при маппинге категорий поверх словаря»), так что набор нарочно "
        "трудный для словаря; по нему нельзя судить о доле ИИ на любых запросах. Не больше 10 кейсов: "
        "бесплатный лимит у каждой модели ограничен.",
        "",
        f"- **Ответил ИИ: {len(ai)} из {n} ({100 * len(ai) / n:.0f}%)**; ответил шаблон (ни одно звено не "
        f"дало ответ или он не прошёл проверку): {n - len(ai)} из {n}. Шаблонные ответы ни в одной доле ИИ "
        "не учитываются.",
        f"- Разбор намерения читал ИИ в {len(intent_ai)} из {n} кейсов (в остальных — только правила).",
        f"- Latency пайплайна, медиана: {_median_ms(lat_ai)} у ответов ИИ ({len(ai)}), {_median_ms(lat_tpl)} у шаблонных "
        f"({n - len(ai)}); сюда входит ожидание отказавших звеньев.",
        "",
        "| звено, написавшее текст | кейсов |",
        "|---|---|",
        *[f"| `{k}` | {v} |" for k, v in links.most_common()],
        f"| шаблон (ИИ не ответил) | {n - len(ai)} |",
        "",
        f"Проверки у {len(ai)} ответов ИИ. Текст карточки (`why`, `what_to_do`, `notes`): утверждение «открыто» "
        f"без данных (`open_claim_in_text`) — {sum(d['open_claim_in_text'] for d in ai)}; метки честности "
        f"(часы, Wi-Fi, доступность) соблюдены — {sum(d['honest_ok'] for d in ai)} из {len(ai)}. Выбор места "
        f"(не текст): категория рекомендованного места вне допустимых по кейсу — "
        f"{sum(d['category_violation'] for d in ai)} кейсов; место выбирает детерминированное ядро по "
        "категориям намерения, которые на шаге разбора мог дополнить ИИ (см. «Дополнительная польза ИИ при "
        "маппинге категорий поверх словаря»).",
        "",
        "| набор | кейс | разбор намерения | звено текста | рек. | open_claim | категория | метки честности "
        "| latency, мс | нарушения |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for name, d in rows:
        by_ai = d["by_ai"]
        lines.append(
            f"| {name} | `{d['case_id']}` | "
            + (f"`{d['intent_model']}`" if d["intent_by_ai"] else "правила (ИИ не ответил)")
            + " | "
            + (f"`{d['model_link']}`" if by_ai else "шаблон")
            + f" | {d['n_recs']} | "
            + (("нет" if not d["open_claim_in_text"] else "**есть**") if by_ai else "н/п")
            + " | "
            + (("ок" if not d["category_violation"] else "**нарушена**") if by_ai else "н/п")
            + " | "
            + (("ок" if d["honest_ok"] else "**нарушены**") if by_ai else "н/п")
            + f" | {d['total_ms']} | {', '.join(d['violations']) or '—'} |"
        )
    lines += [
        "",
        "Для шаблонных строк проверки текста ИИ не определены (`н/п`), общий вердикт по ним — в колонке "
        "«нарушения». Подробности: `app/eval/results/summary_poi.enriched_llm-public.md`, "
        "`summary_poi.enriched_holdout_llm-public.md`.",
    ]
    return [*lines, *_ai_before_after(groups, parts)]


def _ai_before_after(
    groups: dict[str, dict[tuple[str, str], dict]], after: list[tuple[str, dict]]
) -> list[str]:
    """The same ten cases before and after the fix of 846f5fa (categories the AI added are checked against what the
    request excludes), from the kept run `llm-public-before`; empty when that run is not on disk."""
    before = {
        name: groups[name][(CANDIDATE, AI_BEFORE_LABEL)]
        for name in ("main", "holdout")
        if (CANDIDATE, AI_BEFORE_LABEL) in groups.get(name, {})
    }
    if not before:
        return []
    old = {d["case_id"]: d for s in before.values() for d in s["ai_detail"]}
    rows = [(name, d, old.get(d["case_id"])) for name, s in after for d in s["ai_detail"]]
    rows = [r for r in rows if r[2] is not None]
    if not rows:
        return []
    b_date = next(iter(before.values())).get("header", {}).get("generated_at", "")[:10]
    bad = lambda d: d["category_violation"]  # noqa: E731
    lines = [
        "",
        "### До и после исправления разбора намерения",
        "",
        "Те же кейсы, те же цепочки, кэш выключен. «До» — прогон "
        + (f"{b_date}, " if b_date else "")
        + f"метка `{AI_BEFORE_LABEL}` (файлы сохранены): ИИ добавлял к намерению категории, которые запрос "
        "исключает. «После» — прогон на дереве с исправлением 846f5fa: добавленные ИИ категории "
        "отфильтровываются по тому, что исключает запрос. Проверки те же, пересчитаны текущими правилами.",
        "",
        f"- Нарушение категории в рекомендованном месте: было {sum(bad(o) for _, _, o in rows)} из {len(rows)}, "
        f"стало {sum(bad(d) for _, d, _ in rows)} из {len(rows)}.",
        f"- Кейсов без единого нарушения: было {sum(not o['violations'] for _, _, o in rows)}, "
        f"стало {sum(not d['violations'] for _, d, _ in rows)} из {len(rows)}.",
        f"- Ответил ИИ (текст): было {sum(o['by_ai'] for _, _, o in rows)}, "
        f"стало {sum(d['by_ai'] for _, d, _ in rows)} из {len(rows)}.",
        "",
        "| набор | кейс | top-1 до | top-1 после | нарушения до | нарушения после |",
        "|---|---|---|---|---|---|",
    ]
    for name, d, o in rows:
        lines.append(
            f"| {name} | `{d['case_id']}` | {o['top1']} | {d['top1']} | "
            f"{', '.join(o['violations']) or '—'} | {', '.join(d['violations']) or '—'} |"
        )
    return lines


def _historical_section(main: dict[tuple[str, str], dict]) -> list[str]:
    """canonical.md block for each historical run kept on disk: its own table, dated, with the caveat, never in
    the columns of the current numbers."""
    lines: list[str] = []
    for label, (date, what) in HISTORICAL_RUNS.items():
        cols = [(ds, main[(ds, label)]) for ds in (BASE, CANDIDATE) if (ds, label) in main]
        if not cols:
            continue
        n_cases = cols[0][1]["cases"]
        lines += [
            "",
            f"## Исторический стресс-прогон ИИ ({date}, метка `{label}`)",
            "",
            f"Не текущие цифры и не оценка качества ИИ: {what}. Файл записан до введения заголовков (git он не "
            "хранит), код и данные того дня не совпадают с текущими. Находка прогона: когда лимит исчерпан, "
            "система не ломается и не выдумывает — отвечает шаблоном из тех же проверенных данных "
            "(hallucinated_poi = 0), а не ИИ.",
            "",
            "| | " + " | ".join(f"{ds} ({s['cases']})" for ds, s in cols) + " |",
            "|---|" + "---|" * len(cols),
            "| кейсов, где вся цепочка ИИ недоступна и ответил шаблон | "
            + " | ".join(f"{s['llm_chain_failed']} из {s['cases']}" for _, s in cols)
            + " |",
            "| кейсов, на которые ответило звено Google | "
            + " | ".join(
                f"{sum(v for k, v in s['model_link'].items() if k != 'template')} из {s['cases']}"
                + "".join(f" (`{k}`)" for k in s["model_link"] if k != "template")
                for _, s in cols
            )
            + " |",
            "| hallucinated_poi | "
            + " | ".join(str(s["hallucinated_poi"]) for _, s in cols)
            + " |",
            "| latency пайплайна, медиана (включает ожидание отказавших звеньев) | "
            + " | ".join(fmt(s["latency_ms_median"], "ms") for _, s in cols)
            + " |",
            "",
            f"Кейсы — {n_cases} сценариев ТЗ (`tz1`–`tz5`). Подробности по звеньям и ответам: "
            f"`app/eval/results/summary_*_{label}.md`.",
        ]
    return lines


def _holdout2_audit() -> dict | None:
    """Counts of the independent audit of the holdout2 `budget_min` expectations (eval/holdout2_audit.json), None
    when the file is absent."""
    path = HOLDOUT2_PATH.with_name("holdout2_audit.json")
    if not path.is_file():
        return None
    entries = [
        e for e in json.loads(path.read_text(encoding="utf-8")) if e["field"] == "budget_min"
    ]
    bad = ["-".join(e["case_id"].split("-")[:2]) for e in entries if e["verdict"] == "inconsistent"]
    return {
        "cases": len(entries),
        "inconsistent": len(bad),
        "ids": [f"`{b}`" for b in bad],
        "debatable": sum(e["verdict"] == "debatable" for e in entries),
    }


FROZEN_HOLDOUT2_SHA = (
    "d5e4b05"  # holdout2 measured here, before any fix made after seeing its failures
)


def _frozen_holdout2() -> dict[str, dict] | None:
    """The holdout2 summaries of the commit FROZEN_HOLDOUT2_SHA, read from git (the files are not kept next to the
    current ones, so the frozen number cannot drift); None when git or the commit is not there."""
    out = {}
    for ds in (BASE, CANDIDATE):
        try:
            raw = subprocess.run(
                [
                    "git",
                    "show",
                    f"{FROZEN_HOLDOUT2_SHA}:app/eval/results/summary_{ds}_holdout2_offline.json",
                ],
                cwd=REPO_ROOT,
                capture_output=True,
                check=True,
                timeout=20,
            ).stdout
            out[ds] = json.loads(raw.decode("utf-8"))
        except (OSError, subprocess.SubprocessError, ValueError):
            return None
    return out


def _holdout2_label() -> str:
    """What holdout2 is, with the number that made it blind: «слепой на момент замера d5e4b05», not blind after."""
    frozen = _frozen_holdout2()
    first = _holdout_provenance("holdout2", "1d153eb")
    if not frozen:
        return f"**holdout2** — {first} не слепой после исправлений."
    nums = " / ".join(f"{ds} {fmt(s['case_all_ok_rate'], 'pct')}" for ds, s in frozen.items())
    return (
        f"**holdout2** — слепой на момент замера {FROZEN_HOLDOUT2_SHA}: {nums} без нарушений; "
        "после исправлений общих классов ошибок — уже не слепой, его текущие числа показывают прогресс, а не "
        f"обобщение. Набор: {first}"
    )


def _holdout3_label() -> str:
    return "**holdout3** — " + _holdout_provenance("holdout3", "a21c70f") + " это число обобщения."


HOLDOUT_ROLE = "**holdout** — отдельный набор, написан отдельно, правила потом тоже подгонялись под его провалы."
ABSTAIN_ROLE = (
    "**abstain** — кейсы в заведомо скудных или невозможных ситуациях, где честный ответ — «рядом "
    "ничего подходящего нет» либо помеченный компромисс."
)


def set_roles_text() -> str:
    """What each case set is and how far its numbers can be trusted: one wording for canonical.md and for the
    «Оценка» assumption of docs/scenarios.md."""
    return " ".join(
        [
            "**main** — основной набор, на нём подгонялись правила ранжирования;",
            HOLDOUT_ROLE,
            _holdout2_label(),
            _holdout3_label(),
            ABSTAIN_ROLE,
        ]
    )


def _holdout3_note(groups: dict[str, dict[tuple[str, str], dict]], label: str) -> list[str]:
    parts = [
        (ds, groups["holdout3"][(ds, label)])
        for ds in (BASE, CANDIDATE)
        if (ds, label) in groups.get("holdout3", {})
    ]
    if not parts:
        return []
    shown = ", ".join(f"{ds}: {fmt(s['case_all_ok_rate'], 'pct')}" for ds, s in parts)
    return [
        "- **holdout3 — честное число обобщения**: кейсов без нарушений — "
        + shown
        + ". Набор написан "
        "после исправлений и ни разу не использовался для подгонки; провалы разобраны в `summary_*_holdout3_offline.md`."
    ]


# What changed in the metric definitions and the data, and when: one dated list, emitted into canonical.md so that a
# number cannot be compared with an older one without knowing which yardstick it was taken with.
GLOSSARY: tuple[tuple[str, str, str], ...] = (
    (
        "17.10.2026",
        "`open_on_holiday` — «открыто» в государственный праздник",
        "Раньше любая рекомендация со статусом «открыто» в государственный праздник считалась нарушением. После "
        "fuzz-раунда (находка S15, код `6a8cbc9`, определение — `c6861b2`) точная строка часов «24/7» может "
        "остаться «открыто» при оговорке «часы работы могут отличаться»; для любых других часов «открыто» в "
        "праздник по-прежнему нарушение (статус должен быть «неизвестно» с пометкой).",
    ),
    (
        "17.10.2026",
        "оракул часов `poi_hours` (`c6861b2`)",
        "Раньше оракул оценки смотрел только строку часов OSM (`hours_check`). Теперь он учитывает и официальный "
        "сайт: при расходящихся расписаниях (`conflict`) вердикт остаётся по OSM, а если в момент запроса один "
        "источник говорит «открыто», другой «закрыто» (`split`), состояние «неизвестно», не «открыто». Пометка о "
        "расхождении источников засчитывается как метка неизвестных часов (наравне с «Часы работы в данных "
        "неизвестны» и пометкой о празднике); `closed_at_arrival` и закрытые остановки маршрута считаются тем же "
        "оракулом.",
    ),
    (
        "17.10.2026",
        "набор `poi.enriched` (`8cae078`, `c6861b2`)",
        "Было 2183 места (OSM + Overture + Wikipedia), стало 2314 (+131 место; часы и факты с официальных "
        "сайтов). Доля мест с часами 15.8% → 22.3% (`data/poi_enriched_stats.json`). `poi.json` (только OSM) "
        "не менялся.",
    ),
)
FROZEN_CLAUSE = (
    "Замороженные базовые замеры (holdout2 `d5e4b05`, `4c7f45c`) сняты на наборе из 2183 мест до обогащения "
    "сайтами и по определениям метрик того дня; сравнивать их с текущими числами напрямую нельзя."
)
FROZEN_WITH = " Разбор по определениям, коду и данным — в таблице атрибуции выше."
FROZEN_WITHOUT = (
    " Разбор по определениям, коду и данным: `uv run poe eval-attribution` (нужна git-история)."
)


def _glossary_section(has_attribution: bool = False) -> list[str]:
    lines = [
        "",
        "## Определения метрик: что менялось и когда",
        "",
        "| дата | что | как было и как стало |",
        "|---|---|---|",
    ]
    lines += [f"| {date} | {term} | {text} |" for date, term, text in GLOSSARY]
    return [*lines, "", FROZEN_CLAUSE + (FROZEN_WITH if has_attribution else FROZEN_WITHOUT)]


def _attribution_embed(directory: Path, label: str) -> list[str]:
    """The committed results/attribution.md, embedded as it is (it states its own source commit and date), so that
    a regeneration without the git history keeps the section. Marked stale when the current runs no longer match the
    fingerprint it was computed against."""
    path = directory / attribution.ATTRIBUTION_FILE
    if not path.is_file():
        return []
    text = path.read_text(encoding="utf-8").rstrip("\n")
    lines = ["", *text.splitlines()]
    stored = attribution.FINGERPRINT_RE.search(text)
    runs = {
        name: load_runs(attribution.DATASET, label, directory, tag)
        for name, tag in attribution.SETS
    }
    if stored and all(runs.values()) and attribution.fingerprint(runs) != stored.group(1):
        lines += [
            "",
            "> **Раздел устарел**: прогоны колонки 4 изменились после его расчёта (код, данные или определения). "
            "Пересчёт: `cd app && uv run poe eval-attribution`.",
        ]
    return lines


def _holdout2_frozen_section(
    groups: dict[str, dict[tuple[str, str], dict]], label: str, has_attribution: bool = False
) -> list[str]:
    """holdout2 at the frozen commit next to the same cases now, for both datasets."""
    frozen = _frozen_holdout2()
    now = {
        ds: groups["holdout2"][(ds, label)]
        for ds in (BASE, CANDIDATE)
        if (ds, label) in groups.get("holdout2", {})
    }
    if not frozen or not now:
        return []
    keys = [
        ("case_all_ok_rate", "кейсов без нарушений", "pct"),
        ("constraint_ok_rate", "constraint_ok_rate", "pct"),
        ("coverage", "coverage", "pct"),
        ("top1_ok_rate", "top-1 без нарушений", "pct"),
        ("honest_unknown_rate", "honest_unknown_rate", "pct"),
        ("hallucinated_poi", "hallucinated_poi", "int"),
    ]
    dss = [ds for ds in (BASE, CANDIDATE) if ds in now and ds in frozen]
    lines = [
        "",
        "## holdout2: замер до исправлений и сейчас",
        "",
        f"Слепой замер зафиксирован в коммите `{FROZEN_HOLDOUT2_SHA}` (до любых исправлений по его провалам; "
        "числа взяты из git, а не пересчитаны). «Сейчас» — те же 24 кейса на текущем дереве. Кейсы не менялись; "
        "после исправлений общих классов ошибок набор больше не слепой, и разница ниже — прогресс по уже "
        "виденным провалам, а не обобщение (его показывает holdout3). Замороженный замер снят на наборе из 2183 "
        "мест до обогащения сайтами и по определениям метрик того дня, «сейчас» — на наборе из 2314 мест и по "
        "нынешним определениям"
        + (
            ": что из разницы дали определения, код и данные, показано в «Атрибуции» ниже."
            if has_attribution
            else " (разбор разницы — `uv run poe eval-attribution`, нужна git-история)."
        ),
        "",
        "| метрика | "
        + " | ".join(f"{ds} {w}" for ds in dss for w in (FROZEN_HOLDOUT2_SHA, "сейчас"))
        + " |",
        "|---|" + "---|---|" * len(dss),
    ]
    for key, name, kind in keys:
        cells = []
        for ds in dss:
            cells += [fmt(frozen[ds].get(key), kind), fmt(now[ds].get(key), kind)]
        lines.append(f"| {name} | " + " | ".join(cells) + " |")
    return lines


def _holdout_provenance(tag: str, commit: str) -> str:
    """One line on where a blind set came from, read from the `author` / `written_at` fields of its cases."""
    cases = load_cases(CASE_SETS[tag])
    authors = sorted({c["author"] for c in cases if c.get("author")})
    written = sorted({c["written_at"][:10] for c in cases if c.get("written_at")})
    when = f", {written[0]}" if written else ""
    how = (
        "написаны по одному `eval/SCHEMA.md`, без доступа к коду и уже после исправлений"
        if tag == "holdout3"
        else "написаны другой моделью без доступа к коду"
    )
    return f"{len(cases)} кейсов, {how} ({', '.join(authors) or 'автор не указан'}{when}; коммит `{commit}`);"


def _holdout2_budget_note(groups: dict[str, dict[tuple[str, str], dict]], label: str) -> list[str]:
    """How much of holdout2's coverage miss is the time-budget check: the mini-route fills the budget the system read
    from the query (or its default), `over_budget` fires when that is larger than the case's `budget_min`."""
    parts = [
        (ds, groups["holdout2"][(ds, label)])
        for ds in (BASE, CANDIDATE)
        if (ds, label) in groups.get("holdout2", {})
    ]
    if not parts:
        return []
    shown = ", ".join(
        f"{ds}: {s['violation_cases'].get('over_budget', 0)} из {s['cases']}" for ds, s in parts
    )
    lines = [
        "- **holdout2 и бюджет времени.** Кейсов с нарушением `over_budget` (маршрут длиннее `budget_min` кейса; "
        f"маршрут заполняет бюджет, который система взяла из запроса или по умолчанию): {shown}. Coverage и "
        "«кейсов без нарушений» этого набора считаются вместе с ним; число без `over_budget` — в "
        "`summary_*_holdout2_offline.md` (таблица «Нарушения»)."
    ]
    if audit := _holdout2_audit():
        lines.append(
            f"- **Аудит ожиданий holdout2.** {audit['inconsistent']} из {audit['cases']} ожиданий `budget_min` "
            "противоречат тексту запроса по независимому аудиту "
            f"([`app/eval/holdout2_audit.json`](../holdout2_audit.json)): {', '.join(audit['ids'])}; "
            f"ещё {audit['debatable']} спорные. Цифры не пересчитывались."
        )
    return lines


def canonical_md(
    groups: dict[str, dict[tuple[str, str], dict]],
    label: str,
    git_now: str,
    directory: Path = RESULTS_DIR,
) -> str:
    """The one table the deck cites: sets x datasets, every metric, with where each column came from."""
    cols = [
        (name, ds, groups[name][(ds, label)])
        for name in CANONICAL_SETS
        for ds in (BASE, CANDIDATE)
        if (ds, label) in groups.get(name, {})
    ]
    head = [f"{ds} / {name} ({s['cases']})" for name, ds, s in cols]
    lines = [
        "# Каноническая таблица оценки",
        "",
        "Единственный файл с цифрами оценки для презентации. Сгенерирован `cd app && uv run poe eval` "
        f"(`eval/report.py`), git `{git_now}`, прогоны с меткой `{label}` (офлайн: шаблонный текст, без сети; "
        "погода, воздух и время берутся из кейса, дорога — по прямой × 1.3). git — короткий sha последнего "
        "коммита, менявшего `app/walks`, `app/eval` (без `results`), `data`, `collect`; `+uncommitted` — "
        "в этих путях есть незакоммиченные изменения.",
        "",
        "- " + set_roles_text() + " Число кейсов — в заголовке колонки.",
        "- **padding** — доля рекомендаций, добранных расширением радиуса (`radius_factor > 1`), другой "
        "категорией (back-fill) или заменой из-за погоды (`substituted`: при морозе или смоге место в помещении "
        "вместо уличного — парка, смотровой, открытой достопримечательности; категория вне запроса, но не нехватка "
        "мест в данных), а не заявленным радиусом/категорией; берётся из поля `padding` результата пайплайна. "
        "Показана на карточке меткой («чуть дальше» / «другая категория»); замена из-за погоды помечена так же, как "
        "«другая категория», и считается отдельной строкой.",
        "- **honest_abstain_rate** (только abstain) — кейс пройден, если рекомендаций нет или ни одна не выдаёт "
        "несовпадение за совпадение: компромисс помечен (padding-метка, «Категория вне вашего запроса», "
        "«Часы работы в данных неизвестны», «Wi-Fi/розетки не подтверждены»). Кейсы abstain задуманы так, что "
        "обычного совпадения быть не должно; `н/п` — метрика для набора не определена.",
        *_holdout2_budget_note(groups, label),
        *_holdout3_note(groups, label),
        "- Допущения (бюджет времени по умолчанию, доля времени на дорогу, радиусы, скорость): "
        "раздел «Допущения» в `docs/scenarios.md`.",
        "- **н/п** — метрика не определена: для набора (см. выше) или для офлайн-прогона, где нет модели "
        "(недоступность цепочки ИИ, откат из-за проверки ответа ИИ, latency ответа ИИ). Latency пайплайна в "
        "этих колонках — время шаблонного пути, не ИИ.",
        (
            "- ИИ-режим в основную таблицу не входит: он измерен отдельно, на другом наборе кейсов (раздел «ИИ-режим» "
            "ниже), и с числами таблицы не смешан."
            if _ai_runs(groups)
            else "- ИИ-режим в таблицу не входит: текущего воспроизводимого прогона на звеньях Google нет."
        ),
        "  Исторический стресс-прогон 16.10 описан в конце файла и тоже с числами таблицы не смешан.",
        "",
        "## Происхождение колонок",
        "",
        "| колонка | прогон |",
        "|---|---|",
    ]
    for (_name, _ds, s), h in zip(cols, head, strict=True):
        stale = (
            " **(прогон не на текущем коммите)**"
            if s.get("header")
            and s["header"].get("git")
            and not s["header"]["git"].startswith(git_now.split("+")[0])
            else ""
        )
        lines.append(f"| {h} | {_header_text(s.get('header'))}{stale} |")
    lines += [
        "",
        "## Метрики",
        "",
        "| метрика | " + " | ".join(head) + " |",
        "|---|" + "---|" * len(cols),
    ]
    for (key, _, _), (row_label, cells) in zip(
        METRIC_ROWS, metric_rows([s for _, _, s in cols]), strict=True
    ):
        for i, (name, _, _) in enumerate(cols):
            if key in NOT_APPLICABLE.get(name, ()) or (key in ABSTAIN_ONLY and name != "abstain"):
                cells[i] = NOT_AVAILABLE
        lines.append(f"| {row_label} | " + " | ".join(cells) + " |")
    abstain_cols = [(ds, s) for name, ds, s in cols if name == "abstain"]
    if abstain_cols:
        lines += ["", "## Кейсы abstain", ""]
        lines += [
            "| кейс | " + " | ".join(ds for ds, _ in abstain_cols) + " |",
            "|---|" + "---|" * len(abstain_cols),
        ]
        for detail in zip(*(s["abstain_detail"] for _, s in abstain_cols), strict=True):
            lines.append(
                f"| `{detail[0]['case_id']}` | "
                + " | ".join(_abstain_cell(d) for d in detail)
                + " |"
            )
    missing = sorted({f for _, _, s in cols for f in s["padding_missing_fields"]})
    if missing:
        lines += ["", f"Padding посчитан по доступному, нет полей: {', '.join(missing)}."]
    has_attribution = (directory / attribution.ATTRIBUTION_FILE).is_file()
    lines += _holdout2_frozen_section(groups, label, has_attribution)
    lines += _attribution_embed(directory, label)
    lines += _glossary_section(has_attribution)
    lines += _ai_section(groups)
    lines += _historical_section(groups.get("main", {}))
    return "\n".join(lines) + "\n"


def _abstain_cell(d: dict) -> str:
    if d["n_recs"] == 0:
        return "✅ нет рекомендаций"
    if not d["silent"]:
        return (
            f"✅ {d['n_recs']} рек., несовпадений без метки нет "
            f"(с меткой компромисса: {d['labelled_recs']})"
        )
    kinds = sorted({k for ks in d["silent"].values() for k in ks})
    return f"❌ {d['n_recs']} рек., без метки: {', '.join(kinds)}"


def write_canonical(
    groups: dict[str, dict[tuple[str, str], dict]],
    label: str = CANONICAL_LABEL,
    directory: Path = RESULTS_DIR,
) -> Path:
    path = directory / "canonical.md"
    path.write_text(
        canonical_md(groups, label, sha_text(git_state()), directory),
        encoding="utf-8",
        newline="\n",
    )
    return path


def main(argv: list[str] | None = None) -> int:
    from .scenarios import write_scenarios

    ap = argparse.ArgumentParser(
        description="Aggregate eval/results into summaries and canonical.md"
    )
    ap.add_argument(
        "--label",
        default=CANONICAL_LABEL,
        help="run label whose runs go into canonical.md (default: offline; llm runs are not reproducible)",
    )
    ap.add_argument(
        "--attribution",
        action="store_true",
        help="also recompute results/attribution.md (definitions / code / data; needs the git history with the "
        "pre-swap dataset); a plain run only embeds the committed file into canonical.md",
    )
    args = ap.parse_args(argv)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    if args.attribution:
        try:
            print(f"attribution: {attribution.write(args.label, RESULTS_DIR)}")
        except FileNotFoundError as exc:
            print(f"attribution: {exc}")
            return 1
    groups = {
        "main": write_summaries(),
        "holdout": write_summaries(tag="holdout"),
        "holdout2": write_summaries(tag="holdout2"),
        "holdout3": write_summaries(tag="holdout3"),
        "abstain": write_summaries(tag="abstain"),
    }
    write_main_vs_holdout(groups["main"], groups["holdout"], groups["holdout2"], groups["holdout3"])
    for name, group in groups.items():
        for (dataset, mode), s in sorted(group.items()):
            line = (
                f"{name:<8} {dataset:<14} {mode:<8} cases={s['cases']} halluc={s['hallucinated_poi']} "
                f"constraint_ok={s['constraint_ok_rate']}% coverage={s['coverage']}% "
                f"honest={s['honest_unknown_rate']}% diversity={s['diversity']}% "
                f"padded={s['padded_rec_share']}%"
            )
            if name == "abstain":
                line += f" honest_abstain={s['honest_abstain_rate']}%"
            print(line)
    print(f"canonical: {write_canonical(groups, args.label)}")
    path = write_scenarios()
    print(f"docs: {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
