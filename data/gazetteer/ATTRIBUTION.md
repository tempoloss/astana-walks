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
