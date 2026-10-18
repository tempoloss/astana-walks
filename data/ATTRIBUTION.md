# Attribution

Every record in `poi.enriched.json` lists its sources in `sources[]` and, per field, the source, licence and
snapshot date in `field_sources{}`. Nothing is taken from 2GIS, Yandex or Google (their terms forbid storing it).
This file is maintained by hand: `collect.build` never rewrites it (it only refreshes the marked state-registry
block below). The table of every source with the quoted terms, where each duty is met and what production still needs
is [`docs/licensing.md`](../docs/licensing.md); the licence of the files in `data/` is [`NOTICE.md`](NOTICE.md); licence
texts are in [`LICENSES/`](../LICENSES/).

**The files in `data/` are a frozen snapshot of 16–17 October 2026.** Rebuilding them (`collect/README.md`) is optional,
needs the network for a long time (Overpass is sometimes flaky) and yields a different snapshot of the sources below.

- **OpenStreetMap** — © OpenStreetMap contributors, Open Database License (ODbL) 1.0,
  https://www.openstreetmap.org/copyright (Overpass snapshot 2026-10-17; two requests: the base selector set and
  the extra tags `leisure=indoor_play`, `amenity=planetarium|events_venue|fountain`, `club=sport` ... of
  `collect/overpass_poi.py`). The files below that contain OSM data are a Derivative Database under ODbL 1.0 — see
  [`NOTICE.md`](NOTICE.md) (licence, attribution sentence, machine-readable copy, Produced Works).
- **Wikidata** — structured data (ids, labels, descriptions, sitelinks, coordinates P625, classes P31),
  CC0 1.0, https://www.wikidata.org (SPARQL / wbgetentities snapshot 2026-10-17; places that exist
  only in Wikidata / Wikipedia, snapshot 2026-10-17, are records with `source: "wikidata"`).
- **Wikipedia** — article extracts (`wikipedia[lang].extract`, `description` when `description_source` is
  `wikipedia`) and article coordinates from the ru/kk/en Wikipedia, CC BY-SA 4.0,
  https://creativecommons.org/licenses/by-sa/4.0/ ; authors are listed in each article's history, linked as
  `wikipedia[lang].url`. Excerpts are shortened.
- **Wikivoyage** — hours, prices and descriptions of sights from the Astana articles of the en, it, he, pl and ru
  Wikivoyage (`collect/wikivoyage`, snapshots 2026-10-17 in `collect/wikivoyage/snapshots/`; records with `wikivoyage`
  in `sources`), CC BY-SA 4.0, https://creativecommons.org/licenses/by-sa/4.0/ ; authors are listed in each article's
  history, linked from `field_sources`. Descriptions (`description_voyage`) are shown as quoted third-party text with
  this attribution, never as our own words.
- **Museum register «Музеи Казахстана» (e-museum.kz)** — work hours and ticket prices of Astana museums from the
  ministry portal's open WordPress REST API (records with `museum_register` in `sources`, snapshot 2026-10-17); facts
  with the card URL and a verbatim snippet; the portal publishes no terms of use, robots.txt allows it.
- **Wikimedia pageviews** — monthly article views (2026-09) from the Wikimedia REST API,
  CC0 1.0, https://wikimedia.org/api/rest_v1/ .
- **Nominatim** (OpenStreetMap geocoder, ODbL 1.0, 1 request/s, own User-Agent) — coordinates of Wikidata places
  that have none (`field_sources.lat.source = "nominatim"` with `geocode_confidence`) and the address check of
  Overture records (`data/overture_geocheck.json`).
- **Overture Maps** — © Overture Maps Foundation, places theme, release 2026-09-23.1, https://overturemaps.org .
  The `places` theme has NO single licence: it is the licence of the contributing dataset, carried per record in
  `overture_places.json` -> `places[].sources[].license` and, for every field taken from it, in
  `poi.enriched.json` -> `field_sources.<field>.license` / `.contributor`. The page
  https://docs.overturemaps.org/attribution/ (read 2026-10-17) lists for places: Meta, Microsoft, PinMeTo, Krick,
  RenderSEO, DAC, BrightQuery = CDLA-Permissive-2.0; «Data from Foursquare. Copyright 2024 Foursquare Labs, Inc. All
  rights reserved. Available under Apache 2.0. Foursquare data was transformed to the Overture schema. Changed:
  2026-03-18. NOTICE.txt.»; AllThePlaces = CC0 1.0. Measured over the 8 590 shipped records (one contributor each):
  meta 8 118, AllThePlaces 234 (CC0-1.0), **Foursquare 151 (Apache-2.0)**, Microsoft 86, PinMeTo 1
  (CDLA-Permissive-2.0). In `poi.enriched.json` 848 cards point at an Overture record (their own `overture_id` or that of
  a record merged into them): meta 766, Foursquare 45, Microsoft 29, AllThePlaces 10 (a merged card can point at two);
  40 cards carry fields under Apache-2.0. Obligations: the text of CDLA-Permissive-2.0 travels with the data
  (`LICENSES/CDLA-Permissive-2.0.txt`); the Foursquare records need Apache-2.0 §4: the licence copy
  (`LICENSES/Apache-2.0.txt`), a notice that the files are changed and the NOTICE of the dataset — all in
  [`NOTICE_overture.txt`](NOTICE_overture.txt), whose text is the page https://opensource.foursquare.com/places-notice-txt/
  (the page behind the «NOTICE.txt» link of the Overture page; read 2026-10-17). Licence of the files as a database and
  the list of contents licences: [`NOTICE.md`](NOTICE.md). (The other Overture themes `buildings` / `transportation` /
  `divisions` / `base` carry ODbL; we do not ingest them.)
- **The businesses' own websites** (`collect/sites`, `sources` contains `official_site`) — opening hours, phone, address
  and the place's own description of itself, read from the pages of the business (robots.txt respected, at most one
  request a second per domain; snapshot 2026-10-17). Only facts, licence note «facts from the business's own website»;
  each field keeps the page `url` and a verbatim `snippet` in `field_sources{}`. Third-party aggregators (2GIS, Yandex,
  Zoon, social networks) are not used.
- **`data/districts.geojson`** — Astana districts, OSM relations with admin_level=6, ODbL 1.0
  (© OpenStreetMap contributors), snapshot in each feature.
- **`data/population_proxy.json`** — relative residential weight per 500 m cell derived from OSM buildings
  (`building=apartments|residential|dormitory|house…`), ODbL 1.0 (© OpenStreetMap contributors), made by
  `app/scripts/fetch_population_proxy.py` (snapshot date in `meta.snapshot_date`); a proxy for demand simulation,
  not a population count.
- **`data/walk_cache.json`** — walking distances and times between points of the app (preset, POI, POI), computed by
  the public FOSSGIS Valhalla server over OpenStreetMap data (routes of 2026-10-16/17, date `d` in each entry),
  ODbL 1.0 (© OpenStreetMap contributors); terms of use of the service
  https://www.fossgis.de/arbeitsgruppen/osm-server/nutzungsbedingungen/ .
  Stored so that the demo preset needs no network.

Runtime-источники (в файлы данных не попадают):

- **MET Norway** — the weather forecast (`app/walks/metno.py`, `api.met.no/weatherapi/locationforecast/2.0`), CC BY 4.0
  and NLOD 2.0, credit «Data from MET Norway», terms https://api.met.no/doc/TermsOfService (identifying User-Agent,
  respect `Expires`); commercial use allowed.
- **Open-Meteo** — air quality (PM2.5) only, and only when `WALKS_AIR_DEMO=1` (the demo stand); CC BY 4.0, «Weather data
  by Open-Meteo.com» **with a link to https://open-meteo.com next to the data** (https://open-meteo.com/en/licence). The
  free API is for non-commercial use only (https://open-meteo.com/en/terms), so it is off by default.
- **Valhalla** — pedestrian routes of legs that are not in `data/walk_cache.json`; geometry and times are derived from
  OpenStreetMap data, © OpenStreetMap contributors (ODbL 1.0). The demo stand runs its own Valhalla on an Astana
  extract (`deploy/vps/valhalla/`, `WALKS_VALHALLA_URL`); without that variable the app asks the public FOSSGIS server,
  terms https://www.fossgis.de/arbeitsgruppen/osm-server/nutzungsbedingungen/ (≤ 1 request/s, identifying User-Agent,
  a link to https://www.openstreetmap.org/fixthemap, **commercial use only when the service is not a substantial part
  of the offer**): fine for a local demo, not for production.
- **Kazhydromet (РГП «Казгидромет»)** — the METAR of the Astana airport (UACC; issued through the WMO exchange, retrieved
  from NOAA/NWS aviationweather.gov and IEM, public domain) and the storm warnings (ОЯ) and unfavourable-weather (НМУ)
  notices of kazhydromet.kz, shown verbatim with the link to the notice page (Order of the Ministry of Ecology No. 267),
  robots.txt respected. Walking line geometry of the cached legs (`g` in `data/walk_cache.json`, added by
  `app/scripts/backfill_shapes.py`) comes from our own Valhalla on OpenStreetMap data, ODbL.
- **Public holidays of Kazakhstan** — Закон РК «О праздниках в Республике Казахстан» (links in `app/walks/holidays.py`).
- **Basemap** — the map tiles and style come from the public OpenFreeMap instance (https://openfreemap.org, MIT; schema
  OpenMapTiles; data OpenStreetMap). The attribution is shown in the legend row on the map (always on screen: bottom
  left on a desktop, the second line of the top bar on a phone; the MapLibre attribution control is off):
  «OpenFreeMap · © OpenMapTiles · © OpenStreetMap contributors · ODbL» (links to openfreemap.org, openmaptiles.org,
  https://www.openstreetmap.org/copyright and the ODbL text); offline the row shows «© OpenStreetMap contributors · ODbL».
- **LLM providers** — the text of a query and the facts of the candidates go to the model chain (Google Gemini API
  through `google-genai`, or an OpenAI-compatible endpoint). Terms: unpaid Gemini API quota lets Google use prompts and
  responses to improve its products; only paid quota does not (https://ai.google.dev/gemini-api/terms). The model's
  structured answers are cached locally (`app/.local/llm_cache.json`, not tracked) and recorded for the demo in
  `data/demo_llm_cache.json`.

<!-- state_registry:begin -->
- **State registries** (`collect/gov`, `sources` contains `state_registry`) — branch addresses and schedules of the ЦОН (gov4c.kz, НАО «Правительство для граждан») and register №730 «Перечень государственных спортивных объектов» of the Astana sports department (data.egov.kz); open data of a state body of the Republic of Kazakhstan, Law №401-V on access to information (art. 1 p. 5: free use, processing, re-publication). Coordinates of these records are never the registry's: they are those of the OpenStreetMap element matched by name and address (ODbL 1.0, © OpenStreetMap contributors). `data/gazetteer/`: street spellings of Astana from OpenAddresses KZ, attribution «Комитет по правовой статистике и специальным учетам Генеральной прокуратуры РК» (see `data/gazetteer/ATTRIBUTION.md`); `rca_streets.json` — the street layer of the same Committee's address register (ИС «Адресный регистр») via keyless data.egov.kz /api/detailed, the same attribution, Law №401-V; no coordinates.
<!-- state_registry:end -->
