"""Unit tests for the Magnum official-hours join (collect/recon/round13/magnum_hours_join.py)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "collect" / "recon" / "round13"))

from magnum_hours_join import hours_official_text, match_shop

# ~0.0009 deg of latitude is 100 m; the parallel at 51°N scales longitude by ~0.63
SHOPS = [
    {"lat": 51.1009, "lon": 71.4000, "open_h": "08:00:00", "close_h": "23:00:00"},
    {"lat": 51.2000, "lon": 71.5000, "open_h": "00:00:00", "close_h": "00:00:00"},
]


def test_within_100m_matches():
    # ~100 m north of the first shop
    hit = match_shop(51.1018, 71.4000, SHOPS)
    assert hit is not None
    assert hit["open_h"] == "08:00:00"


def test_beyond_130m_no_match():
    # ~130+ m north of the first shop, ~2 km from the second
    assert match_shop(51.1021, 71.4000, SHOPS) is None


def test_match_picks_nearest():
    hit = match_shop(51.1009, 71.4015, SHOPS, max_m=120)
    assert hit is not None
    assert hit["close_h"] == "23:00:00"


def test_empty_shops():
    assert match_shop(51.0, 71.0, [], max_m=120) is None


def test_hours_text_regular():
    assert hours_official_text(("08:00:00", "23:00:00")) == "с 08:00 до 23:00"


def test_hours_text_midnight_pair_is_24_7():
    assert hours_official_text(("00:00:00", "00:00:00")) == "24/7"
