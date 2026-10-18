"""Additional benefit of the LLM for mapping categories on top of the lexicon: rule intent vs rule+LLM intent on the
queries of the main, held-out and abstention sets: no retrieval, no generation, only the intent chain
(walks.intent.parse_intent).

    python -m eval.intent_compare                 # all three sets, 4 s between live calls
    python -m eval.intent_compare --public-only   # only the Google links (gemini:*), response cache off
    WALKS_ENV=demo python -m eval.intent_compare  # the demo chain (extra links after the Google ones)
    python -m eval.intent_compare --sets holdout --limit 5

For every query: the categories the rules found, the ones the LLM added, and whether the LLM closed a gap of the
rule intent against the case's `expected` (eval.metrics.intent_gaps: no allowed category, a forbidden one, a missing
kids / Wi-Fi / step-free flag). A query counts as measured only when a link actually answered it live (`used` names
it): an answer that fell back to the rules is never read as «the LLM did not help», it is listed as not measured
with the attempts, and an answer read from the response cache or given by a non-Google link (shown as
«резервная модель (частный профиль)») is listed but excluded from every total, because it can be neither
reproduced publicly nor attributed to a fresh call. With --public-only the chain is cut to its `gemini:*` links and
the cache is off, so every measured row is a public, live call. After STORM_STREAK consecutive unanswered queries
(a quota storm, or no key at all) the run stops and the table says how many were measured and how many were left.
Output: results/intent_compare.md and .json.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from collections.abc import Callable
from datetime import datetime
from pathlib import Path

from walks.envcfg import load_env_file
from walks.intent import parse_intent
from walks.llm import intent_models
from walks.models import IntentResult

from .cases import CASE_SETS, RESULTS_DIR, git_state, load_cases, sha_text
from .metrics import intent_gaps
from .redact import PRIVATE_LINK, public_text

TITLE = "Дополнительная польза ИИ при маппинге категорий поверх словаря"
MIN_PAUSE_S = 4.0  # between live calls: free-tier rate limits
STORM_STREAK = 3  # consecutive queries without an LLM answer after which the run stops
OUT_STEM = "intent_compare"
_FLAGS = ("with_kids", "quiet", "needs_wifi_socket", "night", "accessibility")


def _row(set_name: str, case: dict, res: IntentResult) -> dict:
    """One comparison row from the intent result of `case`. `measured`: a link answered; `counted`: and it was a
    fresh call of a Google link (a cached answer or the private profile is shown but not totalled)."""
    row = {"case_id": case["id"], "set": set_name, "query": case["query"]}
    step = res.llm_step
    attempts = public_text(step.attempts_text()) if step else None
    measured = res.parser == "rules+llm" and res.rules is not None
    if not measured:
        return {
            **row,
            "measured": False,
            "counted": False,
            "reason": attempts or public_text(res.note) or "—",
        }
    used = public_text(step.model) if step else None
    cached = bool(step and step.cached)
    rules, merged = res.rules.model_dump(), res.intent.model_dump()
    rule_gaps, merged_gaps = intent_gaps(case, rules), intent_gaps(case, merged)
    return {
        **row,
        "measured": True,
        "counted": not cached and used != PRIVATE_LINK,
        "used": used,
        "cached": cached,
        "rule_categories": rules["categories"],
        "added_categories": [c for c in merged["categories"] if c not in rules["categories"]],
        "added_flags": [f for f in _FLAGS if merged[f] and not rules[f]],
        "rule_gaps": rule_gaps,
        "merged_gaps": merged_gaps,
        "fixed": bool(rule_gaps) and not merged_gaps,
        "partial": len(merged_gaps) < len(rule_gaps) and bool(merged_gaps),
        "worse": [g for g in merged_gaps if g not in rule_gaps],
    }


def compare(
    cases: list[tuple[str, dict]],
    *,
    parse: Callable[..., IntentResult] = parse_intent,
    pause_s: float = MIN_PAUSE_S,
    storm: int = STORM_STREAK,
    sleep: Callable[[float], None] = time.sleep,
) -> dict:
    """Run the intent chain over (set name, case) pairs. Returns {"rows": measured + not measured rows,
    "stopped": reason or None, "left": cases not tried after a stop}."""
    rows: list[dict] = []
    streak, stopped = 0, None
    for n, (set_name, case) in enumerate(cases):
        when = datetime.fromisoformat(case["when"]) if "when" in case else None
        res = parse(case["query"], use_llm=True, when=when)
        row = _row(set_name, case, res)
        rows.append(row)
        streak = 0 if row["measured"] else streak + 1
        if res.llm_step is None and not row["measured"]:
            stopped = f"ИИ не вызывался: {row['reason']}"
        elif streak >= storm:
            stopped = (
                f"{streak} запроса подряд без ответа ИИ (лимит / сбой цепочки): {row['reason']}"
            )
        if stopped:
            return {"rows": rows, "stopped": stopped, "left": len(cases) - n - 1}
        if not (res.llm_step and res.llm_step.cached) and n < len(cases) - 1:
            sleep(pause_s)
    return {"rows": rows, "stopped": None, "left": 0}


def summary(result: dict) -> dict:
    rows = result["rows"]
    counted = [r for r in rows if r["counted"]]
    answered = [r for r in rows if r["measured"]]
    with_gap = [r for r in counted if r["rule_gaps"]]
    holdout_gap = [r for r in with_gap if r["set"] == "holdout"]
    return {
        "tried": len(rows),
        "left": result["left"],
        "stopped": result["stopped"],
        "measured": len(counted),
        "excluded": len(answered) - len(counted),
        "not_measured": len(rows) - len(answered),
        "rule_gap_cases": len(with_gap),
        "llm_fixed": sum(r["fixed"] for r in with_gap),
        "llm_partial": sum(r["partial"] for r in with_gap),
        "llm_worse": sum(bool(r["worse"]) for r in counted),
        "holdout_rule_gap_cases": len(holdout_gap),
        "holdout_llm_fixed": sum(r["fixed"] for r in holdout_gap),
        "used": sorted({r["used"] for r in counted if r["used"]}),
    }


def _verdict(r: dict) -> str:
    if not r["measured"]:
        return f"не измерено: {r['reason']}"
    if not r["counted"]:
        why = "ответ из кэша" if r["cached"] else "частный профиль"
        return f"исключено из итогов ({why})"
    if not r["rule_gaps"]:
        return "у правил нет пробела" + (
            f"; ИИ добавил лишнее: {', '.join(r['worse'])}" if r["worse"] else ""
        )
    gaps = ", ".join(r["rule_gaps"])
    if r["fixed"]:
        return f"✅ ИИ закрыл: {gaps}"
    if r["partial"]:
        return f"◐ ИИ закрыл часть, осталось: {', '.join(r['merged_gaps'])}"
    return f"❌ не помог: {gaps}"


def _cell(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


def render(result: dict, header: str) -> str:
    s = summary(result)
    lines = [
        f"# {TITLE}",
        "",
        header,
        "",
        "Словарь (правила) находит категории по ключевым словам; ИИ только добавляет к ним то, что словарь не "
        "распознал (union категорий, OR флагов). Без поиска и без генерации: только цепочка разбора намерения. "
        "Пробел правил — что-то из `expected` кейса, чего нет в их намерении (нет допустимой категории / есть "
        "запрещённая / не взведён флаг «дети», «розетка», «доступность»).",
        "",
        f"- Опрошено запросов: {s['tried']}; измерено (живой ответ звена Google): **{s['measured']}**; "
        f"исключено из итогов (кэш / частный профиль): {s['excluded']}; не измерено: {s['not_measured']}; "
        f"не опрошено после остановки: {s['left']}.",
    ]
    if s["stopped"]:
        lines.append(f"- Остановка: {s['stopped']}.")
    lines += [
        f"- Отвечали звенья: {', '.join(s['used']) or '—'}.",
        f"- У правил есть пробел в {s['rule_gap_cases']} измеренных запросах; ИИ закрыл полностью: "
        f"**{s['llm_fixed']}**, частично: {s['llm_partial']}; добавил новый пробел: {s['llm_worse']}.",
        "- Измерено по наборам: "
        + ", ".join(
            f"{name} {sum(r['counted'] for r in result['rows'] if r['set'] == name)}"
            for name in ("main", "holdout", "abstain")
        )
        + ".",
        (
            f"- Только holdout: пробел правил в {s['holdout_rule_gap_cases']}, ИИ закрыл полностью "
            f"**{s['holdout_llm_fixed']}**."
            if any(r["set"] == "holdout" and r["counted"] for r in result["rows"])
            else "- Только holdout: не опрошен — вывода по нему нет."
        ),
        "",
        "| набор | кейс | запрос | категории правил | добавил ИИ | звено | итог |",
        "|---|---|---|---|---|---|---|",
    ]
    for r in result["rows"]:
        if r["measured"]:
            added = ", ".join([*r["added_categories"], *(f"+{f}" for f in r["added_flags"])]) or "—"
            cats = ", ".join(r["rule_categories"]) or "—"
            used = (r["used"] or "—") + (" (кэш)" if r["cached"] else "")
        else:
            added = cats = used = "—"
        q = r["query"] if len(r["query"]) <= 60 else r["query"][:59] + "…"
        lines.append(
            f"| {r['set']} | `{r['case_id']}` | {_cell(q)} | {cats} | {added} | {_cell(used)} | "
            f"{_cell(_verdict(r))} |"
        )
    return "\n".join(lines) + "\n"


def public_chain() -> list[str]:
    """The intent chain cut to its Google links, in order."""
    return [spec for spec in intent_models() if spec.startswith("gemini:")]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=TITLE)
    ap.add_argument(
        "--sets",
        nargs="+",
        default=["main", "holdout", "abstain"],
        choices=["main", "holdout", "abstain"],
    )
    ap.add_argument("--limit", type=int, help="only the first N queries (after joining the sets)")
    ap.add_argument(
        "--pause",
        type=float,
        default=MIN_PAUSE_S,
        help=f"seconds between live calls (at least {MIN_PAUSE_S:g})",
    )
    ap.add_argument(
        "--public-only",
        action="store_true",
        help="only the gemini:* links of the intent chain, no private profile, response cache off",
    )
    ap.add_argument("--out-dir", type=Path, default=RESULTS_DIR)
    args = ap.parse_args(argv)
    if args.pause < MIN_PAUSE_S:
        ap.error(f"--pause must be at least {MIN_PAUSE_S:g} s")

    if args.public_only:
        os.environ.pop("WALKS_ENV", None)  # no private profile is even read
    load_env_file()
    os.environ["WALKS_REQUEST_LOG"] = "off"
    os.environ.pop("WALKS_OFFLINE", None)
    if args.public_only:
        os.environ["WALKS_LLM_CACHE"] = "off"
        chain = public_chain()
        if not chain:
            ap.error("--public-only: the intent chain has no gemini:* link")
        os.environ["LLM_INTENT_CHAIN"] = ",".join(chain)
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")

    names = ["" if s == "main" else s for s in args.sets]
    cases = [
        (s, c) for s, tag in zip(args.sets, names, strict=True) for c in load_cases(CASE_SETS[tag])
    ]
    cases = cases[: args.limit] if args.limit else cases
    result = compare(cases, pause_s=args.pause)
    s = summary(result)

    header = (
        f"git `{sha_text(git_state())}`, {datetime.now().astimezone():%d.%m.%Y %H:%M}, наборы: "
        f"{', '.join(args.sets)}, пауза между вызовами {args.pause:g} с"
        + (
            ", режим `--public-only`: только звенья Google (без частного профиля), кэш ответов выключен, "
            f"цепочка `{' → '.join(public_chain())}`."
            if args.public_only
            else "."
        )
    )
    args.out_dir.mkdir(parents=True, exist_ok=True)
    (args.out_dir / f"{OUT_STEM}.md").write_text(
        render(result, header), encoding="utf-8", newline="\n"
    )
    (args.out_dir / f"{OUT_STEM}.json").write_text(
        json.dumps(
            {"summary": s, "public_only": args.public_only, "rows": result["rows"]},
            ensure_ascii=False,
            indent=2,
        )
        + "\n",
        encoding="utf-8",
        newline="\n",
    )
    print(
        f"measured {s['measured']}/{s['tried']} (excluded {s['excluded']}, not tried: {s['left']}); "
        f"rule gaps {s['rule_gap_cases']}, LLM fixed {s['llm_fixed']} "
        f"(holdout {s['holdout_llm_fixed']}/{s['holdout_rule_gap_cases']})"
        + (f"; stopped: {s['stopped']}" if s["stopped"] else "")
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
