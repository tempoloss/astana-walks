"""The abstention tier, the padding metric, the run header / label, the link redaction and the intent comparison
of the evaluation harness (app/eval)."""

from __future__ import annotations

import json
from datetime import datetime

import pytest

from eval import metrics
from eval.cases import (
    ABSTAIN_PATH,
    CASE_SETS,
    HEADER_KEY,
    label_from_filename,
    load_cases,
    read_header,
    runs_name,
)
from eval.intent_compare import compare, summary
from eval.metrics import judge_abstain, rec_padding
from eval.redact import PRIVATE_LINK, public_text
from eval.run_eval import main as run_eval_main
from walks.models import CATEGORIES, POI, Intent, IntentResult, LLMAttempt, LLMStep

ASTANA_LAT, ASTANA_LON = (50.95, 51.30), (71.20, 71.70)
POOL = r"бассейн|pool|swimming"


def _poi(pid: str, name: str = "Cafe X", category: str = "cafe", **kw) -> POI:
    return POI(id=pid, name=name, lat=51.1, lon=71.4, category=category, **kw)


def _rec(poi: POI, state: str = "open", padding: str | None = "none", notes: str = "") -> dict:
    rec = {
        "poi_id": poi.id,
        "name": poi.name,
        "category": poi.category,
        "source": "osm",
        "hours_state": state,
        "walk_min": 5,
        "distance_m": 300,
        "why": "Подходит.",
        "what_to_do": "",
        "notes": notes,
    }
    if padding is not None:
        rec["padding"] = padding
    return rec


def _case(**expected) -> dict:
    return {"id": "t", "expected": {"must_flag_unknown_hours": False, **expected}}


def _abstain(case: dict, recs: list[dict], pois: list[POI]) -> dict:
    run = {"recs": recs, "filters": {"radius_declared_m": 720, "radius_effective_m": 720}}
    return judge_abstain(case, run, metrics.dataset_index(pois))


# ---------------------------------------------------------------- abstain_cases.json


def test_abstain_set_is_registered_and_well_formed():
    assert CASE_SETS["abstain"] == ABSTAIN_PATH
    cases = load_cases(ABSTAIN_PATH)
    assert len(cases) == 8
    assert len({c["id"] for c in cases}) == 8
    for c in cases:
        o = c["origin"]
        assert ASTANA_LAT[0] <= o["lat"] <= ASTANA_LAT[1], c["id"]
        assert ASTANA_LON[0] <= o["lon"] <= ASTANA_LON[1], c["id"]
        datetime.fromisoformat(c["when"])
        e = c["expected"]
        assert e["wanted_categories"], c["id"]
        assert set(e["wanted_categories"]) <= set(CATEGORIES), c["id"]
        assert e["notes"]
    from eval.cases import indoor_required

    for c in cases:
        assert c["expected"]["indoor_preferred"] == indoor_required(c), c["id"]


# ---------------------------------------------------------------- honest abstention


def test_no_recommendations_is_an_honest_abstention():
    v = _abstain(_case(wanted_categories=["museum_gallery"]), [], [])
    assert v["abstained"]
    assert v["honest_abstain"]


def test_padding_badge_is_the_label_of_a_compromise():
    cafe = _poi("a")
    case = _case(wanted_categories=["sport"])
    labelled = _abstain(case, [_rec(cafe, padding="backfill")], [cafe])
    assert labelled["honest_abstain"]
    assert labelled["labelled_recs"] == 1
    silent = _abstain(case, [_rec(cafe, padding="none")], [cafe])
    assert not silent["honest_abstain"]
    assert silent["silent_mismatches"] == {"a": ["off_category_unlabeled"]}


def test_a_gym_is_not_a_pool_unless_labelled():
    gym = _poi("g", "Fitness Gym", "sport", tags=["leisure=sports_centre"])
    pool = _poi("p", "Barys Arena Pool", "sport", tags=["overture_category=swimming_pool"])
    case = _case(wanted_categories=["sport"], wanted_pattern=POOL)
    assert _abstain(case, [_rec(gym)], [gym])["silent_mismatches"] == {"g": ["specific_unlabeled"]}
    assert _abstain(case, [_rec(gym, padding="backfill")], [gym])["honest_abstain"]
    assert _abstain(case, [_rec(pool)], [pool])["honest_abstain"]


def test_unverified_requirements_need_their_label():
    cafe = _poi("a")
    case = _case(wanted_categories=["cafe"], needs_wifi_socket=True, step_free=True)
    v = _abstain(case, [_rec(cafe, state="unknown")], [cafe])
    assert v["silent_mismatches"]["a"] == ["hours_unlabeled", "wifi_unlabeled", "access_unlabeled"]
    notes = (
        f"{metrics.UNKNOWN_HOURS_LABEL} — уточните. {metrics.WIFI_NEGATIVE_LABEL} "
        f"{metrics.WHEELCHAIR_LABEL}."
    )
    assert _abstain(case, [_rec(cafe, state="unknown", notes=notes)], [cafe])["honest_abstain"]


# ---------------------------------------------------------------- padding


def test_padding_is_read_from_the_record_else_derived_and_reported():
    cafe = _poi("a")
    run = {"filters": {"radius_declared_m": 700, "radius_m": 1050, "radius_factor": 1.5}}
    assert rec_padding(run, _rec(cafe, padding="expanded")) == ("expanded", False)
    far = {**_rec(cafe, padding=None), "distance_m": 900}
    assert rec_padding(run, far) == ("expanded", True)
    near = {**_rec(cafe, padding=None), "distance_m": 400}
    assert rec_padding(run, near) == ("none", True)
    off = _rec(
        cafe, padding=None, notes="Категория вне вашего запроса: подходящих мест рядом мало."
    )
    assert rec_padding(run, off) == ("backfill", True)
    assert metrics.padding_missing_fields(run, near) == ["recs[].padding"]
    bare = {"poi_id": "a", "category": "cafe", "hours_state": "open"}
    assert metrics.padding_missing_fields({}, bare) == [
        "recs[].padding",
        "recs[].distance_m",
        "filters.radius_declared_m",
    ]
    assert rec_padding({}, bare) == ("none", True)  # computes what it can


def test_summarize_reports_padding_shares():
    from eval.report import summarize

    cafe = _poi("a")
    runs = [
        {
            "case_id": "x",
            "dataset": "poi",
            "mode": "offline",
            "model_link": "template",
            "generation_note": "",
            "recs": [
                _rec(cafe, padding="expanded"),
                _rec(cafe, padding="backfill"),
                _rec(cafe, padding="substituted"),
                _rec(cafe),
            ],
            "route": None,
            "timings": {"total": 1, "generation": 1},
            "filters": {"radius_declared_m": 700},
            "verdict": {
                "ok_recs": 4,
                "honesty_violations": {},
                "hallucinated": [],
                "honest_ok": True,
                "all_ok": True,
                "coverage_ok": True,
                "duplicate_chains": [],
                "constraint_violations": {},
                "wifi_socket_in_data": 0,
                "route_closed_stops": [],
                "violations": [],
            },
        }
    ]
    s = summarize(runs, [{"id": "x", "expected": {}}])
    assert s["padded_rec_share"] == pytest.approx(75.0)
    assert s["expanded_rec_share"] == pytest.approx(25.0)
    assert s["backfill_rec_share"] == pytest.approx(25.0)
    assert s["substituted_rec_share"] == pytest.approx(25.0)  # its own row: not a supply shortage
    assert s["padded_case_share"] == 100.0
    assert s["padding_missing_fields"] == []
    assert s["honest_abstain_rate"] is None


def test_a_substituted_card_is_a_labelled_compromise():
    cafe = _poi("a")
    rec = _rec(cafe, padding="substituted")
    assert rec_padding({}, rec) == ("substituted", False)
    assert "badge_substituted" in metrics.compromise_labels(rec)
    case = _case(wanted_categories=["park_garden"])
    assert _abstain(case, [rec], [cafe])["honest_abstain"]  # the badge is the label


def test_compromise_labels_are_the_strings_of_the_app_in_every_language():
    from walks.i18n import LANGS, STRINGS, pick, t

    assert LANGS == ("kk", "ru", "en")
    checks = {
        "note_off_category": metrics.OFF_CATEGORY_LABELS,
        "note_tight": metrics.TIGHT_FIT_LABELS,
        "budget_over": metrics.OVER_BUDGET_LABELS,
    }
    for key, labels in checks.items():
        assert len(labels) == len(LANGS)
        for lang, label in zip(LANGS, labels, strict=True):
            assert label, (key, lang)
            assert label in t(key, lang, lo=30, left=20), (key, lang)
    for lang, label in zip(LANGS, metrics.OFF_CATEGORY_LABELS, strict=True):
        # the weather variant of the note starts with the same label: one literal finds both
        assert label in pick(STRINGS["note_off_category_weather"], lang)
    expanded = [pick(STRINGS["note_expanded"], lang) for lang in LANGS]
    assert all(metrics._RADIUS_LABEL.search(text) for text in expanded)
    singles = {
        "note_hours_unknown": (
            metrics.UNKNOWN_HOURS_LABEL_KK,
            metrics.UNKNOWN_HOURS_LABEL,
            metrics.UNKNOWN_HOURS_LABEL_EN,
        ),
        "note_holiday": (
            metrics.HOLIDAY_LABEL_KK,
            metrics.HOLIDAY_LABEL,
            metrics.HOLIDAY_LABEL_EN,
        ),
        "note_wheelchair": (
            metrics.WHEELCHAIR_LABEL_KK,
            metrics.WHEELCHAIR_LABEL,
            metrics.WHEELCHAIR_LABEL_EN,
        ),
        "note_wifi": (
            metrics.WIFI_NEGATIVE_LABEL_KK,
            metrics.WIFI_NEGATIVE_LABEL,
            metrics.WIFI_NEGATIVE_LABEL_EN,
        ),
    }
    for key, labels in singles.items():
        for lang, label in zip(LANGS, labels, strict=True):
            assert label, (key, lang)
            assert label in t(key, lang, name="X"), (key, lang)
    # the wording the eval looked for before it read it from the app: unchanged
    assert metrics.OFF_CATEGORY_LABELS[1] == "Категория вне вашего запроса"
    assert metrics.UNKNOWN_HOURS_LABEL == "Часы работы в данных неизвестны"
    assert metrics.HOLIDAY_LABEL == "часы работы могут отличаться"
    assert metrics.WHEELCHAIR_LABEL == "Доступность для колясок в данных не указана"
    assert metrics.WIFI_NEGATIVE_LABEL == "Wi-Fi/розетки в данных не подтверждены."


# ---------------------------------------------------------------- header and label


def test_runs_name_and_label_from_filename(tmp_path):
    assert runs_name("poi", "offline") == "runs_poi_offline.jsonl"
    assert runs_name("poi.enriched", "run2", "abstain") == "runs_poi.enriched_abstain_run2.jsonl"
    assert label_from_filename(tmp_path / "runs_poi_llm-gemini-only.jsonl") == "llm-gemini-only"
    old = tmp_path / "runs_poi_offline.jsonl"
    old.write_text('{"case_id": "x"}\n', encoding="utf-8")
    assert read_header(old) == {"label": "offline", "legacy": True}


def test_run_header_carries_label_dataset_count_sha_mode_time(tmp_path, monkeypatch):
    for key in ("WALKS_OFFLINE", "WALKS_REQUEST_LOG", "WALKS_LLM_CACHE"):
        monkeypatch.setenv(key, "")  # run_eval sets them; the fixture restores the originals
    out = tmp_path / "runs_poi_abstain_probe.jsonl"
    argv = ["--data", "../data/poi.json", "--mode", "offline", "--cases", str(ABSTAIN_PATH)]
    code = run_eval_main([*argv, "--limit", "2", "--out", str(out)])
    assert code == 0
    lines = [json.loads(x) for x in out.read_text(encoding="utf-8").splitlines()]
    head = lines[0][HEADER_KEY]
    assert head["label"] == "probe"  # derived from the file name
    assert head["mode"] == "offline"
    assert head["dataset"] == "poi"
    assert head["data_path"].endswith("data/poi.json")
    assert head["records"] == 2 == len(lines) - 1
    assert head["case_set"] == "abstain"
    assert head["git"]
    assert head["generated_at"]
    assert all(r["recs"] == [] or "padding" in r["recs"][0] for r in lines[1:])
    assert {"radius_declared_m", "radius_effective_m"} <= set(lines[1]["filters"])
    assert read_header(out) == head

    labelled = tmp_path / "x.jsonl"
    argv = [
        "--data",
        "../data/poi.json",
        "--mode",
        "offline",
        "--limit",
        "1",
        "--out",
        str(labelled),
    ]
    run_eval_main([*argv, "--label", "v2"])
    assert (
        json.loads(labelled.read_text(encoding="utf-8").splitlines()[0])[HEADER_KEY]["label"]
        == "v2"
    )
    with pytest.raises(SystemExit):
        run_eval_main(["--data", "../data/poi.json", "--mode", "offline", "--label", "a_b"])


# ---------------------------------------------------------------- redaction


def test_only_google_links_stay_in_the_text():
    text = (
        "gemini:gemini-3.5-flash: 429 (0.4 с) → openai:vendor/model-a@gw: ok (3.1 с) → "
        "openai:model-b: 500 (1 с) → openai:vendor-model:31b@gw: ok (0.9 с)"
    )
    out = public_text(text)
    assert "gemini:gemini-3.5-flash: 429" in out
    assert out.count(PRIVATE_LINK) == 3
    assert "vendor" not in out
    assert "model-b" not in out
    assert ":31b" not in out
    assert public_text(None) is None


# ---------------------------------------------------------------- intent comparison


def _intent(categories=(), **flags) -> Intent:
    return Intent(time_budget_min=60, categories=list(categories), **flags)


def _answered(rules: Intent, merged: Intent, model: str, cached: bool = False) -> IntentResult:
    step = LLMStep(
        chain=[model], model=model, attempts=[LLMAttempt(model=model, status="ok")], cached=cached
    )
    return IntentResult(intent=merged, parser="rules+llm", rules=rules, llm=merged, llm_step=step)


def _failed(why: str = "429") -> IntentResult:
    step = LLMStep(
        chain=["gemini:a"], attempts=[LLMAttempt(model="gemini:a", status="error", detail=why)]
    )
    return IntentResult(
        intent=_intent(), parser="rules", note="ИИ не уточнил разбор", llm_step=step
    )


def _case_for(cid: str, allowed: list[str], **expected) -> tuple[str, dict]:
    return "holdout", {
        "id": cid,
        "query": f"запрос {cid}",
        "expected": {"allowed_categories": allowed, **expected},
    }


def test_intent_gaps_against_expected():
    case = {
        "expected": {
            "allowed_categories": ["cafe"],
            "forbidden_categories": ["bar_nightlife"],
            "kids_ok": True,
        }
    }
    assert metrics.intent_gaps(case, _intent().model_dump()) == ["categories", "with_kids"]
    ok = _intent(["cafe"], with_kids=True).model_dump()
    assert metrics.intent_gaps(case, ok) == []
    assert metrics.intent_gaps(
        case, _intent(["cafe", "bar_nightlife"], with_kids=True).model_dump()
    ) == ["categories"]


def test_compare_totals_only_live_public_answers_and_the_fixes():
    cases = [_case_for("c1", ["cafe"]), _case_for("c2", ["cafe"]), _case_for("c3", ["cafe"])]
    answers = {
        "запрос c1": _answered(_intent(), _intent(["cafe"]), "gemini:m1"),
        "запрос c2": _answered(_intent(), _intent(["cafe"]), "openai:secret@PRIV"),
        "запрос c3": _answered(_intent(), _intent(["cafe"]), "gemini:m1", cached=True),
    }
    pauses: list[float] = []
    res = compare(cases, parse=lambda q, **_: answers[q], pause_s=4.0, sleep=pauses.append)
    s = summary(res)
    assert (s["tried"], s["measured"], s["excluded"], s["not_measured"]) == (3, 1, 2, 0)
    assert (s["left"], s["stopped"]) == (0, None)
    assert (s["rule_gap_cases"], s["llm_fixed"], s["holdout_llm_fixed"]) == (1, 1, 1)
    assert s["used"] == ["gemini:m1"]  # the private and the cached answers are in no total
    assert pauses == [
        4.0,
        4.0,
    ]  # not after the last query; a cached answer needs no pause before it was asked
    rows = {r["case_id"]: r for r in res["rows"]}
    assert rows["c1"]["fixed"]
    assert rows["c1"]["added_categories"] == ["cafe"]
    assert rows["c1"]["counted"]
    assert rows["c2"]["measured"]
    assert not rows["c2"]["counted"]
    assert rows["c2"]["used"] == PRIVATE_LINK
    assert rows["c3"]["measured"]
    assert not rows["c3"]["counted"]


def test_a_fallback_to_rules_is_not_measured_and_a_storm_stops_the_run():
    cases = [_case_for(f"c{i}", ["cafe"]) for i in range(6)]
    seen: list[str] = []

    def parse(q: str, **_) -> IntentResult:
        seen.append(q)
        return _failed() if len(seen) > 1 else _answered(_intent(), _intent(["cafe"]), "gemini:m")

    res = compare(cases, parse=parse, pause_s=4.0, storm=3, sleep=lambda _s: None)
    s = summary(res)
    assert s["measured"] == 1
    assert s["not_measured"] == 3
    assert s["tried"] == 4
    assert s["left"] == 2
    assert "3 запроса подряд" in s["stopped"]
    assert not any(r["measured"] for r in res["rows"][1:])


def test_no_llm_call_at_all_stops_at_once():
    res = compare(
        [_case_for("a", ["cafe"]), _case_for("b", ["cafe"])],
        parse=lambda q, **_: IntentResult(intent=_intent(), parser="rules", note="ИИ не настроен"),
        sleep=lambda _s: None,
    )
    s = summary(res)
    assert (s["tried"], s["measured"], s["left"]) == (1, 0, 1)
    assert s["stopped"].startswith("ИИ не вызывался")
