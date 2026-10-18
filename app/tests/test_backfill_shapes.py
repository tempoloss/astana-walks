"""scripts/backfill_shapes.py: only the geometry of a stored leg is added; a leg whose duration moves is left alone."""

from __future__ import annotations

import importlib.util
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[1] / "scripts" / "backfill_shapes.py"
spec = importlib.util.spec_from_file_location("backfill_shapes", SCRIPT)
backfill_shapes = importlib.util.module_from_spec(spec)
spec.loader.exec_module(backfill_shapes)

A, B = "51.0890,71.4160>51.0894,71.4180", "51.0894,71.4180>51.0870,71.4120"
C, D = "51.0870,71.4120>51.0880,71.4000", "51.0880,71.4000>51.0860,71.4010"


class FakeRouter:
    def __init__(self, answers: dict[tuple, dict | None]):
        self.answers, self.asked = answers, []

    def _fetch(self, a, b):
        self.asked.append((a, b))
        return self.answers.get((a, b))

    def reset_cooldown(self):
        pass


def test_parse_key_is_the_inverse_of_the_cache_key():
    assert backfill_shapes.parse_key(A) == ((51.089, 71.416), (51.0894, 71.418))


def test_only_the_geometry_is_added_and_a_moved_duration_is_left_alone():
    cache = {
        A: {"m": 620, "s": 450, "d": "2026-10-01"},
        B: {"m": 700, "s": 500, "d": "2026-10-01", "g": "have"},
        C: {"m": 900, "s": 600, "d": "2026-10-01"},
        D: {"m": 100, "s": 100, "d": "2026-10-01"},
    }
    before = {k: dict(v) for k, v in cache.items()}
    router = FakeRouter(
        {
            ((51.089, 71.416), (51.0894, 71.418)): {"m": 640, "s": 460, "g": "new-a"},  # +2 %
            ((51.087, 71.412), (51.088, 71.4)): {"m": 900, "s": 300, "g": "new-c"},  # -50 %
            ((51.088, 71.4), (51.086, 71.401)): None,  # no answer
        }
    )
    res = backfill_shapes.backfill(cache, router)
    assert (res["filled"], res["had_shape"]) == (1, 1)
    assert len(res["skipped"]) == 1
    assert C in res["skipped"][0]
    assert len(res["failed"]) == 1
    assert D in res["failed"][0]
    assert cache[A] == {**before[A], "g": "new-a"}  # m, s, d exactly as stored
    assert cache[B] == before[B]  # already had a shape: not even asked
    assert (cache[C], cache[D]) == (before[C], before[D])
    assert len(router.asked) == 3
    assert set(cache) == set(before)  # no leg added


def test_dry_run_asks_nothing():
    cache = {A: {"m": 620, "s": 450, "d": "2026-10-01"}}
    router = FakeRouter({})
    res = backfill_shapes.backfill(cache, router, dry_run=True)
    assert not router.asked
    assert res["filled"] == 0


def test_the_script_refuses_to_run_without_an_own_valhalla(monkeypatch, capsys):
    monkeypatch.delenv("WALKS_VALHALLA_URL", raising=False)
    assert backfill_shapes.main([]) == 2
    assert "WALKS_VALHALLA_URL" in capsys.readouterr().err
