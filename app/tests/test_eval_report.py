"""The report layer of the evaluation harness: provenance sha, «н/п» for LLM-only metrics of an offline run, the
historical stress run kept apart from the current numbers, and the AI-mode text of docs/scenarios.md."""

from __future__ import annotations

import json
import subprocess

import pytest

from eval import cases, metrics, report, scenarios
from eval.cases import git_state, load_cases, sha_text
from eval.report import canonical_md, metric_rows, write_summaries
from walks.models import POI


def _git(root, *args: str) -> str:
    return subprocess.run(
        ["git", *args], cwd=root, capture_output=True, text=True, check=True
    ).stdout.strip()


# ---------------------------------------------------------------- provenance


def test_git_state_is_the_last_commit_of_the_deciding_paths_and_their_dirt(tmp_path, monkeypatch):
    root = tmp_path
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "t@example.com")
    _git(root, "config", "user.name", "t")
    (root / "app" / "walks").mkdir(parents=True)
    (root / "app" / "eval" / "results").mkdir(parents=True)
    (root / "docs").mkdir()
    (root / "app" / "walks" / "a.py").write_text("x = 1\n", encoding="utf-8")
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "walks")
    deciding = _git(root, "rev-parse", "--short", "HEAD")
    monkeypatch.setattr(cases, "REPO_ROOT", root)
    assert git_state() == {"sha": deciding, "dirty": False}

    # results and docs change with every run: neither the sha nor the dirty flag follows them
    (root / "app" / "eval" / "results" / "canonical.md").write_text("1", encoding="utf-8")
    (root / "docs" / "scenarios.md").write_text("1", encoding="utf-8")
    assert git_state() == {"sha": deciding, "dirty": False}
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", "results")
    assert git_state() == {"sha": deciding, "dirty": False}  # a results commit is not a new sha

    (root / "app" / "walks" / "a.py").write_text("x = 2\n", encoding="utf-8")
    assert git_state() == {"sha": deciding, "dirty": True}
    assert sha_text(git_state()) == f"{deciding}+uncommitted"
    _git(root, "commit", "-qam", "walks 2")
    assert git_state() == {"sha": _git(root, "rev-parse", "--short", "HEAD"), "dirty": False}


def test_git_state_outside_a_checkout_is_unknown(tmp_path, monkeypatch):
    monkeypatch.setattr(cases, "REPO_ROOT", tmp_path / "missing")
    assert git_state() == {"sha": "unknown", "dirty": False}


# ---------------------------------------------------------------- offline cells


def _summary(mode: str, **kw) -> dict:
    return {
        "mode": mode,
        "llm_chain_failed": 0,
        "llm_invalid_answers": 0,
        "latency_ms_median": 7.0,
        "latency_ms_p90": 9.0,
        "generation_ms_median": 1.0,
        "generation_ms_p90": 2.0,
        **kw,
    }


def _rows(summaries: list[dict]) -> dict[str, list[str]]:
    return dict(metric_rows(summaries))


def test_offline_llm_metrics_are_not_applicable_and_latency_says_template():
    rows = _rows([_summary("offline")])
    assert rows["кейсов, где вся цепочка ИИ недоступна (→ шаблон)"] == ["н/п"]
    assert rows["кейсов, где ответ ИИ не прошёл проверку poi_id (→ шаблон)"] == ["н/п"]
    assert rows["latency ответа ИИ, медиана"] == ["н/п"]
    assert rows["latency ответа ИИ, p90"] == ["н/п"]
    assert rows["latency пайплайна, медиана (шаблон, без ИИ)"] == ["7 мс"]
    assert rows["latency пайплайна, p90 (шаблон, без ИИ)"] == ["9 мс"]


def test_llm_runs_keep_their_numbers_and_a_mixed_table_tags_the_offline_cell():
    rows = _rows([_summary("llm", llm_chain_failed=4, latency_ms_median=900.0)])
    assert rows["кейсов, где вся цепочка ИИ недоступна (→ шаблон)"] == ["4"]
    assert rows["latency пайплайна, медиана"] == ["900 мс"]
    mixed = _rows([_summary("offline"), _summary("llm", latency_ms_median=900.0)])
    assert mixed["latency пайплайна, медиана"] == ["7 мс (шаблон)", "900 мс"]
    assert mixed["latency ответа ИИ, медиана"] == ["н/п", "1 мс"]


# ---------------------------------------------------------------- canonical.md


def _fake_run(case_id: str, dataset: str, mode: str, link: str, note: str, rec: dict) -> dict:
    by_ai = link != "template"
    return {
        "case_id": case_id,
        "dataset": dataset,
        "mode": mode,
        "model_link": link,
        "generation": "llm" if by_ai else "template",
        "generation_note": note,
        "intent": {
            "parser": "rules+llm" if by_ai else "rules",
            "model": "gemini:i" if by_ai else None,
        },
        "chain": ["gemini:gemma-x"] if mode == "llm" else [],
        "recs": [rec],
        "route": None,
        "timings": {"total": 30000, "generation": 25000},
        "verdict": {},  # recomputed on load
    }


@pytest.fixture
def results(tmp_path, monkeypatch):
    poi = POI(id="a", name="Cafe X", lat=51.1, lon=71.4, category="cafe", hours="24/7")
    rec = {
        "poi_id": "a",
        "name": "Cafe X",
        "category": "cafe",
        "source": "osm",
        "hours_state": "open",
        "hours_raw": "24/7",
        "hours_note": "",
        "walk_min": 5,
        "distance_m": 300,
        "method": "straight",
        "confidence": "medium",
        "text_source": "template",
        "why": "",
        "what_to_do": "",
        "notes": "",
        "padding": "none",
    }
    monkeypatch.setattr(report, "_index", lambda _ds: metrics.dataset_index([poi]))
    case_ids = [c["id"] for c in load_cases()[:5]]
    down = "ошибка ИИ: все звенья цепочки недоступны: gemini:m: 429 (0.4 с)"
    for ds in ("poi", "poi.enriched"):
        lines = [
            _fake_run(c, ds, "offline", "template", "офлайн-режим (WALKS_OFFLINE)", rec)
            for c in case_ids
        ]
        (tmp_path / f"runs_{ds}_offline.jsonl").write_text(
            "\n".join(json.dumps(x) for x in lines) + "\n", encoding="utf-8"
        )
        # a historical run keeps the verdict of its day, even when its place no longer exists in the dataset
        gone = {**rec, "poi_id": "gone-since-then"}
        stored = {
            "n_recs": 1,
            "hallucinated": [],
            "constraint_violations": {},
            "honesty_violations": {},
            "ok_recs": 1,
            "over_budget": False,
            "duplicate_chains": [],
            "coverage_ok": True,
            "honest_ok": True,
            "all_ok": True,
            "route_closed_stops": [],
            "wifi_socket_in_data": 0,
            "violations": [],
        }
        stress = [
            {**_fake_run(c, ds, "llm", "template", down, gone), "verdict": stored}
            for c in case_ids[:4]
        ]
        stress.append(
            {**_fake_run(case_ids[4], ds, "llm", "gemini:gemma-x", "", gone), "verdict": stored}
        )
        (tmp_path / f"runs_{ds}_llm-gemini-only.jsonl").write_text(
            "\n".join(json.dumps(x) for x in stress) + "\n", encoding="utf-8"
        )
    return tmp_path


def test_canonical_prints_na_for_offline_and_keeps_the_stress_run_apart(results):
    main = write_summaries(results)
    text = canonical_md({"main": main}, "offline", "abc1234")
    table = text.split("## Метрики")[1].split("##")[0]
    assert "| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п | н/п |" in table
    assert "| latency ответа ИИ, медиана | н/п | н/п |" in table
    assert "latency пайплайна, медиана (шаблон, без ИИ) | 30000 мс | 30000 мс |" in table
    assert "llm-gemini-only" not in table  # never a column of the current numbers
    stress = text.split("## Исторический стресс-прогон ИИ")[1]
    assert "16.10.2026" in stress.splitlines()[0]
    assert "4 из 5" in stress
    assert "| hallucinated_poi | 0 | 0 |" in stress
    assert "`gemini:gemma-x`" in stress
    assert "git `abc1234`" in text
    assert "ИИ-режим в таблицу не входит" in text


def test_summaries_of_the_stress_run_are_marked_historical(results):
    write_summaries(results)
    for name in ("summary_poi_llm-gemini-only.md", "comparison_llm-gemini-only.md"):
        assert "Исторический прогон 16.10.2026" in (results / name).read_text(encoding="utf-8")
    offline = (results / "summary_poi_offline.md").read_text(encoding="utf-8")
    assert "Исторический" not in offline
    assert "| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п |" in offline
    cmp_offline = (results / "comparison_offline.md").read_text(encoding="utf-8")
    assert "| кейсов, где вся цепочка ИИ недоступна (→ шаблон) | н/п | н/п | н/п |" in cmp_offline


def test_ai_section_counts_only_model_answers_and_never_the_template(results):
    template_link, link = "template", "gemini:gemma-x"
    case_ids = [c["id"] for c in load_cases()[:3]]
    rec = json.loads(
        (results / "runs_poi.enriched_offline.jsonl").read_text("utf-8").splitlines()[0]
    )["recs"][0]
    runs = [
        _fake_run(case_ids[0], "poi.enriched", "llm", link, "", rec),
        _fake_run(case_ids[1], "poi.enriched", "llm", link, "", rec),
        _fake_run(case_ids[2], "poi.enriched", "llm", template_link, "ошибка ИИ: 429", rec),
    ]
    header = {
        "_header": {
            "label": "llm-public",
            "mode": "llm",
            "records": 3,
            "data_path": "data/poi.enriched.json",
            "git": "abc1234",
            "generated_at": "2026-10-17T05:00:00+05:00",
        }
    }
    (results / "runs_poi.enriched_llm-public.jsonl").write_text(
        "\n".join(json.dumps(x) for x in [header, *runs]) + "\n", encoding="utf-8"
    )
    main = write_summaries(results)
    text = canonical_md({"main": main}, "offline", "abc1234")
    section = text.split("## ИИ-режим (")[1].split("\n## ")[0]
    assert section.startswith("публичные модели Gemini, 3 кейсов, 17.10.2026)")
    assert "**Ответил ИИ: 2 из 3 (67%)**" in section
    assert "ответил шаблон" in section
    assert "| `gemini:gemma-x` | 2 |" in section
    assert "| шаблон (ИИ не ответил) | 1 |" in section
    assert "ИИ-режим в основную таблицу не входит" in text
    row = next(x for x in section.splitlines() if case_ids[2] in x)
    assert "| шаблон |" in row
    assert "| н/п | н/п | н/п |" in row  # the template's text is not checked as AI
    assert "Ответил ИИ: 3" not in section
    # a run whose chain has a non-Google link gets no «публичные модели» section at all
    s = main[("poi.enriched", "llm-public")]
    s["chain"] = ["gemini:a", "резервная модель (частный профиль)"]
    assert "## ИИ-режим (" not in canonical_md({"main": main}, "offline", "abc1234")


# ---------------------------------------------------------------- docs/scenarios.md


def test_scenarios_have_no_ai_columns_when_only_historical_or_private_runs_exist(results):
    main = write_summaries(results)
    sums = {(ds, m): s for (ds, m), s in main.items()}
    assert scenarios._summary_columns(sums) == [("poi", "offline"), ("poi.enriched", "offline")]
    assert scenarios._ai_mode_lines(sums) == ["ИИ-режим измерен отдельно."]
    private = {**sums[("poi", "offline")], "model_link": {"резервная модель (частный профиль)": 5}}
    assert not scenarios._public_ai_run("llm", private)
    public = {**sums[("poi", "offline")], "model_link": {"gemini:m": 4, "template": 1}}
    assert scenarios._public_ai_run("llm", public)
    assert not scenarios._public_ai_run("llm-gemini-only", public)


def test_scenarios_show_an_ai_answer_only_from_a_google_link():
    assert scenarios._google_answer({"model_link": "gemini:gemma-x"})
    assert not scenarios._google_answer({"model_link": "template"})
    assert not scenarios._google_answer({"model_link": "резервная модель (частный профиль)"})


# ---------------------------------------------------------------- intent comparison output


def test_intent_compare_render_says_what_was_not_asked():
    from eval.intent_compare import TITLE, render

    row = {
        "case_id": "c1",
        "set": "main",
        "query": "запрос",
        "measured": True,
        "counted": True,
        "used": "gemini:m",
        "cached": False,
        "rule_categories": ["cafe"],
        "added_categories": [],
        "added_flags": [],
        "rule_gaps": [],
        "merged_gaps": [],
        "fixed": False,
        "partial": False,
        "worse": [],
    }
    text = render({"rows": [row], "stopped": "лимит", "left": 5}, "заголовок")
    assert text.startswith(f"# {TITLE}\n")
    assert TITLE == "Дополнительная польза ИИ при маппинге категорий поверх словаря"
    assert "main 1, holdout 0, abstain 0" in text
    assert "- Только holdout: не опрошен" in text
    assert "не опрошено после остановки: 5" in text


# ---------------------------------------------------------------- labels in the three answer languages


@pytest.mark.parametrize("lang", [1, 2, 0])  # index into walks.i18n entries: ru, en, kk
def test_compromise_and_unverified_labels_are_read_in_every_answer_language(lang):
    from walks.i18n import STRINGS

    def s(key: str) -> str:
        return STRINGS[key][lang]

    rec = {
        "why": "",
        "what_to_do": "",
        "notes": " ".join(
            [
                s("note_hours_unknown"),
                s("note_off_category"),
                s("note_wifi"),
                s("note_wheelchair"),
                s("note_tight").format(lo=30, left=24),
                s("note_expanded"),
            ]
        ),
    }
    assert {"off_category", "tight_fit", "expanded_radius"} <= set(metrics.compromise_labels(rec))
    notes = rec["notes"]
    assert any(
        x in notes
        for x in (
            metrics.UNKNOWN_HOURS_LABEL,
            metrics.UNKNOWN_HOURS_LABEL_EN,
            metrics.UNKNOWN_HOURS_LABEL_KK,
        )
    )
    assert any(
        x in notes
        for x in (metrics.WIFI_NEGATIVE_LABEL, metrics.WIFI_NEGATIVE_LABEL_KK, "not confirmed")
    )
    assert any(
        x in notes
        for x in (
            metrics.WHEELCHAIR_LABEL,
            metrics.WHEELCHAIR_LABEL_EN,
            metrics.WHEELCHAIR_LABEL_KK,
        )
    )
    assert any(x in s("budget_over") for x in metrics.OVER_BUDGET_LABELS)


def test_ai_section_shows_before_and_after_of_a_fix_from_the_kept_run(results):
    case_ids = [c["id"] for c in load_cases()[:2]]
    rec = json.loads(
        (results / "runs_poi.enriched_offline.jsonl").read_text("utf-8").splitlines()[0]
    )["recs"][0]
    bad = {**rec, "category": "bar_nightlife"}  # outside what the case allows
    for label, recs in (("llm-public-before", [bad, bad]), ("llm-public", [rec, rec])):
        runs = [
            {
                **_fake_run(c, "poi.enriched", "llm", "gemini:gemma-x", "", r),
                "chain": ["gemini:gemma-x"],
            }
            for c, r in zip(case_ids, recs, strict=True)
        ]
        header = {
            "_header": {
                "label": label,
                "mode": "llm",
                "records": 2,
                "data_path": "data/poi.enriched.json",
                "git": "abc1234",
                "generated_at": "2026-10-17T05:00:00+05:00",
            }
        }
        (results / f"runs_poi.enriched_{label}.jsonl").write_text(
            "\n".join(json.dumps(x) for x in [header, *runs]) + "\n", encoding="utf-8"
        )
    main = write_summaries(results)
    assert ("poi.enriched", "llm-public-before") in main
    text = canonical_md({"main": main}, "offline", "abc1234")
    after = text.split("### До и после исправления разбора намерения")[1].split("\n## ")[0]
    assert "846f5fa" in after
    assert "Ответил ИИ (текст): было 2, стало 2 из 2." in after
    assert "Cafe X (bar_nightlife)" in after  # top-1 before
    assert "Cafe X (cafe)" in after  # top-1 after
    # the kept run is not a column of the summary table of docs/scenarios.md
    assert ("poi.enriched", "llm-public-before") not in scenarios._summary_columns(main)


# ---------------------------------------------------------------- the blind set holdout2


def test_holdout2_is_registered_and_its_provenance_is_read_from_the_cases():
    from eval.cases import CASE_SETS, HOLDOUT2_PATH
    from eval.report import _holdout_provenance

    assert CASE_SETS["holdout2"] == HOLDOUT2_PATH
    cases = load_cases(HOLDOUT2_PATH)
    assert len(cases) == 24
    assert all(c["id"].startswith("h2-") for c in cases)
    line = _holdout_provenance("holdout2", "1d153eb")
    assert f"{len(cases)} кейсов" in line
    assert "без доступа к коду" in line
    assert "1d153eb" in line


def test_canonical_has_holdout2_columns_and_the_budget_note(results):
    from eval.cases import HOLDOUT2_PATH

    case_ids = [c["id"] for c in load_cases(HOLDOUT2_PATH)[:2]]
    rec = json.loads(
        (results / "runs_poi.enriched_offline.jsonl").read_text("utf-8").splitlines()[0]
    )["recs"][0]
    for ds in ("poi", "poi.enriched"):
        runs = [_fake_run(c, ds, "offline", "template", "офлайн-режим", rec) for c in case_ids]
        (results / f"runs_{ds}_holdout2_offline.jsonl").write_text(
            "\n".join(json.dumps(x) for x in runs) + "\n", encoding="utf-8"
        )
    main = write_summaries(results)
    h2 = write_summaries(results, tag="holdout2")
    assert set(h2) == {("poi", "offline"), ("poi.enriched", "offline")}
    assert not any("holdout2" in str(k) for k in main)  # a set's runs are not read into another set
    text = canonical_md({"main": main, "holdout2": h2}, "offline", "abc1234")
    assert "poi / holdout2 (2)" in text
    assert "poi.enriched / holdout2 (2)" in text
    assert "**holdout2** — слепой на момент замера d5e4b05" in text
    assert "уже не слепой" in text
    assert "**holdout3** —" in text
    assert "holdout2 и бюджет времени" in text


def test_holdout3_is_registered_and_shown_as_the_generalization_number(results, monkeypatch):
    from eval.cases import CASE_SETS, HOLDOUT3_PATH

    assert CASE_SETS["holdout3"] == HOLDOUT3_PATH
    cases3 = load_cases(HOLDOUT3_PATH)
    assert len(cases3) == 24
    assert all(c["id"].startswith("h3-") for c in cases3)
    assert {c["author"] for c in cases3} == {"blind-glm-v2"}
    rec = json.loads(
        (results / "runs_poi.enriched_offline.jsonl").read_text("utf-8").splitlines()[0]
    )["recs"][0]
    for ds in ("poi", "poi.enriched"):
        runs = [
            _fake_run(c["id"], ds, "offline", "template", "офлайн-режим", rec) for c in cases3[:2]
        ]
        (results / f"runs_{ds}_holdout3_offline.jsonl").write_text(
            "\n".join(json.dumps(x) for x in runs) + "\n", encoding="utf-8"
        )
    main = write_summaries(results)
    h3 = write_summaries(results, tag="holdout3")
    assert set(h3) == {("poi", "offline"), ("poi.enriched", "offline")}
    text = canonical_md({"main": main, "holdout3": h3}, "offline", "abc1234")
    assert "poi.enriched / holdout3 (2)" in text
    assert "**holdout3** —" in text
    assert "по одному `eval/SCHEMA.md`" in text
    assert "после исправлений" in text
    assert "честное число обобщения" in text


def test_holdout2_frozen_measurement_is_shown_next_to_the_current_one(results, monkeypatch):
    from eval.cases import HOLDOUT2_PATH

    case_ids = [c["id"] for c in load_cases(HOLDOUT2_PATH)[:2]]
    rec = json.loads(
        (results / "runs_poi.enriched_offline.jsonl").read_text("utf-8").splitlines()[0]
    )["recs"][0]
    for ds in ("poi", "poi.enriched"):
        runs = [_fake_run(c, ds, "offline", "template", "офлайн-режим", rec) for c in case_ids]
        (results / f"runs_{ds}_holdout2_offline.jsonl").write_text(
            "\n".join(json.dumps(x) for x in runs) + "\n", encoding="utf-8"
        )
    frozen = {
        ds: {
            "case_all_ok_rate": 20.8,
            "constraint_ok_rate": 76.4,
            "coverage": 29.2,
            "top1_ok_rate": 79.2,
            "honest_unknown_rate": 100.0,
            "hallucinated_poi": 0,
        }
        for ds in ("poi", "poi.enriched")
    }
    monkeypatch.setattr(report, "_frozen_holdout2", lambda: frozen)
    h2 = write_summaries(results, tag="holdout2")
    text = canonical_md({"main": write_summaries(results), "holdout2": h2}, "offline", "abc1234")
    assert "слепой на момент замера d5e4b05: poi 20.8% / poi.enriched 20.8% без нарушений" in text
    section = text.split("## holdout2: замер до исправлений и сейчас")[1].split("\n## ")[0]
    assert (
        "| метрика | poi d5e4b05 | poi сейчас | poi.enriched d5e4b05 | poi.enriched сейчас |"
        in section
    )
    assert "| кейсов без нарушений | 20.8% |" in section
    assert "числа взяты из git" in section
    # without the frozen commit (no git history) the section is left out instead of inventing numbers
    monkeypatch.setattr(report, "_frozen_holdout2", lambda: None)
    text = canonical_md({"main": write_summaries(results), "holdout2": h2}, "offline", "abc1234")
    assert "## holdout2: замер до исправлений и сейчас" not in text
    assert "не слепой после исправлений" in text


def test_the_frozen_holdout2_measurement_is_in_git_history():
    frozen = report._frozen_holdout2()
    if frozen is None:
        pytest.skip("git history of the frozen commit is not available (shallow clone)")
    assert set(frozen) == {"poi", "poi.enriched"}
    assert frozen["poi.enriched"]["cases"] == 24
    assert frozen["poi.enriched"]["case_all_ok_rate"] == 20.8


def test_holdout2_audit_note_is_read_from_the_audit_file():
    from eval.report import _holdout2_audit

    audit = _holdout2_audit()
    assert audit is not None
    assert audit["cases"] == 24
    assert audit["inconsistent"] == 4
    assert audit["ids"] == ["`h2-05`", "`h2-10`", "`h2-16`", "`h2-17`"]
    assert audit["debatable"] == 3


def test_every_eval_writer_ends_lines_with_lf(tmp_path, monkeypatch):
    """Windows must not turn the generated files into CRLF (git keeps warning about it)."""
    import eval.report as rep
    from eval.run_eval import main as run_eval_main

    out = tmp_path / "runs_poi_probe.jsonl"
    run_eval_main(
        ["--data", "../data/poi.json", "--mode", "offline", "--limit", "1", "--out", str(out)]
    )
    assert b"\r" not in out.read_bytes()

    case = load_cases()[0]
    poi = POI(id="a", name="Cafe X", lat=51.1, lon=71.4, category="cafe", hours="24/7")
    rec = {
        "poi_id": "a",
        "name": "Cafe X",
        "category": "cafe",
        "source": "osm",
        "hours_state": "open",
        "hours_raw": "24/7",
        "hours_note": "",
        "walk_min": 5,
        "distance_m": 300,
        "method": "straight",
        "confidence": "medium",
        "text_source": "template",
        "why": "",
        "what_to_do": "",
        "notes": "",
        "padding": "none",
    }
    run = _fake_run(case["id"], "poi", "offline", "template", "офлайн-режим", rec)
    monkeypatch.setattr(rep, "_index", lambda _ds: metrics.dataset_index([poi]))
    (tmp_path / "runs_poi_offline.jsonl").write_text(json.dumps(run) + "\n", encoding="utf-8")
    (tmp_path / "runs_poi.enriched_offline.jsonl").write_text(
        json.dumps({**run, "dataset": "poi.enriched"}) + "\n", encoding="utf-8"
    )
    groups = {"main": write_summaries(tmp_path)}
    rep.write_main_vs_holdout(groups["main"], groups["main"], directory=tmp_path)
    rep.write_canonical(groups, directory=tmp_path)
    written = [p for p in tmp_path.iterdir() if p.suffix in {".md", ".json"}]
    assert len(written) >= 6
    assert all(b"\r" not in p.read_bytes() for p in written), [p.name for p in written]


def test_canonical_and_scenarios_describe_the_case_sets_in_the_same_words():
    from eval.report import HOLDOUT_ROLE, set_roles_text
    from eval.scenarios import _assumptions

    roles = set_roles_text()
    assert HOLDOUT_ROLE in roles
    assert "правила потом тоже подгонялись под его провалы" in roles
    assert "уже не слепой" in roles  # holdout2
    assert "честное число" not in roles or "обобщения" in roles
    text = "\n".join(_assumptions())
    assert roles in text
    assert "Независимая проверка — holdout3" in text
    assert "Независимая проверка — holdout2" not in text
    text_c = report.canonical_md({"main": {}}, "offline", "abc1234")
    assert roles in text_c
