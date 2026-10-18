"""One command to rebuild the whole dataset: districts -> osm -> overture -> geocheck -> wiki -> wiki_places -> merge
-> sites -> gov -> dedupe -> wikivoyage.

Usage: uv run python -m collect.build [--refresh] [--no-sites]

Idempotent: every HTTP response is cached in .local/http_cache.sqlite, the Overture stage is skipped when its
output already holds the latest release (and the current category mapping), so a rerun makes zero requests to
Wikimedia / Overpass / Nominatim. `--refresh` ignores cached responses (re-fetches everything, politely).
The last stage (`collect.sites.apply`) verifies the official-site facts in data/sites/facts (cache only, no
requests), joins them to the POIs (data/sites/joined.json) and writes the shipped data/poi.enriched.json: the merge
stage's dataset with the first-party hours / phones / addresses / descriptions and the new POIs, and extends
data/poi_enriched_stats.json and a section of data/coverage_delta.md. The stage after it (`collect.gov.apply`, offline) adds
the state-registry facts (ЦОН branches of gov4c.kz, sport register №730; data/gov/facts, data/gov/osm_candidates.json)
and the key `state_registry` of the stats. The stage after it (`collect.dedupe`, offline) merges the records of one
venue (a museum, theatre, landmark, park or mall that OSM, Overture and Wikidata list several times) into the richest
one, keeping every fact and the absorbed ids (`aliases`), and writes `data/duplicates_merged.json` and the key
`duplicates` of the stats. The stage after it (`collect.wikivoyage.apply`, offline: the wikitext
snapshots in collect/wikivoyage/snapshots/) adds the hours / prices / descriptions of sights read from the
en/it/he/pl/ru Wikivoyage articles (CC BY-SA 4.0) and the key `wikivoyage` of the stats. `--no-sites` stops after
merge (the dataset without the official-site, state-registry, merged-duplicate and Wikivoyage stages).
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

if __package__ in (None, ""):  # plain script run
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from collect import coord_quality, dedupe, districts, merge, overpass_poi, overture_places, wiki_enrich, wiki_places
from collect.gov import apply as gov_apply
from collect.net import default_net
from collect.sites import apply as sites_apply
from collect.wikivoyage import apply as wikivoyage_apply

WIKIMEDIA_HOSTS = ("wikidata.org", "wikipedia.org", "wikimedia.org")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--refresh", action="store_true", help="ignore the HTTP cache (still writes to it)")
    parser.add_argument("--no-sites", action="store_true",
                        help="skip the official-site stage: data/poi.enriched.json is the merge stage's output")
    args = parser.parse_args(argv)
    if args.refresh:
        os.environ["WALKS_REFRESH"] = "1"

    net = default_net()
    stages = (
        ("districts", districts.main),
        ("osm", overpass_poi.main),
        ("overture", overture_places.main),
        ("geocheck", coord_quality.main),
        ("wiki", wiki_enrich.main),
        ("wiki_places", wiki_places.main),
        ("merge", merge.main),
    )
    if not args.no_sites:
        stages += (("sites", sites_apply.main), ("gov", gov_apply.main), ("dedupe", dedupe.main),
                   ("wikivoyage", wikivoyage_apply.main))
    for name, fn in stages:
        started = time.monotonic()
        print(f"\n=== stage: {name} ===", file=sys.stderr, flush=True)
        rc = fn([])
        if rc:
            print(f"[build] stage {name} failed rc={rc}", file=sys.stderr)
            return rc
        print(f"[build] stage {name} done in {time.monotonic() - started:.1f}s", file=sys.stderr, flush=True)

    wm = {h: v for h, v in net.summary().items() if h.endswith(WIKIMEDIA_HOSTS)}
    wm_net = sum(v["network"] for v in wm.values())
    wm_cache = sum(v["cache_hits"] for v in wm.values())
    net.log_summary("build total")
    print(f"[build] Wikimedia: network_requests={wm_net} cache_hits={wm_cache}", file=sys.stderr)
    return 0


if __name__ == "__main__":
    sys.exit(main())
