"""Does the live intent model change a reading the rules are confident of (walks.confident)? The pipeline asks no model
then, so a change here would be an answer changed by the skip.

    WALKS_ENV=demo uv run python -m eval.intent_skip            # measure what is not measured yet, then the table
    uv run python -m eval.intent_skip --render                   # the table again from results/intent_skip.json

Over the queries of the main, held-out and abstention sets (eval/cases.json, holdout_cases.json, holdout2_cases.json,
abstain_cases.json) and the typical first messages below, every distinct reading of the rules with a kind of place (the
same draft is the same prompt) goes to the live intent chain: the response cache is off and the breakers are closed
before each call; a call that falls back to the rules is tried again (at most ATTEMPTS times) and is listed as not
measured after that. The model's merged reading is compared with the rules' one by walks.confident.same_reading, the
test the pipeline uses to keep the answer prepared for the rules' reading. Which queries the rules are confident of
is read at render time, so a change of walks.confident needs no new model calls. Output: results/intent_skip.md and
.json; exit 1 when a confident reading was changed."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime

from walks.confident import rules_confident, same_reading
from walks.envcfg import load_env_file
from walks.intent import parse_intent, parse_rules, refine_prompt
from walks.llm import Deadline, reset_breakers

from .cases import ABSTAIN_PATH, CASES_PATH, HOLDOUT2_PATH, HOLDOUT_PATH, RESULTS_DIR, load_cases

ATTEMPTS = 3
OUT_STEM = "intent_skip"
SETS = (
    ("main", CASES_PATH),
    ("holdout", HOLDOUT_PATH),
    ("holdout2", HOLDOUT2_PATH),
    ("abstain", ABSTAIN_PATH),
)
# the typical first messages of a visitor (scripts/time_turns.py) and named kinds in every language
TYPICAL = (
    "хочу поесть",
    "кофе рядом",
    "погулять хочу просто",
    "аптека рядом",
    "что посмотреть",
    "куда сходить с ребёнком",
    "баламен қайда баруға болады",
    "what should i see",
    "где поужинать недорого",
    "хочу в парк",
    "музей",
    "банкомат рядом",
    "продуктовый магазин рядом",
    "куда пойти вечером с друзьями",
    "кофе с wifi поработать",
    "кофе ішкім келеді",
    "a quiet place to read",
    "coffee nearby",
    "где погулять с собакой",
    "куда сходить на 2 часа",
    "где поужинать",
    "ресторан рядом",
    "бар рядом",
    "кинотеатр рядом",
    "торговый центр",
    "супермаркет рядом",
    "аптека и банкомат",
    "where is a pharmacy",
    "museum nearby",
    "дәріхана қайда",
    "жақын жерде кафе",
    "мұражай",
)


def _queries() -> list[tuple[str, str, datetime | None]]:
    out = [
        (name, case["query"], datetime.fromisoformat(case["when"]) if "when" in case else None)
        for name, path in SETS
        for case in load_cases(path)
    ]
    return out + [("typical", text, None) for text in TYPICAL]


def _ask(text: str, when: datetime | None):
    res = None
    for _ in range(ATTEMPTS):
        reset_breakers()
        res = parse_intent(text, use_llm=True, deadline=Deadline(), when=when)
        if res.parser == "rules+llm":
            return res
        time.sleep(1.0)
    return res


def _measure(text: str, when: datetime | None) -> dict:
    rules = parse_rules(text, when)
    res = _ask(text, when)
    measured = res is not None and res.parser == "rules+llm"
    row = {
        "measured": measured,
        "same": measured and same_reading(rules.intent, res.intent, text),
        "changed": sorted(
            k
            for k, v in rules.intent.model_dump().items()
            if measured and res.intent.model_dump()[k] != v
        ),
    }
    print(json.dumps({"q": text, **row}, ensure_ascii=False), flush=True)
    return row


def run(old: list[dict]) -> list[dict]:
    """Every reading the skip may decide on, measured once; a reading measured in `old` is kept as it is."""
    kept = {(r["query"], r.get("when")): r for r in old if r["measured"]}
    rows: list[dict] = []
    seen: dict[str, dict] = {}
    for name, text, when in _queries():
        rules = parse_rules(text, when)
        if rules.intent.refusal != "none" or not rules.intent.categories:
            continue  # nothing for the skip to decide: the pipeline never prepares an answer for such a reading
        stamp = when.isoformat() if when else None
        key = refine_prompt(text, rules.intent)
        if key not in seen:
            done = kept.get((text, stamp))
            seen[key] = (
                {k: done[k] for k in ("measured", "same", "changed")}
                if done
                else _measure(text, when)
            )
        rows.append({"set": name, "query": text, "when": stamp, **seen[key]})
    return rows


def _confident(row: dict) -> bool:
    when = datetime.fromisoformat(row["when"]) if row.get("when") else None
    return rules_confident(row["query"], parse_rules(row["query"], when))


def render(rows: list[dict]) -> str:
    """The table, with the confidence of each query read by the current walks.confident."""
    distinct = list({r["query"]: {**r, "confident": _confident(r)} for r in rows}.values())
    conf = [r for r in distinct if r["confident"]]
    rest = [r for r in distinct if not r["confident"]]
    lines = [
        "# Уверенность правил: модель разбора не спрашивают",
        "",
        "`python -m eval.intent_skip`: живая модель разбора (без кэша) на запросах наборов main, holdout, holdout2,",
        "abstain и типичных первых сообщениях. «Тот же разбор» — проверка walks.confident.same_reading, по которой",
        "конвейер оставляет ответ, подготовленный по разбору правил. «Не измерено»: модель не ответила за "
        f"{ATTEMPTS} попытки.",
        "",
        f"- Правила уверены: {len(conf)} разных запросов; тот же разбор у модели: "
        f"{sum(r['same'] for r in conf)}, изменён: {sum(r['measured'] and not r['same'] for r in conf)}, "
        f"не измерено: {sum(not r['measured'] for r in conf)}.",
        f"- Правила не уверены: {len(rest)}; модель изменила разбор в "
        f"{sum(r['measured'] and not r['same'] for r in rest)} из {sum(r['measured'] for r in rest)} измеренных.",
        "",
        "| Набор | Запрос | Правила уверены | Разбор модели |",
        "|---|---|---|---|",
    ]
    for r in sorted(distinct, key=lambda r: (not r["confident"], r["set"], r["query"])):
        verdict = (
            "не измерено"
            if not r["measured"]
            else "тот же"
            if r["same"]
            else "изменён: " + ", ".join(r["changed"])
        )
        query = r["query"].replace("|", "\\|")
        lines.append(f"| {r['set']} | {query} | {'да' if r['confident'] else 'нет'} | {verdict} |")
    return "\n".join(lines) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Уверенность правил против живой модели разбора")
    ap.add_argument("--render", action="store_true", help="only re-render the table from the JSON")
    args = ap.parse_args(argv)
    out = RESULTS_DIR / f"{OUT_STEM}.json"
    old = json.loads(out.read_text(encoding="utf-8")) if out.exists() else []
    if args.render:
        rows = old
    else:
        load_env_file()
        os.environ.update(WALKS_LLM_CACHE="off", WALKS_REQUEST_LOG="off", WALKS_CACHE_PIN="0")
        rows = run(old)
        out.write_text(json.dumps(rows, ensure_ascii=False, indent=1), encoding="utf-8")
    (RESULTS_DIR / f"{OUT_STEM}.md").write_text(render(rows), encoding="utf-8")
    broken = [r for r in rows if _confident(r) and r["measured"] and not r["same"]]
    return 1 if broken else 0


if __name__ == "__main__":
    sys.exit(main())
