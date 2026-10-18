# Attribution — `astana_streets.json`

Street gazetteer of Astana (849 street keys from 20 694 address points): spellings of street names, number of address
points per street, districts. **No coordinates** are stored, and none are used anywhere in the project: the file serves
address aliases and normalisation (`collect/gov/addr.py`, `collect/gov/geocode.py`) only.

- **Source:** OpenAddresses KZ, `https://data.openaddresses.io/cache/uploads/sergiyprotsiv/5f6b95/kz.csv.zip`
  (`sources/kz/countrywide.json` of https://github.com/openaddresses/openaddresses). The zip member is dated 2017-01-21;
  street renames of the 2020s are absent. Retrieved 2026-10-17 (see `retrieved_at` in the JSON).
- **Attribution (as given by the source's manifest):** Комитет по правовой статистике и специальным учетам
  Генеральной прокуратуры Республики Казахстан.
- **Licence:** *not stated by the source.* The OpenAddresses manifest of this source carries an `attribution` but no
  `license` key, and OpenAddresses says that data is not relicensed from the original source. The legal basis used here
  is that of a state address register under the Law of the Republic of Kazakhstan No. 401-V «On access to information»
  (art. 1 p. 5: open data for free use, processing and re-publication), with attribution. It is **not** a Creative
  Commons licence.
- **What was taken:** the `region = АСТАНА` rows reduced to `street`, `district` counts. The `x_point` / `y_point`
  columns are dropped on purpose (their projection is wrong for most of the country and the snapshot is old).

# Attribution — `astana_addresses.json`

House addresses and street positions of Astana for the page's address search («Где вы?», `app/web/geocode.py`):
29 165 houses (street, number, centre of the building) and 1 676 streets (every spelling OSM has for one street and
one position of it). One Overpass request, `collect/osm_addresses.py`.

- **Source:** OpenStreetMap contributors, via the Overpass API (`addr:housenumber` + `addr:street` elements and named
  roads inside the administrative area of Astana). Retrieved 2026-10-18 (see `retrieved_at` in the JSON).
- **Licence:** Open Database Licence 1.0 (ODbL), <https://www.openstreetmap.org/copyright>. The page shows
  «© OpenStreetMap contributors» on the map; this derived database is released under the same ODbL.
- **Attribution:** © OpenStreetMap contributors.
- **What was taken:** the street and house-number tags and the centre of each element. Nothing else of the elements
  (names of businesses, opening hours, etc.) is kept here.
- **How it is used:** the search matches what a person types against these names and returns a point inside Astana.
  The query is never logged or kept. `astana_streets.json` (above) only adds spellings of the same streets.
