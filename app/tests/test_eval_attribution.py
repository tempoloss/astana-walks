"""Attribution of the data swap (definitions / code / data) and the dated glossary of metric definitions."""

from __future__ import annotations

import json
import shutil
from datetime import datetime

import pytest

from eval import attribution as at
from eval import metrics, report
from eval.cases import DATA_DIR
from eval.run_eval import main as run_eval_main
from walks.holidays import holiday_name
from walks.hours import poi_hours
from walks.models import POI, load_pois


def _git_has_the_preswap_dataset() -> bool:
    try:
        at.data_at_rev(at.PRESWAP_REV, "poi.enriched.json")
    except FileNotFoundError:
        return False
    return True


needs_git = pytest.mark.skipif(
    not _git_has_the_preswap_dataset(),
    reason="git history of the pre-swap revision is not available",
)

# ---------------------------------------------------------------- the pre-swap dataset and run_eval --data-rev


@needs_git
def test_the_preswap_dataset_is_the_2183_place_build_and_the_current_one_is_larger():
    index = at.preswap_index("poi.enriched")
    assert index is not None
    assert len(index) == 2183
    assert len(load_pois(DATA_DIR / "poi.enriched.json")) > 2183
    # the OSM-only baseline is not touched by the swap
    assert at.data_at_rev(at.PRESWAP_REV, "poi.json").read_bytes().replace(b"\r\n", b"\n") == (
        DATA_DIR / "poi.json"
    ).read_bytes().replace(b"\r\n", b"\n")


@needs_git
def test_run_eval_data_rev_runs_on_the_dataset_of_the_revision(tmp_path, monkeypatch):
    for key in ("WALKS_OFFLINE", "WALKS_REQUEST_LOG", "WALKS_LLM_CACHE"):
        monkeypatch.setenv(key, "")
    out = tmp_path / "runs_poi.enriched_preswap.jsonl"
    argv = ["--data", "../data/poi.enriched.json", "--mode", "offline", "--limit", "1"]
    assert run_eval_main([*argv, "--data-rev", at.PRESWAP_REV, "--out", str(out)]) == 0
    lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    head = lines[0]["_header"]
    assert head["label"] == "preswap"
    assert head["dataset"] == "poi.enriched"
    assert head["data_path"] == f"git:{at.PRESWAP_REV}:data/poi.enriched.json"
    pre = at.preswap_index("poi.enriched")
    assert all(rec["poi_id"] in pre for rec in lines[1]["recs"])


def test_run_eval_data_rev_rejects_an_unknown_revision(tmp_path):
    argv = ["--data", "../data/poi.enriched.json", "--mode", "offline", "--limit", "1"]
    with pytest.raises(SystemExit):
        run_eval_main([*argv, "--data-rev", "0000000deadbeef", "--out", str(tmp_path / "x.jsonl")])


# ---------------------------------------------------------------- statuses and the section


def _poi(pid: str, name: str = "N", **kw) -> POI:
    return POI(id=pid, name=name, lat=51.1, lon=71.4, category="cafe", **kw)


def _run(cid: str, ids: list[str], ok: bool, codes: tuple[str, ...] = ()) -> dict:
    return {
        "case_id": cid,
        "recs": [{"poi_id": i, "name": f"N{i}", "category": "cafe"} for i in ids],
        "verdict": {"all_ok": ok, "violations": list(codes)},
    }


def test_status_of_an_abstention_case_is_its_honest_abstain_not_all_ok():
    honest = {
        "case_id": "a",
        "recs": [],
        "abstain": {"honest_abstain": True, "silent_mismatches": {}},
    }
    assert at.status(honest, "abstain") == at.Status(True, ())
    silent = {
        "case_id": "a",
        "recs": [],
        "abstain": {"honest_abstain": False, "silent_mismatches": {"p": ["hours_unlabeled"]}},
    }
    assert at.status(silent, "abstain") == at.Status(False, ("hours_unlabeled",))
    # a frozen run has no stored abstain verdict: the summary's detail is read instead
    frozen = {"case_id": "a", "recs": []}
    detail = {"a": {"silent": {"p": ["wifi_unlabeled", "hours_unlabeled"]}}}
    assert at.status(frozen, "abstain", detail) == at.Status(
        False, ("hours_unlabeled", "wifi_unlabeled")
    )
    assert at.status(_run("c", ["a"], False, ("walk_too_long",)), "") == at.Status(
        False, ("walk_too_long",)
    )


def _groups(label: str = "offline") -> dict:
    def s(v: float) -> dict:
        return {"cases": 4, "case_all_ok_rate": v, "constraint_ok_rate": v, "coverage": v}

    return {"holdout": {(at.DATASET, at.PRESWAP_LABEL): s(75.0), (at.DATASET, label): s(50.0)}}


def test_section_names_which_cases_differ_and_whether_definitions_code_or_data(monkeypatch):
    pre = {"a": _poi("a", "A"), "b": _poi("b", "B")}
    now = {**pre, "new": _poi("new", "Nnew")}
    monkeypatch.setattr(at, "preswap_index", lambda _d: pre)
    monkeypatch.setattr(
        at,
        "before_summary",
        lambda _t: {"case_all_ok_rate": 50.0, "constraint_ok_rate": 60.0, "coverage": 70.0},
    )
    before = [
        _run("c-code", ["a"], False, ("category_not_allowed",)),
        _run("c-data", ["a"], True),
        _run("c-def", ["a"], False, ("open_on_holiday",)),
        _run("c-same", ["a"], True),
    ]
    rejudged = [
        _run("c-code", ["a"], False, ("category_not_allowed",)),
        _run("c-data", ["a"], True),
        _run("c-def", ["a"], True),  # today's definition accepts it
        _run("c-same", ["a"], True),
    ]
    preswap = [
        _run("c-code", ["b"], True),  # the code changed the answer
        _run("c-data", ["a"], True),
        _run("c-def", ["a"], True),
        _run("c-same", ["a"], True),
    ]
    current = [
        _run("c-code", ["b"], True),
        _run("c-data", ["a", "new"], False, ("walk_too_long",)),  # a new place entered the answer
        _run("c-def", ["a"], True),
        _run("c-same", ["a"], True),
    ]
    monkeypatch.setattr(at, "before_runs", lambda _t: [dict(r) for r in before])
    monkeypatch.setattr(at, "rejudged_before", lambda _t: rejudged)
    monkeypatch.setattr(
        at,
        "_summaries_of",
        lambda _t, _r: {"case_all_ok_rate": 50.0, "constraint_ok_rate": 60.0, "coverage": 70.0},
    )
    loaded = {at.PRESWAP_LABEL: preswap, "offline": current}
    lines = at.section(_groups(), "offline", lambda _d, lab, _t: loaded[lab], lambda _d: now)
    text = "\n".join(lines)
    assert "## Атрибуция: что изменили определения, код и данные" in text
    row = {cid: next(x for x in lines if f"`{cid}`" in x) for cid in ("c-code", "c-data", "c-def")}
    assert "код (top-1: Na → Nb)" in row["c-code"]
    assert "данные (новое место «Nnew»)" in row["c-data"]
    assert row["c-def"].rstrip().endswith("| определения |")
    assert not any("`c-same`" in x for x in lines)
    assert "(3)" in text  # three cases differ
    # aggregates: 50 -> 50 -> 75 -> 50: no effect of definitions, +25 of code, -25 of data
    agg = next(x for x in lines if x.startswith("| holdout (4) | кейсов без нарушений"))
    assert "| +0.0 п.п. | +25.0 п.п. | -25.0 п.п. |" in agg


def test_section_is_empty_without_the_preswap_runs():
    assert at.section({"holdout": {}}, "offline", lambda *_a: [], lambda _d: {}) == []


# ---------------------------------------------------------------- the dated glossary


def test_canonical_carries_the_glossary_and_the_frozen_baseline_clause(tmp_path):
    text = report.canonical_md({"main": {}}, "offline", "abc1234", tmp_path)
    assert "## Определения метрик: что менялось и когда" in text
    for date_, _term, _txt in report.GLOSSARY:
        assert f"| {date_} |" in text
    assert "`open_on_holiday`" in text
    assert "`poi_hours`" in text
    assert report.FROZEN_CLAUSE in text
    for sha in ("d5e4b05", "4c7f45c", "2183"):
        assert sha in report.FROZEN_CLAUSE


def test_the_glossary_states_what_the_code_does():
    # `poi_hours`: a conflict explains an unknown state; split (one source open, the other closed) is unknown
    assert set(metrics.CONFLICT.values()) <= set(metrics.UNKNOWN_HOURS_LABELS)
    when = datetime(2026, 10, 21, 12, 0)  # a Wednesday, not a holiday
    assert holiday_name(when.date()) is None
    split = _poi(
        "s",
        opening_hours="Mo-Su 09:00-21:00",
        opening_hours_official="Mo-Su 13:00-14:00",
        hours_conflict=True,
    )
    got = poi_hours(split, when)
    assert (got.state, got.issue) == ("unknown", "split")
    # open_on_holiday: «24/7» may stay open with the holiday caveat; any other hours may not
    holiday = datetime(2027, 1, 1, 12, 0)
    assert holiday_name(holiday.date())
    caveat = metrics.HOLIDAY_LABEL
    rec = {"hours_state": "open", "why": "", "what_to_do": "", "notes": caveat}

    def codes(poi: POI, notes: str) -> list[str]:
        return metrics._honesty({**rec, "notes": notes}, poi, {}, holiday)

    assert metrics.OPEN_ON_HOLIDAY not in codes(_poi("a", opening_hours="24/7"), caveat)
    assert metrics.OPEN_ON_HOLIDAY in codes(_poi("a", opening_hours="24/7"), "")  # no caveat
    assert metrics.OPEN_ON_HOLIDAY in codes(_poi("a", opening_hours="Mo-Su 09:00-21:00"), caveat)
    assert all(d == "17.10.2026" for d, _t, _x in report.GLOSSARY)


# ---------------------------------------------------------------- the committed artifact and its embedding


def test_fingerprint_follows_verdicts_and_places_not_timings():
    run = _run("c1", ["a"], True)
    base = at.fingerprint({"main": [run]})
    assert len(base) == 16
    assert at.fingerprint({"main": [{**run, "timings": {"total": 999}}]}) == base
    assert at.fingerprint({"main": [_run("c1", ["a"], False, ("walk_too_long",))]}) != base
    assert at.fingerprint({"main": [_run("c1", ["b"], True)]}) != base


def _results_copy(tmp_path):
    """The current offline runs of the real results directory, copied (the attribution reads them)."""
    for name in (
        "runs_poi.enriched_offline.jsonl",
        "runs_poi.enriched_holdout_offline.jsonl",
        "runs_poi.enriched_holdout2_offline.jsonl",
        "runs_poi.enriched_holdout3_offline.jsonl",
        "runs_poi.enriched_abstain_offline.jsonl",
    ):
        shutil.copy(report.RESULTS_DIR / name, tmp_path / name)
    return tmp_path


@needs_git
def test_attribution_is_written_once_and_canonical_embeds_it_without_git(tmp_path, monkeypatch):
    directory = _results_copy(tmp_path)
    path = at.write("offline", directory)
    assert path == directory / "attribution.md"
    text = path.read_text(encoding="utf-8")
    assert text.startswith("## Атрибуция: что изменили определения, код и данные")
    assert "Источник: git `" in text
    assert "poe eval-attribution" in text
    assert "\r" not in text
    fp = at.FINGERPRINT_RE.search(text)
    assert fp
    for name in (
        "preswap",
    ):  # the pre-swap runs are temporary: nothing is left in the results directory
        assert not list(directory.glob(f"*{name}*"))

    groups = {name: report.write_summaries(directory, tag=tag) for name, tag in at.SETS}
    # without any git history (squashed repository) the embedded file is all that is left of the section
    monkeypatch.setattr(at, "_git_show", lambda *_a, **_k: None)
    at.preswap_index.cache_clear()
    at._materialized.clear()
    try:
        canonical = report.canonical_md(groups, "offline", "abc1234", directory)
    finally:
        monkeypatch.undo()
        at.preswap_index.cache_clear()  # do not leave the «no history» answer cached for other tests
        at._materialized.clear()
    assert text.rstrip("\n") in canonical
    assert "Раздел устарел" not in canonical  # the runs are the ones the file was computed against
    assert report.FROZEN_WITH in canonical
    assert report.FROZEN_WITHOUT not in canonical


def test_canonical_marks_a_stale_attribution_and_works_without_the_file(tmp_path):
    directory = _results_copy(tmp_path)
    groups = {name: report.write_summaries(directory, tag=tag) for name, tag in at.SETS}
    bare = report.canonical_md(groups, "offline", "abc1234", directory)
    assert "## Атрибуция" not in bare
    assert report.FROZEN_WITHOUT in bare
    assert "poe eval-attribution" in bare
    (directory / "attribution.md").write_text(
        "## Атрибуция: проба\n\nИсточник: git `abc1234`, 17.10.2026 16:00. "
        "Отпечаток текущих прогонов (колонка 4) `0123456789abcdef`: если прогоны изменятся, раздел устареет.\n",
        encoding="utf-8",
    )
    stale = report.canonical_md(groups, "offline", "abc1234", directory)
    assert "## Атрибуция: проба" in stale
    assert "Источник: git `abc1234`, 17.10.2026 16:00." in stale
    assert "Раздел устарел" in stale
    assert report.FROZEN_WITH in stale


def test_report_attribution_flag_fails_cleanly_without_the_git_history(monkeypatch, capsys):
    def no_history(_label, _directory):
        raise FileNotFoundError("attribution needs git revisions")

    monkeypatch.setattr(at, "write", no_history)
    assert report.main(["--attribution"]) == 1
    assert "attribution needs git revisions" in capsys.readouterr().out
