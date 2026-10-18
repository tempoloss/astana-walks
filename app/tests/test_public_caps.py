"""A public instance must not let strangers grow the disk: request log, people's marks and profiles are capped."""

from __future__ import annotations

import json
import os
from datetime import datetime
from pathlib import Path

from walks import feedback, profile, reqlog
from walks.models import load_pois
from walks.pipeline import recommend

FIXTURE = Path(__file__).parent / "fixtures" / "poi_sample.json"


def test_request_log_rotates_when_full(tmp_path, monkeypatch):
    log = tmp_path / "requests.jsonl"
    monkeypatch.setenv("WALKS_REQUEST_LOG", str(log))
    monkeypatch.setattr(reqlog, "MAX_LOG_BYTES", 600)
    pois = load_pois(FIXTURE)
    for _ in range(12):
        recommend("кофе", 51.089, 71.416, datetime(2026, 10, 14, 12, 0), use_llm=False, pois=pois)
    assert (tmp_path / "requests.jsonl.1").exists()
    assert log.stat().st_size < 600 * 2
    assert all(json.loads(line) for line in log.read_text(encoding="utf-8").splitlines())


def test_feedback_drops_oldest_people_marks_but_keeps_demo_ones(tmp_path, monkeypatch):
    monkeypatch.setattr(feedback, "MAX_ENTRIES", 4)
    path = tmp_path / "marks.json"
    demo = {
        "poi_id": "d",
        "signal": "quiet",
        "date": "2026-10-01",
        "weekday": "wed",
        "hour_bucket": "day",
        "demo": True,
    }
    path.write_text(json.dumps([demo, demo]), encoding="utf-8")
    for i in range(6):
        feedback.add_feedback(f"node/{i}", "quiet", datetime(2026, 10, 19, 14, 0), path)
    rows = json.loads(path.read_text(encoding="utf-8"))
    assert [r["poi_id"] for r in rows] == ["d", "d", "node/4", "node/5"]


def test_profiles_keep_only_the_most_recent_files(tmp_path, monkeypatch):
    monkeypatch.setenv("WALKS_PROFILE_DIR", str(tmp_path))
    monkeypatch.setattr(profile, "MAX_PROFILES", 3)
    ids = [profile.new_profile_id() for _ in range(5)]
    for n, uid in enumerate(ids):
        path = profile.save_profile(uid, profile.Profile(quiet=True))
        os.utime(path, (1_000_000 + n, 1_000_000 + n))
    assert sorted(p.stem for p in tmp_path.glob("*.json")) == sorted(ids[-3:])
    profile.save_profile(ids[-1], profile.Profile(quiet=False))  # an existing file evicts nothing
    assert len(list(tmp_path.glob("*.json"))) == 3
