"""Attribution of the metric changes of the official-site data swap: definitions, code or data?

Between the last canonical results before the swap (BEFORE_REV) and the current tree three things changed at once:
the metric definitions (`eval/metrics.py`: the hours oracle `poi_hours`, the 24/7 holiday rule), the code (fuzz
rounds, `conflict` / `split` in the hours) and the shipped dataset (2183 places -> 2314, hours from the
businesses' own sites). Four columns separate them:

    1  BEFORE_REV results as measured
    2  the same answers (runs of BEFORE_REV) judged by today's definitions on the dataset they ran on
    3  the CURRENT code on the PRE-SWAP dataset (`git show PRESWAP_REV:data/poi.enriched.json`), offline
    4  the current code on the current dataset
       definitions = 2 - 1      code = 3 - 2      data = 4 - 3

`refresh_runs` writes column 3 (label `preswap`, results/runs_poi.enriched[_<set>]_preswap.jsonl) through
`eval.run_eval --data-rev`; `report.load_runs` judges it against the pre-swap dataset (`preswap_index`), so a place
that the swap added is never counted as hallucinated and the hours oracle sees the hours of its day. `section`
renders the aggregate table and the per-case table that canonical.md carries; nothing in it is typed by hand.
The `poi.json` baseline is not touched by the swap (its file is identical at both revisions): only code differs.
"""

from __future__ import annotations

import atexit
import contextlib
import hashlib
import io
import json
import re
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from datetime import datetime
from functools import lru_cache
from pathlib import Path
from typing import NamedTuple

from walks.models import POI, load_pois

from .cases import (
    CASE_SETS,
    DATA_DIR,
    HEADER_KEY,
    REPO_ROOT,
    git_state,
    load_cases,
    runs_name,
    sha_text,
)
from .metrics import dataset_index, judge_abstain, judge_case

DATASET = "poi.enriched"
PRESWAP_LABEL = "preswap"
PRESWAP_REV = "6a8cbc9"  # parent of 8cae078, the last commit that ships the 2183-place dataset
BEFORE_REV = (
    "a90279c"  # last canonical results before the fuzz code rounds and the data swap (same dataset)
)
SETS = (
    ("main", ""),
    ("holdout", "holdout"),
    ("holdout2", "holdout2"),
    ("holdout3", "holdout3"),
    ("abstain", "abstain"),
)
# (summary key, label); the abstention set has its own pass rate, and coverage is not defined for it
METRICS = (
    ("case_all_ok_rate", "кейсов без нарушений"),
    ("constraint_ok_rate", "constraint_ok_rate"),
    ("coverage", "coverage"),
)
ABSTAIN_METRICS = (
    ("honest_abstain_rate", "honest_abstain_rate"),
    ("constraint_ok_rate", "constraint_ok_rate"),
)


def _git_show(rev: str, path: str) -> bytes | None:
    try:
        return subprocess.run(
            ["git", "show", f"{rev}:{path}"],
            cwd=REPO_ROOT,
            capture_output=True,
            check=True,
            timeout=60,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return None


_materialized: dict[tuple[str, str], Path] = {}


def data_at_rev(rev: str, name: str) -> Path:
    """`data/<name>` as of git revision `rev`, written to a temp file named `<name>` (so the dataset name read from
    the path is the real one). Raises FileNotFoundError when git or the revision is not available."""
    key = (rev, name)
    if key not in _materialized:
        raw = _git_show(rev, f"data/{name}")
        if raw is None:
            raise FileNotFoundError(f"data/{name} at git revision {rev} is not available")
        directory = Path(tempfile.mkdtemp(prefix="eval-data-"))
        atexit.register(shutil.rmtree, directory, ignore_errors=True)
        _materialized[key] = directory / name
        _materialized[key].write_bytes(raw)
    return _materialized[key]


@lru_cache(maxsize=2)
def preswap_index(dataset: str) -> dict[str, POI] | None:
    """Places of the pre-swap dataset by id; None when the revision cannot be read."""
    try:
        return dataset_index(load_pois(data_at_rev(PRESWAP_REV, f"{dataset}.json")))
    except FileNotFoundError:
        return None


def refresh_runs(directory: Path) -> bool:
    """Run the current code over every case set on the pre-swap dataset (offline, label `preswap`) into
    `directory`. False when the pre-swap dataset is not in this checkout's git history (a squashed or shallow
    clone)."""
    try:
        data_at_rev(PRESWAP_REV, f"{DATASET}.json")
    except FileNotFoundError:
        return False
    from .run_eval import main as run_eval_main

    for _name, tag in SETS:
        argv = [
            "--data",
            str(DATA_DIR / f"{DATASET}.json"),
            "--data-rev",
            PRESWAP_REV,
            "--mode",
            "offline",
            "--label",
            PRESWAP_LABEL,
            "--out",
            str(directory / runs_name(DATASET, PRESWAP_LABEL, tag)),
        ]
        if tag:
            argv += ["--cases", str(CASE_SETS[tag])]
        with contextlib.redirect_stdout(io.StringIO()):
            run_eval_main(argv)
    return True


def _sfx(tag: str) -> str:
    return f"_{tag}" if tag else ""


def before_summary(tag: str) -> dict | None:
    raw = _git_show(BEFORE_REV, f"app/eval/results/summary_{DATASET}{_sfx(tag)}_offline.json")
    return json.loads(raw.decode("utf-8")) if raw else None


def before_runs(tag: str) -> list[dict] | None:
    raw = _git_show(BEFORE_REV, f"app/eval/results/{runs_name(DATASET, 'offline', tag)}")
    if raw is None:
        return None
    lines = [json.loads(x) for x in raw.decode("utf-8").splitlines() if x]
    return [r for r in lines if HEADER_KEY not in r]


class Status(NamedTuple):
    ok: bool
    codes: tuple[str, ...]


def status(run: dict, tag: str, detail: dict[str, dict] | None = None) -> Status:
    """Pass / fail of one case with the codes that explain a fail. A case of the abstention set passes when it is an
    honest abstention (its codes are the silent mismatches); every other set passes when no violation is recorded.
    `detail` is the frozen summary's `abstain_detail` by case id, for runs that predate the stored abstain verdict."""
    if tag == "abstain":
        if "abstain" in run:
            a = run["abstain"]
            kinds = sorted({k for ks in a["silent_mismatches"].values() for k in ks})
            return Status(a["honest_abstain"], tuple(kinds))
        d = (detail or {}).get(run["case_id"], {"silent": {}})
        kinds = sorted({k for ks in d["silent"].values() for k in ks})
        return Status(not kinds, tuple(kinds))
    v = run["verdict"]
    return Status(v["all_ok"], tuple(sorted(v["violations"])))


def _cell(s: Status) -> str:
    if s.ok:
        return "✅"
    return "❌ " + ", ".join(s.codes) if s.codes else "❌"


def _top1(run: dict) -> str:
    return run["recs"][0]["name"] if run["recs"] else "—"


def _rec_ids(run: dict) -> list[str]:
    return [r["poi_id"] for r in run["recs"]]


def _code_detail(a: dict, b: dict) -> str:
    """What the code change did to a case, both runs on the same dataset."""
    if _rec_ids(a) == _rec_ids(b):
        return "те же места, другая оценка или пометка"
    if _top1(a) != _top1(b):
        return f"top-1: {_top1(a)} → {_top1(b)}"
    return "набор мест изменился, top-1 тот же"


def _data_detail(b: dict, c: dict, pre: dict[str, POI], now: dict[str, POI]) -> str:
    """What the new data did to a case, both runs on the same code: which recommended place is new or has other
    hours."""
    before = set(_rec_ids(b))
    bits = []
    for rec in c["recs"]:
        pid = rec["poi_id"]
        if pid in before:
            continue
        if pid not in pre:
            bits.append(f"новое место «{rec['name']}»")
        elif pre[pid].opening_hours != now.get(pid, pre[pid]).opening_hours:
            bits.append(f"у «{rec['name']}» изменились часы")
        else:
            bits.append(f"«{rec['name']}» вошло в ответ (в данных то же место)")
    gone = len(before - set(_rec_ids(c)))
    if gone and not bits:
        return "выпали места, новых нет"
    return "; ".join(bits[:2]) or "те же места, другая оценка или пометка"


def _pp(a: float | None, b: float | None) -> str:
    return "—" if a is None or b is None else f"{b - a:+.1f} п.п."


def _pct(v: float | None) -> str:
    return "н/п" if v is None else f"{v:.1f}%"


Loader = Callable[[str, str, str], list[dict]]


def rejudged_before(tag: str) -> list[dict] | None:
    """The answers measured at BEFORE_REV, judged by the CURRENT metric definitions against the pre-swap dataset
    (the dataset they were produced on): the same answers, today's yardstick. Separates a change of definitions
    from a change of code."""
    runs, index = before_runs(tag), preswap_index(DATASET)
    if runs is None or index is None:
        return None
    cases = {c["id"]: c for c in load_cases(CASE_SETS[tag])}
    for run in runs:
        case = cases[run["case_id"]]
        run["verdict"] = judge_case(case, run["recs"], run["route"], index)
        if tag == "abstain":
            run["abstain"] = judge_abstain(case, run, index)
    return runs


def _summaries_of(tag: str, runs: list[dict]) -> dict:
    from .report import summarize  # report imports this module: resolve at call time

    return summarize(runs, load_cases(CASE_SETS[tag]))


def section(
    groups: dict[str, dict[tuple[str, str], dict]],
    label: str,
    load: Loader,
    now_index: Callable[[str], dict[str, POI]],
    source_note: str = "",
) -> list[str]:
    """canonical.md block: aggregates over the four columns (before as measured / the same answers under today's
    definitions / current code on the pre-swap dataset / current code and dataset) and every case whose result
    differs between them, with the cause. Empty when the pre-swap runs are not there."""
    have = [
        (name, tag)
        for name, tag in SETS
        if (DATASET, PRESWAP_LABEL) in groups.get(name, {})
        and (DATASET, label) in groups.get(name, {})
    ]
    if not have:
        return []
    frozen = {name: before_summary(tag) for name, tag in have}
    pre_idx = preswap_index(DATASET)
    if pre_idx is None or not any(frozen.values()):
        return []
    rejudged = {name: rejudged_before(tag) for name, tag in have}
    lines = [
        "",
        "## Атрибуция: что изменили определения, код и данные",
        "",
        f"Между замером `{BEFORE_REV}` и текущим деревом изменилось сразу три вещи: определения метрик "
        "(`eval/metrics.py`: оракул часов `poi_hours`, правило 24/7 в праздник, см. «Определения метрик» ниже), "
        "код системы (раунды fuzz, `split` и `conflict` в часах) и набор `poi.enriched` (2183 → 2314 мест, часы "
        "с официальных сайтов). Четыре колонки их разделяют: **1** — замер как есть; **2** — те же ответы "
        "(прогоны `"
        + BEFORE_REV
        + "`), оценённые определениями сейчас на наборе до обогащения; **3** — текущий "
        f"код на наборе до обогащения (`git show {PRESWAP_REV}:data/poi.enriched.json`, офлайн, метка "
        f"`{PRESWAP_LABEL}`); **4** — текущий код и набор. Вклад определений = 2 − 1, кода = 3 − 2, данных = "
        "4 − 3. Набор `poi.json` обогащением не менялся (файл тот же), для него различается только код; в "
        "таблицу он не входит. Таблица строится из прогонов и git, вручную не правится.",
        *(["", source_note] if source_note else []),
        "",
        "| набор | метрика | 1 до, как измерено | 2 до, определения сейчас | 3 код сейчас, данные до (2183) "
        "| 4 код и данные сейчас (2314) | вклад определений | вклад кода | вклад данных |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for name, tag in have:
        keys = ABSTAIN_METRICS if tag == "abstain" else METRICS
        two = _summaries_of(tag, rejudged[name]) if rejudged[name] else {}
        for key, title in keys:
            v1 = (frozen[name] or {}).get(key)
            v2 = two.get(key)
            v3 = groups[name][(DATASET, PRESWAP_LABEL)].get(key)
            v4 = groups[name][(DATASET, label)].get(key)
            lines.append(
                f"| {name} ({groups[name][(DATASET, label)]['cases']}) | {title} | {_pct(v1)} | {_pct(v2)} | "
                f"{_pct(v3)} | {_pct(v4)} | {_pp(v1, v2)} | {_pp(v2, v3)} | {_pp(v3, v4)} |"
            )
    now = now_index(DATASET)
    rows: list[str] = []
    for name, tag in have:
        fruns, rruns = before_runs(tag), rejudged[name]
        if fruns is None or rruns is None:
            continue
        detail = {d["case_id"]: d for d in (frozen[name] or {}).get("abstain_detail", [])}
        a_by = {r["case_id"]: r for r in fruns}
        a2_by = {r["case_id"]: r for r in rruns}
        b_by = {r["case_id"]: r for r in load(DATASET, PRESWAP_LABEL, tag)}
        c_by = {r["case_id"]: r for r in load(DATASET, label, tag)}
        for cid, c in c_by.items():
            a, a2, b = a_by.get(cid), a2_by.get(cid), b_by.get(cid)
            if a is None or a2 is None or b is None:
                continue
            s1, s2, s3, s4 = status(a, tag, detail), status(a2, tag), status(b, tag), status(c, tag)
            if s1 == s2 == s3 == s4:
                continue
            why = []
            if s1 != s2:
                why.append("определения")
            if s2 != s3:
                why.append(f"код ({_code_detail(a2, b)})")
            if s3 != s4:
                why.append(f"данные ({_data_detail(b, c, pre_idx, now)})")
            rows.append(
                f"| {name} | `{cid}` | {_cell(s1)} | {_cell(s2)} | {_cell(s3)} | {_cell(s4)} | "
                f"{'; '.join(why)} |"
            )
    lines += [
        "",
        f"Кейсы, у которых результат отличается между четырьмя колонками ({len(rows)}). «Определения» — "
        "отличие колонок 1 и 2 (те же ответы, та же база), «код» — 2 и 3 (одна база и одни определения), "
        "«данные» — 3 и 4 (один код и одни определения).",
        "",
        "| набор | кейс | 1 | 2 | 3 | 4 | причина |",
        "|---|---|---|---|---|---|---|",
        *(rows or ["| — | — | — | — | — | — | различий нет |"]),
    ]
    return lines


def fingerprint(runs_by_set: dict[str, list[dict]]) -> str:
    """A short hash of what the current runs (column 4) say per case: pass / fail, violation codes, recommended
    places. Timings and headers are left out, so a regeneration that changes nothing keeps the hash and a change of
    code, data or definitions moves it."""
    rows = []
    for name in sorted(runs_by_set):
        for r in sorted(runs_by_set[name], key=lambda x: x["case_id"]):
            v = r["verdict"]
            rows.append(
                [
                    name,
                    r["case_id"],
                    v["all_ok"],
                    sorted(v["violations"]),
                    [x["poi_id"] for x in r["recs"]],
                    (r.get("abstain") or {}).get("honest_abstain"),
                ]
            )
    return hashlib.sha256(json.dumps(rows, ensure_ascii=False).encode("utf-8")).hexdigest()[:16]


ATTRIBUTION_FILE = "attribution.md"
FINGERPRINT_RE = re.compile(r"Отпечаток текущих прогонов \(колонка 4\) `([0-9a-f]{16})`")


def build(label: str, directory: Path) -> list[str]:
    """The attribution section, computed now: the current code is re-run on the pre-swap dataset into a temp
    directory (those runs are not kept) and compared with the runs of `directory` and with BEFORE_REV from git.
    Raises FileNotFoundError when the git history it needs is not there."""
    from .report import (  # report imports this module: resolve at call time
        _index,
        load_runs,
        summarize,
    )

    with tempfile.TemporaryDirectory(prefix="eval-preswap-") as tmp:
        tmp_dir = Path(tmp)
        if not refresh_runs(tmp_dir):
            raise FileNotFoundError(
                f"attribution needs git revisions {PRESWAP_REV} (pre-swap dataset) and {BEFORE_REV} (results)"
            )

        def load(_ds: str, lab: str, tag: str) -> list[dict]:
            return load_runs(DATASET, lab, tmp_dir if lab == PRESWAP_LABEL else directory, tag)

        groups: dict[str, dict[tuple[str, str], dict]] = {}
        current: dict[str, list[dict]] = {}
        for name, tag in SETS:
            cases = load_cases(CASE_SETS[tag])
            before, now = load(DATASET, PRESWAP_LABEL, tag), load(DATASET, label, tag)
            if before and now:
                groups[name] = {
                    (DATASET, PRESWAP_LABEL): summarize(before, cases),
                    (DATASET, label): summarize(now, cases),
                }
                current[name] = now
        note = (
            f"Источник: git `{sha_text(git_state())}`, {datetime.now():%d.%m.%Y %H:%M}. Раздел считается отдельной "
            "командой `cd app && uv run poe eval-attribution` (ей нужна git-история с коммитами "
            f"`{BEFORE_REV}` и `{PRESWAP_REV}`); обычный `poe eval` его не пересчитывает, а вставляет этот файл "
            f"как есть. Отпечаток текущих прогонов (колонка 4) `{fingerprint(current)}`: если прогоны изменятся, "
            "`canonical.md` пометит раздел устаревшим."
        )
        lines = section(groups, label, load, _index, source_note=note)
    if not lines:
        raise FileNotFoundError(
            "attribution: no case set has both the pre-swap and the current runs"
        )
    return lines


def write(label: str, directory: Path) -> Path:
    """Compute the section and write it to `<directory>/attribution.md` (committed: it is what canonical.md
    embeds when the git history is not there)."""
    path = directory / ATTRIBUTION_FILE
    path.write_text(
        "\n".join(build(label, directory)).lstrip("\n") + "\n", encoding="utf-8", newline="\n"
    )
    return path
