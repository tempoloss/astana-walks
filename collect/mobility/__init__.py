"""Getting there and parking (SOURCES.md §14.2): bus stops, airport bus facts, paid parking zones.

Modules: `stops` (Zenodo GTFS CC BY 4.0 + OSM platforms via the Overpass mirror, ODbL, merged and
de-duplicated), `airport_bus` (nn-airport.kz route facts with evidence snippets), `parking`
(ЦОДД UIMS gateway — **no licence, reverse-engineered private JSON**: collected into an isolated file,
the whole feature off by default behind `WALKS_MOBILITY_PARKING=1`, removable by deleting this package).

Run from the repo root:  uv run python -m collect.mobility
Outputs: `data/mobility/{parking_zones,stops,airport_bus}.json` + `mobility_stats.json`.
"""
