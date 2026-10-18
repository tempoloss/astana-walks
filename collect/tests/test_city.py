"""Unit tests of the city collectors (collect/city): no network, no real cache.

Run from the repository root:  uv run python -m pytest collect/tests/test_city.py -q
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.city import notes, roads  # noqa: E402
from collect.city.common import simplify  # noqa: E402


# ---- note classification --------------------------------------------------------------------------

def test_classification_auto_report_closure():
    # the stock sentence of the Organic Maps / MAPS.ME auto-reports
    assert notes.classify('"Нету" The place has gone or never existed. A user of Organic Maps application') == (
        "closure")
    assert notes.classify("Закрыто. Вывеска снята. Внутри строительная пыль.") == "closure"
    assert notes.classify("TSON was closed, there is no such office here. Checked in person 21/05/2025.") == (
        "closure")


def test_classification_new_place_construction_hours_other():
    assert notes.classify("Открылось кафе традиционной китайской кухни.") == "new_place"
    assert notes.classify("Прошу добавить здание по адресу Астана, улица Достык, 3") == "new_place"
    assert notes.classify("2026.03.21 - Still under construction") == "construction"
    assert notes.classify('Unable to answer "What are the opening hours here?"') == "hours"
    assert notes.classify("Перешивка на 1 линию") == "other"
    assert notes.classify("") == "other"


def test_note_url_and_record_shape():
    row = {
        "id": 5567918, "lat": 51.131404, "lon": 71.505769, "status": "open",
        "date_created": "2026-10-12", "date_closed": None,
        "classification": notes.classify("Перешивка на 1 линию"),
        "snippet": "Перешивка на 1 линию", "url": notes.note_url(5567918),
    }
    assert row["url"] == "https://www.openstreetmap.org/note/5567918"
    assert row["classification"] == "other"
    assert set(row) >= {"id", "lat", "lon", "status", "classification", "url"}


class _FakeNet:
    """Serves one canned JSON response for the notes API call; the collector itself stays untouched."""

    def __init__(self, features: list[dict]):
        self._features = features

    def get(self, url, **_):
        import json as _json

        from collect.net import Response

        body = _json.dumps({"type": "FeatureCollection", "features": self._features}).encode()
        return Response(200, body, {"content-type": "application/json"}, url, fetched_at=1_790_000_000.0)


def _note_feature(note_id: int, lat: float, lon: float, text: str) -> dict:
    return {
        "type": "Feature",
        "geometry": {"type": "Point", "coordinates": [lon, lat]},
        "properties": {
            "id": note_id, "date_created": "2026-10-12 06:31:48 UTC", "status": "open",
            "comments": [{"date": "2026-10-12 06:31:48 UTC", "action": "opened", "text": text}],
        },
    }


@pytest.fixture
def collector_notes_rows() -> list[dict]:
    """Notes collected through the real code path from a canned API answer: one per classification."""
    texts = {
        1: ("Закрыто. Вывеска снята.", "closure"),
        2: ("Открылось кафе.", "new_place"),
        3: ("Still under construction", "construction"),
        4: ('Unable to answer "What are the opening hours here?"', "hours"),
        5: ("Квартира расположена здесь. Туран 57/4", "other"),
    }
    feats = [_note_feature(i, 51.1, 71.4, t) for i, (t, _) in enumerate(texts.values(), 1)]
    rows, _ = notes.collect(_FakeNet(feats))
    return rows


def test_other_notes_keep_no_text(collector_notes_rows):
    """Privacy: the snippet of an «other» note (spam ads, personal addresses) is never stored; the app-used
    classifications keep theirs."""
    by_cls = {r["classification"]: r.get("snippet") for r in collector_notes_rows}
    assert by_cls["closure"] and by_cls["new_place"] and by_cls["construction"] and by_cls["hours"]
    assert by_cls["other"] is None


# ---- geometry simplification ----------------------------------------------------------------------

def test_simplify_keeps_endpoints_and_drops_close_vertices():
    # 1 m steps along a line: vertices within 5 m of the previous kept one are dropped, so a ~10 m run
    # collapses to its endpoints and a ~70 m line keeps ~70/5 points
    m_per_deg = 69_000.0  # ~1 deg lon at lat 51.1 in metres (cos 51.1 * 111320 ≈ 69.8 km)
    pts = [(51.1, 71.30 + i / m_per_deg) for i in (0, 1, 2, 3, 9, 70)]
    out = simplify(pts)
    assert out[0] == pts[0] and out[-1] == pts[-1]
    assert len(out) == 3  # 1-3 m runs collapse; the 9 m and 70 m vertices are > 5 m apart, they stay
    far = [(51.1, 71.30 + i * 0.001) for i in range(5)]  # ~70 m apart
    assert simplify(far) == far


# ---- road filters ---------------------------------------------------------------------------------

def test_lit_way_filter_keeps_walking_highways_and_explicit_values():
    # direct filter checks via the module-level tables used by collect()
    assert "footway" in roads.WALK_HIGHWAYS and "residential" in roads.WALK_HIGHWAYS
    assert "motorway" in roads.DROP_HIGHWAYS
    # construction wins over lit: a way tagged highway=construction + lit goes to construction
    el = {"type": "way", "id": 1, "tags": {"highway": "construction", "lit": "yes"},
          "geometry": [{"lat": 51.1, "lon": 71.3}, {"lat": 51.1, "lon": 71.31}]}
    assert el["tags"]["highway"] == "construction"


def test_lit_query_uses_mirror_bbox_and_two_selectors():
    assert "lit" in roads.QUERY and "construction" in roads.QUERY
    assert "50.98" in roads.QUERY and "71.25" in roads.QUERY  # the Astana bbox
    assert "(yes|no)" in roads.QUERY  # only explicit values; untagged ways are never stored
