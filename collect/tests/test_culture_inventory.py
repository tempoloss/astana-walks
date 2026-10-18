"""collect.sites.culture_inventory: the culture/landmark crawl inventory."""

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from collect.sites import culture_inventory as ci  # noqa: E402


def _poi(i, name, cat, website=None, opening_hours=None):
    tags = [] if i != "wd" else ["wikidata=Q42"]
    return {"id": i, "name": name, "names": {"name": name}, "category": cat, "website": website,
            "lat": 51.1, "lon": 71.4, "opening_hours": opening_hours, "tags": tags}


@pytest.fixture
def pois():
    return [
        _poi("m1", "Музей", "museum_gallery", "https://covered.kz/"),
        _poi("m2", "Музей 2", "museum_gallery", "https://newdom.kz/"),
        _poi("m3", "Парк", "park_garden", None),
        _poi("m4", "Театр с часами", "culture_theatre_cinema", "https://withhours.kz/", "Mo-Su 10:00-18:00"),
        _poi("wd", "Ак орда", "attraction_landmark", None),
    ]


def test_hours_measures_counts_website_without_day_qualified_hours(pois):
    m = ci.hours_measures(pois)
    assert m["poi_total"] == 5
    assert m["per_category"]["museum_gallery"]["pois"] == 2
    assert m["per_category"]["museum_gallery"]["with_day_qualified_hours"] == 0
    assert m["pois_with_website"] == 3
    assert m["pois_with_website_no_day_qualified_hours"] == 2  # m4 has day-qualified hours


def test_build_drops_covered_domains_and_keeps_new(pois, tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "ROOT", tmp_path)
    monkeypatch.setattr(ci, "_covered_domains", lambda: {"covered.kz"})
    monkeypatch.setattr(ci, "_p856_snapshot", lambda: {"Q42": ["https://akorda.example/"]})
    monkeypatch.setattr(ci, "_e_museum_entry", lambda pois: {
        "domain": ci.E_MUSEUM, "poi_ids": [], "names": [], "categories": {}, "wikidata_ids": [],
        "robots": "allowed", "notes": "test", "origin": ["e_museum_register"], "poi_count": 0})
    inv = ci.build(pois)
    domains = {e["domain"]: e for e in inv["entries"]}
    assert "covered.kz" not in domains  # owned by another partition
    assert domains["newdom.kz"]["poi_ids"] == ["m2"]
    assert domains["akorda.example"]["origin"] == ["wikidata_p856"]
    assert domains["akorda.example"]["wikidata_ids"] == ["Q42"]
    assert inv["counts"]["culture_pois_without_day_qualified_hours"] == 4


def test_partitions_balance_by_pois_without_hours(pois, tmp_path, monkeypatch):
    monkeypatch.setattr(ci, "ROOT", tmp_path)
    monkeypatch.setattr(ci, "_covered_domains", lambda: set())
    monkeypatch.setattr(ci, "_p856_snapshot", lambda: {})
    monkeypatch.setattr(ci, "_e_museum_entry", lambda pois: {
        "domain": ci.E_MUSEUM, "poi_ids": ["m1", "m2", "m3"], "names": [], "categories": {}, "wikidata_ids": [],
        "robots": "allowed", "notes": "", "origin": ["e_museum_register"], "poi_count": 3})
    inv = ci.build(pois)
    bins = ci.partitions(inv)
    assert [b["partition"] for b in bins] == ["p1", "p2", "p3"]
    weights = [b["weight"] for b in bins]
    assert max(weights) - min(weights) <= 2.5  # 3 bins, 5 single-POI domains + one 3-POI domain: dealt lightest-first
    assert sum(b["poi_count"] for b in bins) == sum(e["poi_count"] for e in inv["entries"])
