# Coverage delta: OSM-only (`poi.json`) vs enriched (`poi.enriched.json`)

Overture release `2026-09-23.1`, bbox 50.98–51.25 / 71.25–71.60; Wikidata snapshot 2026-10-16.

## Relevance expansion (2026-10-17): before = enriched v1 of 2026-10-16, after = this build

v1 = `data/poi_enriched_v1_stats.json` (frozen; OSM + Overture + Wikipedia, 2178 records). Ids of existing records are
kept except **31**: 28 Overture-only records were dropped for suspect
coordinates (below) and 3 Overture-only records are now the OSM record of the same place
(Astana Music Hall, Eagilik - Books and Coffee, Kidburg). New records: **36**
(osm 14, overture 9, wikidata 13).

| metric | v1 | now | delta |
|---|---|---|---|
| records, total | 2178 | 2183 | 5 |
| museum_gallery | 25 | 25 | 0 |
| entertainment | 32 | 45 | 13 |
| kids, indoor (entertainment / museum / theatre with a kids signal) | 1 | 13 | 12 |
| kids, outdoor playgrounds (`kids_playground`) | 336 | 328 | -8 |
| viewpoint | 1 | 1 | 0 |
| indoor places (app INDOOR_CATEGORIES) | 652 | 672 | 20 |
| records with opening_hours | 345 | 346 | 1 |
| % with opening_hours | 15.8 | 15.8 | 0.0 |
| % museum_gallery with opening_hours | 4.0 | 4.0 | 0.0 |
| records with a real description (osm / wikipedia) | 23 | 52 | 29 |
| % real description | 1.1 | 2.4 | 1.3 |

Per category:

| category | v1 | now | delta |
|---|---|---|---|
| cafe | 469 | 464 | -5 |
| restaurant | 406 | 391 | -15 |
| fast_food | 158 | 158 | 0 |
| bar_nightlife | 247 | 243 | -4 |
| museum_gallery | 25 | 25 | 0 |
| attraction_landmark | 116 | 127 | 11 |
| viewpoint | 1 | 1 | 0 |
| park_garden | 199 | 198 | -1 |
| kids_playground | 336 | 328 | -8 |
| entertainment | 32 | 45 | 13 |
| mall | 73 | 75 | 2 |
| culture_theatre_cinema | 35 | 45 | 10 |
| coworking_library | 18 | 18 | 0 |
| sport | 34 | 36 | 2 |
| transit_station | 29 | 29 | 0 |

What the new records come from:

- OSM, second Overpass request (tags the first selector set missed; `collect/overpass_poi.py` `EXTRA_SELECTORS`):
  `leisure=indoor_play`, `playground=indoor`, `amenity=planetarium|events_venue|fountain(named)|community_centre(palaces)`,
  `club=sport`, `shop=books` with a cafe in the name, `man_made=tower`+`tower:type=observation`. Live count inside the
  Astana area: `tourism=viewpoint` 1 (unnamed, already in v1), observation towers 0, planetariums 0, trampoline parks 0,
  `leisure=indoor_play` 1.
- Overture, remapped taxonomy + name rules for generic buckets: **9** Overture-only records
  that v1 left as `other` (name rules: kids_leisure_name 3, mall_name 2, leisure_name 1).
  The confidence cut-off 0.7 is unchanged.
- Wikidata / Wikipedia (`collect/wiki_places.py`): 245 candidates (Wikidata P131* + ru/en Wikipedia
  geosearch + categories), 65 of a mapped class, 55 located inside the Astana districts
  (Nominatim lookups 10, accepted 2); 18 already
  in the dataset, 19 existing records got a Wikidata item + Wikipedia extract,
  5 were duplicates of an existing record (not enriched), **13 new**
  (park_garden 1, attraction_landmark 6, culture_theatre_cinema 3, museum_gallery 2, sport 1).

### Opening hours: what was checked (2026-10-17)

- Overture release `2026-09-23.1`: the places schema has no hours field (`DESCRIBE` of the parquet: id, geometry,
  confidence, websites, emails, socials, phones, brand, addresses, names, sources, operating_status, basic_category,
  taxonomy, version, bbox); `operating_status` is set on 1 of 8590 Astana records. 0 hours gained.
- Wikidata: 0 items located in Astana (P131*) have P3025 (open days) or P8626 (opening time) — SPARQL counts. 0 hours gained.
- Foursquare OS Places: the open schema has no hours column (Foursquare documentation; hours are a premium attribute) and the
  dataset is gated — not used.
- visitastana.kz: its place pages carry injected spam JSON-LD (casino/slot advertising inside `application/ld+json`) and the
  site has no terms page that allows storing its data — not used, nothing stored.
- OSM `opening_hours` stays the only source: v1 15.8% -> now 15.8%.
  The data-quality map (`city_ui`) and the «часы неизвестны» label in the app are the honest answer to this gap.

### Viewpoints

OSM has exactly one `tourism=viewpoint` in Astana (unnamed) and no observation tower; Overture has no `scenic_viewpoint` /
`observation_deck` / `lookout` record in the bbox; Wikidata knows one observation tower (Baiterek, already a landmark
record). The category stays at 1: a viewpoint is not invented from a tower or a high building.

### Overture coordinate quality (Overture-only records; OSM records are never touched)

- 689 Overture records (14 points) share one point (5 decimals) with
  >= 7 other records and their addresses disagree (no street, or no address above
  40%): placeholder / centroid coordinates. 15 records passing the
  cut-off have a street >2 km from every other record of that street and were geocoded with Nominatim: address_far 13, unverified 2.
- Overture-only records dropped for it: **28** (collapsed_point 15, address_far 13); kept but flagged
  `coord_quality.status = suspect_unverified`: 1.

| name | category | confidence | address | reason | records on point / geocoder m / street m |
|---|---|---|---|---|---|
| Bar & Grill | bar_nightlife | 0.973 | Астана, Қабанбай батыр даңғылы 19/1 | collapsed_point | 16 |
| Family Bakery | restaurant | 0.9571 | Астана, Ұлы Дала проспект 27/3 | address_far | 6904 |
| Мята Сауран | restaurant | 0.9192 | Астана, Сауран көшесі 10б | collapsed_point | 158 |
| Stove bakery | cafe | 0.9106 | Целиноград ауданы, Ахмет Байтұрсынов көшесі 1 | collapsed_point | 158 |
| Starbucks Казахстан | cafe | 0.8821 | Астана, Кургальджинское шоссе, д. 1 | collapsed_point | 40 |
| Bozoq Museum | museum_gallery | 0.875 | Астана, Бозок, проспект Абая 98Б | address_far | 6523 |
| Lugano итальянский ресторан | restaurant | 0.8719 | Целиноград ауданы, Абай көшесі 1 | address_far | 16882 |
| Семейный ресторан «Вокруг Света» | restaurant | 0.8706 | Астана, улица Сыганак 16 | collapsed_point | 118 |
| Лагман Шах | cafe | 0.87 | Целиноград ауданы, 2-ші шағын аудан 26 | collapsed_point | 158 |
| Ресторан Kubbe | restaurant | 0.8594 | Астана, Kunaeva, 7 | collapsed_point | 158 |
| Starbucks | cafe | 0.85 | Astana, TC Khan Shatyr, Туран 37 | address_far | 6469 |
| Green Park Astana | park_garden | 0.8092 | Астана, Косшы | collapsed_point | 40 |

### 10 new records

| id | name | category | lat, lon | sources | basis |
|---|---|---|---|---|---|
| wikidata/Q4146879 | Государственный музей золота и драгоценных металлов | museum_gallery | 51.15700, 71.43130 | wikidata; coords: wikidata | wikidata_class=Q33506 |
| node/12508539014 | Kidburg | entertainment | 51.12217, 71.42911 | osm+overture; coords: osm | leisure=indoor_play |
| node/5101392526 | Дворец торжеств «Салтанат сарайы» | culture_theatre_cinema | 51.15023, 71.42351 | osm; coords: osm | amenity=community_centre |
| node/2712544656 | Фонтан "Дерево жизни" | attraction_landmark | 51.16623, 71.41532 | osm; coords: osm | amenity=fountain |
| wikidata/Q104866684 | Президентский парк (Нур-Султан) | park_garden | 51.11667, 71.45000 | wikidata; coords: wikidata | wikidata_class=Q22698 |
| way/1108448985 | Лыжная база | sport | 51.15436, 71.41316 | osm; coords: osm | - |
| node/4387005493 | Eagilik - Books & Coffee | cafe | 51.16761, 71.43828 | osm+overture; coords: osm | - |
| overture/a6206477-2569-492f-b1a8-73bf3df4421e | Торгово-развлекательный центр Keruenсity/Nur-Sultan | mall | 51.14535, 71.41397 | overture; coords: overture | overture_category=arts_and_entertainment |
| wikidata/Q85787940 | National Military-Patriotic Center of the Armed Forces of Kazakhstan | museum_gallery | 51.15592, 71.43153 | wikidata; coords: wikidata | wikidata_class=Q16735822 |
| overture/329aec0c-b4a5-4566-ad32-44e224f782f8 | Спорткомплекс Алатау | entertainment | 51.15170, 71.45120 | overture; coords: overture | overture_category=pool_billiards |



## Totals

| metric | value |
|---|---|
| OSM POI in the re-collected snapshot (`poi.osm.json`) | 1501 |
| Overture places in bbox (all) | 8590 |
| Overture passing confidence >= 0.7 | 2802 |
|   ...of them dropped as closed / nameless | 0 |
| Overture dropped by confidence < 0.7 | 5788 |
| OSM ∩ Overture matched (1:1) | 186 |
| Overture-only, mapped category (added to `poi.enriched.json`) | 669 |
| Overture-only, category `other` (not added; stays in `overture_places.json`) | 1914 |
| Wikidata matched POI | 76 |

## Per category (before = frozen `poi.json`, after = `poi.enriched.json`)

| category | before | after | delta |
|---|---|---|---|
| cafe | 328 | 464 | 136 |
| restaurant | 176 | 391 | 215 |
| fast_food | 123 | 158 | 35 |
| bar_nightlife | 109 | 243 | 134 |
| museum_gallery | 10 | 25 | 15 |
| attraction_landmark | 88 | 127 | 39 |
| viewpoint | 1 | 1 | 0 |
| park_garden | 177 | 198 | 21 |
| kids_playground | 336 | 328 | -8 |
| entertainment | 5 | 45 | 40 |
| mall | 51 | 75 | 24 |
| culture_theatre_cinema | 25 | 45 | 20 |
| coworking_library | 11 | 18 | 7 |
| sport | 23 | 36 | 13 |
| transit_station | 25 | 29 | 4 |
| other | 0 | 0 | 0 |
| **total** | 1488 | 2183 | 695 |

## Attribute coverage

| metric | before | after |
|---|---|---|
| % with opening_hours (all records) | 23.2 | 15.8 |
| % with opening_hours (OSM-origin records only) | 23.2 | 23.1 |
| % real description (osm + wikipedia) | 0.1 | 2.4 |
|   of which osm | 0.1 | 0.1 |
|   of which wikipedia | 0.0 | 2.3 |
| % derived description | 99.9 | 97.6 |
| % with website | 13.1 | 25.1 |
| % with phone | 12.8 | 37.9 |

Opening hours: none of the added sources carries `opening_hours` (Overture adds *objects*, not hours; Wikidata has no Astana
item with P3025 / P8626; Foursquare OS Places has no hours column), so the share over all records moves only with the
OSM-origin extras: 23.2% in `poi.json`, 15.8% over all
records now, 23.1% among OSM-origin records. Every Overture-only and Wikidata-only record
enters with `hours_state: "unknown"`.

## Overture confidence cut-off

Cut-off **0.7**. The bbox holds 8590 Overture places, 94% from the Meta dataset, with a wide confidence spread (0.2-0.9, see `overture_places.json` -> meta). Evidence for 0.7 in our categories: below 0.7 every record is single-source Meta, websites are present in at most 37% and only 0-8% of records have an OSM counterpart (same name within 150 m) with no trend; from 0.7 records from other datasets (Microsoft, Foursquare, AllThePlaces) appear, the website share rises to 50-74% and the OSM match rate climbs steeply (see table). The table below is the independent check. Below the cut-off a record is dropped entirely (not merged into an OSM POI, not added as Overture-only); records must also have a name and not be marked closed. A false positive (a closed cafe on a walking route) costs more than a missed place, hence the strict side.

Overture records in our categories, share with an OSM counterpart by confidence bucket:

| confidence | records | matched to OSM | match rate % |
|---|---|---|---|
| 0.1-0.2 | 10 | 0 | 0.0 |
| 0.2-0.3 | 78 | 2 | 2.6 |
| 0.3-0.4 | 104 | 7 | 6.7 |
| 0.4-0.5 | 160 | 12 | 7.5 |
| 0.5-0.6 | 319 | 13 | 4.1 |
| 0.6-0.7 | 309 | 27 | 8.7 |
| 0.7-0.8 | 334 | 37 | 11.1 |
| 0.8-0.9 | 265 | 41 | 15.5 |
| 0.9-1.0 | 270 | 95 | 35.2 |

## Wikidata/Wikipedia matches by method

| method | POI |
|---|---|
| tag | 29 |
| sparql | 10 |
| fuzzy | 5 |
| wikipedia_list | 19 |
| source | 13 |

## Overture <-> OSM chain duplicates

An Overture-only record is the same venue as an OSM record when the normalised name key (casefold, Cyrillic incl.
kk -> Latin, punctuation dropped; same rules as `name_key` in `app/walks/retrieve.py`) is equal, or brand /
brand:wikidata are equal, within 150 m; for identical names the radius is 250 m. Category
mismatches (cafe / fast_food / restaurant ...) do not block the match; type-only names ("Кафе") never match.

- merged into the OSM record (phone / website / brand taken over): **3**
- dropped because that OSM record already has its Overture counterpart: **1**
- by signal: name 4

Examples (the 4 farthest):

| OSM | OSM category / id | Overture | Overture category / id | m | by | result |
|---|---|---|---|---|---|---|
| Starbucks | cafe `node/10976892637` | Starbucks | cafe `cb7d45f2` | 238 | name | merged into OSM record |
| Starbucks | cafe `node/9047331875` | Starbucks | cafe `d10ba25c` | 191 | name | merged into OSM record |
| Korean House | restaurant `node/14107301089` | Korean House | restaurant `5a3a52f0` | 179 | name | merged into OSM record |
| Национальная академическая библиотека Республики Казахстан | coworking_library `way/230358855` | Национальная Академическая библиотека Республики Казахстан | coworking_library `01356b49` | 11 | name | dropped (OSM already has a counterpart) |

## Overture records demoted to `other` (not a walkable POI)

Residential complexes, offices / business centres, real estate and construction, schools, clinics, government
offices, banks / ATMs and car services by name or taxonomy; Overture `historic_site` records whose name says
nothing about heritage (in Astana that label is mostly put on residential complexes and addresses). Demoted records
stay in `overture_places.json` and are never added to `poi.enriched.json`.

| reason | records passing the cut-off | all usable records |
|---|---|---|
| residential_complex | 36 | 95 |
| historic_site_unverified | 14 | 64 |
| school_education | 1 | 4 |

Demoted from category (passing the cut-off): attraction_landmark 50, coworking_library 1.

Examples (15, round-robin over reasons, most confident first):

| name | Overture taxonomy | was | reason | confidence |
|---|---|---|---|---|
| HighVill Astana | historic_site | attraction_landmark | historic_site_unverified | 0.9411 |
| ЖК Коркем | historic_site | attraction_landmark | residential_complex | 0.9264 |
| L.N. Gumilyov Eurasian National University | library | coworking_library | school_education | 0.8 |
| Nova City | historic_site | attraction_landmark | historic_site_unverified | 0.8564 |
| ЖК Северное Сияние | historic_site | attraction_landmark | residential_complex | 0.9244 |
| Астана Су Арнасы | historic_site | attraction_landmark | historic_site_unverified | 0.8496 |
| ЖК Времена года - Осень | historic_site | attraction_landmark | residential_complex | 0.8864 |
| Самал, д. 6 | historic_site | attraction_landmark | historic_site_unverified | 0.8094 |
| ЖК Capital Park | historic_site | attraction_landmark | residential_complex | 0.8669 |
| Urban | historic_site | attraction_landmark | historic_site_unverified | 0.8051 |
| "ЖК "Барыс"" | historic_site | attraction_landmark | residential_complex | 0.8631 |
| Astana, Kz | historic_site | attraction_landmark | historic_site_unverified | 0.781 |
| ZhK Megapolis | historic_site | attraction_landmark | residential_complex | 0.8438 |
| ул. Габита Мусрепова | historic_site | attraction_landmark | historic_site_unverified | 0.7758 |
| "ЖК "Премьера!"" | historic_site | attraction_landmark | residential_complex | 0.8418 |

## Official-site facts (first-party hours, phone, address; new POIs)

Generated 2026-10-17 by `collect.sites.apply` into the shipped `data/poi.enriched.json` (stats: `data/poi_enriched_stats.json`, key `official_sites`). Facts come from the businesses' own pages (robots respected, verbatim evidence snippets); only schedules that name days count as hours.

| metric | before | after |
|---|---|---|
| POIs | 2183 | 2316 |
| POIs with day-qualified `opening_hours` | 346 (15.85%) | 514 (22.19%) |
| `hours_unqualified` (text without days / ambiguous 24h, not in `opening_hours`) | 0 | 20 |
| `hours_conflict` (OSM kept, site value in `opening_hours_official`) | 0 | 31 |
| `price_text` (the site's/register's own price wording, never parsed) | 0 | 3 |

Matched to existing POIs: **133** ({'coords+name': 54, 'domain+address': 16, 'domain+name': 53, 'domain_unique': 4, 'register_name_address': 1, 'coords+domain': 5}); hours added to existing POIs: **41**, to new POIs: **127**; identical-to-OSM confirmations: 7; other join conflicts (kept POI value): {'opening_hours': 31, 'phone': 68, 'address': 67, 'description': 1}.

### New POIs from official branches with first-party coordinates: 133

| category | new POIs |
|---|---|
| cafe | 116 |
| fast_food | 10 |
| restaurant | 7 |

Skipped candidates: no first-party coordinates: 133; duplicate of an existing POI (<= 75 m, similar name): 24; no usable name: 8; duplicate of an earlier new POI (<= 75 m, similar name): 4

### By domain (top 20 by POIs touched)

| domain | branches | matched POIs | hours added | new POIs | new POIs with hours | hours conflicts | hours_unqualified |
|---|---|---|---|---|---|---|---|
| happycake.kz | 75 | 1 | 1 | 74 | 74 | 0 | 0 |
| coffeeboom.kz | 59 | 0 | 0 | 31 | 30 | 0 | 1 |
| kfc.kz | 20 | 16 | 4 | 1 | 1 | 10 | 0 |
| hardees.kz | 12 | 7 | 5 | 5 | 5 | 2 | 0 |
| starbucks.com.kz | 13 | 7 | 1 | 4 | 4 | 4 | 0 |
| shashlychok.kz | 10 | 6 | 1 | 4 | 4 | 5 | 0 |
| abr.kz | 9 | 5 | 0 | 4 | 4 | 4 | 0 |
| white.kz | 10 | 5 | 0 | 0 | 0 | 1 | 1 |
| edagoroda.kz | 7 | 2 | 0 | 3 | 0 | 0 | 5 |
| crepecafe.kz | 5 | 3 | 0 | 2 | 0 | 0 | 0 |
| goodproject.kz | 5 | 5 | 0 | 0 | 0 | 2 | 0 |
| rafe.kz | 4 | 2 | 1 | 2 | 2 | 0 | 0 |
| e-museum.kz | 4 | 3 | 1 | 0 | 0 | 0 | 2 |
| papajohns.kz | 4 | 3 | 3 | 0 | 0 | 0 | 0 |
| qaganat24.kz | 3 | 3 | 2 | 0 | 0 | 0 | 0 |
| satgroup.kz | 6 | 2 | 2 | 0 | 0 | 0 | 0 |
| plov.kz | 2 | 0 | 0 | 2 | 2 | 0 | 0 |
| sushiman.kz | 2 | 1 | 1 | 1 | 1 | 0 | 0 |
| im.kz | 7 | 1 | 0 | 0 | 0 | 0 | 1 |
| ritzcarlton.com | 7 | 1 | 1 | 0 | 0 | 0 | 0 |

## State registries (ЦОН branches, sport register №730)

Generated 2026-10-17 by `collect.gov.apply` (facts: `data/gov/facts`, joins: `data/gov/joined.json`). Source: gov4c.kz (ЦОН branches) and data.egov.kz register №730; licence: открытые данные госоргана РК, Закон №401-V (ст. 1 п. 5: свободное использование, обработка, повторная публикация).

- ЦОН branches found: **25**; sport register records: **7**.
- Geocoded (matched to an OSM element or a POI by name+address): **19** ({'poi_name_address': 2, 'osm_address': 8, 'poi_name': 1, 'osm_name_address': 5, 'osm_name': 3}); unmapped (kept, not on the map): **13**.
- Attached to existing POIs: **3** (filled: {'admin_hours': 3, 'address_kk': 1, 'address': 1}); new POIs: **10** ({'other': 10}).
- POIs with `admin_hours` (office week of the administration, never `opening_hours`): **3**.
- POIs with `address_kk` (kk street spelling from the RCA register, `data/gazetteer/rca_streets.json`): **6**.
- POIs: 2316 -> 2326; day-qualified `opening_hours`: 514 -> 524.
- Catalogue of Астана қаласы әкімдігі on data.egov.kz: 52 published datasets, 0 with coordinates, 1 with a working-hours field (`collect/gov/catalog.json`).

## Same-venue duplicates (one card per venue)

Generated by `collect.dedupe` (rules: `collect/dedupe.py`, names: `collect/venue_names.py`; log with every cluster: `data/duplicates_merged.json`). The absorbed ids stay on the surviving record as `aliases`.

- POIs: 2326 -> 2294 (32 records merged into 26 venues' cards: 23 clusters, 3 kind-only pins).
- Links by rule: {'colocated': 3, 'kind_pin': 3, 'name': 29, 'worship': 1}.
- Same rules in categories left alone (not merged): {'coworking_library': 3, 'entertainment': 2, 'sport': 1, 'transit_station': 1}.

| category | records merged away |
|---|---|
| attraction_landmark | 12 |
| culture_theatre_cinema | 1 |
| mall | 5 |
| museum_gallery | 7 |
| park_garden | 7 |

- attraction_landmark: **Алие Молдагуловой** ← Памятник Алия Молдагуловой (name)
- attraction_landmark: **Жамбыл** ← Памятник Жамбылу Жабаеву (name)
- attraction_landmark: **Мустафе Кемалю Ататюрку** ← Atatürk Heykeli Astana; Ататүрік ескерткіші (name)
- attraction_landmark: **Бейт Рахель Хабад Любавич** ← Beit Rachel Synagogue (name)
- attraction_landmark: **Бейт Рахель Хабад Любавич** ← синагога (kind_pin)
- attraction_landmark: **А. С. Пушкину** ← Памятник Пушкину (name)
- attraction_landmark: **Римско-Католический Приход Матери Божией Неустанной Помощи** ← Our Lady of Perpetual Help Cathedral; Католический кафедральный собор Девы Марии (colocated, name, worship)
- attraction_landmark: **Храм во имя святого преподобного Серафима Саровского** ← Храм Серафима Саровского (name)
- attraction_landmark: **Свято-Успенский кафедральный собор** ← Успенский православный кафедральный собор (colocated)
- attraction_landmark: **Мечеть Абу Насыра аль-Фараби** ← Mosque Abu Nasr Al-Farabi (name)
- culture_theatre_cinema: **IMAX Кинопарк7** ← Kinopark 7 (name)
- mall: **KeruenCity** ← Торгово-развлекательный центр Keruenсity/Nur-Sultan (name)
- mall: **Азия Парк** ← Asia Park Mall (name)
- mall: **Рахмет ТЦ** ← Рахмет (name)
- mall: **ТД Гульжан** ← ТЦ Гульжан (name)
- mall: **Mega Silk Way** ← Мега Силк Вей (name)
- museum_gallery: **Национальный музей Республики Казахстан** ← Historical Museum Astana (kind_pin)
- museum_gallery: **Военно-исторический музей** ← Военно-Исторический музей ВС РК; ҚР ҚК Әскери-тарихи музейі; Государственный военно-исторический музей; National Military-Patriotic Center of the Armed Forces of Kazakhstan (colocated, name)
- museum_gallery: **Historical Museum Astana** ← Kazakistan Tarihi Müzesi @astana (name)
- museum_gallery: **Этно-мемориальный комплекс Карта Казахстана Атамекен** ← «Карта Казахстана «Атамекен» (name)
- park_garden: **Парк Астана** ← «Астана» саябағы / Парк «Астана» / Astana Park (kind_pin)
- park_garden: **Парк Жеруйык** ← Жерұйық саябағы / Парк Жеруйык (name)
- park_garden: **Парк имени Бауыржана Момышулы** ← Парк им. Б. Момышулы (name)
- park_garden: **Парк Ататюрка** ← Парк Ата Тюрк Астана; парк «Ататюрк» (name)
- park_garden: **Сквер шахматистов** ← Шахматшылар гүл бағы / Сквер шахматистов (name)
- park_garden: **Парк Жетысу** ← Jetisy Park (name)
- park_garden: **Парк Астана** ← «Астана» саябағы / Парк «Астана» / Astana Park (kind_pin, 61 m)
- attraction_landmark: **Бейт Рахель Хабад Любавич** ← синагога (kind_pin, 111 m)
- museum_gallery: **Национальный музей Республики Казахстан** ← Historical Museum Astana (kind_pin, 194 m)

## Wikivoyage (hours, prices, descriptions of sights)

Generated 2026-10-17 by `collect.wikivoyage.apply` (snapshots: `collect/wikivoyage/snapshots/`, join log: `data/wikivoyage_joined.json`). Source: the Astana articles of the en/it/he/pl/ru Wikivoyage (CC BY-SA 4.0).

- Listings parsed: **187** (en 52, it 51, he 39, pl 14, ru 31); joined by wdid **30**, by name **32**, by coords+name **2**; unmatched **59**.
- Fields filled: hours **12** (+ hours-voyage 3 when the record already had OSM/site hours; unqualified 0), prices **5**, descriptions **6**; POIs 2294 -> 2294 (no new records: a listing that matches nothing is logged, not added).

Radius pairs (rule `coords+name`/`name`) are listed in `data/wikivoyage_joined.json` for a human check; the false-pair rule is in `collect/wikivoyage/join.py`.
