"""The numbers the slides state, each computed from its file; build.py fails if slides.html does not show them.

* data/api_data_2026-10-19.json - the public /api/data of the live stand («Данные»), saved 19.10.2026 17:15;
* app/eval/results/canonical.md and runs_poi.enriched_offline.jsonl - the evaluation (offline runs of 19.10.2026,
  poi.enriched columns; the LLM-mode table of 17.10.2026);
* data/poi.enriched.json - the base itself;
* the code the privacy, speed and refresh lines describe, read for the constant itself;
* the constants below, each with its source.
"""

from __future__ import annotations

import json
import re
from functools import cache

import figures as F

RESULTS = F.ROOT / "app" / "eval" / "results"
CANONICAL = RESULTS / "canonical.md"
OFFLINE_RUNS = RESULTS / "runs_poi.enriched_offline.jsonl"
BRIEF_CASES = ("tz1", "tz2", "tz3", "tz4", "tz5")  # the five scenarios of the brief (НИЦ Smart City, section 1)

TESTS_AT_LEAST = 3000  # pytest gate on main, 19.10.2026 evening: 3 010 and more passed; the slide says «3 000+»
PERSONA_ROUNDS = 7  # rounds of the simulated users (AI personas): docs/dialog.md, «Wave 9 (round 7 of the personas)»


def _int(n: int) -> str:
    return f"{n:,}".replace(",", " ")


def _const(path, pattern: str) -> int:
    m = re.search(pattern, path.read_text(encoding="utf-8"), re.M)
    if not m:
        raise SystemExit(f"{path}: no {pattern!r}")
    return int(m.group(1))


@cache
def canonical() -> dict[str, dict[str, str]]:
    """The «Метрики» table of canonical.md: row label -> {set: value} for the poi.enriched columns."""
    lines = CANONICAL.read_text(encoding="utf-8").splitlines()
    start = next(i for i, ln in enumerate(lines) if ln.startswith("| метрика | poi / main"))
    head = [c.strip() for c in lines[start].strip("|").split("|")]
    out: dict[str, dict[str, str]] = {}
    for ln in lines[start + 2 :]:
        if not ln.startswith("|"):
            break
        cells = [c.strip() for c in ln.strip("|").split("|")]
        row = {}
        for h, c in zip(head[1:], cells[1:]):
            m = re.fullmatch(r"poi\.enriched / (\w+) \(\d+\)", h)
            if m:
                row[m.group(1)] = c
        out[cells[0]] = row
    return out


def brief_cases_clean() -> int:
    """How many of the brief's scenarios pass with no violation both offline and in the LLM-mode table."""
    offline = {}
    for ln in OFFLINE_RUNS.read_text(encoding="utf-8").splitlines():
        r = json.loads(ln)
        if r.get("case_id") in BRIEF_CASES:
            offline[r["case_id"]] = r["verdict"]["all_ok"] and not r["verdict"]["violations"]
    llm = {m.group(1): m.group(2).strip() == "—"
           for m in re.finditer(r"^\| main \| `(tz\d)` \|.*\|([^|]*)\|$", CANONICAL.read_text(encoding="utf-8"), re.M)}
    return sum(1 for c in BRIEF_CASES if offline.get(c) and llm.get(c))


@cache
def numbers() -> dict[str, str]:
    """label -> the number as the slide writes it (spaces inside numbers are compared loosely)."""
    c = canonical()
    cases = sum(int(v) for v in c["кейсов"].values())
    honest = set(c["honest_unknown_rate (кейсы)"].values())
    if honest != {"100.0%"}:
        raise SystemExit(f"honest_unknown_rate is not 100 % on every set: {honest}")
    if brief_cases_clean() != len(BRIEF_CASES):
        raise SystemExit(f"only {brief_cases_clean()} of the brief's {len(BRIEF_CASES)} scenarios pass clean")
    app = F.ROOT / "app"
    wait_ms = _const(app / "web" / "static" / "js" / "assistant.js", r"^const WAIT_SHAPE = (\d+);")
    n = {
        "мест в базе": _int(F.api()["coverage"]["places"]),
        "тестовых сценариев": str(cases),
        "выдуманных мест": str(sum(int(v) for v in c["hallucinated_poi (должно быть 0)"].values())),
        "честных ответов, %": "100",
        "сценариев ТЗ без нарушений": "пять",
        "автотестов": f"{_int(TESTS_AT_LEAST)}+",
        "раундов ИИ-персон": str(PERSONA_ROUNDS),
        "ход ответа, с": f"{wait_ms / 1000:.1f}".replace(".", ","),
        "точка, м": str(_const(F.ROOT / "README.md", r"округляются до ~(\d+) м")),
        "участок, м": str(_const(app / "walks" / "reqlog.py", r"^CELL_M = (\d+)")),
        "группа от": str(_const(app / "walks" / "demand.py", r"^K_DEFAULT = (\d+)")),
        "афиша, часов": str(_const(F.ROOT / "deploy" / "vps" / "anyq-events.timer", r"OnCalendar=\*-\*-\* 00/(\d+):")),
    }
    for k, v in F.origin_counts().items():
        n[f"источник {k}"] = _int(v)
    return n
