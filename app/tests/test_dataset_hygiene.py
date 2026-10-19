"""Dataset hygiene over the real base: names the owner ships must look like places, not data-pipeline artifacts.
The Overture handle bug (`kafel_laminat_astana`, 19 records, found while auditing why «панорама» listed a cafe)
must never come back on a re-collect."""

from __future__ import annotations

from walks.models import load_pois

POIS = load_pois()


def test_no_place_name_is_a_underscored_handle():
    handles = [p.name for p in POIS if "_" in p.name]
    assert not handles, handles


def test_no_place_name_is_a_bare_technical_string():
    # a name is either Cyrillic or Latin letters/digits with normal separators, never a file fragment or a code
    bad = [
        p.name
        for p in POIS
        if p.name.strip() != p.name or p.name.lower().endswith((".jpg", ".png", ".webp"))
    ]
    assert not bad, bad
