# NOTICE — licence of the files in `data/`

Written 2026-10-17. The full table of sources, quotations of their terms and what a paid product still has to do is in
[`docs/licensing.md`](../docs/licensing.md); the per-source attribution lines are in [`ATTRIBUTION.md`](ATTRIBUTION.md).
This file is the notice that ODbL 1.0 section 4.2 d asks for «in a location (such as a relevant directory) where users
would be likely to look for it», because the JSON files cannot carry it inside.

## 1. The database is under the Open Database License (ODbL) 1.0

`poi.osm.json`, `poi.json`, `poi.enriched.json`, `districts.geojson`, `population_proxy.json`, `walk_cache.json`,
`city/*.json`, `mobility/stops.json`, `gov/osm_candidates.json`, `gazetteer/astana_addresses.json` and `overture_geocheck.json` contain a substantial
part of the OpenStreetMap database (the Overpass extract of the places of Astana is not «insubstantial»: the OSMF
guideline calls fewer than 100 features insubstantial and a systematic extraction of all places of a kind in an
area substantial; `poi.osm.json` has 1 501 places). Together with the records we added
to it they are a **Derivative Database** in the sense of ODbL section 1.0 («a database based upon the Database, and
includes any translation, adaptation, arrangement, modification, or any other alteration of the Database or of a
Substantial part of the Contents. This includes … Extracting or Re-utilising the whole or a Substantial part of the
Contents in a new Database»). Therefore:

- The licence of these files **as a database** is ODbL 1.0, including everything we added to them (merge, matching,
  derived fields, the structure of `field_sources`). Text: [`../LICENSES/ODbL-1.0.txt`](../LICENSES/ODbL-1.0.txt);
  URI: https://opendatacommons.org/licenses/odbl/1-0/ (section 4.2 b).
- Attribution (ODbL 4.2 c, OSMF Attribution Guideline, «Databases»): **© OpenStreetMap contributors**,
  https://www.openstreetmap.org/copyright — «Contains information from OpenStreetMap, which is made available here
  under the Open Database License (ODbL).» (the sentence of ODbL 4.3 a).
- Machine-readable copy (ODbL 4.6): the files themselves are the machine-readable Derivative Database, and the method
  of making the alterations is the code in `collect/` (ODbL 4.6 b allows «the method of making the alterations …
  (such as an algorithm)»). Whoever receives a copy of a Produced Work from these files must be offered them free of
  charge over the internet.
- Section 4.7: no technical measure or additional term may restrict what ODbL grants. Do not put `data/` behind a
  paywall or a licence that forbids re-use; a password-protected copy is allowed only next to an open one (4.7 b).

## 2. The contents keep their own licences (ODbL 2.4)

ODbL covers the database, not each item in it. The licence of a field is in its `field_sources.<field>.license`:

| `license` value | what | text / URI |
|---|---|---|
| `ODbL-1.0`, `ODbL 1.0, © OpenStreetMap contributors` | OpenStreetMap elements and what is derived from their geometry | `LICENSES/ODbL-1.0.txt` |
| `CDLA-Permissive-2.0` | Overture records contributed by Meta, Microsoft, PinMeTo | `LICENSES/CDLA-Permissive-2.0.txt` (CDLA 2.1: the text of the agreement must be made available with the shared data) |
| `Apache-2.0` | Overture records contributed by Foursquare (`contributor: "Foursquare"`) | `LICENSES/Apache-2.0.txt` and [`NOTICE_overture.txt`](NOTICE_overture.txt) (Apache-2.0 4 a, b, d) |
| `CC0-1.0` | Overture records contributed by AllThePlaces; Wikidata; Wikimedia pageviews | https://creativecommons.org/publicdomain/zero/1.0/ |
| `CC-BY-SA-4.0` | Wikipedia extracts (`wikipedia[lang].extract`, `description`), shortened by us; each carries its article `url` | https://creativecommons.org/licenses/by-sa/4.0/ |
| `CC-BY-4.0` | `mobility/stops.json` entries with `source: zenodo_gtfs` (Zenodo 10.5281/zenodo.15769359) | https://creativecommons.org/licenses/by/4.0/ |
| `facts from the business's own website` | opening hours, phone, address, self-description read from the pages of the business (facts, not works: Law of the Republic of Kazakhstan on copyright and related rights, art. 8 item 4); each field has `url` and a verbatim `snippet` | — |
| open data of a state body (Law No. 401-V art. 1 item 5) | `gov/`, `gazetteer/` | — |

Overture's `places` theme has no theme-level licence; the licence is per record in `overture_places.json` →
`places[].sources[].license`. Measured on 2026-10-17 over the 8 590 shipped records: meta 8 118 and Microsoft 86 and
PinMeTo 1 (CDLA-Permissive-2.0), AllThePlaces 234 (CC0-1.0), Foursquare 151 (Apache-2.0).

## 3. What a user of these files must do

1. Keep this notice, `ATTRIBUTION.md`, `NOTICE_overture.txt` and `LICENSES/` with the files (or the URIs above).
2. Show «© OpenStreetMap contributors» and the ODbL link wherever a Produced Work made from the files is shown to
   the public (a card, a map, a generated text): ODbL 4.3.
3. Publish the Derivative Database you build from these files under ODbL (4.4), unless you only use it inside your own
   organisation (4.5 c) or only as a separate Collective Database (4.5 a) next to your own, independent data.
4. For Foursquare records, keep «Copyright 2024 Foursquare Labs, Inc.» and `NOTICE_overture.txt`; say that the files
   are changed (Apache-2.0 4 b).
5. For Wikipedia extracts, give the link to the article and say that they are CC BY-SA 4.0 and shortened.

This is not legal advice; it is what the licence texts say, read by engineers. A lawyer must confirm it before a paid
launch.
