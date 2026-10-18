"""Loader for the eval case sets (cases.json, holdout_cases.json, abstain_cases.json), the weather/air conditions
a case injects into the pipeline, and the provenance header every runs file starts with."""

from __future__ import annotations

import json
import re
import subprocess
from datetime import datetime
from pathlib import Path

from walks.models import WeatherInfo
from walks.weather import manual_weather

EVAL_DIR = Path(__file__).resolve().parent
CASES_PATH = EVAL_DIR / "cases.json"
HOLDOUT_PATH = EVAL_DIR / "holdout_cases.json"
HOLDOUT2_PATH = (
    EVAL_DIR / "holdout2_cases.json"
)  # blind set: written by another model without code access; frozen at d5e4b05, not blind after the fixes
HOLDOUT3_PATH = (
    EVAL_DIR / "holdout3_cases.json"
)  # written after those fixes from eval/SCHEMA.md only (author blind-glm-v2)
ABSTAIN_PATH = EVAL_DIR / "abstain_cases.json"
RESULTS_DIR = EVAL_DIR / "results"
DOCS_SCENARIOS = EVAL_DIR.parents[1] / "docs" / "scenarios.md"
DATA_DIR = EVAL_DIR.parents[1] / "data"

# "Normal" conditions of a case without overrides: mild autumn day, clean air. Always injected (even offline)
# so that every run sees the same weather and the same sunset computation, never a live Open-Meteo answer.
NORMAL_APPARENT_C = 8.0
NORMAL_PRECIP_MM = 0.0
NORMAL_PM25 = 12.0

AXES = {
    "origin": ["expo", "msw", "baiterek", "khan", "lrt", "left"],
    "when": ["wk14", "eve", "night", "hol"],
    "weather": ["normal", "cold", "smog"],
    "persona": ["tourist", "kids", "quiet", "night", "walk", "mobility"],
}


# case set tag -> file; the tag names the results of a set (runs_<dataset>_<tag>_<label>.jsonl), "" is the main set
CASE_SETS = {
    "": CASES_PATH,
    "holdout": HOLDOUT_PATH,
    "holdout2": HOLDOUT2_PATH,
    "holdout3": HOLDOUT3_PATH,
    "abstain": ABSTAIN_PATH,
}
REPO_ROOT = EVAL_DIR.parents[1]
HEADER_KEY = (
    "_header"  # the first line of a runs file: {"_header": {...}}; every other line is one case run
)
LABEL_RE = re.compile(
    r"[A-Za-z0-9-]+"
)  # no "_": the label is the last `_`-token of a runs file name


def case_set_tag(path: Path) -> str:
    """Tag of a cases file in the results names: "" for the main set, else the file stem without `_cases`."""
    path = path.resolve()
    return "" if path == CASES_PATH else path.stem.removesuffix("_cases")


def runs_name(dataset: str, label: str, tag: str = "") -> str:
    """File name of one run: runs_<dataset>[_<tag>]_<label>.jsonl. The label is the run's name; for a run
    without --label it is the mode (offline / llm)."""
    return f"runs_{dataset}_{tag}_{label}.jsonl" if tag else f"runs_{dataset}_{label}.jsonl"


def label_from_filename(path: Path) -> str:
    """Label of a runs file written before headers existed: the last `_`-token of its stem."""
    return path.stem.rpartition("_")[2]


# What decides the numbers: the pipeline, the eval harness with its case files, the datasets and their collectors.
# Results (eval/results) change with every run and are not part of it, so a run's header is attributable to a
# commit and `poe eval` writes the same text twice in a row on one tree.
PROVENANCE_PATHS = (
    "app/walks",
    "app/eval",
    "data",
    "collect",
    ":(exclude)app/eval/results",
)


def git_state() -> dict:
    """{"sha": short sha of the last commit touching PROVENANCE_PATHS, "dirty": bool: uncommitted changes in those
    paths only}. sha "unknown" outside a git checkout."""

    def git(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=REPO_ROOT, capture_output=True, text=True, check=True, timeout=20
        ).stdout.strip()

    try:
        sha = git("log", "-1", "--format=%h", "--", *PROVENANCE_PATHS)
        dirty = bool(git("status", "--porcelain", "--", *PROVENANCE_PATHS))
    except (OSError, subprocess.SubprocessError):
        return {"sha": "unknown", "dirty": False}
    return {"sha": sha or "unknown", "dirty": dirty}


def sha_text(state: dict) -> str:
    return state["sha"] + ("+uncommitted" if state["dirty"] else "")


def read_header(path: Path) -> dict:
    """Header of a runs file; for a file without one (older run) only what the file name gives, flagged legacy."""
    with path.open(encoding="utf-8") as fh:
        first = fh.readline()
    if first:
        head = json.loads(first).get(HEADER_KEY)
        if head:
            return head
    return {"label": label_from_filename(path), "legacy": True}


def load_cases(path: Path = CASES_PATH) -> list[dict]:
    return json.loads(path.read_text(encoding="utf-8"))


def conditions(case: dict) -> tuple[float, float, float]:
    """(apparent °C, precipitation mm/h, PM2.5) of the case after applying its overrides."""
    wo = case.get("weather_override") or {}
    ao = case.get("air_override") or {}
    return (
        float(wo.get("apparent_c", NORMAL_APPARENT_C)),
        float(wo.get("precip_mm", NORMAL_PRECIP_MM)),
        float(ao.get("pm25", NORMAL_PM25)),
    )


def case_weather(case: dict) -> WeatherInfo:
    apparent, precip, pm25 = conditions(case)
    return manual_weather(apparent, precip, pm25=pm25)


def case_when(case: dict) -> datetime:
    return datetime.fromisoformat(case["when"])


def indoor_required(case: dict) -> bool:
    """True when the conditions are cold / heavy-precipitation / smoggy enough that outdoor places must not be
    recommended (the same thresholds as walks.weather)."""
    return case_weather(case).indoor_preferred


def describe_conditions(case: dict) -> str:
    apparent, precip, pm25 = conditions(case)
    return f"ощущается {apparent:.0f}°C, осадки {precip:g} мм/ч, PM2.5 {pm25:.0f}"
