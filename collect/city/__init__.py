"""City-state layers from OpenStreetMap (SOURCES.md §14.2 and §14.6; everything ODbL).

Three collectors, one command:

    uv run python -m collect.city            # data/city/{osm_notes,lit,construction}.json + city_stats.json

- `notes.py` — one page (open + closed, any age) of OSM Notes in the Astana bbox via api.openstreetmap.org (the
  auto-reports «заведение исчезло» are the closure signal; the open count is a lower bound, not a window); stores
  id, coords, dates, status, a coarse classification and the note URL — never the full comment thread, author
  names or html.
- `roads.py` — `lit=yes|no` ways (any `highway`, which includes footway/path/cycleway) and `highway=construction`
  ways, via the Overpass mirror that answers from this host (maps.mail.ru, see SOURCES §14.7), geometry simplified
  to ~5 m.

Licence of everything stored: ODbL-1.0 (© OpenStreetMap contributors). The module API consumed by the app lives in
`app/walks/city_layers.py` (pure, reads the JSON files, no network).
"""

from __future__ import annotations
